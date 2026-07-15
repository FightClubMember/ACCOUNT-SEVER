import os
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from bot.database import async_session_maker, engine
from bot.models import Account
from bot.utils.decorators import admin_only
from bot.utils.formatters import get_progress_bar, format_size, format_date
from bot.encryption import decrypt_password
from bot import config
from sqlalchemy import select, func, and_

logger = logging.getLogger(__name__)

@admin_only
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered by the '📊 Stats' main menu option or /stats command."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    async with async_session_maker() as session:
        # 1. Base counts (excluding deleted)
        total_stmt = select(func.count(Account.id)).where(Account.deleted_at.is_(None))
        total_res = await session.execute(total_stmt)
        total_active = total_res.scalar() or 0
        
        avail_stmt = select(func.count(Account.id)).where(and_(Account.status == "Available", Account.deleted_at.is_(None)))
        avail_res = await session.execute(avail_stmt)
        total_avail = avail_res.scalar() or 0
        
        used_stmt = select(func.count(Account.id)).where(and_(Account.status == "Used", Account.deleted_at.is_(None)))
        used_res = await session.execute(used_stmt)
        total_used = used_res.scalar() or 0
        
        fav_stmt = select(func.count(Account.id)).where(and_(Account.favorite == True, Account.deleted_at.is_(None)))
        fav_res = await session.execute(fav_stmt)
        total_fav = fav_res.scalar() or 0
        
        pinned_stmt = select(func.count(Account.id)).where(and_(Account.pinned == True, Account.deleted_at.is_(None)))
        pinned_res = await session.execute(pinned_stmt)
        total_pinned = pinned_res.scalar() or 0
        
        # 2. Time interval counts
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        month_start = now - timedelta(days=30)
        
        today_stmt = select(func.count(Account.id)).where(and_(Account.created_at >= today_start, Account.deleted_at.is_(None)))
        today_res = await session.execute(today_stmt)
        added_today = today_res.scalar() or 0
        
        week_stmt = select(func.count(Account.id)).where(and_(Account.created_at >= week_start, Account.deleted_at.is_(None)))
        week_res = await session.execute(week_stmt)
        added_week = week_res.scalar() or 0
        
        month_stmt = select(func.count(Account.id)).where(and_(Account.created_at >= month_start, Account.deleted_at.is_(None)))
        month_res = await session.execute(month_stmt)
        added_month = month_res.scalar() or 0
        
        # 3. Average & max fetch counts
        avg_fetch_stmt = select(func.avg(Account.fetch_count)).where(Account.deleted_at.is_(None))
        avg_fetch_res = await session.execute(avg_fetch_stmt)
        avg_fetch = avg_fetch_res.scalar()
        avg_fetch_val = float(avg_fetch) if avg_fetch is not None else 0.0
        
        most_used_stmt = select(Account).where(Account.deleted_at.is_(None)).order_by(Account.fetch_count.desc()).limit(1)
        most_used_res = await session.execute(most_used_stmt)
        most_used_acc = most_used_res.scalar_one_or_none()
        
    # 4. Storage & file sizes
    db_size_str = "N/A"
    sqlite_file_size = 0
    if config.DATABASE_URL.startswith("sqlite+aiosqlite:///"):
        db_path = config.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
        try:
            if os.path.exists(db_path):
                sqlite_file_size = os.path.getsize(db_path)
                db_size_str = format_size(sqlite_file_size)
        except Exception as e:
            logger.error(f"Error reading SQLite file size: {e}")
            db_size_str = "Error reading file"
    else:
        db_size_str = "Cloud Database (PostgreSQL)"

    # 5. Last Backup
    last_backup_str = "Never"
    try:
        from bot.backup import BACKUP_DIR
        if BACKUP_DIR.exists():
            backups = [BACKUP_DIR / f for f in os.listdir(BACKUP_DIR) if os.path.isfile(BACKUP_DIR / f)]
            if backups:
                newest_file = max(backups, key=os.path.getmtime)
                mtime = os.path.getmtime(newest_file)
                last_backup_str = format_date(datetime.fromtimestamp(mtime))
    except Exception as e:
        logger.error(f"Error finding last backup file: {e}")

    # Calculate percentages
    avail_pct = (total_avail / total_active * 100.0) if total_active > 0 else 0.0
    used_pct = (total_used / total_active * 100.0) if total_active > 0 else 0.0
    
    # Format Most Used Account details
    if most_used_acc and most_used_acc.fetch_count > 0:
        most_used_str = f"#{most_used_acc.id:04d} ({most_used_acc.email}) — {most_used_acc.fetch_count} fetches"
    else:
        most_used_str = "None"
        
    # Render dashboard
    dashboard_text = (
        "📊 <b>System Statistics</b>\n\n"
        f"<b>Total Accounts:</b> {total_active} active records\n\n"
        f"<b>Available Status:</b> {total_avail} ({avail_pct:.1f}%)\n"
        f"<code>{get_progress_bar(avail_pct)}</code>\n\n"
        f"<b>Used Status:</b> {total_used} ({used_pct:.1f}%)\n"
        f"<code>{get_progress_bar(used_pct)}</code>\n\n"
        f"⭐ <b>Favorites:</b> {total_fav} accounts\n"
        f"📌 <b>Pinned:</b> {total_pinned} accounts\n\n"
        f"📅 <b>Added Today:</b> {added_today} records\n"
        f"📅 <b>Added This Week:</b> {added_week} records\n"
        f"📅 <b>Added This Month:</b> {added_month} records\n\n"
        f"📈 <b>Average Fetch Count:</b> {avg_fetch_val:.1f} fetches/account\n"
        f"🔥 <b>Most Fetched Account:</b> <code>{most_used_str}</code>\n\n"
        f"💾 <b>Storage Size:</b> {db_size_str}\n"
        f"🗂️ <b>Database Size:</b> {total_active} accounts in database\n"
        f"📥 <b>Last Backup File:</b> {last_backup_str}"
    )
    
    await update.message.reply_text(
        text=dashboard_text,
        parse_mode="HTML"
    )
