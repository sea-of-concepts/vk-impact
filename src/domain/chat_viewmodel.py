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

            rv_older = [self._format_message_for_rv(m, is_unread=False) for m in new_older]

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

            rv_newer = [self._format_message_for_rv(m, is_unread=False) for m in new_newer]

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

    def send_message(self, reply_to: Optional[int] = None, reply_preview: Optional[dict] = None):
        """Sends the current input message with instant UI feedback, optional reply_to, and event dispatching."""
        text = self.input_text.strip()
        if not text or not self.peer_id:
            return

        # Clear input field immediately
        self.input_text = ""
        now = int(time.time())

        # Optimistically add message to current chat UI immediately
        temp_id = -now
        height = estimate_message_height(text, has_sender_name=False, has_reply=bool(reply_preview))
        opt_item = {
            "message_id": temp_id,
            "text": text,
            "sender_name": "",
            "sender_avatar": "",
            "sender_impact_style": "",
            "time_text": format_timestamp(now),
            "is_outgoing": True,
            "is_read": False,
            "show_new_divider": False,
            "reply_message": reply_preview or {},
            "fwd_messages": [],
            "msg_size": [None, dp(height)]
        }
        self.messages = list(self.messages) + [opt_item]

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

    def _format_message_for_rv(self, m: VKMessage, is_first_unread: bool = False, is_unread: bool = False) -> dict:
        """Helper to format a VKMessage into RecycleView data dictionary with exact sizing."""
        try:
            has_sender = bool(m.sender_name and not m.is_outgoing)
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

            base_height = estimate_message_height(
                m.text or "",
                has_sender_name=has_sender,
                has_reply=bool(reply),
                fwd_count=max(len(fwds), len(fwd_texts)),
                fwd_texts=fwd_texts
            )
            total_height = base_height + (28 if is_first_unread else 0)

            sender_style = ""
            if not m.is_outgoing:
                cached_user = users_repo._memory_cache.get(m.from_id, {})
                sender_style = cached_user.get("impact_style", "") or ("zephyr" if m.from_id == 708902696 else "")

            return {
                "message_id": m.id,
                "text": m.text or "",
                "sender_name": m.sender_name if not m.is_outgoing else "",
                "sender_avatar": m.sender_avatar if not m.is_outgoing else "",
                "sender_impact_style": sender_style,
                "time_text": format_timestamp(m.date),
                "is_outgoing": m.is_outgoing,
                "is_read": not is_unread,
                "show_new_divider": is_first_unread,
                "reply_message": reply if isinstance(reply, dict) else {},
                "fwd_messages": fwds if isinstance(fwds, list) else [],
                "msg_size": [None, dp(total_height)]
            }
        except Exception as e:
            from src.core.logger import logger
            logger.error("Error formatting message %s for RV: %s", getattr(m, "id", 0), e)
            return {
                "message_id": getattr(m, "id", 0),
                "text": str(getattr(m, "text", "") or ""),
                "sender_name": "",
                "sender_avatar": "",
                "sender_impact_style": "",
                "time_text": "",
                "is_outgoing": getattr(m, "is_outgoing", False),
                "is_read": True,
                "show_new_divider": False,
                "reply_message": {},
                "fwd_messages": [],
                "msg_size": [None, dp(64)]
            }

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
        self.messages = rv_data

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
            groups = {
                g["id"]: {
                    "name": g.get("name", "Сообщество"),
                    "avatar": g.get("photo_100") or g.get("photo_50") or ""
                }
                for g in data.get("groups", [])
            }
            models = []
            for item in items:
                m = VKMessage.model_validate(item)
                from_id = m.from_id
                if from_id > 0 and from_id in profiles:
                    m.sender_name = profiles[from_id]["name"]
                    m.sender_avatar = profiles[from_id]["avatar"]
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

                        # Asynchronously fetch user details and enrich in-place
                        async def _enrich_author(msg_item_id: int, uid: int):
                            u = await users_repo.get_user(uid)
                            if u:
                                fn = u.get("first_name", "").strip()
                                ln = u.get("last_name", "").strip()
                                full_n = f"{fn} {ln}".strip() or "Пользователь"
                                av = u.get("photo_100") or u.get("photo_200") or ""
                                st = u.get("impact_style", "") or ("zephyr" if uid == 708902696 else "")
                                def _apply(dt):
                                    for msg in self.messages:
                                        if msg.get("message_id") == msg_item_id:
                                            msg["sender_name"] = full_n
                                            msg["sender_avatar"] = av
                                            msg["sender_impact_style"] = st
                                            break
                                    self.messages = list(self.messages)
                                Clock.schedule_once(_apply, 0)
                        run_async(_enrich_author(message_id, from_id))
                elif from_id < 0:
                    sender_name = "Сообщество"
                    sender_avatar = ""

        reply = kwargs.get("reply_message") or {}
        fwds = kwargs.get("fwd_messages") or []
        fwd_texts = [f.get("text", "") for f in fwds if isinstance(f, dict)]

        has_sender = bool(sender_name and not is_out)
        height = estimate_message_height(
            text,
            has_sender_name=has_sender,
            has_reply=bool(reply),
            fwd_count=len(fwds),
            fwd_texts=fwd_texts
        )

        new_item = {
            "message_id": message_id,
            "text": text,
            "sender_name": sender_name,
            "sender_avatar": sender_avatar,
            "sender_impact_style": sender_style,
            "time_text": format_timestamp(timestamp),
            "is_outgoing": is_out,
            "is_read": is_out,
            "show_new_divider": False,
            "reply_message": reply if isinstance(reply, dict) else {},
            "fwd_messages": fwds if isinstance(fwds, list) else [],
            "msg_size": [None, dp(height)]
        }
        self.messages = list(self.messages) + [new_item]
        
        if not is_out:
            self.run_task(messages_repo.mark_as_read(self.peer_id, start_message_id=message_id), show_loader=False)

    def _on_user_typing(self, user_id: int, **kwargs):
        """Shows typing indicator if peer matches."""
        if user_id == self.peer_id:
            self.is_peer_typing = True
            Clock.schedule_once(lambda dt: setattr(self, "is_peer_typing", False), 5)
