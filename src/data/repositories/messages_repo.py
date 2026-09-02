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
                fwd_messages=r.get("fwd_messages", [])
            ))
        return messages

    async def fetch_messages(self, peer_id: int, offset: int = 0, count: int = 40) -> List[VKMessage]:
        """Fetches messages with sender profiles from VK API and caches them."""
        data = await api_client.messages_get_history(peer_id=peer_id, offset=offset, count=count, extended=1)
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

        models: List[VKMessage] = []
        for item in items:
            m = VKMessage.model_validate(item)
            from_id = m.from_id
            if from_id > 0 and from_id in profiles:
                m.sender_name = profiles[from_id]["name"]
                m.sender_avatar = profiles[from_id]["avatar"]
            elif from_id < 0 and abs(from_id) in groups:
                m.sender_name = groups[abs(from_id)]["name"]
                m.sender_avatar = groups[abs(from_id)]["avatar"]
            models.append(m)

        # Cache to database
        raw_to_cache = [m.model_dump() for m in models]
        await db_manager.save_messages(raw_to_cache)
        # Return in ascending chronological order (oldest to newest)
        models.sort(key=lambda m: (m.date, m.id))
        return models

    async def send_message(self, peer_id: int, text: str) -> int:
        """Sends a text message and returns the newly assigned message_id."""
        msg_id = await api_client.messages_send(peer_id=peer_id, message=text)
        return msg_id

    async def mark_as_read(self, peer_id: int, start_message_id: Optional[int] = None) -> int:
        """Marks incoming messages in chat as read."""
        return await api_client.messages_mark_as_read(peer_id=peer_id, start_message_id=start_message_id)


messages_repo = MessagesRepository()
