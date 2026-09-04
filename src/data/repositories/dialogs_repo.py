"""Dialogs repository coordinating local cache and VK API."""
from typing import List, Dict, Any, Optional
from src.core.logger import logger
from src.data.api.client import api_client
from src.data.api.models import VKDialogItem
from src.data.database.db_manager import db_manager


class DialogsRepository:
    """Provides dialog items with cache-first strategy."""

    async def get_cached_dialogs(self) -> List[VKDialogItem]:
        """Loads cached dialogs from local database."""
        raw = await db_manager.get_cached_dialogs()
        return [
            VKDialogItem(
                peer_id=r["peer_id"],
                title=r["title"] or "Диалог",
                avatar_url=r["avatar_url"] or "",
                last_message_text=r["last_message_text"] or "",
                last_message_time=r["last_message_time"] or 0,
                unread_count=r["unread_count"] or 0,
                is_online=bool(r["is_online"]),
                is_outgoing=bool(r["is_outgoing"]),
                is_read=bool(r["is_read"]),
                is_pinned=bool(r.get("is_pinned", 0)),
                is_archived=bool(r.get("is_archived", 0)),
                is_muted=bool(r.get("is_muted", 0)),
                is_channel=bool(r.get("is_channel", 0)),
                impact_style=r.get("impact_style", "") or ("zephyr" if r.get("peer_id") == 708902696 else "")
            )
            for r in raw
        ]

    @staticmethod
    def _compute_next_cursor(
        start_from: Optional[str],
        conv_items: List[Dict[str, Any]],
        channel_items: List[Dict[str, Any]]
    ) -> str:
        """
        Computes next cursor for messages.getItems: conversations_{conv_minor_id},channels_{ch_minor_id}_{ch_id}.
        Returns empty string when no progress can be made (end of pagination).
        """
        conv_c = 0
        ch_m = 0
        ch_id = 0
        if start_from:
            for part in start_from.split(","):
                if part.startswith("conversations_"):
                    try:
                        conv_c = int(part.replace("conversations_", ""))
                    except ValueError:
                        pass
                elif part.startswith("channels_"):
                    ch_parts = part.replace("channels_", "").split("_")
                    if len(ch_parts) >= 2:
                        try:
                            ch_m = int(ch_parts[0])
                            ch_id = int(ch_parts[1])
                        except ValueError:
                            pass

        new_conv_c = conv_c
        if conv_items:
            last_conv = conv_items[-1].get("conversation", {})
            sort_id = last_conv.get("sort_id", {})
            minor = sort_id.get("minor_id") if isinstance(sort_id, dict) else None
            new_conv_c = minor or last_conv.get("last_message_id", conv_c)

        new_ch_m = ch_m
        new_ch_id = ch_id
        if channel_items:
            last_ch = channel_items[-1].get("channel", {})
            sort_id = last_ch.get("sort_id", {})
            minor = sort_id.get("minor_id") if isinstance(sort_id, dict) else None
            cid = last_ch.get("channel_id") or last_ch.get("id")
            if minor is not None and cid:
                new_ch_m = minor
                new_ch_id = cid

        candidate = f"conversations_{new_conv_c},channels_{new_ch_m}_{new_ch_id}"
        if candidate == (start_from or "conversations_0,channels_0_0"):
            return ""
        return candidate

    async def fetch_dialogs(
        self,
        offset: int = 0,
        count: int = 20,
        filter: Optional[str] = None,
        start_from: Optional[str] = None
    ) -> List[VKDialogItem]:
        api_filter = filter or "all"
        is_items_api = True
        try:
            data = await api_client.messages_get_items(
                filter=api_filter,
                start_from=start_from or "conversations_0,channels_0_0",
                target_count=count
            )
        except Exception as e:
            logger.warning("messages.getItems unavailable (%s), falling back to messages.getConversations: %s", type(e), e)
            is_items_api = False
            data = await api_client.messages_get_conversations(offset=offset, count=count, extended=1, filter=filter)

        profiles = {p["id"]: p for p in data.get("profiles", [])}
        groups = {g["id"]: g for g in data.get("groups", [])}

        if is_items_api and ("conversations" in data or "channels" in data):
            conv_items = data.get("conversations", {}).get("items", [])
            channel_items = data.get("channels", {}).get("items", [])
            server_cursor = data.get("next_from")
            if server_cursor:
                self.last_next_from = server_cursor
            else:
                self.last_next_from = self._compute_next_cursor(
                    start_from=start_from,
                    conv_items=conv_items,
                    channel_items=channel_items
                )
        else:
            conv_items = data.get("items", [])
            channel_items = []
            if len(conv_items) >= count:
                self.last_next_from = f"conversations_{offset + count},channels_0_0"
            else:
                self.last_next_from = ""

        dialog_items: List[VKDialogItem] = []
        raw_to_cache: List[Dict[str, Any]] = []

        # 1. Parse standard conversations
        for item in conv_items:
            conv = item.get("conversation", {})
            last_msg = item.get("last_message", {})
            peer = conv.get("peer", {})
            peer_id = peer.get("id", 0)
            peer_type = peer.get("type", "user")

            title = "Диалог"
            avatar_url = ""
            is_online = False
            chat_settings = conv.get("chat_settings", {})

            impact_style = ""
            if peer_type == "user":
                u = profiles.get(peer_id, {})
                title = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or "Пользователь"
                avatar_url = u.get("photo_200") or u.get("photo_100") or ""
                is_online = bool(u.get("online", 0))
                if isinstance(u.get("impact_extra"), dict):
                    impact_style = str(u["impact_extra"].get("impact_style", "")).lower()
                elif u.get("impact_style"):
                    impact_style = str(u["impact_style"]).lower()

                if not impact_style:
                    cached_u = await db_manager.get_cached_user(peer_id)
                    if cached_u and cached_u.get("impact_style"):
                        impact_style = str(cached_u["impact_style"]).lower()
                    elif peer_id == 708902696:
                        impact_style = "zephyr"
            elif peer_type == "group":
                g_id = abs(peer_id)
                g = groups.get(g_id, {})
                title = g.get("name", "Сообщество")
                avatar_url = g.get("photo_200") or g.get("photo_100") or ""
            elif peer_type == "chat":
                title = chat_settings.get("title", "Беседа")
                photo = chat_settings.get("photo", {})
                avatar_url = photo.get("photo_200") or photo.get("photo_100") or ""

            msg_text = last_msg.get("text", "")
            if not msg_text and last_msg.get("attachments"):
                first_att = last_msg["attachments"][0].get("type", "вложение")
                msg_text = f"[{first_att}]"

            # For group chats (peer_id > 2000000000), prefix with author's first_name and last_name initial
            if peer_id > 2000000000 or peer_type == "chat":
                from_id = last_msg.get("from_id", 0)
                if from_id > 0 and from_id in profiles:
                    u_author = profiles[from_id]
                    fn = u_author.get("first_name", "").strip()
                    ln = u_author.get("last_name", "").strip()
                    initial = f" {ln[0]}." if ln else ""
                    prefix = f"{fn}{initial}: ".strip() + " "
                    msg_text = f"{prefix}{msg_text}"
                elif from_id < 0 and abs(from_id) in groups:
                    g_name = groups[abs(from_id)].get("name", "").strip()
                    if g_name:
                        msg_text = f"{g_name}: {msg_text}"

            sort_id = conv.get("sort_id", {})
            major_id = sort_id.get("major_id", 0) if isinstance(sort_id, dict) else 0
            is_pinned = bool(
                conv.get("is_pinned") or 
                major_id > 0 or 
                conv.get("pinned_at") or 
                chat_settings.get("is_pinned")
            )

            is_archived = bool(
                filter == "archive" or
                conv.get("is_archived") or
                conv.get("archive_time") or
                (isinstance(sort_id, dict) and sort_id.get("archive_id"))
            )

            push_settings = conv.get("push_settings", {})
            is_muted = bool(isinstance(push_settings, dict) and push_settings.get("disabled_forever") is True)
            is_channel = bool(conv.get("is_channel") or chat_settings.get("is_channel") or peer_type == "channel")

            d_item = VKDialogItem(
                peer_id=peer_id,
                title=title,
                avatar_url=avatar_url,
                last_message_text=msg_text,
                last_message_time=last_msg.get("date") or last_msg.get("time", 0),
                unread_count=conv.get("unread_count", 0),
                is_online=is_online,
                is_outgoing=bool(last_msg.get("out", 0)),
                is_read=last_msg.get("id") <= conv.get("out_read", 0) if last_msg.get("out") else True,
                is_pinned=is_pinned,
                is_archived=is_archived,
                is_muted=is_muted,
                is_channel=is_channel,
                impact_style=impact_style
            )
            dialog_items.append(d_item)
            raw_to_cache.append(d_item.model_dump())

        # 2. Parse channels from messages.getItems
        for item in channel_items:
            ch_data = item.get("channel", {})
            last_msg = item.get("last_message", {})
            ch_id = ch_data.get("channel_id") or ch_data.get("id") or 0
            if not ch_id:
                continue

            title = ch_data.get("title") or "Канал"
            avatar_url = ch_data.get("photo_base") or ""
            user_data = ch_data.get("user_data", {})
            read_state = user_data.get("read_state", {}) if isinstance(user_data, dict) else {}
            unread_count = read_state.get("unread_count", 0) if isinstance(read_state, dict) else 0

            notif = user_data.get("notification_settings", {}) if isinstance(user_data, dict) else {}
            is_muted = bool(isinstance(notif, dict) and notif.get("is_enabled") is False)
            is_archived = bool(user_data.get("is_archived", False)) if isinstance(user_data, dict) else False

            sort_id = ch_data.get("sort_id", {})
            major_id = sort_id.get("major_id", 0) if isinstance(sort_id, dict) else 0
            is_pinned = bool(
                ch_data.get("is_pinned") or
                user_data.get("is_pinned") or
                user_data.get("pinned_at") or
                ch_data.get("pinned_at") or
                major_id > 0
            )

            msg_text = last_msg.get("text", "")
            if not msg_text and last_msg.get("attachments"):
                first_att = last_msg["attachments"][0].get("type", "вложение")
                msg_text = f"[{first_att}]"

            msg_time = last_msg.get("time") or last_msg.get("date", 0)

            ch_item = VKDialogItem(
                peer_id=ch_id,
                title=title,
                avatar_url=avatar_url,
                last_message_text=msg_text,
                last_message_time=msg_time,
                unread_count=unread_count,
                is_online=False,
                is_outgoing=False,
                is_read=unread_count == 0,
                is_pinned=is_pinned,
                is_archived=is_archived,
                is_muted=is_muted,
                is_channel=True
            )
            dialog_items.append(ch_item)
            raw_to_cache.append(ch_item.model_dump())

        # Save to cache asynchronously
        await db_manager.save_dialogs(raw_to_cache)
        dialog_items.sort(key=lambda d: (1 if d.is_pinned else 0, d.last_message_time), reverse=True)
        return dialog_items

    async def check_conversation_archive(self, peer_id: int) -> bool:
        """Fetches conversation by ID and updates archive status in SQLite."""
        try:
            data = await api_client.messages_get_conversations_by_id(peer_ids=[peer_id])
            items = data.get("items", [])
            if items:
                conv = items[0]
                sort_id = conv.get("sort_id", {})
                is_archived = bool(
                    conv.get("is_archived") or
                    conv.get("archive_time") or
                    (isinstance(sort_id, dict) and sort_id.get("archive_id"))
                )
                push_settings = conv.get("push_settings", {})
                is_muted = bool(isinstance(push_settings, dict) and push_settings.get("disabled_forever") is True)
                import aiosqlite
                async with aiosqlite.connect(db_manager.db_path) as db:
                    await db.execute("UPDATE dialogs SET is_archived = ?, is_muted = ? WHERE peer_id = ?", (int(is_archived), int(is_muted), peer_id))
                    await db.commit()
                return is_archived
        except Exception as e:
            logger.warning("Failed to check archive for peer %s: %s", peer_id, e)
        return False

    async def save_dialog_new_message(self, peer_id: int, text: str, timestamp: int, is_out: bool, message_id: int = 0, attachments: Any = None, is_archived: Optional[bool] = None):
        """Saves a new incoming/outgoing message to SQLite and updates dialog record in a single fast transaction."""
        import aiosqlite
        import json
        async with aiosqlite.connect(db_manager.db_path) as db:
            # 1. Save to messages table
            if message_id:
                await db.execute("""
                    INSERT OR REPLACE INTO messages
                    (id, peer_id, from_id, sender_name, sender_avatar, date, text, out, is_read, attachments_json, fwd_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    message_id,
                    peer_id,
                    0 if is_out else peer_id,
                    "Вы" if is_out else "",
                    "",
                    timestamp,
                    text,
                    1 if is_out else 0,
                    1 if is_out else 0,
                    json.dumps(attachments or []),
                    "[]"
                ))

            # 2. Update dialogs table in SQLite
            unread_delta = 0 if is_out else 1
            if is_archived is not None:
                await db.execute("""
                    UPDATE dialogs
                    SET last_message_text = ?,
                        last_message_time = ?,
                        is_outgoing = ?,
                        unread_count = unread_count + ?,
                        is_archived = ?,
                        updated_at = ?
                    WHERE peer_id = ?
                """, (text, timestamp, int(is_out), unread_delta, int(is_archived), timestamp, peer_id))
            else:
                await db.execute("""
                    UPDATE dialogs
                    SET last_message_text = ?,
                        last_message_time = ?,
                        is_outgoing = ?,
                        unread_count = unread_count + ?,
                        updated_at = ?
                    WHERE peer_id = ?
                """, (text, timestamp, int(is_out), unread_delta, timestamp, peer_id))
            await db.commit()




dialogs_repo = DialogsRepository()
