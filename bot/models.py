from datetime import datetime
from sqlalchemy import String, Text, Boolean, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from bot.database import Base

class Account(Base):
    __tablename__ = "accounts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    password_encrypted: Mapped[str] = mapped_column(String(1024), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Available", index=True)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    fetch_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_fetched: Mapped[datetime] = mapped_column(DateTime, nullable=True)

class Settings(Base):
    __tablename__ = "settings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    password_length: Mapped[int] = mapped_column(Integer, default=16)
    use_symbols: Mapped[bool] = mapped_column(Boolean, default=True)
    use_uppercase: Mapped[bool] = mapped_column(Boolean, default=True)
    use_lowercase: Mapped[bool] = mapped_column(Boolean, default=True)
    use_numbers: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_backup: Mapped[bool] = mapped_column(Boolean, default=True)
    duplicate_email_protection: Mapped[bool] = mapped_column(Boolean, default=True)
    confirm_delete: Mapped[bool] = mapped_column(Boolean, default=True)
