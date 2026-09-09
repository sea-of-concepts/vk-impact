"""Messages repository coordinating message fetching, sender profiling and caching."""
from typing import List, Dict, Any, Optional
from src.core.logger import logger
from src.data.api.client import api_client
from src.data.api.models import VKMessage
from src.data.database.db_manager import db_manager


class MessagesRepository:
    """Manages chat messages for individual dialogs and group chats."""

    async def get_cached_messages(self, peer_id: int, limit: int = 50) -> List[VKMessage]:
        """Loads cached messages from local SQLite."""
        raw = await db_manager.get_cached_messages(peer_id, limit=limit)
        messages = []
        for r in raw:
            messages.append(VKMessage(
                id=r["id"],
                peer_id=r["peer_id"],
                from_id=r["from_id"],
                sender_name=r.get("sender_name", ""),
                sender_avatar=r.get("sender_avatar", ""),
                date=r["date"],
                text=r["text"],
                out=r["out"],
                is_read=bool(r["is_read"]),
                attachments=r.get("attachments", []),
                fwd_messages=r.get("fwd_messages", []),
                reply_message=r.get("reply_message")
            ))
        return messages

    async def fetch_messages(self, peer_id: int, offset: int = 0, count: int = 40) -> List[VKMessage]:
        """Fetches messages with sender profiles from VK API and caches them."""
        is_channel = False
        try:
            import aiosqlite
            async with aiosqlite.connect(db_manager.db_path) as db:
                async with db.execute("SELECT is_channel FROM dialogs WHERE peer_id = ?", (peer_id,)) as cur:
                    row = await cur.fetchone()
                    if row:
                        is_channel = bool(row[0])
        except Exception:
            pass

        data: Dict[str, Any] = {}
        if is_channel:
            data = await api_client.channels_get_history(channel_id=peer_id, offset=offset, count=count, start_cmid=1_000_000_000, extended=1)
        else:
            try:
                data = await api_client.messages_get_history(peer_id=peer_id, offset=offset, count=count, extended=1)
            except Exception as e:
                if peer_id < 0:
                    logger.info("messages.getHistory failed for %s, trying channels.getHistory: %s", peer_id, e)
                    data = await api_client.channels_get_history(channel_id=peer_id, offset=offset, count=count, start_cmid=1_000_000_000, extended=1)
                else:
                    raise e

            # If messages.getHistory returned 0 items for a community peer, try channels.getHistory
            if peer_id < 0 and not data.get("items"):
                try:
                    ch_data = await api_client.channels_get_history(channel_id=peer_id, offset=offset, count=count, start_cmid=1_000_000_000, extended=1)
                    if ch_data.get("items"):
                        data = ch_data
                        try:
                            import aiosqlite
                            async with aiosqlite.connect(db_manager.db_path) as db:
                                await db.execute("UPDATE dialogs SET is_channel = 1 WHERE peer_id = ?", (peer_id,))
                                await db.commit()
                        except Exception:
                            pass
                except Exception as e_ch:
                    logger.debug("channels.getHistory check for %s returned: %s", peer_id, e_ch)

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

        # Fallback to dialog title and avatar for channels
        chat_title, chat_avatar = "", ""
        try:
            import aiosqlite
            async with aiosqlite.connect(db_manager.db_path) as db:
                async with db.execute("SELECT title, avatar_url FROM dialogs WHERE peer_id = ?", (peer_id,)) as cur:
                    row = await cur.fetchone()
                    if row:
                        chat_title = row[0] or ""
                        chat_avatar = row[1] or ""
        except Exception:
            pass

        models: List[VKMessage] = []
        for item in items:
            # Normalize channel items (cmid -> id, author_id -> from_id, time -> date, channel_id -> peer_id)
            if "cmid" in item and "id" not in item:
                item["id"] = item["cmid"]
            if "author_id" in item and "from_id" not in item:
                item["from_id"] = item["author_id"]
            if "time" in item and "date" not in item:
                item["date"] = item["time"]
            if "channel_id" in item and "peer_id" not in item:
                item["peer_id"] = item["channel_id"]

            m = VKMessage.model_validate(item)
            from_id = m.from_id
            if from_id > 0 and from_id in profiles:
                m.sender_name = profiles[from_id]["name"]
                m.sender_avatar = profiles[from_id]["avatar"]
            elif from_id < 0 and abs(from_id) in groups:
                m.sender_name = groups[abs(from_id)]["name"]
                m.sender_avatar = groups[abs(from_id)]["avatar"]
            elif from_id == peer_id and chat_title:
                m.sender_name = chat_title
                m.sender_avatar = chat_avatar

            # Resolve sender info for reply_message
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

            # Resolve sender info and timestamp for fwd_messages (including nested)
            if m.fwd_messages and isinstance(m.fwd_messages, list):
                try:
                    from src.utils.formatters import format_fwd_timestamp

                    def _resolve_fwd_item(fwd_item):
                        if not isinstance(fwd_item, dict):
                            return
                        f_from = fwd_item.get("from_id")
                        try:
                            f_from_int = int(f_from) if f_from is not None else 0
                        except (ValueError, TypeError):
                            f_from_int = 0
                        if f_from_int > 0 and f_from_int in profiles:
                            fwd_item["sender_name"] = profiles[f_from_int]["name"]
                            fwd_item["sender_avatar"] = profiles[f_from_int]["avatar"]
                        elif f_from_int < 0 and abs(f_from_int) in groups:
                            fwd_item["sender_name"] = groups[abs(f_from_int)]["name"]
                            fwd_item["sender_avatar"] = groups[abs(f_from_int)]["avatar"]
                        elif not fwd_item.get("sender_name"):
                            fwd_item["sender_name"] = "Сообщение"
                        if "date" in fwd_item and "time_text" not in fwd_item:
                            fwd_item["time_text"] = format_fwd_timestamp(fwd_item.get("date"))

                        # Resolve reply_message inside this forward
                        rep = fwd_item.get("reply_message")
                        if rep and isinstance(rep, dict):
                            _resolve_fwd_item(rep)

                        nested = fwd_item.get("fwd_messages")
                        if nested and isinstance(nested, list):
                            for nf in nested:
                                _resolve_fwd_item(nf)

                    for fwd in m.fwd_messages:
                        _resolve_fwd_item(fwd)
                except Exception as e_fwd:
                    logger.warning("Failed enriching fwd_messages: %s", e_fwd)


            models.append(m)

        # Cache to database
        raw_to_cache = [m.model_dump() for m in models]
        await db_manager.save_messages(raw_to_cache)
        # Return in ascending chronological order (oldest to newest)
        models.sort(key=lambda m: (m.date, m.id))
        return models

    async def send_message(self, peer_id: int, text: str, reply_to: Optional[int] = None) -> int:
        """Sends a text message with optional reply_to and returns the newly assigned message_id."""
        msg_id = await api_client.messages_send(peer_id=peer_id, message=text, reply_to=reply_to)
        return msg_id

    async def mark_as_read(self, peer_id: int, start_message_id: Optional[int] = None, is_channel: bool = False) -> int:
        """Marks incoming messages in chat or channel as read both on VK API and locally in SQLite & EventBus."""
        from src.core.events import event_bus
        from src.core.constants import EventType

        # 1. Update locally first for instant UI response
        try:
            await db_manager.mark_dialog_as_read(peer_id)
        except Exception as e:
            logger.debug("Failed to mark dialog as read in db: %s", e)

        event_bus.emit(EventType.MESSAGE_READ, peer_id=peer_id)

        # 2. Query newest message ID from SQLite if start_message_id not given
        resolved_msg_id = start_message_id
        if not resolved_msg_id:
            try:
                import aiosqlite
                async with aiosqlite.connect(db_manager.db_path) as db:
                    async with db.execute("SELECT id FROM messages WHERE peer_id = ? ORDER BY date DESC, id DESC LIMIT 1", (peer_id,)) as cur:
                        row = await cur.fetchone()
                        if row and row[0]:
                            resolved_msg_id = row[0]
            except Exception:
                pass

        # 3. Call VK API
        res = 0
        if is_channel or peer_id < 0:
            ch = is_channel
            if not ch:
                try:
                    import aiosqlite
                    async with aiosqlite.connect(db_manager.db_path) as db:
                        async with db.execute("SELECT is_channel FROM dialogs WHERE peer_id = ?", (peer_id,)) as cur:
                            row = await cur.fetchone()
                            if row:
                                ch = bool(row[0])
                except Exception:
                    pass

            if ch:
                last_read_cmid = resolved_msg_id or 1_000_000_000
                try:
                    res = await api_client.channels_mark_as_read(channel_id=peer_id, last_read_cmid=last_read_cmid)
                except Exception as e:
                    logger.debug("channels.markAsRead failed for %s: %s", peer_id, e)
                return res

        try:
            res = await api_client.messages_mark_as_read(peer_id=peer_id, start_message_id=resolved_msg_id)
        except Exception as e:
            logger.debug("messages.markAsRead failed for %s: %s", peer_id, e)
        return res

    async def update_read_progress(self, peer_id: int, highest_cmid: int, unread_remaining: int, is_channel: bool = False):
        """Marks messages as read up to highest_cmid and updates remaining unread count locally."""
        from src.core.events import event_bus
        from src.core.constants import EventType

        try:
            await db_manager.update_dialog_unread(peer_id, unread_remaining)
        except Exception as e:
            logger.debug("Failed to update unread progress in db: %s", e)

        event_bus.emit(
            EventType.DIALOG_UPDATED,
            peer_id=peer_id,
            unread_count=unread_remaining,
            is_read=(unread_remaining <= 0)
        )

        if highest_cmid > 0:
            if is_channel or peer_id < 0:
                try:
                    await api_client.channels_mark_as_read(channel_id=peer_id, last_read_cmid=highest_cmid)
                except Exception as e:
                    logger.debug("channels.markAsRead failed for %s: %s", peer_id, e)
            else:
                try:
                    await api_client.messages_mark_as_read(peer_id=peer_id, start_message_id=highest_cmid)
                except Exception as e:
                    logger.debug("messages.markAsRead failed for %s: %s", peer_id, e)


messages_repo = MessagesRepository()
