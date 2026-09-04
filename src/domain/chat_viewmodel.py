"""Chat screen ViewModel managing message history, sizes and real-time updates."""
from typing import List, Dict, Any, Optional
from kivy.properties import ListProperty, StringProperty, NumericProperty, BooleanProperty
from kivy.clock import Clock
from src.domain.base_viewmodel import BaseViewModel
from src.data.repositories.messages_repo import messages_repo
from src.data.repositories.users_repo import users_repo
from src.data.api.models import VKMessage
from src.core.events import event_bus
from src.core.constants import EventType
from src.utils.formatters import format_timestamp, estimate_message_height


class ChatViewModel(BaseViewModel):
    """Manages active chat message stream, pre-calculated heights and smooth updates."""

    peer_id = NumericProperty(0)
    chat_title = StringProperty("")
    avatar_url = StringProperty("")
    input_text = StringProperty("")
    messages = ListProperty([])
    is_peer_typing = BooleanProperty(False)
    is_channel = BooleanProperty(False)
    is_muted = BooleanProperty(False)
    notification_button_text = StringProperty("Включить уведомления")
    initial_unread_count = NumericProperty(0)
    unread_below_count = NumericProperty(0)
    highest_read_cmid = NumericProperty(0)
    top_offset = NumericProperty(0)
    bottom_offset = NumericProperty(0)
    has_more_older = BooleanProperty(True)
    has_more_newer = BooleanProperty(False)
    is_loading_history = BooleanProperty(False)

    @property
    def has_more_history(self) -> bool:
        return self.has_more_older

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._read_message_ids: set = set()
        event_bus.subscribe(EventType.NEW_MESSAGE, self._on_new_message)
        event_bus.subscribe(EventType.USER_TYPING, self._on_user_typing)

    def open_chat(self, peer_id: int, title: str, avatar_url: str = "", is_channel: bool = False, is_muted: bool = False, unread_count: int = 0):
        """Initializes chat state for a given peer."""
        self.peer_id = peer_id
        self.chat_title = title
        self.avatar_url = avatar_url
        self.is_channel = is_channel
        self.is_muted = is_muted
        self._read_message_ids = set()
        self.initial_unread_count = max(0, unread_count)
        self.unread_below_count = self.initial_unread_count
        self.highest_read_cmid = 0
        self.has_more_older = True
        self.is_loading_history = False
        self._update_notification_button_text()
        self.messages = []
        self.input_text = ""

        # Point 4: offset = unread_count - 10 if unread_count >= 10 else 0
        if unread_count >= 10:
            initial_offset = unread_count - 10
            self.bottom_offset = initial_offset
            self.top_offset = initial_offset + 40
            self.has_more_newer = True
        else:
            initial_offset = 0
            self.bottom_offset = 0
            self.top_offset = 40
            self.has_more_newer = False

        self.load_messages(initial_offset=initial_offset)

    def _update_notification_button_text(self):
        """Updates channel notification button text based on is_muted state."""
        if self.is_muted:
            self.notification_button_text = "Включить уведомления"
        else:
            self.notification_button_text = "Выключить уведомления"

    def toggle_channel_notifications(self):
        """Toggles notification mode between enabled and disabled for the active channel."""
        if not self.peer_id or not self.is_channel:
            return

        target_mode = "enabled" if self.is_muted else "disabled"

        async def _call():
            from src.data.api.client import api_client
            return await api_client.channels_set_notification_mode(channel_id=self.peer_id, mode=target_mode)

        def _on_success(res):
            self.is_muted = (target_mode == "disabled")
            self._update_notification_button_text()

            # Persist to SQLite
            async def _update_db():
                import aiosqlite
                from src.data.database.db_manager import db_manager
                try:
                    async with aiosqlite.connect(db_manager.db_path) as db:
                        await db.execute("UPDATE dialogs SET is_muted = ? WHERE peer_id = ?", (1 if self.is_muted else 0, self.peer_id))
                        await db.commit()
                except Exception:
                    pass
            self.run_task(_update_db(), show_loader=False)

            # Notify UI & DialogsScreen
            event_bus.emit(EventType.DIALOG_UPDATED, peer_id=self.peer_id, is_muted=self.is_muted)

        def _on_error(exc):
            from src.core.logger import logger
            logger.error("Failed to set channel notification mode for %s: %s", self.peer_id, exc)

        self.run_task(_call(), on_success=_on_success, on_error=_on_error, show_loader=False)

    def load_messages(self, initial_offset: int = 0):
        """Loads messages from VK API around initial_offset without mass-reading."""
        if not self.peer_id:
            return

        # Sync is_channel and is_muted from database if needed
        async def _sync_channel_info():
            import aiosqlite
            from src.data.database.db_manager import db_manager
            try:
                async with aiosqlite.connect(db_manager.db_path) as db:
                    async with db.execute("SELECT is_channel, is_muted FROM dialogs WHERE peer_id = ?", (self.peer_id,)) as cur:
                        row = await cur.fetchone()
                        if row:
                            return bool(row[0]), bool(row[1])
            except Exception:
                pass
            return None

        def _on_channel_info(res):
            if res is not None:
                self.is_channel, self.is_muted = res
                self._update_notification_button_text()

        self.run_task(_sync_channel_info(), on_success=_on_channel_info, show_loader=False)

        # 1. Fetch fresh messages from VK API around initial_offset
        async def _load_fresh():
            try:
                fresh = await messages_repo.fetch_messages(self.peer_id, offset=initial_offset, count=40)
                return fresh
            except Exception as e:
                from src.core.logger import logger
                logger.error("Failed to load fresh messages for %s: %s", self.peer_id, e)
                return []

        def _on_fresh(fresh_items: List[VKMessage]):
            if fresh_items:
                if len(fresh_items) < 40:
                    self.has_more_older = False
                self._update_messages_list(fresh_items)

        self.run_task(_load_fresh(), on_success=_on_fresh, show_loader=not bool(self.messages))

    def load_older_messages(self, on_data_ready=None):
        """Loads older messages when user scrolls up towards the top of chat history."""
        if not self.peer_id or self.is_loading_history or not self.has_more_older:
            if on_data_ready:
                on_data_ready([])
            return

        self.is_loading_history = True

        async def _fetch_older():
            try:
                return await messages_repo.fetch_messages(self.peer_id, offset=self.top_offset, count=40)
            except Exception as e:
                from src.core.logger import logger
                logger.error("Failed to load older messages for %s: %s", self.peer_id, e)
                return []

        def _on_success(older_items: List[VKMessage]):
            self.is_loading_history = False
            if not older_items:
                self.has_more_older = False
                if on_data_ready:
                    on_data_ready([])
                return

            if len(older_items) < 40:
                self.has_more_older = False

            self.top_offset += len(older_items)

            existing_ids = {m.get("message_id") for m in self.messages}
            new_older = [m for m in older_items if m.id not in existing_ids]

            if not new_older:
                if on_data_ready:
                    on_data_ready([])
                return

            rv_older = []
            for m in new_older:
                has_sender = bool(m.sender_name and not m.is_outgoing)
                height = estimate_message_height(m.text, has_sender_name=has_sender)
                rv_older.append({
                    "message_id": m.id,
                    "text": m.text,
                    "sender_name": m.sender_name if not m.is_outgoing else "",
                    "sender_avatar": m.sender_avatar if not m.is_outgoing else "",
                    "sender_impact_style": (users_repo._memory_cache.get(m.from_id, {}).get("impact_style", "") or ("zephyr" if m.from_id == 708902696 else "")) if not m.is_outgoing else "",
                    "time_text": format_timestamp(m.date),
                    "is_outgoing": m.is_outgoing,
                    "is_read": True,
                    "show_new_divider": False,
                    "msg_size": [None, height]
                })

            if on_data_ready:
                on_data_ready(rv_older)
            else:
                self.messages = rv_older + list(self.messages)

        def _on_error(exc):
            self.is_loading_history = False
            if on_data_ready:
                on_data_ready([])

        self.run_task(_fetch_older(), on_success=_on_success, on_error=_on_error, show_loader=False)

    def load_newer_messages(self, on_data_ready=None):
        """Loads newer messages when user scrolls down towards the bottom of chat history."""
        if not self.peer_id or self.is_loading_history or not self.has_more_newer:
            if on_data_ready:
                on_data_ready([])
            return

        self.is_loading_history = True
        fetch_count = min(40, self.bottom_offset)
        new_bottom = max(0, self.bottom_offset - fetch_count)

        async def _fetch_newer():
            try:
                return await messages_repo.fetch_messages(self.peer_id, offset=new_bottom, count=fetch_count)
            except Exception as e:
                from src.core.logger import logger
                logger.error("Failed to load newer messages for %s: %s", self.peer_id, e)
                return []

        def _on_success(newer_items: List[VKMessage]):
            self.is_loading_history = False
            self.bottom_offset = new_bottom
            if self.bottom_offset <= 0:
                self.has_more_newer = False

            if not newer_items:
                if on_data_ready:
                    on_data_ready([])
                return

            existing_ids = {m.get("message_id") for m in self.messages}
            new_newer = [m for m in newer_items if m.id not in existing_ids]

            if not new_newer:
                if on_data_ready:
                    on_data_ready([])
                return

            rv_newer = []
            for m in new_newer:
                has_sender = bool(m.sender_name and not m.is_outgoing)
                height = estimate_message_height(m.text, has_sender_name=has_sender)
                rv_newer.append({
                    "message_id": m.id,
                    "text": m.text,
                    "sender_name": m.sender_name if not m.is_outgoing else "",
                    "sender_avatar": m.sender_avatar if not m.is_outgoing else "",
                    "sender_impact_style": (users_repo._memory_cache.get(m.from_id, {}).get("impact_style", "") or ("zephyr" if m.from_id == 708902696 else "")) if not m.is_outgoing else "",
                    "time_text": format_timestamp(m.date),
                    "is_outgoing": m.is_outgoing,
                    "is_read": False,
                    "show_new_divider": False,
                    "msg_size": [None, height]
                })

            if on_data_ready:
                on_data_ready(rv_newer)
            else:
                self.messages = list(self.messages) + rv_newer

        def _on_error(exc):
            self.is_loading_history = False
            if on_data_ready:
                on_data_ready([])

        self.run_task(_fetch_newer(), on_success=_on_success, on_error=_on_error, show_loader=False)

    def jump_to_bottom(self, on_complete=None):
        """Loads latest messages (offset=0) and marks everything as read."""
        if not self.has_more_newer:
            self.bottom_offset = 0
            if self.messages:
                self.highest_read_cmid = max(self.highest_read_cmid, self.messages[-1].get("message_id", 0))
            self.unread_below_count = 0
            for m in self.messages:
                m["is_read"] = True
            self.messages = list(self.messages)
            self.sync_read_progress()
            if on_complete:
                on_complete()
            return

        async def _fetch_latest():
            return await messages_repo.fetch_messages(self.peer_id, offset=0, count=40)

        def _on_latest(items: List[VKMessage]):
            self.bottom_offset = 0
            self.has_more_newer = False
            self.unread_below_count = 0
            if items:
                self.highest_read_cmid = items[-1].id
                self._update_messages_list(items)
                for m in self.messages:
                    m["is_read"] = True
                self.messages = list(self.messages)
            self.sync_read_progress()
            if on_complete:
                on_complete()

        self.run_task(_fetch_latest(), on_success=_on_latest, show_loader=False)

    def sync_read_progress(self):
        """Sends markAsRead up to highest_read_cmid and updates remaining unread count."""
        if not self.peer_id:
            return
        self.run_task(
            messages_repo.update_read_progress(
                peer_id=self.peer_id,
                highest_cmid=self.highest_read_cmid,
                unread_remaining=self.unread_below_count,
                is_channel=self.is_channel
            ),
            show_loader=False
        )

    def send_message(self):
        """Sends the current input message."""
        text = self.input_text.strip()
        if not text or not self.peer_id:
            return

        # Clear input field immediately
        self.input_text = ""

        async def _send():
            return await messages_repo.send_message(self.peer_id, text)

        def _on_sent(msg_id: int):
            pass

        self.run_task(_send(), on_success=_on_sent, show_loader=False)

    def _update_messages_list(self, items: List[VKMessage]):
        """Formats message list with pre-calculated static heights in chronological order (oldest to newest)."""
        rv_data = []
        total = len(items)
        if self.initial_unread_count >= 10:
            first_unread_idx = 10
        elif self.initial_unread_count > 0:
            first_unread_idx = max(0, total - self.initial_unread_count)
        else:
            first_unread_idx = total

        for idx, m in enumerate(items):
            has_sender = bool(m.sender_name and not m.is_outgoing)
            is_first_unread = (idx == first_unread_idx and self.initial_unread_count > 0)
            is_unread = (idx >= first_unread_idx and not m.is_outgoing and self.initial_unread_count > 0 and m.id not in self._read_message_ids)
            
            base_height = estimate_message_height(m.text, has_sender_name=has_sender)
            total_height = base_height + (28 if is_first_unread else 0)

            rv_data.append({
                "message_id": m.id,
                "text": m.text,
                "sender_name": m.sender_name if not m.is_outgoing else "",
                "sender_avatar": m.sender_avatar if not m.is_outgoing else "",
                "sender_impact_style": (users_repo._memory_cache.get(m.from_id, {}).get("impact_style", "") or ("zephyr" if m.from_id == 708902696 else "")) if not m.is_outgoing else "",
                "time_text": format_timestamp(m.date),
                "is_outgoing": m.is_outgoing,
                "is_read": not is_unread,
                "show_new_divider": is_first_unread,
                "msg_size": [None, total_height]
            })
        self.messages = rv_data

    def _on_new_message(self, peer_id: int, message_id: int, text: str, timestamp: int, is_out: bool, **kwargs):
        """Handles incoming new message event in active chat with deduplication and thread safety."""
        if peer_id != self.peer_id:
            return

        # Avoid duplicate message insertion
        if message_id and any(m.get("message_id") == message_id for m in self.messages):
            return

        has_sender = bool(self.chat_title and not is_out)
        height = estimate_message_height(text, has_sender_name=has_sender)
        from_id = kwargs.get("from_id", 0)
        sender_style = (users_repo._memory_cache.get(from_id, {}).get("impact_style", "") or ("zephyr" if from_id == 708902696 else "")) if not is_out else ""

        new_item = {
            "message_id": message_id,
            "text": text,
            "sender_name": self.chat_title if not is_out else "",
            "sender_avatar": self.avatar_url if not is_out else "",
            "sender_impact_style": sender_style,
            "time_text": format_timestamp(timestamp),
            "is_outgoing": is_out,
            "is_read": is_out,
            "msg_size": [None, height]
        }
        self.messages = list(self.messages) + [new_item]
        
        if not is_out:
            self.run_task(messages_repo.mark_as_read(self.peer_id, start_message_id=message_id), show_loader=False)

    def _on_user_typing(self, user_id: int, **kwargs):
        """Shows typing indicator if peer matches."""
        if user_id == self.peer_id:
            self.is_peer_typing = True
            Clock.schedule_once(lambda dt: setattr(self, "is_peer_typing", False), 5)
