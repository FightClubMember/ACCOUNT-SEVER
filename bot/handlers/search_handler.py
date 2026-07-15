import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters
)
from bot.search import search_accounts
from bot.database import async_session_maker
from bot.models import Account, Settings
from bot.encryption import decrypt_password
from bot.utils.decorators import admin_only
from bot.keyboards.reply_keyboards import get_home_keyboard
from bot.keyboards.inline_keyboards import (
    get_search_detail_keyboard,
    get_delete_confirmation_keyboard
)
from bot.handlers.fetch import format_account_details_html, escape_html
from datetime import datetime
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Conversation State
SEARCH_QUERY = 0

@admin_only
async def start_search_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the search conversation flow."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text(
        "🔍 *Search Vault*\n\nPlease enter your search query (matches Email, ID, Notes, Status, or Date):",
        parse_mode="Markdown"
    )
    return SEARCH_QUERY

@admin_only
async def process_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Executes search and displays the list of results or details."""
    query = update.message.text.strip()
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    results = await search_accounts(query)
    
    if not results:
        await update.message.reply_text(
            "❌ No matching accounts found. Search cancelled.",
            reply_markup=get_home_keyboard()
        )
        return ConversationHandler.END
        
    if len(results) == 1:
        # Show details directly
        account = results[0]
        try:
            decrypted_pwd = decrypt_password(account.password_encrypted)
        except Exception:
            decrypted_pwd = "[Decryption Failed]"
            
        await update.message.reply_text(
            text=format_account_details_html(account, decrypted_pwd),
            reply_markup=get_search_detail_keyboard(account),
            parse_mode="HTML",
            reply_markup_clear=True
        )
        return ConversationHandler.END
        
    # Multiple results: Display listing buttons
    keyboard = []
    for acc in results[:10]: # Limit to 10 for search quick list
        markers = ""
        if acc.pinned:
            markers += "📌"
        if acc.favorite:
            markers += "⭐"
        if acc.status == "Used":
            markers += "✔️"
        label = f"#{acc.id:04d}: {acc.email} {markers}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"search:view:{acc.id}")])
        
    keyboard.append([InlineKeyboardButton("❌ Close", callback_data="search:close")])
    
    await update.message.reply_text(
        text=f"🔍 <b>Search Results ({len(results)} matches):</b>\nSelect an account to view details:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def search_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes search result inline button interactions."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    from bot import config
    if user_id != config.ADMIN_ID:
        return
        
    data = query.data
    
    if data == "search:close":
        await query.message.delete()
        return
        
    parts = data.split(":")
    action = parts[1]
    account_id = int(parts[2])
    
    async with async_session_maker() as session:
        account = await session.get(Account, account_id)
        if not account or account.deleted_at is not None:
            await query.edit_message_text("❌ Account no longer exists.")
            return
            
        if action == "view":
            try:
                decrypted_pwd = decrypt_password(account.password_encrypted)
            except Exception:
                decrypted_pwd = "[Decryption Failed]"
                
            await query.edit_message_text(
                text=format_account_details_html(account, decrypted_pwd),
                reply_markup=get_search_detail_keyboard(account),
                parse_mode="HTML"
            )
            
        elif action == "status":
            next_status = parts[3]
            account.status = next_status
            account.updated_at = datetime.utcnow()
            await session.commit()
            
            try:
                decrypted_pwd = decrypt_password(account.password_encrypted)
            except Exception:
                decrypted_pwd = "[Decryption Failed]"
                
            await query.edit_message_text(
                text=format_account_details_html(account, decrypted_pwd),
                reply_markup=get_search_detail_keyboard(account),
                parse_mode="HTML"
            )
            
        elif action == "pin":
            account.pinned = not account.pinned
            account.updated_at = datetime.utcnow()
            await session.commit()
            
            try:
                decrypted_pwd = decrypt_password(account.password_encrypted)
            except Exception:
                decrypted_pwd = "[Decryption Failed]"
                
            await query.edit_message_text(
                text=format_account_details_html(account, decrypted_pwd),
                reply_markup=get_search_detail_keyboard(account),
                parse_mode="HTML"
            )
            
        elif action == "favorite":
            account.favorite = not account.favorite
            account.updated_at = datetime.utcnow()
            await session.commit()
            
            try:
                decrypted_pwd = decrypt_password(account.password_encrypted)
            except Exception:
                decrypted_pwd = "[Decryption Failed]"
                
            await query.edit_message_text(
                text=format_account_details_html(account, decrypted_pwd),
                reply_markup=get_search_detail_keyboard(account),
                parse_mode="HTML"
            )
            
        elif action == "delete":
            sett_res = await session.execute(select(Settings).where(Settings.id == 1))
            settings = sett_res.scalar_one()
            
            if settings.confirm_delete:
                await query.edit_message_text(
                    text=f"❓ Are you sure you want to delete account #00{account.id:03d} (<code>{escape_html(account.email)}</code>)?",
                    reply_markup=get_delete_confirmation_keyboard(account.id, "search"),
                    parse_mode="HTML"
                )
            else:
                account.deleted_at = datetime.utcnow()
                account.updated_at = datetime.utcnow()
                await session.commit()
                await query.edit_message_text("🗑 Account moved to Trash.")
                
        elif action == "edit_notes":
            context.user_data["awaiting_notes_edit"] = {
                "account_id": account.id,
                "source": "search",
                "message_id": query.message.message_id
            }
            await query.message.reply_text(
                "📝 Please reply to this message with the new notes (Markdown is disabled):"
            )

@admin_only
async def cancel_search_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Aborts the search conversation flow."""
    await update.message.reply_text("❌ Search cancelled.", reply_markup=get_home_keyboard())
    return ConversationHandler.END

def get_search_handler() -> ConversationHandler:
    """Returns the ConversationHandler configuration for the search flow."""
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🔍 Search$"), start_search_flow),
            CommandHandler("search", start_search_flow)
        ],
        states={
            SEARCH_QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_search_query)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_search_flow),
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel_search_flow)
        ],
        allow_reentry=True
    )
