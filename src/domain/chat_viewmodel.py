import time
from typing import List, Dict, Any, Optional
from kivy.properties import ListProperty, StringProperty, NumericProperty, BooleanProperty
from kivy.clock import Clock
from kivy.metrics import dp
from src.domain.base_viewmodel import BaseViewModel
from src.data.repositories.messages_repo import messages_repo
from src.data.repositories.dialogs_repo import dialogs_repo
from src.data.repositories.users_repo import users_repo
from src.data.api.models import VKMessage
from src.core.events import event_bus
from src.core.constants import EventType
from src.core.logger import logger
from src.utils.async_tools import run_async
from src.utils.formatters import (
    format_timestamp,
    estimate_message_height,
    estimate_bubble_width,
    check_time_needs_own_line,
    clean_message_text,
    extract_photo_attachments,
    format_fallback_attachment_text,
)


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
        if getattr(self, "peer_id", None) != peer_id:
            self.messages = []
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

        # 1. Immediately load cached messages from local SQLite so UI renders with ZERO delay (no black screen)
        async def _load_cached():
            try:
                return await messages_repo.get_cached_messages(self.peer_id, limit=40)
            except Exception:
                return []

        def _on_cached(cached_items: List[VKMessage]):
            if cached_items and not self.messages:
                self._update_messages_list(cached_items)

        self.run_task(_load_cached(), on_success=_on_cached, show_loader=False)

        # 2. Fetch fresh messages from VK API around initial_offset
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

        self.run_task(_load_fresh(), on_success=_on_fresh, show_loader=False)

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

            rv_older = [self._format_message_for_rv(m, is_unread=False) for m in new_older]

            if on_data_ready:
                on_data_ready(rv_older)
            else:
                self.messages = self._apply_grouping(rv_older + list(self.messages))

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

            rv_newer = [self._format_message_for_rv(m, is_unread=False) for m in new_newer]

            if on_data_ready:
                on_data_ready(rv_newer)
            else:
                self.messages = self._apply_grouping(list(self.messages) + rv_newer)

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

    def send_message(self, reply_to: Optional[int] = None, reply_preview: Optional[dict] = None):
        """Sends the current input message with instant UI feedback, optional reply_to, and event dispatching."""
        text = self.input_text.strip()
        if not text or not self.peer_id:
            return

        # Clear input field immediately
        self.input_text = ""
        now = int(time.time())
        temp_id = -now

        # Optimistically add message to current chat UI immediately
        is_grp = (self.peer_id >= 2000000000 or self.peer_id < 0)
        time_needs_own = check_time_needs_own_line(text, is_outgoing=True, is_group_chat=is_grp)
        bw = estimate_bubble_width(
            text=text,
            photos=[],
            sender_name="",
            has_reply=bool(reply_preview),
            has_fwd=False,
            time_needs_own_line=time_needs_own,
            is_outgoing=True,
            is_group_chat=is_grp
        )
        height = estimate_message_height(
            text,
            has_sender_name=False,
            has_reply=bool(reply_preview),
            time_needs_own_line=time_needs_own,
            bubble_w=bw
        )
        opt_item = {
            "message_id": temp_id,
            "from_id": 0,
            "date": now,
            "is_group_chat": (self.peer_id >= 2000000000 or self.peer_id < 0),
            "text": text,
            "photos": [],
            "full_sender_name": "",
            "sender_name": "",
            "full_sender_avatar": "",
            "sender_avatar": "",
            "show_avatar": False,
            "sender_impact_style": "",
            "time_text": format_timestamp(now),
            "is_outgoing": True,
            "is_read": False,
            "show_new_divider": False,
            "reply_message": reply_preview or {},
            "fwd_messages": [],
            "time_needs_own_line": time_needs_own,
            "bubble_width": dp(bw),
            "msg_size": [None, dp(height)]
        }
        self.messages = self._apply_grouping(list(self.messages) + [opt_item])

        # Emit to EventBus so DialogsViewModel and any observers update the last message immediately!
        event_bus.emit(
            EventType.NEW_MESSAGE,
            message_id=temp_id,
            peer_id=self.peer_id,
            from_id=0,
            text=text,
            timestamp=now,
            is_out=True,
            attachments={}
        )
        event_bus.emit(EventType.DIALOG_UPDATED, peer_id=self.peer_id)

        async def _send():
            real_id = await messages_repo.send_message(self.peer_id, text, reply_to=reply_to)
            try:
                await dialogs_repo.save_dialog_new_message(
                    peer_id=self.peer_id,
                    text=f"Вы: {text}",
                    timestamp=now,
                    is_out=True,
                    message_id=real_id
                )
            except Exception as e:
                logger.debug("Failed to save outgoing message to dialogs repo: %s", e)
            return real_id

        def _on_sent(real_msg_id: int):
            for m in self.messages:
                if m.get("message_id") == temp_id:
                    m["message_id"] = real_msg_id
                    break

        self.run_task(_send(), on_success=_on_sent, show_loader=False)

    def _enrich_user_in_background(self, uid: int, msg_id: int):
        """Asynchronously fetches user or group profile and updates UI messages & DB in-place."""
        if not uid:
            return

        async def _fetch():
            full_n, av, st = "", "", ""
            if uid > 0:
                cached_u = await db_manager.get_cached_user(uid)
                if not cached_u:
                    cached_u = await users_repo.get_user(uid)
                if cached_u:
                    fn = cached_u.get("first_name", "").strip()
                    ln = cached_u.get("last_name", "").strip()
                    full_n = f"{fn} {ln}".strip() or "Пользователь"
                    av = cached_u.get("photo_100") or cached_u.get("photo_200") or ""
                    st = cached_u.get("impact_style", "") or ("zephyr" if uid == 708902696 else "")
            else:
                gid = abs(uid)
                try:
                    g_resp = await api_client.request("groups.getById", {
                        "group_ids": str(gid),
                        "fields": "photo_100,photo_200"
                    })
                    g_items = g_resp if isinstance(g_resp, list) else g_resp.get("groups", [])
                    if g_items:
                        g = g_items[0]
                        full_n = g.get("name", "Сообщество")
                        av = g.get("photo_100") or g.get("photo_200") or g.get("photo_50") or ""
                except Exception:
                    pass

            if not full_n:
                return

            # Persist enriched sender into SQLite database
            try:
                import aiosqlite
                from src.data.database.db_manager import db_manager
                async with aiosqlite.connect(db_manager.db_path) as db:
                    await db.execute(
                        "UPDATE messages SET sender_name = ?, sender_avatar = ? WHERE (from_id = ? OR id = ?) AND (sender_name IS NULL OR sender_name = '' OR sender_name LIKE 'ID %')",
                        (full_n, av, uid, msg_id)
                    )
                    await db.commit()
            except Exception:
                pass

                def _apply(dt):
                    new_messages = []
                    updated = False
                    for msg in self.messages:
                        if msg.get("from_id") == uid or msg.get("message_id") == msg_id or (msg.get("sender_name") == f"ID {uid}"):
                            m_copy = dict(msg)
                            m_copy["full_sender_name"] = full_n
                            m_copy["sender_name"] = full_n
                            m_copy["full_sender_avatar"] = av
                            m_copy["sender_avatar"] = av
                            m_copy["sender_impact_style"] = st

                            t = m_copy.get("text", "")
                            time_needs_own = m_copy.get("time_needs_own_line", False)
                            reply = m_copy.get("reply_message")
                            fwds = m_copy.get("fwd_messages", [])
                            fwd_texts = [f.get("text", "") for f in fwds if isinstance(f, dict)]
                            photos = m_copy.get("photos", [])
                            bw = estimate_bubble_width(
                                text=t,
                                photos=photos,
                                sender_name=full_n,
                                has_reply=bool(reply),
                                has_fwd=bool(fwds),
                                time_needs_own_line=time_needs_own,
                                is_outgoing=False,
                                is_group_chat=m_copy.get("is_group_chat", False)
                            )
                            h = estimate_message_height(
                                t,
                                has_sender_name=True,
                                has_reply=bool(reply),
                                fwd_count=len(fwds),
                                fwd_texts=fwd_texts,
                                time_needs_own_line=time_needs_own,
                                photos=photos,
                                bubble_w=bw
                            )
                            m_copy["bubble_width"] = dp(bw)
                            m_copy["msg_size"] = [None, dp(h)]
                            new_messages.append(m_copy)
                            updated = True
                        else:
                            new_messages.append(msg)
                    if updated:
                        self.messages = self._apply_grouping(new_messages)
                Clock.schedule_once(_apply, 0)
        run_async(_fetch())

    def _format_message_for_rv(self, m: VKMessage, is_first_unread: bool = False, is_unread: bool = False) -> dict:
        """Helper to format a VKMessage into RecycleView data dictionary with exact sizing."""
        try:
            raw_text = clean_message_text(m.text or "")
            attachments = getattr(m, "attachments", None) or []
            photos = extract_photo_attachments(attachments)
            if not raw_text and not photos and attachments:
                raw_text = format_fallback_attachment_text(attachments)

            sender_name = m.sender_name if not m.is_outgoing else ""
            sender_avatar = m.sender_avatar if not m.is_outgoing else ""
            if not m.is_outgoing and m.from_id > 0 and (not sender_name or sender_name.startswith("ID ")):
                cached_u = users_repo._memory_cache.get(m.from_id)
                if cached_u:
                    fn = cached_u.get("first_name", "").strip()
                    ln = cached_u.get("last_name", "").strip()
                    sender_name = f"{fn} {ln}".strip() or "Пользователь"
                    sender_avatar = cached_u.get("photo_100") or cached_u.get("photo_200") or ""
                else:
                    self._enrich_user_in_background(m.from_id, m.id)

            has_sender = bool(sender_name and not m.is_outgoing)
            reply = getattr(m, "reply_message", None)
            fwds = getattr(m, "fwd_messages", None) or []
            fwd_texts = []
            if isinstance(fwds, list):
                def _collect_texts(items):
                    for it in items:
                        if isinstance(it, dict):
                            t = it.get("text")
                            if t:
                                fwd_texts.append(str(t))
                            rep = it.get("reply_message")
                            if rep and isinstance(rep, dict) and rep.get("text"):
                                fwd_texts.append(str(rep.get("text")))
                            nested = it.get("fwd_messages")
                            if nested and isinstance(nested, list):
                                _collect_texts(nested)
                _collect_texts(fwds)

            has_text = bool(raw_text.strip())
            is_grp = (self.peer_id >= 2000000000 or self.peer_id < 0)
            time_needs_own = check_time_needs_own_line(raw_text, m.is_outgoing, is_group_chat=is_grp, sender_name=sender_name) if has_text else False
            bubble_w = estimate_bubble_width(
                text=raw_text,
                photos=photos,
                sender_name=sender_name,
                has_reply=bool(reply),
                has_fwd=bool(fwds),
                time_needs_own_line=time_needs_own,
                is_outgoing=m.is_outgoing,
                is_group_chat=is_grp
            )
            base_height = estimate_message_height(
                raw_text,
                has_sender_name=has_sender,
                has_reply=bool(reply),
                fwd_count=max(len(fwds), len(fwd_texts)),
                fwd_texts=fwd_texts,
                time_needs_own_line=time_needs_own,
                photos=photos,
                bubble_w=bubble_w
            )
            total_height = base_height + (28 if is_first_unread else 0)

            sender_style = ""
            if not m.is_outgoing:
                cached_user = users_repo._memory_cache.get(m.from_id, {})
                sender_style = cached_user.get("impact_style", "") or ("zephyr" if m.from_id == 708902696 else "")

            return {
                "message_id": m.id,
                "from_id": m.from_id,
                "date": getattr(m, "date", 0),
                "is_group_chat": (self.peer_id >= 2000000000 or self.peer_id < 0 or getattr(m, "peer_id", 0) >= 2000000000 or getattr(m, "peer_id", 0) < 0),
                "text": raw_text,
                "photos": photos,
                "full_sender_name": sender_name,
                "sender_name": sender_name,
                "full_sender_avatar": sender_avatar,
                "sender_avatar": sender_avatar,
                "show_avatar": bool(sender_avatar),
                "sender_impact_style": sender_style,
                "time_text": format_timestamp(m.date),
                "is_outgoing": m.is_outgoing,
                "is_read": not is_unread,
                "show_new_divider": is_first_unread,
                "reply_message": reply if isinstance(reply, dict) else {},
                "fwd_messages": fwds if isinstance(fwds, list) else [],
                "time_needs_own_line": time_needs_own,
                "bubble_width": dp(bubble_w),
                "msg_size": [None, dp(total_height)]
            }
        except Exception as e:
            from src.core.logger import logger
            logger.error("Error formatting message %s for RV: %s", getattr(m, "id", 0), e)
            return {
                "message_id": getattr(m, "id", 0),
                "from_id": getattr(m, "from_id", 0),
                "date": getattr(m, "date", 0),
                "text": clean_message_text(str(getattr(m, "text", "") or "")),
                "photos": [],
                "full_sender_name": "",
                "sender_name": "",
                "full_sender_avatar": "",
                "sender_avatar": "",
                "show_avatar": False,
                "sender_impact_style": "",
                "time_text": "",
                "is_outgoing": getattr(m, "is_outgoing", False),
                "is_read": True,
                "show_new_divider": False,
                "reply_message": {},
                "fwd_messages": [],
                "bubble_width": dp(220),
                "msg_size": [None, dp(64)]
            }

    def _apply_grouping(self, messages: List[dict]) -> List[dict]:
        """
        Applies VK-style message grouping for consecutive messages:
        - First message in a group shows sender_name (nickname in group chats).
        - Last message in a group shows sender_avatar (at the bottom next to the sharp corner).
        - Middle messages show neither.
        - Single messages show both.
        - Recalculates exact bubble_width and msg_size height to reflect whether sender_name is present.
        """
        if not messages:
            return messages

        is_group = bool(self.peer_id >= 2000000000 or self.peer_id < 0 or (messages[0].get("is_group_chat", False) if messages else False))
        n = len(messages)

        for i in range(n):
            curr = messages[i]
            is_out = curr.get("is_outgoing", False)

            if is_out or not is_group:
                curr["show_avatar"] = False
                curr["sender_name"] = ""
                curr["show_sender_name"] = False
            else:
                prev = messages[i - 1] if i > 0 else None
                nxt = messages[i + 1] if i < n - 1 else None

                is_first = (
                    prev is None
                    or prev.get("is_outgoing", False)
                    or prev.get("from_id") != curr.get("from_id")
                    or curr.get("show_new_divider", False)
                    or abs(curr.get("date", 0) - prev.get("date", 0)) > 300
                )

                is_last = (
                    nxt is None
                    or nxt.get("is_outgoing", False)
                    or nxt.get("from_id") != curr.get("from_id")
                    or nxt.get("show_new_divider", False)
                    or abs(nxt.get("date", 0) - curr.get("date", 0)) > 300
                )

                full_name = curr.get("full_sender_name") or curr.get("sender_name", "")
                curr["full_sender_name"] = full_name
                curr["sender_name"] = full_name if is_first else ""
                curr["show_sender_name"] = is_first

                full_av = curr.get("full_sender_avatar") or curr.get("sender_avatar", "")
                curr["full_sender_avatar"] = full_av
                curr["sender_avatar"] = full_av if is_last else ""
                curr["show_avatar"] = bool(is_last and full_av)

            # Recalculate bubble_width and height only if sender_name changed or size not yet calculated
            old_sn = curr.get("_last_calc_sender_name")
            new_sn = curr.get("sender_name", "")
            if curr.get("bubble_width") is None or curr.get("msg_size") is None or old_sn != new_sn:
                curr["_last_calc_sender_name"] = new_sn
                t = curr.get("text", "")
                photos = curr.get("photos", [])
                reply = curr.get("reply_message")
                fwds = curr.get("fwd_messages", [])
                fwd_texts = [f.get("text", "") for f in fwds if isinstance(f, dict)]
                time_own = curr.get("time_needs_own_line", False)

                bw = estimate_bubble_width(
                    text=t,
                    photos=photos,
                    sender_name=new_sn,
                    has_reply=bool(reply),
                    has_fwd=bool(fwds),
                    time_needs_own_line=time_own,
                    is_outgoing=is_out,
                    is_group_chat=is_group
                )
                curr["bubble_width"] = dp(bw)

                h = estimate_message_height(
                    t,
                    has_sender_name=bool(new_sn),
                    has_reply=bool(reply),
                    fwd_count=len(fwds),
                    fwd_texts=fwd_texts,
                    time_needs_own_line=time_own,
                    photos=photos,
                    bubble_w=bw
                )
                curr["msg_size"] = [None, dp(h + (28 if curr.get("show_new_divider") else 0))]

        return messages

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
            is_first_unread = (idx == first_unread_idx and self.initial_unread_count > 0)
            is_unread = (idx >= first_unread_idx and not m.is_outgoing and self.initial_unread_count > 0 and m.id not in self._read_message_ids)
            rv_data.append(self._format_message_for_rv(m, is_first_unread=is_first_unread, is_unread=is_unread))
        self.messages = self._apply_grouping(rv_data)

    def load_history_around_message(self, message_id: int, on_complete=None):
        """Loads chat history centered around a target message (for jump-to-reply)."""
        async def _fetch():
            self.is_loading_history = True
            data = await api_client.messages_get_history(
                peer_id=self.peer_id,
                start_message_id=message_id,
                offset=-15,
                count=35,
                extended=1
            )
            items = data.get("items", [])
            profiles = {
                p["id"]: {
                    "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or "Пользователь",
                    "avatar": p.get("photo_100") or p.get("photo_50") or ""
                }
                for p in data.get("profiles", [])
            }
            for p in data.get("profiles", []):
                uid = p.get("id")
                if uid:
                    users_repo._memory_cache[uid] = {
                        "id": uid,
                        "first_name": p.get("first_name", ""),
                        "last_name": p.get("last_name", ""),
                        "photo_100": p.get("photo_100") or p.get("photo_50") or "",
                        "photo_200": p.get("photo_200") or p.get("photo_100") or "",
                        "online": int(p.get("online", 0)),
                        "impact_style": p.get("impact_style", "") or ("zephyr" if uid == 708902696 else ""),
                        "updated_at": int(time.time())
                    }
            # Collect any missing user or group IDs
            missing_uids = set()
            for item in items:
                fid = item.get("from_id") or item.get("author_id", 0)
                if fid and fid > 0 and fid not in profiles:
                    missing_uids.add(fid)
                rep = item.get("reply_message")
                if rep and isinstance(rep, dict):
                    rfid = rep.get("from_id", 0)
                    if rfid and rfid > 0 and rfid not in profiles:
                        missing_uids.add(rfid)

            # Resolve from cache or fetch
            still_missing = set()
            for uid in missing_uids:
                if uid in users_repo._memory_cache:
                    u = users_repo._memory_cache[uid]
                    profiles[uid] = {
                        "name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or "Пользователь",
                        "avatar": u.get("photo_100") or u.get("photo_200") or ""
                    }
                else:
                    still_missing.add(uid)

            if still_missing:
                try:
                    fetched = await api_client.users_get(user_ids=list(still_missing))
                    for u in fetched:
                        profiles[u.id] = {"name": u.full_name or "Пользователь", "avatar": u.avatar_url}
                        users_repo._memory_cache[u.id] = {
                            "id": u.id, "first_name": u.first_name, "last_name": u.last_name,
                            "photo_100": u.photo_100 or "", "photo_200": u.photo_200 or "",
                            "online": int(u.online), "impact_style": u.impact_style,
                            "updated_at": int(time.time())
                        }
                except Exception as e_f:
                    logger.warning("Failed fetching missing profiles in history around message: %s", e_f)

            models = []
            for item in items:
                m = VKMessage.model_validate(item)
                from_id = m.from_id
                if from_id > 0 and from_id in profiles:
                    m.sender_name = profiles[from_id]["name"]
                    m.sender_avatar = profiles[from_id]["avatar"]
                elif from_id > 0:
                    cached_u = users_repo._memory_cache.get(from_id)
                    if cached_u:
                        fn = cached_u.get("first_name", "")
                        ln = cached_u.get("last_name", "")
                        m.sender_name = f"{fn} {ln}".strip() or "Пользователь"
                        m.sender_avatar = cached_u.get("photo_100") or cached_u.get("photo_200") or ""
                elif from_id < 0 and abs(from_id) in groups:
                    m.sender_name = groups[abs(from_id)]["name"]
                    m.sender_avatar = groups[abs(from_id)]["avatar"]
                if m.reply_message and isinstance(m.reply_message, dict):
                    r_from = m.reply_message.get("from_id")
                    try:
                        r_from_int = int(r_from) if r_from is not None else 0
                    except (ValueError, TypeError):
                        r_from_int = 0
                    if r_from_int > 0 and r_from_int in profiles:
                        m.reply_message["sender_name"] = profiles[r_from_int]["name"]
                        m.reply_message["sender_avatar"] = profiles[r_from_int]["avatar"]
                    elif r_from_int < 0 and abs(r_from_int) in groups:
                        m.reply_message["sender_name"] = groups[abs(r_from_int)]["name"]
                        m.reply_message["sender_avatar"] = groups[abs(r_from_int)]["avatar"]
                    elif not m.reply_message.get("sender_name"):
                        m.reply_message["sender_name"] = "Собеседник"

                if m.fwd_messages and isinstance(m.fwd_messages, list):
                    from src.utils.formatters import format_fwd_timestamp
                    for fwd in m.fwd_messages:
                        if isinstance(fwd, dict):
                            f_from = fwd.get("from_id")
                            try:
                                f_from_int = int(f_from) if f_from is not None else 0
                            except (ValueError, TypeError):
                                f_from_int = 0
                            if f_from_int > 0 and f_from_int in profiles:
                                fwd["sender_name"] = profiles[f_from_int]["name"]
                                fwd["sender_avatar"] = profiles[f_from_int]["avatar"]
                            elif f_from_int < 0 and abs(f_from_int) in groups:
                                fwd["sender_name"] = groups[abs(f_from_int)]["name"]
                                fwd["sender_avatar"] = groups[abs(f_from_int)]["avatar"]
                            elif not fwd.get("sender_name"):
                                fwd["sender_name"] = "Сообщение"
                            if "date" in fwd and "time_text" not in fwd:
                                fwd["time_text"] = format_fwd_timestamp(fwd.get("date"))
                models.append(m)


            models.sort(key=lambda m: (m.date, m.id))
            raw_to_cache = [m.model_dump() for m in models]
            await db_manager.save_messages(raw_to_cache)
            return models

        def _on_success(models):
            self.is_loading_history = False
            self.has_more_older = True
            self.has_more_newer = True
            self._update_messages_list(models)
            if on_complete:
                on_complete()

        def _on_error(exc):
            self.is_loading_history = False
            logger.error("Failed loading history around message %s: %s", message_id, exc)

        self.run_task(_fetch(), on_success=_on_success, on_error=_on_error, show_loader=True)

    def _on_new_message(self, peer_id: int, message_id: int, text: str, timestamp: int, is_out: bool, **kwargs):
        """Handles incoming new message event in active chat with proper author resolution, deduplication and thread safety."""
        if peer_id != self.peer_id:
            return

        # Avoid duplicate message insertion (matching real message_id or temp negative ID)
        if message_id:
            for m in self.messages:
                if m.get("message_id") == message_id:
                    return
                # If this confirms an optimistic outgoing message
                if is_out and m.get("is_outgoing") and m.get("message_id", 0) < 0 and m.get("text") == text:
                    m["message_id"] = message_id
                    return

        from_id = kwargs.get("from_id", 0)
        sender_name = ""
        sender_avatar = ""
        sender_style = ""

        if not is_out:
            if self.peer_id < 2000000000:
                # 1-on-1 dialogue: other party is the chat peer
                sender_name = self.chat_title
                sender_avatar = self.avatar_url
                sender_style = (users_repo._memory_cache.get(from_id or self.peer_id, {}).get("impact_style", "") or ("zephyr" if (from_id or self.peer_id) == 708902696 else ""))
            else:
                # Group chat (peer_id >= 2000000000): author is from_id
                if from_id > 0:
                    cached_user = users_repo._memory_cache.get(from_id)
                    if cached_user:
                        fn = cached_user.get("first_name", "").strip()
                        ln = cached_user.get("last_name", "").strip()
                        sender_name = f"{fn} {ln}".strip() or "Пользователь"
                        sender_avatar = cached_user.get("photo_100") or cached_user.get("photo_200") or ""
                        sender_style = cached_user.get("impact_style", "") or ("zephyr" if from_id == 708902696 else "")
                    else:
                        sender_name = f"ID {from_id}"
                        sender_avatar = ""
                        self._enrich_user_in_background(from_id, message_id)
                elif from_id < 0:
                    sender_name = "Сообщество"
                    sender_avatar = ""

        reply = kwargs.get("reply_message") or {}
        fwds = kwargs.get("fwd_messages") or []
        fwd_texts = [f.get("text", "") for f in fwds if isinstance(f, dict)]

        raw_attachments = kwargs.get("attachments") or []
        cmid = kwargs.get("conversation_message_id", 0)
        photos = []
        photo_ids_from_dict = []

        if isinstance(raw_attachments, list):
            photos = extract_photo_attachments(raw_attachments)
        elif isinstance(raw_attachments, dict) and any(k.startswith("attach") for k in raw_attachments):
            # Parse photo IDs from compact dict e.g. attach1_type == 'photo', attach1 == '708902696_457257321'
            for k, v in raw_attachments.items():
                if k.endswith("_type") and v == "photo":
                    p_key = k[:-5]
                    p_val = raw_attachments.get(p_key)
                    if p_val:
                        photo_ids_from_dict.append(str(p_val))

            if photo_ids_from_dict:
                cnt = max(1, len(photo_ids_from_dict))
                # Initial placeholder photos for instant layout calculation & rendering
                photos = [{"url": "", "aspect_ratio": 1.33, "loading": True} for _ in range(cnt)]

            # LongPoll compact attachment dictionary: fetch full message to get photo sizes/URLs
            async def _fetch_full_attachments(mid: int, c_mid: int):
                try:
                    res = None
                    if c_mid and (self.peer_id >= 2000000000 or self.peer_id < 0):
                        try:
                            res = await api_client.request(
                                "messages.getByConversationMessageId",
                                {"peer_id": self.peer_id, "conversation_message_ids": c_mid, "extended": 1}
                            )
                        except Exception as e_cmid:
                            logger.debug("messages.getByConversationMessageId failed: %s", e_cmid)

                    if not res or not res.get("items"):
                        try:
                            res = await api_client.request("messages.getById", {"message_ids": mid, "extended": 1})
                        except Exception as e_mid:
                            logger.debug("messages.getById failed: %s", e_mid)

                    fetched_photos = []
                    full_items = res.get("items", []) if res else []
                    if full_items:
                        full_att = full_items[0].get("attachments", [])
                        fetched_photos = extract_photo_attachments(full_att)

                    # Fallback: fetch directly via photos.getById if we have photo IDs
                    if not fetched_photos and photo_ids_from_dict:
                        try:
                            p_res = await api_client.request("photos.getById", {"photos": ",".join(photo_ids_from_dict)})
                            p_items = p_res if isinstance(p_res, list) else p_res.get("items", [])
                            if p_items:
                                fetched_photos = extract_photo_attachments([{"type": "photo", "photo": p} for p in p_items])
                        except Exception as e_p:
                            logger.debug("photos.getById fallback failed: %s", e_p)

                    if fetched_photos:
                        def _apply_photos(dt):
                            updated = []
                            changed = False
                            for m in self.messages:
                                if m.get("message_id") == mid:
                                    m_new = dict(m)
                                    m_new["photos"] = fetched_photos
                                    bw = estimate_bubble_width(
                                        text=m_new.get("text", ""),
                                        photos=fetched_photos,
                                        sender_name=m_new.get("sender_name", ""),
                                        has_reply=bool(m_new.get("reply_message")),
                                        has_fwd=bool(m_new.get("fwd_messages")),
                                        time_needs_own_line=m_new.get("time_needs_own_line", False),
                                        is_outgoing=m_new.get("is_outgoing", False),
                                        is_group_chat=m_new.get("is_group_chat", False)
                                    )
                                    h = estimate_message_height(
                                        m_new.get("text", ""),
                                        has_sender_name=bool(m_new.get("sender_name") and not m_new.get("is_outgoing")),
                                        has_reply=bool(m_new.get("reply_message")),
                                        fwd_count=len(m_new.get("fwd_messages", [])),
                                        photos=fetched_photos,
                                        bubble_w=bw
                                    )
                                    m_new["bubble_width"] = dp(bw)
                                    m_new["msg_size"] = [None, dp(h)]
                                    updated.append(m_new)
                                    changed = True
                                else:
                                    updated.append(m)
                            if changed:
                                self.messages = updated
                                self.property("messages").dispatch(self)
                        Clock.schedule_once(_apply_photos, 0)
                except Exception as e_att:
                    logger.debug("Failed fetching full attachments for %s: %s", mid, e_att)
            run_async(_fetch_full_attachments(message_id, cmid))

        clean_text = clean_message_text(text)
        if not clean_text and not photos and raw_attachments:
            clean_text = format_fallback_attachment_text(raw_attachments, include_photo=False)
        has_text = bool(clean_text.strip())
        has_sender = bool(sender_name and not is_out)
        is_grp = (self.peer_id >= 2000000000 or self.peer_id < 0)
        time_needs_own = check_time_needs_own_line(clean_text, is_out, is_group_chat=is_grp, sender_name=sender_name) if has_text else False
        bw = estimate_bubble_width(
            text=clean_text,
            photos=photos,
            sender_name=sender_name,
            has_reply=bool(reply),
            has_fwd=bool(fwds),
            time_needs_own_line=time_needs_own,
            is_outgoing=is_out,
            is_group_chat=is_grp
        )
        height = estimate_message_height(
            clean_text,
            has_sender_name=has_sender,
            has_reply=bool(reply),
            fwd_count=len(fwds),
            fwd_texts=fwd_texts,
            time_needs_own_line=time_needs_own,
            photos=photos,
            bubble_w=bw
        )

        new_item = {
            "message_id": message_id,
            "from_id": from_id,
            "date": timestamp,
            "is_group_chat": (self.peer_id >= 2000000000 or self.peer_id < 0),
            "text": clean_text,
            "photos": photos,
            "full_sender_name": sender_name,
            "sender_name": sender_name,
            "full_sender_avatar": sender_avatar,
            "sender_avatar": sender_avatar,
            "show_avatar": bool(sender_avatar),
            "sender_impact_style": sender_style,
            "time_text": format_timestamp(timestamp),
            "is_outgoing": is_out,
            "is_read": is_out,
            "show_new_divider": False,
            "reply_message": reply if isinstance(reply, dict) else {},
            "fwd_messages": fwds if isinstance(fwds, list) else [],
            "time_needs_own_line": time_needs_own,
            "bubble_width": dp(bw),
            "msg_size": [None, dp(height)]
        }
        self.messages = self._apply_grouping(list(self.messages) + [new_item])
        
        if not is_out:
            self.run_task(messages_repo.mark_as_read(self.peer_id, start_message_id=message_id), show_loader=False)

    def _on_user_typing(self, user_id: int, **kwargs):
        """Shows typing indicator if peer matches."""
        if user_id == self.peer_id:
            self.is_peer_typing = True
            Clock.schedule_once(lambda dt: setattr(self, "is_peer_typing", False), 5)
