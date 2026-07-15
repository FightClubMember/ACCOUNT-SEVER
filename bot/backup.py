import os
import json
import csv
import shutil
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from sqlalchemy import select, insert
from bot import config
from bot.database import async_session_maker, Base, engine as primary_engine
from bot.models import Account, Settings
from bot.encryption import decrypt_password, encrypt_password
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)

# Backup folder path
BACKUP_DIR = config.BOT_DIR / "data" / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

async def export_sqlite() -> str:
    """
    Creates a backup copy of the SQLite database.
    If the bot is running on PostgreSQL, it dumps the schema and records 
    into a temporary SQLite database on the fly and returns it.
    """
    # 1. Local SQLite shortcut
    if config.DATABASE_URL.startswith("sqlite+aiosqlite:///"):
        db_path = config.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
        temp_dir = tempfile.gettempdir()
        dest_path = os.path.join(temp_dir, f"accounts_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db")
        # Run copy operation
        shutil.copy2(db_path, dest_path)
        logger.info(f"Local SQLite database copied to: {dest_path}")
        return dest_path

    # 2. PostgreSQL to SQLite conversion on-the-fly
    temp_dir = tempfile.gettempdir()
    dest_path = os.path.join(temp_dir, f"accounts_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db")
    
    # Create temporary SQLite engine and tables
    temp_sqlite_url = f"sqlite+aiosqlite:///{dest_path.replace(os.sep, '/')}"
    temp_engine = create_async_engine(temp_sqlite_url, echo=False)
    
    async with temp_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # Read from primary db and insert into sqlite
    async with async_session_maker() as src_session:
        result = await src_session.execute(select(Account))
        accounts = result.scalars().all()
        
        if accounts:
            async with temp_engine.begin() as dest_conn:
                for acc in accounts:
                    # SQLite needs simple types, so we pass column dictionaries
                    await dest_conn.execute(
                        insert(Account).values(
                            id=acc.id,
                            email=acc.email,
                            password_encrypted=acc.password_encrypted,
                            notes=acc.notes,
                            status=acc.status,
                            favorite=acc.favorite,
                            pinned=acc.pinned,
                            fetch_count=acc.fetch_count,
                            created_at=acc.created_at,
                            updated_at=acc.updated_at,
                            deleted_at=acc.deleted_at,
                            last_fetched=acc.last_fetched
                        )
                    )
    await temp_engine.dispose()
    logger.info(f"Dumped PostgreSQL accounts to SQLite backup file: {dest_path}")
    return dest_path

async def export_csv() -> str:
    """Exports decrypted accounts as a CSV file."""
    temp_dir = tempfile.gettempdir()
    dest_path = os.path.join(temp_dir, f"accounts_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv")
    
    async with async_session_maker() as session:
        result = await session.execute(select(Account).where(Account.deleted_at.is_(None)))
        accounts = result.scalars().all()
        
        with open(dest_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "ID", "Email", "Password", "Notes", "Status", 
                "Favorite", "Pinned", "Fetch Count", "Created At", "Updated At"
            ])
            
            for acc in accounts:
                try:
                    decrypted_pwd = decrypt_password(acc.password_encrypted)
                except Exception:
                    decrypted_pwd = "[DECRYPTION_FAILED]"
                
                writer.writerow([
                    f"#{acc.id:05d}",
                    acc.email,
                    decrypted_pwd,
                    acc.notes or "",
                    acc.status,
                    acc.favorite,
                    acc.pinned,
                    acc.fetch_count,
                    acc.created_at.strftime("%Y-%m-%d %H:%M:%S") if acc.created_at else "",
                    acc.updated_at.strftime("%Y-%m-%d %H:%M:%S") if acc.updated_at else ""
                ])
                
    logger.info(f"CSV export saved to: {dest_path}")
    return dest_path

async def export_json_encrypted() -> str:
    """Exports encrypted JSON backup containing account information."""
    from bot.encryption import encrypt_password, decrypt_password
    
    async with async_session_maker() as session:
        result = await session.execute(select(Account))
        accounts = result.scalars().all()
        
        export_data = []
        for acc in accounts:
            try:
                # Store decrypted passwords in the JSON list, then encrypt the whole JSON
                # Or we can just dump encrypted passwords. To allow restoration on a new Fernet key,
                # we decrypt first, and then encrypt the entire JSON blob.
                # If we encrypt the entire JSON string, it's highly secure and robust!
                decrypted_pwd = decrypt_password(acc.password_encrypted)
            except Exception:
                decrypted_pwd = ""
                
            export_data.append({
                "email": acc.email,
                "password": decrypted_pwd,
                "notes": acc.notes,
                "status": acc.status,
                "favorite": acc.favorite,
                "pinned": acc.pinned,
                "fetch_count": acc.fetch_count,
                "created_at": acc.created_at.isoformat() if acc.created_at else None,
                "updated_at": acc.updated_at.isoformat() if acc.updated_at else None,
                "deleted_at": acc.deleted_at.isoformat() if acc.deleted_at else None,
                "last_fetched": acc.last_fetched.isoformat() if acc.last_fetched else None
            })
            
        json_str = json.dumps(export_data, indent=2)
        
        # Encrypt the JSON text with the current key
        encrypted_data = encrypt_password(json_str)
        
        temp_dir = tempfile.gettempdir()
        dest_path = os.path.join(temp_dir, f"vault_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json.enc")
        
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(encrypted_data)
            
    logger.info(f"Encrypted JSON backup saved to: {dest_path}")
    return dest_path

async def import_json_encrypted(file_content: str) -> dict:
    """
    Imports accounts from an encrypted JSON backup file.
    Skips duplicates based on duplicate_email_protection setting.
    """
    try:
        # Decrypt the file content
        decrypted_json_str = decrypt_password(file_content)
        records = json.loads(decrypted_json_str)
    except Exception as e:
        logger.error(f"Failed to decrypt or parse import file: {e}")
        raise ValueError("Invalid backup file or encryption key mismatch.")

    stats = {
        "total": len(records),
        "imported": 0,
        "skipped": 0,
        "errors": 0
    }
    
    async with async_session_maker() as session:
        # Load duplicate protection setting
        result = await session.execute(select(Settings).where(Settings.id == 1))
        settings = result.scalar_one()
        dup_protection = settings.duplicate_email_protection
        
        for record in records:
            try:
                email = record.get("email")
                pwd = record.get("password")
                if not email or not pwd:
                    stats["errors"] += 1
                    continue
                
                # Check for duplicate
                if dup_protection:
                    dup_check = await session.execute(
                        select(Account).where(Account.email == email, Account.deleted_at.is_(None))
                    )
                    if dup_check.scalars().first():
                        stats["skipped"] += 1
                        continue
                
                # Create and insert account
                encrypted_pwd = encrypt_password(pwd)
                
                created_at = datetime.fromisoformat(record["created_at"]) if record.get("created_at") else datetime.utcnow()
                updated_at = datetime.fromisoformat(record["updated_at"]) if record.get("updated_at") else datetime.utcnow()
                deleted_at = datetime.fromisoformat(record["deleted_at"]) if record.get("deleted_at") else None
                last_fetched = datetime.fromisoformat(record["last_fetched"]) if record.get("last_fetched") else None
                
                new_account = Account(
                    email=email,
                    password_encrypted=encrypted_pwd,
                    notes=record.get("notes"),
                    status=record.get("status", "Available"),
                    favorite=record.get("favorite", False),
                    pinned=record.get("pinned", False),
                    fetch_count=record.get("fetch_count", 0),
                    created_at=created_at,
                    updated_at=updated_at,
                    deleted_at=deleted_at,
                    last_fetched=last_fetched
                )
                session.add(new_account)
                stats["imported"] += 1
            except Exception as e:
                logger.error(f"Error importing account record: {e}")
                stats["errors"] += 1
                
        await session.commit()
        
    return stats
