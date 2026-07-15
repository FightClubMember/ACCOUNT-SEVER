import os
import logging
import tempfile
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from bot.database import async_session_maker
from bot.utils.decorators import admin_only
from bot.backup import (
    export_sqlite,
    export_csv,
    export_json_encrypted,
    import_json_encrypted
)
from bot.keyboards.reply_keyboards import get_home_keyboard

logger = logging.getLogger(__name__)

@admin_only
async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered by '📤 Export' main menu option or /export command."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    keyboard = [
        [
            InlineKeyboardButton("💾 SQLite Database", callback_data="export:sqlite"),
            InlineKeyboardButton("📂 CSV Spreadsheet", callback_data="export:csv")
        ],
        [InlineKeyboardButton("🔒 Encrypted JSON Backup", callback_data="export:json")],
        [InlineKeyboardButton("❌ Close", callback_data="export:close")]
    ]
    
    await update.message.reply_text(
        text="📤 <b>Export Dashboard</b>\n\nSelect your desired backup format to export your vault data:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def export_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes callback query interactions for data exports."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    from bot import config
    if user_id != config.ADMIN_ID:
        return
        
    data = query.data
    
    if data == "export:close":
        await query.message.delete()
        return
        
    action = data.split(":")[1]
    
    # Show loading status
    await query.edit_message_text("🔄 Preparing export file, please wait...")
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="upload_document")
    
    file_path = None
    try:
        if action == "sqlite":
            file_path = await export_sqlite()
            caption = "💾 Account Vault SQLite Database Backup File."
        elif action == "csv":
            file_path = await export_csv()
            caption = "📂 Account Vault Decrypted CSV Spreadsheet."
        elif action == "json":
            file_path = await export_json_encrypted()
            caption = "🔒 Account Vault Fernet-Encrypted JSON Backup File."
        else:
            await query.edit_message_text("❌ Unknown export format.")
            return
            
        # Send document to user
        with open(file_path, "rb") as document:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=document,
                filename=os.path.basename(file_path),
                caption=caption
            )
            
        await query.edit_message_text("✅ Export completed successfully. File sent.")
        logger.info(f"Successful vault export generated: {action}")
        
    except Exception as e:
        logger.error(f"Error during vault export: {e}")
        await query.edit_message_text("❌ Export failed due to an internal error.")
        
    finally:
        # Delete the temporary export file
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as remove_err:
                logger.error(f"Error deleting temporary export file: {remove_err}")

@admin_only
async def import_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered by '📥 Import' main menu option or /import command."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    context.user_data["awaiting_import_file"] = True
    
    await update.message.reply_text(
        text=(
            "📥 <b>Import Vault Data</b>\n\n"
            "Please upload and send your encrypted JSON backup file (<code>.json.enc</code>).\n"
            "This import will skip duplicates according to your email uniqueness settings.\n\n"
            "To cancel, type /cancel."
        ),
        parse_mode="HTML"
    )

@admin_only
async def handle_import_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Intercepts and parses uploaded backup files."""
    if not context.user_data.get("awaiting_import_file"):
        return
        
    document = update.message.document
    
    # 1. Basic validation of document presence
    if not document:
        await update.message.reply_text("❌ Please send a valid backup document file (.json.enc).")
        return
        
    # Check file suffix/type
    if not document.file_name.endswith(".json.enc"):
        await update.message.reply_text("❌ Invalid file format. Only .json.enc files are supported.")
        return
        
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text("📥 Downloading and decrypting file...")
    
    temp_path = None
    try:
        # 2. Download file
        file_id = document.file_id
        tg_file = await context.bot.get_file(file_id)
        
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"import_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json.enc")
        await tg_file.download_to_drive(temp_path)
        
        # 3. Read content
        with open(temp_path, "r", encoding="utf-8") as f:
            file_content = f.read().strip()
            
        # 4. Import logic
        report = await import_json_encrypted(file_content)
        
        # 5. Display success report
        report_text = (
            "✅ <b>Import Completed Successfully</b>\n\n"
            f"• <b>Total Parsed:</b> {report['total']} records\n"
            f"• <b>Imported Successfully:</b> {report['imported']}\n"
            f"• <b>Skipped (Duplicates):</b> {report['skipped']}\n"
            f"• <b>Errors:</b> {report['errors']}"
        )
        await update.message.reply_text(text=report_text, parse_mode="HTML", reply_markup=get_home_keyboard())
        logger.info(f"Vault imported successfully: {report['imported']} added, {report['skipped']} skipped.")
        
    except ValueError as val_err:
        logger.error(f"Import decryption/parsing mismatch: {val_err}")
        await update.message.reply_text(
            f"❌ <b>Import Failed:</b>\n{val_err}",
            parse_mode="HTML",
            reply_markup=get_home_keyboard()
        )
    except Exception as e:
        logger.error(f"Unexpected error during import processing: {e}")
        await update.message.reply_text(
            "❌ <b>Import Failed:</b> An internal server error occurred during parsing.",
            parse_mode="HTML",
            reply_markup=get_home_keyboard()
        )
    finally:
        # Cleanup
        context.user_data.pop("awaiting_import_file", None)
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.error(f"Error removing temp import file: {e}")
