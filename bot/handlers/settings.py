import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.database import async_session_maker
from bot.models import Settings
from bot.keyboards.inline_keyboards import get_settings_keyboard
from bot.utils.decorators import admin_only
from sqlalchemy import select

logger = logging.getLogger(__name__)

@admin_only
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered by the '⚙️ Settings' main menu option or /settings command."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    async with async_session_maker() as session:
        result = await session.execute(select(Settings).where(Settings.id == 1))
        settings = result.scalar_one()
        
    menu_text = (
        "⚙️ <b>Settings Dashboard</b>\n\n"
        "Configure your account vault settings below:\n"
        "• Select numbers to change generated password length.\n"
        "• Click boolean buttons to toggle character rules and features."
    )
    
    await update.message.reply_text(
        text=menu_text,
        reply_markup=get_settings_keyboard(settings),
        parse_mode="HTML"
    )

async def settings_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline button clicks in the settings dashboard."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    from bot import config
    if user_id != config.ADMIN_ID:
        return
        
    data = query.data
    
    if data == "settings:close":
        await query.message.delete()
        return
        
    parts = data.split(":")
    action = parts[1]
    
    async with async_session_maker() as session:
        # Load settings row
        result = await session.execute(select(Settings).where(Settings.id == 1))
        settings = result.scalar_one()
        
        if action == "len":
            length = int(parts[2])
            settings.password_length = length
            await session.commit()
            logger.info(f"Settings Updated: password_length set to {length}")
            
        elif action == "toggle":
            field = parts[2]
            # Verify field exists in settings model to prevent attribute injection
            if hasattr(settings, field):
                current_val = getattr(settings, field)
                setattr(settings, field, not current_val)
                await session.commit()
                logger.info(f"Settings Updated: {field} toggled to {not current_val}")
                
        # Re-fetch settings for rendering updated dashboard
        await session.refresh(settings)
        
    menu_text = (
        "⚙️ <b>Settings Dashboard</b>\n\n"
        "Configure your account vault settings below:\n"
        "• Select numbers to change generated password length.\n"
        "• Click boolean buttons to toggle character rules and features."
    )
    
    await query.edit_message_text(
        text=menu_text,
        reply_markup=get_settings_keyboard(settings),
        parse_mode="HTML"
    )
