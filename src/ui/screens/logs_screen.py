"""Screen for viewing real-time API, LongPoll and Media logs with exact row index synchronization."""
from typing import Optional
from kivy.metrics import dp
from kivy.properties import StringProperty, ListProperty, BooleanProperty, NumericProperty
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivymd.uix.screen import MDScreen
from kivy.uix.boxlayout import BoxLayout
from src.core.log_collector import log_collector
from src.core.events import event_bus
from src.core.constants import EventType, ScreenName


class LogRowItem(RecycleDataViewBehavior, BoxLayout):
    """Single expandable log entry row in RecycleView with exact position tracking."""
    index = None
    log_id = NumericProperty(0)
    time_str = StringProperty("")
    category = StringProperty("")
    message = StringProperty("")
    level = StringProperty("INFO")
    raw_payload = StringProperty("")
    preview_text = StringProperty("")
    is_expanded = BooleanProperty(False)
    row_size = ListProperty([None, dp(68)])

    def refresh_view_attrs(self, rv, index, data):
        """Called by RecycleView when widget is bound to data at index."""
        self.index = index
        return super().refresh_view_attrs(rv, index, data)

    def toggle_expand(self):
        """Toggles expansion state for this exact row in RecycleView data."""
        if self.index is None:
            return
        parent_screen = self.parent
        while parent_screen and not hasattr(parent_screen, "toggle_entry_expand"):
            parent_screen = parent_screen.parent
        if parent_screen and hasattr(parent_screen, "toggle_entry_expand"):
            parent_screen.toggle_entry_expand(self.index)


class LogsScreen(MDScreen):
    """View displaying live console of system events (>/. section) with DockBar and accurate row expander."""
    active_category = StringProperty("Все")
    logs = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = ScreenName.LOGS
        event_bus.subscribe(EventType.LOG_ENTRY, self._on_log_entry)

    def on_enter(self, *args):
        """Pauses LongPoll service while inspecting logs and loads filtered items."""
        if hasattr(self.ids, "dockbar"):
            self.ids.dockbar.sync_with_screen()
        from kivymd.app import MDApp
        from src.utils.async_tools import run_async
        app = MDApp.get_running_app()
        if app and hasattr(app, "longpoll_service"):
            run_async(app.longpoll_service.stop())

        self._refresh_logs()

    def on_leave(self, *args):
        """Resumes LongPoll service upon leaving logs screen."""
        from kivymd.app import MDApp
        from src.utils.async_tools import run_async
        app = MDApp.get_running_app()
        if app and hasattr(app, "longpoll_service") and getattr(app, "screen_manager", None):
            if app.screen_manager.current != ScreenName.AUTH:
                run_async(app.longpoll_service.start())

    def toggle_entry_expand(self, rv_index: int):
        """Toggles expansion of full payload for a row using its exact RecycleView index."""
        if 0 <= rv_index < len(self.logs):
            logs_copy = [dict(item) for item in self.logs]
            item = logs_copy[rv_index]
            new_state = not item.get("is_expanded", False)
            item["is_expanded"] = new_state
            
            if new_state:
                log_id = item.get("log_id", 0)
                payload = log_collector.get_entry_payload_by_id(log_id)
                item["raw_payload"] = payload or item.get("preview_text", "")
                item["row_size"] = [None, dp(270)]
            else:
                item["row_size"] = [None, dp(68)]
                
            self.logs = logs_copy

    def filter_category(self, category: str):
        """Switches active log filter instantly."""
        self.active_category = category
        self._refresh_logs()

    def clear_logs(self):
        """Clears all collected logs."""
        log_collector.clear()
        self.logs = []

    def _refresh_logs(self):
        """Fetches lightweight filtered log items from log_collector."""
        self.logs = log_collector.get_entries(category=self.active_category)

    def _on_log_entry(
        self,
        time_str: str,
        category: str,
        message: str,
        level: str,
        preview_text: str = "",
        log_id: int = 0,
        **kwargs
    ):
        """Handles incoming real-time log record efficiently."""
        if self.active_category in ("Все", category):
            new_item = {
                "log_id": log_id,
                "time_str": time_str,
                "category": category,
                "message": message,
                "level": level,
                "preview_text": preview_text,
                "raw_payload": "",
                "is_expanded": False,
                "row_size": [None, dp(68)]
            }
            self.logs = list(self.logs) + [new_item]
