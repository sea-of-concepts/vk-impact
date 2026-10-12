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


def _measure_text_height(text: str, font_size_sp: int = 15, is_outgoing: bool = False) -> int:
    """Measures exact rendered text height in dp matching Kivy Label word-wrapping."""
    if not text:
        return 0
    clean_text = clean_message_text(text)
    try:
        from kivy.core.text import Label as CoreLabel
        from kivy.core.window import Window
        from kivy.metrics import dp, sp

        win_w = Window.width if (Window and getattr(Window, "width", 0) > 0) else dp(380)
        win_w_dp = min(dp(390), win_w)
        bubble_text_w = max(dp(160), (win_w_dp - dp(16)) * 0.78 - dp(28))
        core = CoreLabel(text=clean_text, font_size=sp(font_size_sp), text_size=(bubble_text_w, None))
        core.refresh()
        if core.texture and core.texture.size[1] > 0:
            return int(core.texture.size[1] / dp(1))
    except Exception:
        pass

    # Thread-safe accurate fallback matching Kivy Label's 15sp line height (18dp)
    limit = 32 if is_outgoing else 28
    total_lines = 0
    for para in clean_text.split("\n"):
        if not para:
            total_lines += 1
            continue
        cur = 0
        pl = 1
        for w in para.split(" "):
            wl = len(w)
            if cur == 0:
                cur = wl
            elif cur + 1 + wl <= limit:
                cur += 1 + wl
            else:
                pl += 1
                cur = wl
        total_lines += pl
    line_h = 18 if font_size_sp >= 15 else 16
    return total_lines * line_h


def get_text_width_dp(text: str, font_size_sp: int = 15) -> float:
    """Measures exact width of a single-line string in dp using Kivy CoreLabel."""
    if not text:
        return 0.0
    try:
        from kivy.core.text import Label as CoreLabel
        from kivy.metrics import sp, dp
        c = CoreLabel(text=text, font_size=sp(font_size_sp))
        c.refresh()
        if c.texture and c.texture.size[0] > 0:
            return c.texture.size[0] / dp(1)
    except Exception:
        pass
    return len(text) * 8.5


def check_time_needs_own_line(text: str, is_outgoing: bool = False, max_w_dp: Optional[float] = None) -> bool:
    """
    Returns True if the last line of text is too wide to fit the timestamp inline,
    requiring a separate row below the text.
    """
    if not text:
        return False
    clean_text = clean_message_text(text)
    time_space_dp = 58.0 if is_outgoing else 44.0
    lines = clean_text.split("\n")
    last_paragraph = lines[-1].strip()
    if not last_paragraph:
        return False

    if max_w_dp is None:
        try:
            from kivy.core.window import Window
            from kivy.metrics import dp
            win_w = Window.width / dp(1) if (Window and getattr(Window, "width", 0) > 0) else 380
        except Exception:
            win_w = 380
        avatar_space = 38 if not is_outgoing else 0
        max_w_dp = (win_w - 16 - avatar_space) * 0.78 - 24

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
        # Thread-safe character-based fallback with word boundary tracking
        limit = 32 if is_outgoing else 28
        time_chars = 8 if is_outgoing else 6
        cur = 0
        for w in words:
            wl = len(w)
            if cur == 0:
                cur = wl
            elif cur + 1 + wl <= limit:
                cur += 1 + wl
            else:
                cur = wl
        return (cur + time_chars) > limit


def format_fallback_attachment_text(attachments: list) -> str:
    """Returns readable fallback badge text for non-photo attachments if message text is empty."""
    if not attachments or not isinstance(attachments, list):
        return ""
    labels = []
    for att in attachments:
        if not isinstance(att, dict):
            continue
        t = att.get("type", "")
        if t == "sticker":
            labels.append("[Стикер]")
        elif t in ("audio_message", "audiomsg"):
            labels.append("[Голосовое сообщение]")
        elif t == "audio":
            labels.append("[Аудиозапись]")
        elif t == "doc":
            doc_title = att.get("doc", {}).get("title", "")
            labels.append(f"[Документ: {doc_title}]" if doc_title else "[Документ]")
        elif t == "video":
            labels.append("[Видеозапись]")
        elif t == "wall":
            labels.append("[Запись на стене]")
        elif t == "link":
            labels.append("[Ссылка]")
        elif t != "photo":
            labels.append("[Вложение]")
    return " ".join(labels)


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
        h = container_width / ar if ar > 0 else 180
        return int(max(130, min(260, h)))
    elif n == 2:
        return 170
    elif n == 3:
        return 140 + 105 + 2  # 247
    elif n == 4:
        return 115 + 115 + 2  # 232
    elif n == 5:
        return 115 + 90 + 2   # 207
    elif n == 6:
        return 100 + 100 + 2  # 202
    elif n == 7:
        return 100 + 85 + 2   # 187
    elif n == 8:
        return 90 + 90 + 2    # 182
    elif n == 9:
        return 85 + 85 + 85 + 4  # 259
    else:
        # 10 photos: 4 in top row, 6 in bottom row (Screenshot 4)
        return 115 + 85 + 2   # 202


def estimate_bubble_width(
    text: str = "",
    photos: Optional[list] = None,
    sender_name: str = "",
    has_reply: bool = False,
    has_fwd: bool = False,
    time_needs_own_line: bool = False,
    is_outgoing: bool = False,
    is_group_chat: bool = False
) -> int:
    """Calculates dynamic bubble width in dp so short messages shrink-wrap tightly."""
    try:
        from kivy.core.window import Window
        from kivy.metrics import dp
        win_w = Window.width / dp(1) if (Window and getattr(Window, "width", 0) > 0) else 380
    except Exception:
        win_w = 380

    avatar_space = 38 if (not is_outgoing and (is_group_chat or sender_name)) else 0
    avail_w = win_w - 16 - avatar_space
    max_bubble_w = max(160, int(avail_w * 0.78))

    clean_text = clean_message_text(text) if text else ""
    has_text = bool(clean_text.strip())
    has_photos = bool(photos)
    photo_count = len(photos) if photos else 0

    if has_photos and photo_count >= 2:
        return max_bubble_w

    if has_photos and photo_count == 1:
        ar = photos[0].get("aspect_ratio", 1.33) if photos else 1.33
        h = max(130, min(260, 240 / ar if ar > 0 else 180))
        single_p_w = int(h * ar)
        req_w = min(max_bubble_w, max(180, single_p_w + (4 if not has_text else 24)))
        if not has_text:
            return req_w
    else:
        req_w = 0

    if has_fwd or has_reply:
        return max_bubble_w

    padding_w = 24  # 12dp left + 12dp right
    sender_w = int(get_text_width_dp(sender_name, 12) + padding_w) if (sender_name and not is_outgoing) else 0

    if has_text:
        lines = clean_text.split("\n")
        time_space = 58 if is_outgoing else 44
        if len(lines) == 1:
            line_w = int(get_text_width_dp(lines[0], 15) + (time_space if not time_needs_own_line else 0))
            text_w = line_w + padding_w
        else:
            max_l = max(get_text_width_dp(l, 15) for l in lines)
            last_l = get_text_width_dp(lines[-1], 15)
            if not time_needs_own_line and (last_l + time_space + padding_w) <= max_bubble_w:
                text_w = int(max(max_l + padding_w, last_l + time_space + padding_w))
            else:
                text_w = max_bubble_w
    else:
        text_w = 75  # Standalone timestamp width

    needed = max(req_w, sender_w, text_w)
    return min(max_bubble_w, max(75, needed))


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
        base_padding = 10  # content_box vertical padding (6) + bubble_row padding (4)

    if has_sender_name:
        base_padding += 16  # Sender name header (14) + gap (2)

    if has_reply:
        base_padding += 38  # Reply preview box (36) + spacing (2)

    if has_photos:
        base_padding += estimate_photos_height(photos)
        if has_text:
            base_padding += 4  # Spacing between photos and text

    if has_text:
        if time_needs_own_line:
            base_padding += 13  # Extra line for timestamp only when text is too wide to share line
        text_height = _measure_text_height(clean_text, font_size_sp=15, is_outgoing=not has_sender_name)
    elif not has_photos:
        text_height = 14  # Standalone timestamp min height
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

