import logging
from datetime import datetime
from telegram import Update, Message
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    CommandHandler
)
from bot.database import async_session_maker
from bot.models import Account, Settings
from bot.encryption import encrypt_password
from bot.password_generator import generate_secure_password
from bot.utils.validation import validate_email
from bot.utils.decorators import admin_only
from bot.keyboards.inline_keyboards import (
    get_password_generation_keyboard,
    get_skip_notes_keyboard
)
from bot.keyboards.reply_keyboards import get_home_keyboard
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Conversation States
EMAIL, PASSWORD_CONFIRM, NOTES = range(3)

@admin_only
async def start_add_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Begins the Add Account conversation flow."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Prompt the user for email address
    await update.message.reply_text(
        text="📧 *Send Email Address*\n\nPlease enter the email address for the new account record:",
        parse_mode="Markdown"
    )
    return EMAIL

@admin_only
async def process_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validates the input email and prompts the password generation step."""
    email = update.message.text.strip()
    
    # 1. Validate email format
    if not validate_email(email):
        await update.message.reply_text(
            text="❌ *Invalid Email Format*\n\nPlease send a valid email address (e.g., user@example.com) or type /cancel to abort:",
            parse_mode="Markdown"
        )
        return EMAIL
        
    # 2. Check for duplicate email in database (if protection is enabled)
    async with async_session_maker() as session:
        result = await session.execute(select(Settings).where(Settings.id == 1))
        settings = result.scalar_one()
        
        if settings.duplicate_email_protection:
            # Query db for matching email where not deleted
            db_res = await session.execute(
                select(Account).where(Account.email == email, Account.deleted_at.is_(None))
            )
            existing = db_res.scalars().first()
            if existing:
                await update.message.reply_text(
                    text="❌ *Duplicate Email Address*\n\nThis email already exists in your active account vault. Please send a different email address or type /cancel to abort:",
                    parse_mode="Markdown"
                )
                return EMAIL
                
    # Email is valid. Store email in context user_data
    context.user_data["add_email"] = email
    
    # Generate password
    password = generate_secure_password(
        length=settings.password_length,
        use_symbols=settings.use_symbols,
        use_uppercase=settings.use_uppercase,
        use_lowercase=settings.use_lowercase,
        use_numbers=settings.use_numbers
    )
    context.user_data["add_password"] = password
    
    pwd_message = (
        "🔑 *Generated Password*\n\n"
        f"`{password}`\n\n"
        "Click *Use Password* to confirm or *Generate Again* for a different one."
    )
    
    await update.message.reply_text(
        text=pwd_message,
        reply_markup=get_password_generation_keyboard(),
        parse_mode="Markdown"
    )
    return PASSWORD_CONFIRM

async def regen_password_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Regenerates a new password and updates the message."""
    query = update.callback_query
    await query.answer()
    
    # Fetch settings
    async with async_session_maker() as session:
        result = await session.execute(select(Settings).where(Settings.id == 1))
        settings = result.scalar_one()
        
    password = generate_secure_password(
        length=settings.password_length,
        use_symbols=settings.use_symbols,
        use_uppercase=settings.use_uppercase,
        use_lowercase=settings.use_lowercase,
        use_numbers=settings.use_numbers
    )
    context.user_data["add_password"] = password
    
    pwd_message = (
        "🔑 *Generated Password*\n\n"
        f"`{password}`\n\n"
        "Click *Use Password* to confirm or *Generate Again* for a different one."
    )
    
    await query.edit_message_text(
        text=pwd_message,
        reply_markup=get_password_generation_keyboard(),
        parse_mode="Markdown"
    )
    return PASSWORD_CONFIRM

async def use_password_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Accepts the generated password and transitions to notes collection."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        text="📝 *Add Notes (Optional)*\n\nPlease send any notes/descriptions for this account, or click the button below to skip this step:",
        reply_markup=get_skip_notes_keyboard(),
        parse_mode="Markdown"
    )
    return NOTES

@admin_only
async def process_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Accepts notes from typed message and finishes the flow by saving."""
    notes = update.message.text.strip()
    context.user_data["add_notes"] = notes
    return await save_account(update, context)

async def skip_notes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skips notes step and completes the flow by saving."""
    query = update.callback_query
    await query.answer()
    context.user_data["add_notes"] = None
    return await save_account(update, context)

async def save_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the account details into the database and displays the final report."""
    email = context.user_data.get("add_email")
    pwd = context.user_data.get("add_password")
    notes = context.user_data.get("add_notes")
    
    if not email or not pwd:
        # Unexpected error, abort
        err_msg = "❌ An unexpected error occurred. Aborting add flow."
        if update.callback_query:
            await update.callback_query.edit_message_text(err_msg)
        else:
            await update.message.reply_text(err_msg)
        return ConversationHandler.END
        
    try:
        # Encrypt password
        encrypted_pwd = encrypt_password(pwd)
        
        # Save to database
        async with async_session_maker() as session:
            new_account = Account(
                email=email,
                password_encrypted=encrypted_pwd,
                notes=notes,
                status="Available"
            )
            session.add(new_account)
            await session.commit()
            
            # Retrieve ID
            await session.refresh(new_account)
            account_id = new_account.id
            
            # Check if auto backup is enabled
            result = await session.execute(select(Settings).where(Settings.id == 1))
            settings = result.scalar_one()
            auto_backup = settings.auto_backup
            
        logger.info(f"Account saved successfully: ID #{account_id:05d}, Email: {email}")
        
        import html
        success_text = (
            "✅ <b>Saved Successfully</b>\n\n"
            "<b>Email:</b>\n"
            f"{html.escape(email)}\n\n"
            "<b>Password Generated</b>\n\n"
            "<b>Status:</b>\n"
            "Available\n\n"
            "<b>ID:</b>\n"
            f"#00{account_id:03d}"
        )
        
        # Trigger Auto-Backup if toggled on
        if auto_backup:
            try:
                from bot.backup import export_json_encrypted
                await export_json_encrypted()
                logger.info("Auto-backup triggered successfully during account creation.")
            except Exception as backup_err:
                logger.error(f"Auto-backup failed: {backup_err}")
                
        if update.callback_query:
            await update.callback_query.edit_message_text(success_text, parse_mode="HTML")
        else:
            await update.message.reply_text(success_text, parse_mode="HTML", reply_markup=get_home_keyboard())
            
    except Exception as e:
        logger.error(f"Error saving account to database: {e}")
        err_msg = "❌ Database error. Failed to save account."
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text(err_msg)
            else:
                await update.message.reply_text(err_msg, reply_markup=get_home_keyboard())
        except Exception as send_err:
            logger.error(f"Failed to send error message: {send_err}")
            
    # Clear session data
    context.user_data.pop("add_email", None)
    context.user_data.pop("add_password", None)
    context.user_data.pop("add_notes", None)
    
    return ConversationHandler.END

@admin_only
async def cancel_add_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the Add Account conversation flow."""
    # Check if this is from command or callback button
    if update.callback_query:
        query = update.callback_query
        await query.answer("Add flow cancelled.")
        await query.edit_message_text("❌ *Operation Cancelled*", parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "❌ *Operation Cancelled*",
            reply_markup=get_home_keyboard(),
            parse_mode="Markdown"
        )
        
    context.user_data.pop("add_email", None)
    context.user_data.pop("add_password", None)
    context.user_data.pop("add_notes", None)
    return ConversationHandler.END

def get_add_account_handler() -> ConversationHandler:
    """Returns the ConversationHandler configuration for the add flow."""
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^➕ Add Account$"), start_add_flow),
            CommandHandler("add", start_add_flow)
        ],
        states={
            EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_email)
            ],
            PASSWORD_CONFIRM: [
                CallbackQueryHandler(regen_password_callback, pattern="^pwd:regen$"),
                CallbackQueryHandler(use_password_callback, pattern="^pwd:use$"),
                CallbackQueryHandler(cancel_add_flow, pattern="^pwd:cancel$")
            ],
            NOTES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_notes),
                CallbackQueryHandler(skip_notes_callback, pattern="^add_notes:skip$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_add_flow),
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel_add_flow)
        ],
        allow_reentry=True
    )
