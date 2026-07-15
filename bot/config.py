import os
from pathlib import Path
from dotenv import load_dotenv

# Load local environment variables from .env if present
load_dotenv()

# Project directory
BOT_DIR = Path(__file__).resolve().parent

# Config variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID_STR = os.getenv("ADMIN_ID")
ADMIN_ID = int(ADMIN_ID_STR) if ADMIN_ID_STR else None

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Fallback to local SQLite database in bot/data/
    data_dir = BOT_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite+aiosqlite:///{data_dir}/vault.db"
else:
    # Format postgres URLs to use asyncpg driver
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    # Strip sslmode parameters since asyncpg doesn't support them in query args
    if "sslmode=" in DATABASE_URL:
        import urllib.parse
        parsed = urllib.parse.urlparse(DATABASE_URL)
        query_params = urllib.parse.parse_qs(parsed.query)
        query_params.pop("sslmode", None)
        new_query = urllib.parse.urlencode(query_params, doseq=True)
        DATABASE_URL = urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
        )

# Fernet encryption key config
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    # Fallback to secret.key file
    data_dir = BOT_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    key_file = data_dir / "secret.key"
    if key_file.exists():
        ENCRYPTION_KEY = key_file.read_text().strip()
    else:
        # Generate a new Fernet key and save it locally
        from cryptography.fernet import Fernet
        new_key = Fernet.generate_key().decode()
        key_file.write_text(new_key)
        ENCRYPTION_KEY = new_key
