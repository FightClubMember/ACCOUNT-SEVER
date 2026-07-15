import logging
import html
import secrets
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from bot.database import async_session_maker
from bot.models import Account, Settings
from bot.encryption import decrypt_password
from bot.utils.decorators import admin_only
from bot.utils.formatters import format_date
from bot.keyboards.inline_keyboards import (
    get_fetch_keyboard,
    get_delete_confirmation_keyboard
)
from sqlalchemy import select, update, and_

logger = logging.getLogger(__name__)

def escape_html(text: str) -> str:
    """Escapes HTML special characters to prevent markup injection."""
    if not text:
        return "None"
    return html.escape(text)

async def get_random_available_account(exclude_id: int = None) -> Account:
    """Fetches a random available account, excluding the provided ID if possible."""
    async with async_session_maker() as session:
        stmt = select(Account).where(
            and_(
                Account.status == "Available",
                Account.deleted_at.is_(None)
            )
        )
        result = await session.execute(stmt)
        accounts = result.scalars().all()
        
        if not accounts:
            return None
            
        if len(accounts) == 1:
            return accounts[0]
            
        # If there are multiple, filter out the excluded ID to avoid consecutive repeats
        available_pool = accounts
        if exclude_id is not None:
            available_pool = [a for a in accounts if a.id != exclude_id]
            if not available_pool: # Fallback just in case
                available_pool = accounts
                
        return secrets.choice(available_pool)

def format_account_details_html(account: Account, decrypted_pwd: str) -> str:
    """Helper to format account information in safe HTML."""
    markers = ""
    if account.pinned:
        markers += " 📌"
    if account.favorite:
        markers += " ⭐"
        
    notes_disp = escape_html(account.notes)
    
    return (
        f"🔑 <b>Account Details</b>\n\n"
        f"<b>ID:</b> #00{account.id:03d}{markers}\n"
        f"<b>Email:</b> <code>{escape_html(account.email)}</code>\n"
        f"<b>Password:</b> <code>{escape_html(decrypted_pwd)}</code>\n"
        f"<b>Status:</b> {escape_html(account.status)}\n"
        f"<b>Created:</b> {format_date(account.created_at)}\n"
        f"<b>Fetch Count:</b> {account.fetch_count}\n\n"
        f"<b>Notes (Plain Text):</b>\n"
        f"{notes_disp}"
    )

@admin_only
async def fetch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches and displays a random available account."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    last_fetched_id = context.user_data.get("last_fetched_id")
    account = await get_random_available_account(exclude_id=last_fetched_id)
    
    if not account:
        await update.message.reply_text("🎲 No Available Accounts.")
        return
        
    # Increment fetch count
    async with async_session_maker() as session:
        account.fetch_count += 1
        account.last_fetched = datetime.utcnow()
        await session.merge(account)
        await session.commit()
        
    context.user_data["last_fetched_id"] = account.id
    
    try:
        decrypted_pwd = decrypt_password(account.password_encrypted)
    except Exception:
        decrypted_pwd = "[Decryption Failed]"
        
    await update.message.reply_text(
        text=format_account_details_html(account, decrypted_pwd),
        reply_markup=get_fetch_keyboard(account),
        parse_mode="HTML"
    )

async def fetch_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes callback query actions for the Fetch flow."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    from bot import config
    if user_id != config.ADMIN_ID:
        return
        
    data = query.data
    
    if data == "fetch:close":
        await query.message.delete()
        return
        
    elif data == "fetch:next":
        last_fetched_id = context.user_data.get("last_fetched_id")
        account = await get_random_available_account(exclude_id=last_fetched_id)
        
        if not account:
            await query.edit_message_text("🎲 No Available Accounts. Closing...")
            return
            
        async with async_session_maker() as session:
            # Re-fetch from session to merge/increment
            db_acc = await session.get(Account, account.id)
            db_acc.fetch_count += 1
            db_acc.last_fetched = datetime.utcnow()
            await session.commit()
            account = db_acc
            
        context.user_data["last_fetched_id"] = account.id
        
        try:
            decrypted_pwd = decrypt_password(account.password_encrypted)
        except Exception:
            decrypted_pwd = "[Decryption Failed]"
            
        await query.edit_message_text(
            text=format_account_details_html(account, decrypted_pwd),
            reply_markup=get_fetch_keyboard(account),
            parse_mode="HTML"
        )
        return

    # Parse actions with ID
    parts = data.split(":")
    if len(parts) < 3:
        return
        
    action = parts[1]
    account_id = int(parts[2])
    
    async with async_session_maker() as session:
        account = await session.get(Account, account_id)
        if not account or account.deleted_at is not None:
            await query.edit_message_text("❌ This account no longer exists.")
            return
            
        if action == "used":
            account.status = "Used"
            account.updated_at = datetime.utcnow()
            await session.commit()
            logger.info(f"Account ID #{account_id} marked as Used.")
            
            # Show update
            await query.edit_message_text(
                f"✅ Account ID #00{account_id:03d} (<code>{escape_html(account.email)}</code>) has been marked as <b>Used</b>.",
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
                reply_markup=get_fetch_keyboard(account),
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
                reply_markup=get_fetch_keyboard(account),
                parse_mode="HTML"
            )
            
        elif action == "delete":
            # Check if confirm delete is enabled
            sett_res = await session.execute(select(Settings).where(Settings.id == 1))
            settings = sett_res.scalar_one()
            
            if settings.confirm_delete:
                # Show confirmation
                await query.edit_message_text(
                    text=f"❓ Are you sure you want to delete account #00{account.id:03d} (<code>{escape_html(account.email)}</code>)? It will be moved to Trash.",
                    reply_markup=get_delete_confirmation_keyboard(account.id, "fetch"),
                    parse_mode="HTML"
                )
            else:
                # Soft delete directly
                account.deleted_at = datetime.utcnow()
                account.updated_at = datetime.utcnow()
                await session.commit()
                logger.info(f"Account ID #{account_id} soft deleted.")
                await query.edit_message_text("🗑 Account moved to Trash.")
                
        elif action == "edit_notes":
            # Enable notes editing state for the user
            context.user_data["awaiting_notes_edit"] = {
                "account_id": account.id,
                "source": "fetch",
                "message_id": query.message.message_id
            }
            await query.message.reply_text(
                "📝 Please reply to this message with the new notes (Markdown is disabled):"
            )

async def confirm_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes confirm/cancel actions for deletion."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    from bot import config
    if user_id != config.ADMIN_ID:
        return
        
    parts = query.data.split(":")
    # confirm_del:yes:<id>:<source>
    choice = parts[1]
    account_id = int(parts[2])
    source = parts[3]
    
    async with async_session_maker() as session:
        account = await session.get(Account, account_id)
        if not account:
            await query.edit_message_text("❌ Account no longer exists.")
            return
            
        if choice == "yes":
            account.deleted_at = datetime.utcnow()
            account.updated_at = datetime.utcnow()
            await session.commit()
            logger.info(f"Account ID #{account_id} soft deleted.")
            await query.edit_message_text("🗑 Account moved to Trash.")
        else:
            # Go back to displaying detail
            if source == "fetch":
                try:
                    decrypted_pwd = decrypt_password(account.password_encrypted)
                except Exception:
                    decrypted_pwd = "[Decryption Failed]"
                await query.edit_message_text(
                    text=format_account_details_html(account, decrypted_pwd),
                    reply_markup=get_fetch_keyboard(account),
                    parse_mode="HTML"
                )
            elif source.startswith("acc"):
                # Format: acc_<filter>_<page>
                _, filter_name, page_str = source.split("_")
                try:
                    from bot.handlers.accounts_list import display_single_account
                    await display_single_account(query, account, filter_name, int(page_str))
                except Exception as e:
                    logger.error(f"Error returning to list item: {e}")
                    await query.edit_message_text("❌ Operation Cancelled.")
            else:
                await query.edit_message_text("❌ Operation Cancelled.")

@admin_only
async def handle_notes_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes plain text input for notes editing."""
    edit_info = context.user_data.get("awaiting_notes_edit")
    if not edit_info:
        return
        
    account_id = edit_info["account_id"]
    source = edit_info["source"]
    orig_msg_id = edit_info["message_id"]
    
    new_notes = update.message.text.strip()
    
    # Save notes
    async with async_session_maker() as session:
        account = await session.get(Account, account_id)
        if account:
            account.notes = new_notes
            account.updated_at = datetime.utcnow()
            await session.commit()
            logger.info(f"Notes updated for Account ID #{account_id}")
            
    # Delete the prompt and user's reply
    try:
        await update.message.delete()
    except Exception:
        pass
        
    # Clear state
    context.user_data.pop("awaiting_notes_edit", None)
    
    # Update the original message if possible
    async with async_session_maker() as session:
        account = await session.get(Account, account_id)
        if not account or account.deleted_at is not None:
            return
            
        try:
            decrypted_pwd = decrypt_password(account.password_encrypted)
        except Exception:
            decrypted_pwd = "[Decryption Failed]"
            
        # Check source and edit accordingly
        if source == "fetch":
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=orig_msg_id,
                text=format_account_details_html(account, decrypted_pwd),
                reply_markup=get_fetch_keyboard(account),
                parse_mode="HTML"
            )
        elif source.startswith("acc"):
            # Format: acc_<filter>_<page>
            _, filter_name, page_str = source.split("_")
            from bot.keyboards.inline_keyboards import get_account_view_back_keyboard
            
            detail_html = (
                f"📂 <b>Account Details</b>\n\n"
                f"<b>ID:</b> #00{account.id:03d}\n"
                f"<b>Email:</b> <code>{escape_html(account.email)}</code>\n"
                f"<b>Password:</b> <code>{escape_html(decrypted_pwd)}</code>\n"
                f"<b>Status:</b> {escape_html(account.status)}\n"
                f"<b>Created:</b> {format_date(account.created_at)}\n"
                f"<b>Notes (Plain Text):</b>\n"
                f"{escape_html(account.notes)}"
            )
            
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=orig_msg_id,
                text=detail_html,
                reply_markup=get_account_view_back_keyboard(account.id, filter_name, int(page_str)),
                parse_mode="HTML"
            )
        elif source == "search":
            from bot.keyboards.inline_keyboards import get_search_detail_keyboard
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=orig_msg_id,
                text=format_account_details_html(account, decrypted_pwd),
                reply_markup=get_search_detail_keyboard(account),
                parse_mode="HTML"
            )
