"""Chat screen ViewModel managing message history, sizes and real-time updates."""
from typing import List, Dict, Any, Optional
from kivy.properties import ListProperty, StringProperty, NumericProperty, BooleanProperty
from kivy.clock import Clock
from src.domain.base_viewmodel import BaseViewModel
from src.data.repositories.messages_repo import messages_repo
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        event_bus.subscribe(EventType.NEW_MESSAGE, self._on_new_message)
        event_bus.subscribe(EventType.USER_TYPING, self._on_user_typing)

    def open_chat(self, peer_id: int, title: str, avatar_url: str = ""):
        """Initializes chat state for a given peer."""
        self.peer_id = peer_id
        self.chat_title = title
        self.avatar_url = avatar_url
        self.messages = []
        self.input_text = ""
        self.load_messages()

    def load_messages(self):
        """Loads cached messages first, then fetches fresh messages from VK API."""
        if not self.peer_id:
            return

        # 1. Immediately display cached messages from local SQLite
        async def _load_cached():
            return await messages_repo.get_cached_messages(self.peer_id, limit=50)

        def _on_cached(cached_items: List[VKMessage]):
            if cached_items:
                self._update_messages_list(cached_items)

        self.run_task(_load_cached(), on_success=_on_cached, show_loader=not bool(self.messages))

        # 2. Fetch fresh messages from VK API in the background
        async def _load_fresh():
            try:
                fresh = await messages_repo.fetch_messages(self.peer_id, offset=0, count=40)
                await messages_repo.mark_as_read(self.peer_id)
                return fresh
            except Exception as e:
                return []

        def _on_fresh(fresh_items: List[VKMessage]):
            if fresh_items:
                self._update_messages_list(fresh_items)

        self.run_task(_load_fresh(), on_success=_on_fresh, show_loader=False)

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
        for m in items:
            has_sender = bool(m.sender_name and not m.is_outgoing)
            height = estimate_message_height(m.text, has_sender_name=has_sender)
            
            rv_data.append({
                "message_id": m.id,
                "text": m.text,
                "sender_name": m.sender_name if not m.is_outgoing else "",
                "sender_avatar": m.sender_avatar if not m.is_outgoing else "",
                "time_text": format_timestamp(m.date),
                "is_outgoing": m.is_outgoing,
                "is_read": m.is_read,
                "msg_size": [None, height]
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

        new_item = {
            "message_id": message_id,
            "text": text,
            "sender_name": self.chat_title if not is_out else "",
            "sender_avatar": self.avatar_url if not is_out else "",
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
