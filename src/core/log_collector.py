"""High-performance live log collector with unique IDs and lazy payload formatting."""
import time
import json
from collections import deque
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from src.core.events import event_bus
from src.core.constants import EventType


@dataclass
class LogEntry:
    """Represents a structured live log record with unique ID and lazy payload serialization."""
    id: int
    timestamp: float
    time_str: str
    category: str  # "API", "LongPoll", "Media", "System"
    message: str
    level: str = "INFO"  # "INFO", "WARN", "ERROR"
    raw_data: Any = None
    preview_text: str = ""
    _cached_json: Optional[str] = None

    def get_formatted_payload(self) -> str:
        """Lazily serializes payload to formatted JSON only when requested."""
        if self._cached_json is None:
            if self.raw_data is None:
                self._cached_json = ""
            elif isinstance(self.raw_data, str):
                self._cached_json = self.raw_data
            else:
                try:
                    self._cached_json = json.dumps(self.raw_data, ensure_ascii=False, indent=2)
                except Exception:
                    self._cached_json = str(self.raw_data)
        return self._cached_json


class LogCollector:
    """Thread-safe circular in-memory buffer with unique IDs and lazy JSON formatting."""

    def __init__(self, max_entries: int = 150):
        self.max_entries = max_entries
        self._entries: deque = deque(maxlen=max_entries)
        self._counter: int = 0

    def log(
        self,
        category: str,
        message: str,
        level: str = "INFO",
        raw_data: Any = None,
        preview_text: str = ""
    ):
        """Records a log entry with a unique monotonic ID and broadcasts it."""
        now = time.time()
        time_str = time.strftime("%H:%M:%S", time.localtime(now)) + f".{int((now % 1) * 1000):03d}"
        self._counter += 1
        
        entry = LogEntry(
            id=self._counter,
            timestamp=now,
            time_str=time_str,
            category=category,
            message=message,
            level=level,
            raw_data=raw_data,
            preview_text=preview_text
        )
        self._entries.append(entry)

        # Broadcast event with unique log_id
        event_bus.emit(
            EventType.LOG_ENTRY,
            log_id=entry.id,
            time_str=time_str,
            category=category,
            message=message,
            level=level,
            preview_text=preview_text
        )

    def log_api(
        self,
        method: str,
        status: int = 200,
        duration_ms: float = 0.0,
        error: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        response_data: Optional[Any] = None
    ):
        """Helper for API call logging with lazy payload inspection."""
        lvl = "ERROR" if error or status >= 400 else "INFO"
        msg = f"{method} [{status}] ({duration_ms:.1f}ms)"
        if error:
            msg += f" - {error}"

        payload_dict = {}
        if params:
            safe_p = dict(params)
            if "access_token" in safe_p:
                safe_p["access_token"] = safe_p["access_token"][:8] + "..."
            payload_dict["params"] = safe_p

        if response_data is not None:
            payload_dict["response"] = response_data
        elif error:
            payload_dict["error"] = error

        # Fast preview generation
        preview = ""
        if isinstance(response_data, dict):
            if "items" in response_data and response_data["items"]:
                first_item = response_data["items"][0]
                if isinstance(first_item, dict):
                    preview = str(first_item.get("last_message", {}).get("text", "")) or str(first_item.get("text", ""))
            elif "first_name" in response_data:
                preview = f"{response_data.get('first_name')} {response_data.get('last_name')}"
        elif isinstance(response_data, list) and response_data:
            first_elem = response_data[0]
            if isinstance(first_elem, dict):
                preview = f"{first_elem.get('first_name', '')} {first_elem.get('last_name', '')}".strip()

        if not preview and params:
            keys = list(params.keys())
            preview = f"params: {', '.join(keys[:3])}"

        self.log("API", msg, level=lvl, raw_data=payload_dict, preview_text=preview[:90])

    def log_longpoll(self, event_type: str, details: str = "", raw_data: Optional[Any] = None):
        """Helper for LongPoll event logging."""
        msg = f"Event: {event_type}"
        if details:
            msg += f" - {details}"
        self.log("LongPoll", msg, raw_data=raw_data or details, preview_text=details)

    def log_media(self, action: str, url: str, is_hit: bool = False):
        """Helper for Media caching logging."""
        status = "HIT" if is_hit else "DOWNLOAD"
        short_url = url.split("?")[0][-35:] if url else ""
        msg = f"[{status}] {action}: ...{short_url}"
        self.log("Media", msg, raw_data=url, preview_text=url)

    def get_entries(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns entries formatted for RecycleView display with persistent unique IDs."""
        res = []
        for e in self._entries:
            if category and category != "Все" and e.category != category:
                continue
            res.append({
                "log_id": e.id,
                "time_str": e.time_str,
                "category": e.category,
                "message": e.message,
                "level": e.level,
                "preview_text": e.preview_text,
                "raw_payload": "",
                "is_expanded": False,
                "row_size": [None, 68]
            })
        return res

    def get_entry_payload_by_id(self, log_id: int) -> str:
        """Returns lazily formatted JSON payload for an entry by its unique ID."""
        for e in self._entries:
            if e.id == log_id:
                return e.get_formatted_payload()
        return ""

    def clear(self):
        """Clears stored logs."""
        self._entries.clear()


log_collector = LogCollector()
