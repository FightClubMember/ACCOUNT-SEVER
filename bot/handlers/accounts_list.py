import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from bot.database import async_session_maker
from bot.models import Account, Settings
from bot.encryption import decrypt_password
from bot.utils.decorators import admin_only
from bot.utils.formatters import format_date
from bot.keyboards.inline_keyboards import (
    get_accounts_list_keyboard,
    get_account_view_back_keyboard,
    get_delete_confirmation_keyboard
)
from sqlalchemy import select, func, and_

logger = logging.getLogger(__name__)

PAGE_SIZE = 20

async def get_accounts_by_filter(filter_name: str, page: int = 1) -> tuple[list[Account], int]:
    """Retrieves paginated accounts according to the specified filter."""
    offset = (page - 1) * PAGE_SIZE
    
    async with async_session_maker() as session:
        # Base query excluding soft-deleted accounts
        base_query = select(Account).where(Account.deleted_at.is_(None))
        count_query = select(func.count(Account.id)).where(Account.deleted_at.is_(None))
        
        # Apply filter clauses
        if filter_name == "newest":
            stmt = base_query.order_by(Account.created_at.desc())
        elif filter_name == "oldest":
            stmt = base_query.order_by(Account.created_at.asc())
        elif filter_name == "available":
            stmt = base_query.where(Account.status == "Available").order_by(Account.created_at.desc())
            count_query = count_query.where(Account.status == "Available")
        elif filter_name == "used":
            stmt = base_query.where(Account.status == "Used").order_by(Account.created_at.desc())
            count_query = count_query.where(Account.status == "Used")
        elif filter_name == "favorites":
            stmt = base_query.where(Account.favorite == True).order_by(Account.created_at.desc())
            count_query = count_query.where(Account.favorite == True)
        elif filter_name == "pinned":
            stmt = base_query.where(Account.pinned == True).order_by(Account.created_at.desc())
            count_query = count_query.where(Account.pinned == True)
        else:
            stmt = base_query.order_by(Account.created_at.desc())
            
        # Execute total count query
        count_result = await session.execute(count_query)
        total_records = count_result.scalar()
        
        # Execute paginated query
        stmt = stmt.offset(offset).limit(PAGE_SIZE)
        accounts_result = await session.execute(stmt)
        accounts = list(accounts_result.scalars().all())
        
        # Calculate total pages
        total_pages = max(1, (total_records + PAGE_SIZE - 1) // PAGE_SIZE)
        
        return accounts, total_pages

async def display_single_account(query, account: Account, filter_name: str, page: int):
    """Formats and displays a single account details screen with a back option."""
    try:
        decrypted_pwd = decrypt_password(account.password_encrypted)
    except Exception:
        decrypted_pwd = "[Decryption Failed]"
        
    markers = ""
    if account.pinned:
        markers += " 📌"
    if account.favorite:
        markers += " ⭐"
        
    import html
    detail_html = (
        f"📂 <b>Account Details</b>\n\n"
        f"<b>ID:</b> #00{account.id:03d}{markers}\n"
        f"<b>Email:</b> <code>{html.escape(account.email)}</code>\n"
        f"<b>Password:</b> <code>{html.escape(decrypted_pwd)}</code>\n"
        f"<b>Status:</b> {html.escape(account.status)}\n"
        f"<b>Created:</b> {format_date(account.created_at)}\n"
        f"<b>Fetch Count:</b> {account.fetch_count}\n\n"
        f"<b>Notes (Plain Text):</b>\n"
        f"{html.escape(account.notes or 'None')}"
    )
    
    await query.edit_message_text(
        text=detail_html,
        reply_markup=get_account_view_back_keyboard(account.id, filter_name, page),
        parse_mode="HTML"
    )

@admin_only
async def accounts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered by the '📂 Accounts' main menu option or /accounts command."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    filter_name = "newest"
    accounts, total_pages = await get_accounts_by_filter(filter_name, page=1)
    
    markup = get_accounts_list_keyboard(accounts, filter_name, 1, total_pages)
    
    await update.message.reply_text(
        text=f"📂 <b>Accounts Vault (Filter: {filter_name.capitalize()})</b>\nSelect an account below:",
        reply_markup=markup,
        parse_mode="HTML"
    )

async def accounts_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes callback query interactions for the Accounts listing screen."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    from bot import config
    if user_id != config.ADMIN_ID:
        return
        
    data = query.data
    
    if data == "acc:noop":
        return
    elif data == "acc:close":
        await query.message.delete()
        return
        
    parts = data.split(":")
    action = parts[1]
    
    if action == "list":
        # acc:list:<filter>:<page>
        filter_name = parts[2]
        page = int(parts[3])
        
        accounts, total_pages = await get_accounts_by_filter(filter_name, page)
        markup = get_accounts_list_keyboard(accounts, filter_name, page, total_pages)
        
        await query.edit_message_text(
            text=f"📂 <b>Accounts Vault (Filter: {filter_name.capitalize()})</b>\nSelect an account below:",
            reply_markup=markup,
            parse_mode="HTML"
        )
        
    elif action == "view":
        # acc:view:<id>:<filter>:<page>
        account_id = int(parts[2])
        filter_name = parts[3]
        page = int(parts[4])
        
        async with async_session_maker() as session:
            account = await session.get(Account, account_id)
            if not account or account.deleted_at is not None:
                await query.edit_message_text("❌ Account no longer exists.")
                return
                
            await display_single_account(query, account, filter_name, page)
            
    elif action == "delete":
        # acc:delete:<id>:<filter>:<page>
        account_id = int(parts[2])
        filter_name = parts[3]
        page = int(parts[4])
        
        async with async_session_maker() as session:
            account = await session.get(Account, account_id)
            if not account:
                await query.edit_message_text("❌ Account no longer exists.")
                return
                
            sett_res = await session.execute(select(Settings).where(Settings.id == 1))
            settings = sett_res.scalar_one()
            
            # Format return callback
            ret_cb = f"acc_{filter_name}_{page}"
            
            if settings.confirm_delete:
                import html
                await query.edit_message_text(
                    text=f"❓ Are you sure you want to delete account #00{account.id:03d} (<code>{html.escape(account.email)}</code>)?",
                    reply_markup=get_delete_confirmation_keyboard(account.id, ret_cb),
                    parse_mode="HTML"
                )
            else:
                account.deleted_at = datetime.utcnow()
                account.updated_at = datetime.utcnow()
                await session.commit()
                await query.edit_message_text("🗑 Account moved to Trash.")
                
    elif action == "edit_notes":
        # acc:edit_notes:<id>:<filter>:<page>
        account_id = int(parts[2])
        filter_name = parts[3]
        page = int(parts[4])
        
        context.user_data["awaiting_notes_edit"] = {
            "account_id": account_id,
            "source": f"acc_{filter_name}_{page}",
            "message_id": query.message.message_id
        }
        await query.message.reply_text(
            "📝 Please reply to this message with the new notes (Markdown is disabled):"
        )
