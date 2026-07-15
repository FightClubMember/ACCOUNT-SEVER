import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from bot.database import async_session_maker
from bot.models import Account, Settings
from bot.encryption import decrypt_password
from bot.utils.decorators import admin_only
from bot.utils.formatters import format_date
from bot.keyboards.inline_keyboards import (
    get_trash_list_keyboard,
    get_trash_item_keyboard,
    get_delete_confirmation_keyboard,
    get_empty_trash_confirmation_keyboard
)
from sqlalchemy import select, func, and_, delete

logger = logging.getLogger(__name__)

TRASH_PAGE_SIZE = 20

async def get_trashed_accounts(page: int = 1) -> tuple[list[Account], int]:
    """Retrieves paginated soft-deleted accounts in trash."""
    offset = (page - 1) * TRASH_PAGE_SIZE
    
    async with async_session_maker() as session:
        # Base query for soft-deleted accounts
        base_query = select(Account).where(Account.deleted_at.is_not(None))
        count_query = select(func.count(Account.id)).where(Account.deleted_at.is_not(None))
        
        # Execute total count
        count_result = await session.execute(count_query)
        total_records = count_result.scalar() or 0
        
        # Execute paginated query (newest deleted first)
        stmt = base_query.order_by(Account.deleted_at.desc()).offset(offset).limit(TRASH_PAGE_SIZE)
        accounts_result = await session.execute(stmt)
        accounts = list(accounts_result.scalars().all())
        
        total_pages = max(1, (total_records + TRASH_PAGE_SIZE - 1) // TRASH_PAGE_SIZE)
        return accounts, total_pages

@admin_only
async def trash_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered by the '🗑 Trash' main menu option or /trash command."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    accounts, total_pages = await get_trashed_accounts(page=1)
    
    if not accounts:
        await update.message.reply_text("🗑 Trash is empty.")
        return
        
    await update.message.reply_text(
        text="🗑 <b>Trash Bin (Soft Deleted Accounts)</b>\nStored for 30 days before permanent automatic deletion:",
        reply_markup=get_trash_list_keyboard(accounts, 1, total_pages),
        parse_mode="HTML"
    )

async def trash_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes callback query interactions for the Trash bin."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    from bot import config
    if user_id != config.ADMIN_ID:
        return
        
    data = query.data
    
    if data == "trash:noop":
        return
    elif data == "trash:close":
        await query.message.delete()
        return
        
    parts = data.split(":")
    action = parts[1]
    
    if action == "list":
        page = int(parts[2])
        accounts, total_pages = await get_trashed_accounts(page)
        
        if not accounts:
            await query.edit_message_text("🗑 Trash is empty.")
            return
            
        await query.edit_message_text(
            text="🗑 <b>Trash Bin (Soft Deleted Accounts)</b>\nStored for 30 days before permanent automatic deletion:",
            reply_markup=get_trash_list_keyboard(accounts, page, total_pages),
            parse_mode="HTML"
        )
        
    elif action == "view":
        # trash:view:<id>:<page>
        account_id = int(parts[2])
        page = int(parts[3])
        
        async with async_session_maker() as session:
            account = await session.get(Account, account_id)
            if not account or account.deleted_at is None:
                await query.edit_message_text("❌ Account no longer in trash.")
                return
                
            try:
                decrypted_pwd = decrypt_password(account.password_encrypted)
            except Exception:
                decrypted_pwd = "[Decryption Failed]"
                
            import html
            detail_html = (
                f"🗑 <b>Trashed Account Details</b>\n\n"
                f"<b>ID:</b> #00{account.id:03d}\n"
                f"<b>Email:</b> <code>{html.escape(account.email)}</code>\n"
                f"<b>Password:</b> <code>{html.escape(decrypted_pwd)}</code>\n"
                f"<b>Deleted At:</b> {format_date(account.deleted_at)}\n"
                f"<b>Notes (Plain Text):</b>\n"
                f"{html.escape(account.notes or 'None')}"
            )
            
            await query.edit_message_text(
                text=detail_html,
                reply_markup=get_trash_item_keyboard(account.id, page),
                parse_mode="HTML"
            )
            
    elif action == "restore":
        # trash:restore:<id>:<page>
        account_id = int(parts[2])
        page = int(parts[3])
        
        async with async_session_maker() as session:
            account = await session.get(Account, account_id)
            if account:
                account.deleted_at = None
                account.status = "Available" # Reset to Available on restore
                account.updated_at = datetime.utcnow()
                await session.commit()
                logger.info(f"Account ID #{account_id} restored from trash.")
                
        # Return to list
        accounts, total_pages = await get_trashed_accounts(page)
        if not accounts:
            await query.edit_message_text("🗑 Trash is empty.")
            return
            
        await query.edit_message_text(
            text="🗑 <b>Trash Bin (Soft Deleted Accounts)</b>\nStored for 30 days before permanent automatic deletion:",
            reply_markup=get_trash_list_keyboard(accounts, page, total_pages),
            parse_mode="HTML"
        )
        
    elif action == "perm_delete":
        # trash:perm_delete:<id>:<page>
        account_id = int(parts[2])
        page = int(parts[3])
        
        async with async_session_maker() as session:
            sett_res = await session.execute(select(Settings).where(Settings.id == 1))
            settings = sett_res.scalar_one()
            
            if settings.confirm_delete:
                account = await session.get(Account, account_id)
                import html
                await query.edit_message_text(
                    text=f"⚠️ <b>PERMANENT DELETE WARNING</b>\n\nAre you sure you want to permanently erase #00{account.id:03d} (<code>{html.escape(account.email)}</code>)? This cannot be undone!",
                    reply_markup=get_delete_confirmation_keyboard(account.id, f"trash_perm_{page}"),
                    parse_mode="HTML"
                )
            else:
                # Direct delete
                await session.execute(delete(Account).where(Account.id == account_id))
                await session.commit()
                logger.info(f"Account ID #{account_id} permanently deleted.")
                
                # Return to list
                accounts, total_pages = await get_trashed_accounts(page)
                if not accounts:
                    await query.edit_message_text("🗑 Trash is empty.")
                    return
                    
                await query.edit_message_text(
                    text="🗑 <b>Trash Bin (Soft Deleted Accounts)</b>\nStored for 30 days before permanent automatic deletion:",
                    reply_markup=get_trash_list_keyboard(accounts, page, total_pages),
                    parse_mode="HTML"
                )
                
    elif action == "empty":
        # Prompt confirmation
        await query.edit_message_text(
            text="⚠️ <b>EMPTY TRASH WARNING</b>\n\nAre you sure you want to permanently delete ALL accounts currently in the trash bin? This action is IRREVERSIBLE!",
            reply_markup=get_empty_trash_confirmation_keyboard(),
            parse_mode="HTML"
        )

async def confirm_perm_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles deletion confirmation for permanent soft-deleted accounts."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    from bot import config
    if user_id != config.ADMIN_ID:
        return
        
    parts = query.data.split(":")
    choice = parts[1]
    account_id = int(parts[2])
    # Format: trash_perm_<page>
    page = int(parts[3].split("_")[-1])
    
    async with async_session_maker() as session:
        if choice == "yes":
            await session.execute(delete(Account).where(Account.id == account_id))
            await session.commit()
            logger.info(f"Account ID #{account_id} permanently deleted.")
            
    # Return to list
    accounts, total_pages = await get_trashed_accounts(page)
    if not accounts:
        await query.edit_message_text("🗑 Trash is empty.")
        return
        
    await query.edit_message_text(
        text="🗑 <b>Trash Bin (Soft Deleted Accounts)</b>\nStored for 30 days before permanent automatic deletion:",
        reply_markup=get_trash_list_keyboard(accounts, page, total_pages),
        parse_mode="HTML"
    )

async def confirm_empty_trash_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes final confirmation to empty the Trash bin."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    from bot import config
    if user_id != config.ADMIN_ID:
        return
        
    choice = query.data.split(":")[1]
    
    if choice == "yes":
        async with async_session_maker() as session:
            # Delete all soft deleted accounts
            await session.execute(delete(Account).where(Account.deleted_at.is_not(None)))
            await session.commit()
            logger.info("Trash bin emptied.")
        await query.edit_message_text("🗑 Trash bin emptied successfully.")
    else:
        # Return to list
        accounts, total_pages = await get_trashed_accounts(page=1)
        if not accounts:
            await query.edit_message_text("🗑 Trash is empty.")
            return
            
        await query.edit_message_text(
            text="🗑 <b>Trash Bin (Soft Deleted Accounts)</b>\nStored for 30 days before permanent automatic deletion:",
            reply_markup=get_trash_list_keyboard(accounts, 1, total_pages),
            parse_mode="HTML"
        )

async def cleanup_old_trash_job(context: ContextTypes.DEFAULT_TYPE = None):
    """
    Background job to delete records from the trash bin that are older than 30 days.
    """
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    try:
        async with async_session_maker() as session:
            stmt = delete(Account).where(
                and_(
                    Account.deleted_at.is_not(None),
                    Account.deleted_at < cutoff_date
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            deleted_count = result.rowcount
            if deleted_count > 0:
                logger.info(f"Auto-trash cleanup job: Purged {deleted_count} records older than 30 days.")
    except Exception as e:
        logger.error(f"Failed to execute auto-trash cleanup job: {e}")
