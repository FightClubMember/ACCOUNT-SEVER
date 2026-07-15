from telegram import Update
from telegram.ext import ContextTypes
from bot.keyboards.reply_keyboards import get_home_keyboard
from bot.utils.decorators import admin_only

@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command and renders the persistent home reply keyboard."""
    # Premium typing animation effect
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    welcome_text = (
        "🔒 *Account Vault (Admin Only)*\n\n"
        "Welcome to your personal and secure account inventory. "
        "All credentials are stored fully encrypted with AES-256 standard and "
        "can only be decrypted on demand.\n\n"
        "Use the quick menu buttons below to manage your database."
    )
    
    await update.message.reply_text(
        text=welcome_text,
        reply_markup=get_home_keyboard(),
        parse_mode="Markdown"
    )
