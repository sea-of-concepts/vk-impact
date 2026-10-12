"""About settings sub-screen with application version, metadata, and cache management."""
import os
import sqlite3
import threading
from kivymd.uix.screen import MDScreen
from kivy.properties import StringProperty, BooleanProperty
from kivy.clock import Clock
from src.core.config import config
from src.core.constants import ScreenName
from src.core.logger import logger


def get_message_cache_size_bytes() -> int:
    """Calculates total disk space used by message cache (SQLite messages + media)."""
    total = 0
    # 1. Media cache in CACHE_DIR
    try:
        cache_dir = config.CACHE_DIR
        if cache_dir.exists():
            for root, _, files in os.walk(cache_dir):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except Exception:
                        pass
    except Exception as e:
        logger.debug("Error calculating media cache size: %s", e)

    # 2. SQLite messages data across all databases in DATA_DIR
    try:
        data_dir = config.DATA_DIR
        if data_dir.exists():
            for db_f in os.listdir(data_dir):
                if db_f.endswith(".db"):
                    db_p = os.path.join(data_dir, db_f)
                    try:
                        with sqlite3.connect(db_p) as conn:
                            cur = conn.cursor()
                            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
                            if cur.fetchone():
                                cur.execute("SELECT COALESCE(SUM(LENGTH(COALESCE(text, '')) + LENGTH(COALESCE(attachments_json, '')) + LENGTH(COALESCE(fwd_json, '')) + LENGTH(COALESCE(reply_json, '')) + 128), 0) FROM messages")
                                row = cur.fetchone()
                                if row and row[0]:
                                    total += int(row[0])
                    except Exception:
                        pass
    except Exception as e:
        logger.debug("Error calculating DB message size: %s", e)

    return total


def format_cache_size(size_bytes: int) -> str:
    """Formats bytes into readable MB string."""
    mb = size_bytes / (1024 * 1024)
    if mb < 0.05 and size_bytes > 0:
        return f"{mb:.2f} МБ"
    return f"{mb:.1f} МБ"


def clear_message_cache_all() -> None:
    """Clears all cached messages from SQLite and disk media cache."""
    # 1. Clear SQLite messages in all .db files
    try:
        data_dir = config.DATA_DIR
        if data_dir.exists():
            for db_f in os.listdir(data_dir):
                if db_f.endswith(".db"):
                    db_p = os.path.join(data_dir, db_f)
                    try:
                        with sqlite3.connect(db_p) as conn:
                            cur = conn.cursor()
                            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
                            if cur.fetchone():
                                cur.execute("DELETE FROM messages")
                                conn.commit()
                                cur.execute("VACUUM")
                    except Exception as e:
                        logger.warning("Failed clearing messages in %s: %s", db_f, e)
    except Exception as e:
        logger.warning("Failed clearing messages DB: %s", e)

    # 2. Clear media cache files
    try:
        cache_dir = config.CACHE_DIR
        if cache_dir.exists():
            for root, dirs, files in os.walk(cache_dir):
                for f in files:
                    try:
                        os.remove(os.path.join(root, f))
                    except Exception:
                        pass
    except Exception as e:
        logger.warning("Failed clearing media cache: %s", e)

    # 3. Clear memory caches
    try:
        from src.data.cache.media_cache import media_cache
        media_cache._memory_cache.clear()
        media_cache._pending_downloads.clear()
    except Exception:
        pass


class AboutSettingsScreen(MDScreen):
    """View displaying application version, metadata, and cache management."""

    app_version = StringProperty(config.VERSION)
    app_name = StringProperty(config.APP_NAME)
    cache_size_str = StringProperty("0.0 МБ")
    is_clearing = BooleanProperty(False)
    clear_status_message = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = ScreenName.SETTINGS_ABOUT

    def on_enter(self, *args):
        """Refreshes cache size when entering the screen."""
        super().on_enter(*args)
        self.refresh_cache_size()

    def refresh_cache_size(self):
        """Asynchronously measures message cache size without UI blocking."""
        def _calc():
            sz = get_message_cache_size_bytes()
            formatted = format_cache_size(sz)
            def _apply(dt):
                self.cache_size_str = formatted
            Clock.schedule_once(_apply, 0)

        threading.Thread(target=_calc, daemon=True).start()

    def clear_message_cache(self):
        """Clears all cached messages and media files, then updates UI."""
        if self.is_clearing:
            return
        self.is_clearing = True
        self.clear_status_message = "Очистка..."

        def _do_clear():
            clear_message_cache_all()
            new_sz = get_message_cache_size_bytes()
            formatted = format_cache_size(new_sz)
            def _apply(dt):
                self.cache_size_str = formatted
                self.is_clearing = False
                self.clear_status_message = "Кэш сообщений успешно очищен"
            Clock.schedule_once(_apply, 0)

        threading.Thread(target=_do_clear, daemon=True).start()

    def on_back_pressed(self):
        """Navigates back to main settings menu."""
        if self.manager:
            self.manager.current = ScreenName.SETTINGS
