"""High-performance SQLite database manager with WAL mode and fast batch writes."""
import os
import json
import time
from typing import List, Dict, Any, Optional
import aiosqlite
from src.core.logger import logger


class DatabaseManager:
    """Manages local SQLite cache for dialogs, messages, users and custom folders."""

    def __init__(self, db_path: str = "cache/storage.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)

    async def init_db(self) -> None:
        """Initializes database tables with WAL mode and memory pragmas."""
        async with aiosqlite.connect(self.db_path) as db:
            # Enable high-performance SQLite WAL mode & memory optimizations
            await db.execute("PRAGMA journal_mode = WAL;")
            await db.execute("PRAGMA synchronous = NORMAL;")
            await db.execute("PRAGMA temp_store = MEMORY;")
            await db.execute("PRAGMA cache_size = -64000;")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS dialogs (
                    peer_id INTEGER PRIMARY KEY,
                    title TEXT,
                    avatar_url TEXT,
                    last_message_text TEXT,
                    last_message_time INTEGER,
                    unread_count INTEGER,
                    is_online INTEGER,
                    is_outgoing INTEGER,
                    is_read INTEGER,
                    is_pinned INTEGER DEFAULT 0,
                    is_archived INTEGER DEFAULT 0,
                    is_muted INTEGER DEFAULT 0,
                    is_channel INTEGER DEFAULT 0,
                    impact_style TEXT DEFAULT '',
                    updated_at INTEGER
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    peer_id INTEGER,
                    from_id INTEGER,
                    sender_name TEXT,
                    sender_avatar TEXT,
                    date INTEGER,
                    text TEXT,
                    out INTEGER,
                    is_read INTEGER,
                    attachments_json TEXT,
                    fwd_json TEXT
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_messages_peer_date ON messages(peer_id, date DESC)")
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS custom_folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    peer_ids_json TEXT DEFAULT '[]',
                    order_index INTEGER DEFAULT 0
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    photo_100 TEXT,
                    photo_200 TEXT,
                    online INTEGER DEFAULT 0,
                    impact_style TEXT DEFAULT '',
                    updated_at INTEGER DEFAULT 0
                )
            """)

            # Upgrade columns if needed
            try:
                await db.execute("ALTER TABLE dialogs ADD COLUMN is_pinned INTEGER DEFAULT 0")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE dialogs ADD COLUMN is_archived INTEGER DEFAULT 0")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE dialogs ADD COLUMN is_muted INTEGER DEFAULT 0")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE dialogs ADD COLUMN is_channel INTEGER DEFAULT 0")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE dialogs ADD COLUMN impact_style TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE users ADD COLUMN impact_style TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE messages ADD COLUMN sender_name TEXT")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE messages ADD COLUMN sender_avatar TEXT")
            except Exception:
                pass
            await db.commit()
            logger.info("Database initialized with WAL mode at %s", self.db_path)

    async def save_dialogs(self, dialogs: List[Dict[str, Any]]) -> None:
        """Saves or updates dialog items in local cache with fast batch executemany."""
        if not dialogs:
            return
        params = [
            (
                d.get("peer_id"),
                d.get("title"),
                d.get("avatar_url"),
                d.get("last_message_text"),
                d.get("last_message_time"),
                d.get("unread_count", 0),
                int(d.get("is_online", False)),
                int(d.get("is_outgoing", False)),
                int(d.get("is_read", True)),
                int(d.get("is_pinned", False)),
                int(d.get("is_archived", False)),
                int(d.get("is_muted", False)),
                int(d.get("is_channel", False)),
                d.get("impact_style", ""),
                d.get("last_message_time", 0)
            )
            for d in dialogs
        ]
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany("""
                INSERT INTO dialogs 
                (peer_id, title, avatar_url, last_message_text, last_message_time, unread_count, is_online, is_outgoing, is_read, is_pinned, is_archived, is_muted, is_channel, impact_style, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(peer_id) DO UPDATE SET
                    title = excluded.title,
                    avatar_url = excluded.avatar_url,
                    last_message_text = excluded.last_message_text,
                    last_message_time = excluded.last_message_time,
                    unread_count = CASE 
                        WHEN dialogs.is_read = 1 AND excluded.last_message_time <= dialogs.last_message_time THEN 0 
                        ELSE excluded.unread_count 
                    END,
                    is_online = excluded.is_online,
                    is_outgoing = excluded.is_outgoing,
                    is_read = CASE 
                        WHEN dialogs.is_read = 1 AND excluded.last_message_time <= dialogs.last_message_time THEN 1 
                        ELSE excluded.is_read 
                    END,
                    is_pinned = excluded.is_pinned,
                    is_archived = excluded.is_archived,
                    is_muted = excluded.is_muted,
                    is_channel = excluded.is_channel,
                    impact_style = excluded.impact_style,
                    updated_at = excluded.updated_at
            """, params)
            await db.commit()

    async def mark_dialog_as_read(self, peer_id: int) -> None:
        """Sets unread_count=0 and is_read=1 for dialog and marks messages read in SQLite."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE dialogs SET unread_count = 0, is_read = 1 WHERE peer_id = ?", (peer_id,))
            await db.execute("UPDATE messages SET is_read = 1 WHERE peer_id = ?", (peer_id,))
            await db.commit()

    async def update_dialog_unread(self, peer_id: int, unread_count: int) -> None:
        """Updates remaining unread_count and is_read status for dialog in SQLite."""
        async with aiosqlite.connect(self.db_path) as db:
            is_read = 1 if unread_count <= 0 else 0
            await db.execute(
                "UPDATE dialogs SET unread_count = ?, is_read = ? WHERE peer_id = ?",
                (max(0, unread_count), is_read, peer_id)
            )
            await db.commit()

    async def get_cached_dialogs(self) -> List[Dict[str, Any]]:
        """Retrieves cached dialogs ordered with pinned chats first, then by date descending."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM dialogs ORDER BY is_pinned DESC, last_message_time DESC")
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_cached_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves user profile from cache."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def save_cached_users(self, users: List[Dict[str, Any]]) -> None:
        """Saves or updates user profiles in local cache with timestamp."""
        if not users:
            return
        params = [
            (
                u.get("id"),
                u.get("first_name", ""),
                u.get("last_name", ""),
                u.get("photo_100", ""),
                u.get("photo_200", ""),
                int(u.get("online", 0)),
                u.get("impact_style", ""),
                int(u.get("updated_at", time.time()))
            )
            for u in users
        ]
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany("""
                INSERT OR REPLACE INTO users (id, first_name, last_name, photo_100, photo_200, online, impact_style, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, params)
            await db.commit()

    async def save_messages(self, messages: List[Dict[str, Any]]) -> None:
        """Saves message history items using fast batch executemany."""
        if not messages:
            return
        params = [
            (
                m.get("id"),
                m.get("peer_id"),
                m.get("from_id"),
                m.get("sender_name", ""),
                m.get("sender_avatar", ""),
                m.get("date"),
                m.get("text", ""),
                m.get("out", 0),
                int(m.get("is_read", True)),
                json.dumps(m.get("attachments", [])),
                json.dumps(m.get("fwd_messages", []))
            )
            for m in messages
        ]
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany("""
                INSERT OR REPLACE INTO messages
                (id, peer_id, from_id, sender_name, sender_avatar, date, text, out, is_read, attachments_json, fwd_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, params)
            await db.commit()

    async def get_cached_messages(self, peer_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves the most recent cached messages for a peer in chronological (ASC) order."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM (
                    SELECT * FROM messages WHERE peer_id = ? ORDER BY date DESC, id DESC LIMIT ?
                ) ORDER BY date ASC, id ASC
            """, (peer_id, limit))
            rows = await cursor.fetchall()
            messages = []
            for row in rows:
                item = dict(row)
                item["attachments"] = json.loads(item.get("attachments_json") or "[]")
                item["fwd_messages"] = json.loads(item.get("fwd_json") or "[]")
                messages.append(item)
            return messages

    async def get_custom_folders(self) -> List[Dict[str, Any]]:
        """Retrieves user-created custom folders."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM custom_folders ORDER BY order_index ASC, id ASC")
            rows = await cursor.fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["peer_ids"] = json.loads(item.get("peer_ids_json") or "[]")
                result.append(item)
            return result

    async def save_custom_folder(self, title: str, peer_ids: List[int], folder_id: Optional[int] = None) -> int:
        """Creates or updates a custom folder."""
        peer_ids_json = json.dumps(peer_ids)
        async with aiosqlite.connect(self.db_path) as db:
            if folder_id:
                await db.execute("""
                    UPDATE custom_folders 
                    SET title = ?, peer_ids_json = ?
                    WHERE id = ?
                """, (title, peer_ids_json, folder_id))
                await db.commit()
                return folder_id
            else:
                cursor = await db.execute("""
                    INSERT INTO custom_folders (title, peer_ids_json)
                    VALUES (?, ?)
                """, (title, peer_ids_json))
                await db.commit()
                return cursor.lastrowid

    async def delete_custom_folder(self, folder_id: int) -> None:
        """Deletes a custom folder by its SQLite primary key ID."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM custom_folders WHERE id = ?", (folder_id,))
            await db.commit()


db_manager = DatabaseManager()
