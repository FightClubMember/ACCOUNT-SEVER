import logging
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import select
from bot import config

logger = logging.getLogger(__name__)

# Ensure directory exists for SQLite
if config.DATABASE_URL.startswith("sqlite+aiosqlite:///"):
    db_path = config.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    # Standard SQLite path cleanup
    if db_path.startswith("/"):
        # For Unix absolute paths or Windows absolute paths without driver letter
        path = Path(db_path)
    else:
        path = Path(db_path)
    
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)

# Create async engine
engine = create_async_engine(config.DATABASE_URL, echo=False)

# Async session factory
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

async def init_db():
    """Initializes the database schema and ensures default settings are loaded."""
    from bot.models import Settings  # Import inside to prevent circular import
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Insert default settings row if it doesn't exist
    async with async_session_maker() as session:
        try:
            result = await session.execute(select(Settings).where(Settings.id == 1))
            settings = result.scalar_one_or_none()
            if not settings:
                default_settings = Settings(id=1)
                session.add(default_settings)
                await session.commit()
                logger.info("Default system settings seeded successfully.")
        except Exception as e:
            logger.error(f"Error seeding default settings: {e}")
            await session.rollback()
