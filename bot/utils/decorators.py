import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from bot import config

logger = logging.getLogger(__name__)

def admin_only(func):
    """
    Decorator to restrict access strictly to the configured ADMIN_ID.
    Blocks unauthorized users and replies with '❌ Access Denied'.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or user.id != config.ADMIN_ID:
            username = f"@{user.username}" if user and user.username else "No Username"
            user_id = user.id if user else "Unknown ID"
            logger.warning(f"Unauthorized access blocked: User {user_id} ({username}) tried to call {func.__name__}")
            
            if update.message:
                await update.message.reply_text("❌ Access Denied")
            elif update.callback_query:
                await update.callback_query.answer("❌ Access Denied", show_alert=True)
            return
            
        return await func(update, context, *args, **kwargs)
    return wrapper
