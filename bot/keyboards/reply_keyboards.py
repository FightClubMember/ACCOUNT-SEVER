from telegram import ReplyKeyboardMarkup, KeyboardButton

def get_home_keyboard() -> ReplyKeyboardMarkup:
    """
    Returns the persistent main menu Reply Keyboard.
    Matches the exact layout of the Home Menu request:
    - Row 1: Add Account
    - Row 2: Fetch Account | Search
    - Row 3: Accounts | Stats
    - Row 4: Settings | Export
    - Row 5: Import | Trash
    """
    keyboard = [
        [KeyboardButton("➕ Add Account"), KeyboardButton("✍️ Custom Add")],
        [KeyboardButton("🎲 Fetch Account"), KeyboardButton("🔍 Search")],
        [KeyboardButton("📂 Accounts"), KeyboardButton("📊 Stats")],
        [KeyboardButton("⚙️ Settings"), KeyboardButton("📤 Export")],
        [KeyboardButton("📥 Import"), KeyboardButton("🗑 Trash")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)
