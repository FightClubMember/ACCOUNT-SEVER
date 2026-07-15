from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from bot.models import Account, Settings

def get_password_generation_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for password generation step in Add Account flow."""
    keyboard = [
        [
            InlineKeyboardButton("🔄 Generate Again", callback_data="pwd:regen"),
            InlineKeyboardButton("✅ Use Password", callback_data="pwd:use")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="pwd:cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_skip_notes_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for skipping notes step in Add Account flow."""
    keyboard = [[InlineKeyboardButton("Skip ⏭️", callback_data="add_notes:skip")]]
    return InlineKeyboardMarkup(keyboard)

def get_fetch_keyboard(account: Account) -> InlineKeyboardMarkup:
    """Keyboard for random account fetch view."""
    pin_text = "📌 Unpin" if account.pinned else "📌 Pin"
    fav_text = "⭐ Unfavorite" if account.favorite else "⭐ Favorite"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Mark Used", callback_data=f"fetch:used:{account.id}"),
            InlineKeyboardButton("🎲 Next", callback_data="fetch:next")
        ],
        [
            InlineKeyboardButton("✏ Edit Notes", callback_data=f"fetch:edit_notes:{account.id}"),
            InlineKeyboardButton(pin_text, callback_data=f"fetch:pin:{account.id}")
        ],
        [
            InlineKeyboardButton(fav_text, callback_data=f"fetch:favorite:{account.id}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"fetch:delete:{account.id}")
        ],
        [InlineKeyboardButton("❌ Close", callback_data="fetch:close")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_search_detail_keyboard(account: Account) -> InlineKeyboardMarkup:
    """Keyboard for displaying search results details."""
    pin_text = "📌 Unpin" if account.pinned else "📌 Pin"
    fav_text = "⭐ Unfavorite" if account.favorite else "⭐ Favorite"
    status_toggle_text = "Mark Available 🔓" if account.status == "Used" else "Mark Used ✅"
    next_status = "Available" if account.status == "Used" else "Used"
    
    keyboard = [
        [
            InlineKeyboardButton(status_toggle_text, callback_data=f"search:status:{account.id}:{next_status}"),
            InlineKeyboardButton("✏ Edit Notes", callback_data=f"search:edit_notes:{account.id}")
        ],
        [
            InlineKeyboardButton(pin_text, callback_data=f"search:pin:{account.id}"),
            InlineKeyboardButton(fav_text, callback_data=f"search:favorite:{account.id}")
        ],
        [
            InlineKeyboardButton("🗑 Delete", callback_data=f"search:delete:{account.id}"),
            InlineKeyboardButton("❌ Close", callback_data="search:close")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_settings_keyboard(settings: Settings) -> InlineKeyboardMarkup:
    """Generates settings configuration dashboard with toggles."""
    
    def get_status_emoji(val: bool) -> str:
        return "✅" if val else "❌"
        
    keyboard = [
        # Password lengths
        [
            InlineKeyboardButton(f"{'👉 ' if settings.password_length == length else ''}{length}", callback_data=f"settings:len:{length}")
            for length in [12, 16, 20, 24, 32]
        ],
        # Toggles
        [
            InlineKeyboardButton(f"{get_status_emoji(settings.use_uppercase)} Uppercase", callback_data="settings:toggle:use_uppercase"),
            InlineKeyboardButton(f"{get_status_emoji(settings.use_lowercase)} Lowercase", callback_data="settings:toggle:use_lowercase")
        ],
        [
            InlineKeyboardButton(f"{get_status_emoji(settings.use_numbers)} Numbers", callback_data="settings:toggle:use_numbers"),
            InlineKeyboardButton(f"{get_status_emoji(settings.use_symbols)} Symbols", callback_data="settings:toggle:use_symbols")
        ],
        [
            InlineKeyboardButton(f"{get_status_emoji(settings.auto_backup)} Auto Backup", callback_data="settings:toggle:auto_backup"),
            InlineKeyboardButton(f"{get_status_emoji(settings.duplicate_email_protection)} Dup Protection", callback_data="settings:toggle:duplicate_email_protection")
        ],
        [
            InlineKeyboardButton(f"{get_status_emoji(settings.confirm_delete)} Confirm Delete", callback_data="settings:toggle:confirm_delete")
        ],
        [InlineKeyboardButton("❌ Close Menu", callback_data="settings:close")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_accounts_list_keyboard(
    accounts: list[Account],
    current_filter: str,
    page: int,
    total_pages: int
) -> InlineKeyboardMarkup:
    """Generates paginated account list view."""
    keyboard = []
    
    # 1. Accounts list buttons
    for acc in accounts:
        # Show email + markers
        markers = ""
        if acc.pinned:
            markers += "📌"
        if acc.favorite:
            markers += "⭐"
        if acc.status == "Used":
            markers += "✔️"
            
        label = f"#{acc.id:04d}: {acc.email} {markers}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"acc:view:{acc.id}:{current_filter}:{page}")])
        
    # 2. Pagination controls row
    pagination_row = []
    if page > 1:
        pagination_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"acc:list:{current_filter}:{page - 1}"))
    else:
        pagination_row.append(InlineKeyboardButton("⏹️", callback_data="acc:noop"))
        
    pagination_row.append(InlineKeyboardButton(f"Page {page}/{total_pages}", callback_data="acc:noop"))
    
    if page < total_pages:
        pagination_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"acc:list:{current_filter}:{page + 1}"))
    else:
        pagination_row.append(InlineKeyboardButton("⏹️", callback_data="acc:noop"))
        
    keyboard.append(pagination_row)
    
    # 3. Filter tabs rows
    # Highlight the current active filter tab
    def get_filter_text(filter_name: str, display: str) -> str:
        return f"🔹 {display} 🔹" if current_filter == filter_name else display
        
    keyboard.append([
        InlineKeyboardButton(get_filter_text("newest", "Newest"), callback_data="acc:list:newest:1"),
        InlineKeyboardButton(get_filter_text("oldest", "Oldest"), callback_data="acc:list:oldest:1"),
        InlineKeyboardButton(get_filter_text("available", "Available"), callback_data="acc:list:available:1")
    ])
    keyboard.append([
        InlineKeyboardButton(get_filter_text("used", "Used"), callback_data="acc:list:used:1"),
        InlineKeyboardButton(get_filter_text("favorites", "Favorites"), callback_data="acc:list:favorites:1"),
        InlineKeyboardButton(get_filter_text("pinned", "Pinned"), callback_data="acc:list:pinned:1")
    ])
    
    keyboard.append([InlineKeyboardButton("❌ Close", callback_data="acc:close")])
    
    return InlineKeyboardMarkup(keyboard)

def get_account_view_back_keyboard(account_id: int, current_filter: str, page: int) -> InlineKeyboardMarkup:
    """Back button keyboard when viewing account detail from paginated list."""
    keyboard = [
        [
            InlineKeyboardButton("✏ Edit Notes", callback_data=f"acc:edit_notes:{account_id}:{current_filter}:{page}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"acc:delete:{account_id}:{current_filter}:{page}")
        ],
        [InlineKeyboardButton("⬅️ Back to List", callback_data=f"acc:list:{current_filter}:{page}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_trash_list_keyboard(
    accounts: list[Account],
    page: int,
    total_pages: int
) -> InlineKeyboardMarkup:
    """Keyboard for listing trashed (soft-deleted) accounts."""
    keyboard = []
    
    for acc in accounts:
        label = f"🗑 #{acc.id:04d}: {acc.email}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"trash:view:{acc.id}:{page}")])
        
    # Pagination
    pagination_row = []
    if page > 1:
        pagination_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"trash:list:{page - 1}"))
    else:
        pagination_row.append(InlineKeyboardButton("⏹️", callback_data="trash:noop"))
        
    pagination_row.append(InlineKeyboardButton(f"Page {page}/{total_pages}", callback_data="trash:noop"))
    
    if page < total_pages:
        pagination_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"trash:list:{page + 1}"))
    else:
        pagination_row.append(InlineKeyboardButton("⏹️", callback_data="trash:noop"))
        
    keyboard.append(pagination_row)
    
    # Empty Trash button and Close
    keyboard.append([InlineKeyboardButton("💥 Empty Trash", callback_data="trash:empty")])
    keyboard.append([InlineKeyboardButton("❌ Close", callback_data="trash:close")])
    
    return InlineKeyboardMarkup(keyboard)

def get_trash_item_keyboard(account_id: int, page: int) -> InlineKeyboardMarkup:
    """Keyboard for viewing detail of a single trashed account."""
    keyboard = [
        [
            InlineKeyboardButton("🔄 Restore", callback_data=f"trash:restore:{account_id}:{page}"),
            InlineKeyboardButton("❌ Delete Permanently", callback_data=f"trash:perm_delete:{account_id}:{page}")
        ],
        [InlineKeyboardButton("⬅️ Back to Trash", callback_data=f"trash:list:{page}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_delete_confirmation_keyboard(account_id: int, return_callback: str) -> InlineKeyboardMarkup:
    """Generic delete confirmation keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("⚠️ YES, DELETE", callback_data=f"confirm_del:yes:{account_id}:{return_callback}"),
            InlineKeyboardButton("❌ NO, CANCEL", callback_data=f"confirm_del:no:{account_id}:{return_callback}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_empty_trash_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Confirmation for emptying trash."""
    keyboard = [
        [
            InlineKeyboardButton("⚠️ YES, EMPTY TRASH", callback_data="confirm_empty_trash:yes"),
            InlineKeyboardButton("❌ NO, CANCEL", callback_data="confirm_empty_trash:no")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
