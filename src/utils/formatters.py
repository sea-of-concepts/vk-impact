"""Formatting helpers for UI presentation."""
from datetime import datetime, date, timedelta
from typing import Optional, Tuple, Any


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


def format_timestamp(timestamp: Any) -> str:
    """
    Formats a UNIX timestamp into user-friendly localized text:
    - Today: '14:32'
    - Yesterday: 'Вчера'
    - This year: '12 мая'
    - Previous years: '12.05.2023'
    """
    if not timestamp:
        return ""
    try:
        ts = int(timestamp)
        dt = datetime.fromtimestamp(ts)
    except Exception:
        return str(timestamp)

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


def format_fwd_timestamp(timestamp: Any) -> str:
    """
    Formats timestamp for forwarded messages:
    - Today: 'Сегодня в 14:32'
    - Yesterday: 'Вчера в 14:32'
    - Other: '12 мая в 14:32' (or '12.05.2023 в 14:32')
    """
    if not timestamp:
        return ""
    try:
        ts = int(timestamp)
        dt = datetime.fromtimestamp(ts)
    except Exception:
        return str(timestamp)

    now = datetime.now()
    today = now.date()
    msg_date = dt.date()
    time_part = dt.strftime("%H:%M")

    if msg_date == today:
        return f"Сегодня в {time_part}"
    elif msg_date == today - timedelta(days=1):
        return f"Вчера в {time_part}"
    elif msg_date.year == today.year:
        months_ru = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
        return f"{dt.day} {months_ru[dt.month - 1]} в {time_part}"
    else:
        return dt.strftime(f"%d.%m.%Y в {time_part}")



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


import html


def clean_message_text(text: str) -> str:
    """Unescapes HTML entities (&quot;, &amp;, &lt;, &gt;) and converts <br> tags to standard newlines."""
    if not text:
        return ""
    cleaned = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<BR>", "\n")
    return html.unescape(cleaned)


def _measure_text_height(text: str, font_size_sp: int = 15) -> int:
    """Measures exact rendered text height in dp using Kivy's CoreLabel engine targeting mobile bubble width."""
    if not text:
        return 0
    clean_text = clean_message_text(text)
    try:
        from kivy.core.text import Label as CoreLabel
        from kivy.core.window import Window
        from kivy.metrics import dp, sp

        win_w = Window.width if (Window and getattr(Window, "width", 0) > 0) else dp(380)
        win_w_dp = min(dp(390), win_w)
        # Mobile bubble inner text width: (window - outer_padding(16)) * 0.78 - content_box_padding(28)
        bubble_text_w = max(dp(160), (win_w_dp - dp(16)) * 0.78 - dp(28))
        core = CoreLabel(text=clean_text, font_size=sp(font_size_sp), text_size=(bubble_text_w, None))
        core.refresh()
        if core.texture and core.texture.size[1] > 0:
            return int(core.texture.size[1] / dp(1)) + 1
    except Exception:
        pass

    # Safe fallback estimate
    lines = clean_text.split("\n")
    total_lines = 0
    for line in lines:
        line_len = len(line)
        wrapped_count = max(1, (line_len + 27) // 28)
        total_lines += wrapped_count
    return total_lines * (font_size_sp + 5)


def check_time_needs_own_line(text: str, is_outgoing: bool = False, max_w_dp: float = 235.0) -> bool:
    """
    Returns True if the last line of text is too wide to fit the timestamp inline,
    requiring a separate row below the text.
    """
    if not text:
        return False
    clean_text = clean_message_text(text)
    time_space_dp = 54.0 if is_outgoing else 40.0
    lines = clean_text.split("\n")
    last_paragraph = lines[-1].strip()
    if not last_paragraph:
        return False

    words = last_paragraph.split(" ")
    cur_line_words = []
    wrapped_lines = []
    try:
        from kivy.core.text import Label as CoreLabel
        from kivy.metrics import dp, sp
        max_px = dp(max_w_dp)
        for w in words:
            if not w:
                continue
            test_line = " ".join(cur_line_words + [w]) if cur_line_words else w
            c = CoreLabel(text=test_line, font_size=sp(15))
            c.refresh()
            if c.texture and c.texture.size[0] > max_px:
                if cur_line_words:
                    wrapped_lines.append(" ".join(cur_line_words))
                    cur_line_words = [w]
                else:
                    wrapped_lines.append(w)
                    cur_line_words = []
            else:
                cur_line_words.append(w)
        if cur_line_words:
            wrapped_lines.append(" ".join(cur_line_words))

        last_line = wrapped_lines[-1] if wrapped_lines else ""
        c_last = CoreLabel(text=last_line, font_size=sp(15))
        c_last.refresh()
        last_w_dp = (c_last.texture.size[0] / dp(1)) if (c_last.texture and c_last.texture.size[0] > 0) else 0
        return (last_w_dp + time_space_dp) > max_w_dp
    except Exception:
        last_chars = len(last_paragraph) % 28
        if last_chars == 0 and len(last_paragraph) > 0:
            last_chars = 28
        return last_chars > 20


def extract_photo_attachments(attachments: list) -> list:
    """Extracts list of { 'url': str, 'width': int, 'height': int, 'aspect_ratio': float } from message attachments."""
    if not attachments or not isinstance(attachments, list):
        return []
    photos = []
    for att in attachments:
        if not isinstance(att, dict) or att.get("type") != "photo":
            continue
        p = att.get("photo")
        if not isinstance(p, dict):
            continue
        sizes = p.get("sizes", [])
        if not sizes:
            continue
        # Find optimal size for display (width between 360 and 1080)
        sorted_sizes = sorted(sizes, key=lambda s: s.get("width", 0))
        best = None
        for s in sorted_sizes:
            if s.get("width", 0) >= 360:
                best = s
                break
        if not best:
            best = sorted_sizes[-1]
        url = best.get("url", "")
        w = best.get("width", 0) or 600
        h = best.get("height", 0) or 400
        if url:
            aspect = max(0.4, min(2.5, (w / h) if h > 0 else 1.33))
            photos.append({
                "url": url,
                "width": w,
                "height": h,
                "aspect_ratio": aspect
            })
    return photos


def estimate_photos_height(photos: list, container_width: float = 240.0) -> int:
    """Estimates the render height in dp for a given list of photo attachments."""
    if not photos:
        return 0
    n = len(photos)
    if n == 1:
        ar = photos[0].get("aspect_ratio", 1.33)
        h = container_width / ar
        return int(max(120, min(260, h)))
    elif n == 2:
        return 140
    elif n == 3:
        return 215
    elif n == 4:
        return 200
    else:
        rows = (n + 2) // 3
        return int(rows * 85)


def estimate_message_height(
    text: str,
    has_sender_name: bool = False,
    has_reply: bool = False,
    fwd_count: int = 0,
    fwd_texts: list = None,
    time_needs_own_line: Optional[bool] = None,
    photos: Optional[list] = None
) -> int:
    """
    Accurately calculates message bubble height in dp to eliminate RecycleView layout dancing
    and ensure proper spacing between messages even on large text blocks.
    """
    clean_text = clean_message_text(text)
    has_text = bool(clean_text.strip())
    has_photos = bool(photos)

    if time_needs_own_line is None:
        time_needs_own_line = check_time_needs_own_line(clean_text, is_outgoing=not has_sender_name) if has_text else False

    # Minimal padding for photo-only bubble
    if has_photos and not has_text and not has_sender_name:
        base_padding = 8
    else:
        base_padding = 10  # content_box vertical padding (8) + bubble_row padding (2)

    if has_sender_name:
        base_padding += 17  # Sender name header (15) + spacing (2)

    if has_reply:
        base_padding += 38  # Reply preview box (36) + spacing (2)

    if has_photos:
        base_padding += estimate_photos_height(photos)
        if has_text:
            base_padding += 4  # Spacing between photos and text

    if has_text:
        if time_needs_own_line:
            base_padding += 13  # Extra line for timestamp only when text is too wide to share line
        text_height = _measure_text_height(clean_text, font_size_sp=15)
    else:
        text_height = 0

    fwd_extra = 0
    if fwd_count > 0:
        fwd_extra += fwd_count * 38
        if fwd_texts:
            for ft in fwd_texts:
                if ft:
                    fwd_extra += _measure_text_height(ft, font_size_sp=14)

    total = base_padding + text_height + fwd_extra
    return max(36, int(total))



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

