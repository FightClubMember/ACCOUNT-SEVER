import os
from datetime import datetime

def format_size(size_bytes: int) -> str:
    """Format bytes into a human-readable size (e.g., KB, MB)."""
    for unit in ['Bytes', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"

def format_date(dt: datetime) -> str:
    """Formats datetime object to standard display string."""
    if not dt:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def get_progress_bar(percentage: float, length: int = 10) -> str:
    """
    Creates a visual text-based progress bar.
    Example: 80% -> ████████░░ 80%
    """
    percentage = max(0.0, min(100.0, percentage))
    filled_count = int(round((percentage / 100.0) * length))
    empty_count = length - filled_count
    
    bar = "█" * filled_count + "░" * empty_count
    return f"{bar} {percentage:.1f}%"
