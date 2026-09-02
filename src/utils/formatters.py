"""Formatting helpers for UI presentation."""
from datetime import datetime, date, timedelta
from typing import Optional, Tuple


# Palette of pleasant Material Design avatar colors
AVATAR_COLORS = [
    (0.89, 0.31, 0.31, 1),  # Red
    (0.93, 0.46, 0.20, 1),  # Orange
    (0.96, 0.65, 0.14, 1),  # Amber
    (0.30, 0.69, 0.31, 1),  # Green
    (0.13, 0.59, 0.95, 1),  # Blue
    (0.24, 0.48, 0.95, 1),  # VK Blue
    (0.41, 0.35, 0.80, 1),  # Indigo
    (0.61, 0.35, 0.71, 1),  # Purple
    (0.91, 0.30, 0.50, 1),  # Pink
    (0.00, 0.59, 0.53, 1),  # Teal
]


def get_avatar_color(peer_id: int) -> Tuple[float, float, float, float]:
    """Returns deterministic background color for an avatar based on peer_id."""
    idx = abs(peer_id) % len(AVATAR_COLORS)
    return AVATAR_COLORS[idx]


def get_user_initials(name: str) -> str:
    """Returns 1-2 uppercase initials from a name (e.g. 'Павел Дуров' -> 'ПД')."""
    if not name:
        return "VK"
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()
    elif len(parts) == 1 and len(parts[0]) > 0:
        return parts[0][:2].upper()
    return "VK"


def format_timestamp(timestamp: int) -> str:
    """
    Formats a UNIX timestamp into user-friendly localized text:
    - Today: '14:32'
    - Yesterday: 'Вчера'
    - This year: '12 мая'
    - Previous years: '12.05.2023'
    """
    if not timestamp:
        return ""
        
    dt = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    today = now.date()
    msg_date = dt.date()
    
    if msg_date == today:
        return dt.strftime("%H:%M")
    elif msg_date == today - timedelta(days=1):
        return "Вчера"
    elif msg_date.year == today.year:
        months_ru = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
        return f"{dt.day} {months_ru[dt.month - 1]}"
    else:
        return dt.strftime("%d.%m.%Y")


def format_online_status(online: int, last_seen: Optional[dict] = None) -> str:
    """Formats user online status string."""
    if online == 1:
        return "В сети"
    if not last_seen or "time" not in last_seen:
        return "Был(а) в сети давно"
        
    dt = datetime.fromtimestamp(last_seen["time"])
    return f"Был(а) в сети {format_timestamp(last_seen['time'])}"


def truncate_text(text: str, max_length: int = 50) -> str:
    """Truncates text with ellipsis if exceeding max length."""
    if not text:
        return ""
    # Replace newlines with spaces for preview
    single_line = " ".join(text.split())
    if len(single_line) <= max_length:
        return single_line
    return single_line[:max_length - 3] + "..."


def estimate_message_height(text: str, has_sender_name: bool = False) -> int:
    """
    Accurately calculates message bubble height in dp to eliminate RecycleView layout dancing.
    """
    base_padding = 40  # Top/bottom padding + timestamp row
    if has_sender_name:
        base_padding += 20  # Sender name header

    if not text:
        return base_padding + 22

    # Estimate wrapped lines (average ~26 chars per line in 78% bubble width)
    lines = text.split("\n")
    total_lines = 0
    for line in lines:
        line_len = len(line)
        wrapped_count = max(1, (line_len + 25) // 26)
        total_lines += wrapped_count

    text_height = total_lines * 22
    total = base_padding + text_height
    return max(56, total)


def format_unread_count(count: int) -> str:
    """
    Formats unread messages count according to scale:
    - <= 0: ''
    - 1 - 999: '1' - '999'
    - 1,000 - 999,999: only thousands with 'к' (e.g. 1000 -> '1к', 15000 -> '15к')
    - 1,000,000+: only millions with 'м' (e.g. 1000000 -> '1м')
    """
    if count <= 0:
        return ""
    if count >= 1_000_000:
        return f"{count // 1_000_000}м"
    if count >= 1_000:
        return f"{count // 1_000}к"
    return str(count)

