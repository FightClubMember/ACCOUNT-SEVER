import logging
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from bot import config
from bot.database import init_db
from bot.keyboards.reply_keyboards import get_home_keyboard
from bot.utils.decorators import admin_only

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Verify environment configuration
if not config.TELEGRAM_BOT_TOKEN:
    logger.critical("TELEGRAM_BOT_TOKEN environment variable is missing. Exiting.")
    exit(1)
if not config.ADMIN_ID:
    logger.critical("ADMIN_ID environment variable is missing. Exiting.")
    exit(1)

# Import Handlers
from bot.handlers.start import start_command
from bot.handlers.add_account import get_add_account_handler
from bot.handlers.fetch import (
    fetch_command,
    fetch_callback_handler,
    confirm_delete_callback,
    handle_notes_edit_input
)
from bot.handlers.search_handler import (
    get_search_handler,
    search_callback_handler
)
from bot.handlers.accounts_list import (
    accounts_command,
    accounts_callback_handler
)
from bot.handlers.stats import stats_command
from bot.handlers.settings import (
    settings_command,
    settings_callback_handler
)
from bot.handlers.export_import import (
    export_command,
    export_callback_handler,
    import_command,
    handle_import_file_upload
)
from bot.handlers.trash import (
    trash_command,
    trash_callback_handler,
    confirm_perm_delete_callback,
    confirm_empty_trash_callback,
    cleanup_old_trash_job
)

async def trash_cleanup_loop():
    """Background task running every 24 hours to automatically purge old trash."""
    # Run initially on startup
    await asyncio.sleep(10) # Give database some time to settle
    while True:
        try:
            logger.info("Executing automatic 30-day trash cleanup job...")
            await cleanup_old_trash_job()
        except Exception as e:
            logger.error(f"Error in automatic trash cleanup loop: {e}")
        # Sleep for 24 hours
        await asyncio.sleep(24 * 60 * 60)

async def post_init(application) -> None:
    """Startup initialization routine."""
    logger.info("Starting Account Vault initialization...")
    # Initialize database tables and seed default settings
    await init_db()
    # Launch background trash cleaner loop
    asyncio.create_task(trash_cleanup_loop())
    logger.info("Account Vault initialization completed successfully.")

@admin_only
async def global_cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback handler to reset user state and send them back to the main keyboard."""
    # Clear any active state flags
    context.user_data.pop("awaiting_notes_edit", None)
    context.user_data.pop("awaiting_import_file", None)
    
    await update.message.reply_text(
        "❌ Active operations cancelled. Returned to main menu.",
        reply_markup=get_home_keyboard()
    )

def main():
    """Main application entry point."""
    # Build application
    application = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    # 1. Register Conversation Handlers (Add, Search)
    application.add_handler(get_add_account_handler())
    application.add_handler(get_search_handler())
    
    # 2. Register Global Command Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cancel", global_cancel_command))
    application.add_handler(CommandHandler("fetch", fetch_command))
    application.add_handler(CommandHandler("accounts", accounts_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("import", import_command))
    application.add_handler(CommandHandler("trash", trash_command))
    
    # 3. Register Reply Keyboard Button Text Handlers
    application.add_handler(MessageHandler(filters.Regex("^🎲 Fetch Account$"), fetch_command))
    application.add_handler(MessageHandler(filters.Regex("^📂 Accounts$"), accounts_command))
    application.add_handler(MessageHandler(filters.Regex("^📊 Stats$"), stats_command))
    application.add_handler(MessageHandler(filters.Regex("^⚙️ Settings$"), settings_command))
    application.add_handler(MessageHandler(filters.Regex("^📤 Export$"), export_command))
    application.add_handler(MessageHandler(filters.Regex("^📥 Import$"), import_command))
    application.add_handler(MessageHandler(filters.Regex("^🗑 Trash$"), trash_command))
    
    # 4. Intercept state-based inputs (notes editing, import document uploads)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_notes_edit_input
    ))
    application.add_handler(MessageHandler(
        filters.Document.ALL,
        handle_import_file_upload
    ))
    
    # 5. Register Callback Query Handlers with strict pattern regexes
    application.add_handler(CallbackQueryHandler(fetch_callback_handler, pattern="^fetch:.*$"))
    
    # Soft delete confirmation
    application.add_handler(CallbackQueryHandler(
        confirm_delete_callback,
        pattern="^confirm_del:(yes|no):\\d+:(fetch|acc_.*)$"
    ))
    
    # Permanent delete confirmation
    application.add_handler(CallbackQueryHandler(
        confirm_perm_delete_callback,
        pattern="^confirm_del:(yes|no):\\d+:trash_perm_\\d+$"
    ))
    
    application.add_handler(CallbackQueryHandler(search_callback_handler, pattern="^search:.*$"))
    application.add_handler(CallbackQueryHandler(accounts_callback_handler, pattern="^acc:.*$"))
    application.add_handler(CallbackQueryHandler(settings_callback_handler, pattern="^settings:.*$"))
    application.add_handler(CallbackQueryHandler(export_callback_handler, pattern="^export:.*$"))
    application.add_handler(CallbackQueryHandler(trash_callback_handler, pattern="^trash:.*$"))
    application.add_handler(CallbackQueryHandler(confirm_empty_trash_callback, pattern="^confirm_empty_trash:.*$"))
    
    # Run the bot
    logger.info("Starting Telegram Bot listener...")
    application.run_polling()

if __name__ == "__main__":
    main()
