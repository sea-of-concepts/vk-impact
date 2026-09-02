import os
import sys
import asyncio
import tempfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from src.core.config import AppConfig
from src.core.security import SecurityManager
from src.core.events import EventBus
from src.core.constants import EventType
from src.utils.formatters import format_timestamp, format_online_status, truncate_text
from src.data.api.models import VKUser, VKMessage, VKDialogItem
from src.data.database.db_manager import DatabaseManager


def test_formatters():
    """Tests string formatting utilities."""
    assert truncate_text("Short text", max_length=20) == "Short text"
    assert truncate_text("Very long text that exceeds limit", max_length=15) == "Very long te..."
    assert format_online_status(1) == "В сети"
    assert format_timestamp(0) == ""


def test_models():
    """Tests Pydantic models creation and serialization."""
    user = VKUser(
        id=1,
        first_name="Pavel",
        last_name="Durov",
        photo_200="https://vk.com/photo.jpg",
        online=1
    )
    assert user.full_name == "Pavel Durov"
    assert user.avatar_url == "https://vk.com/photo.jpg"

    msg = VKMessage(
        id=101,
        peer_id=1,
        from_id=1,
        date=1700000000,
        text="Hello world!",
        out=1
    )
    assert msg.is_outgoing is True


def test_security_manager():
    """Tests encryption and decryption of user session."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        sec = SecurityManager(
            key_file=tmp_path / "key.dat",
            session_file=tmp_path / "session.enc"
        )
        saved = sec.save_session(token="vk1.a.test_token_string", user_id=12345, extra_data={"foo": "bar"})
        assert saved is True

        loaded = sec.load_session()
        assert loaded is not None
        assert loaded["access_token"] == "vk1.a.test_token_string"
        assert loaded["user_id"] == 12345
        assert loaded["extra"]["foo"] == "bar"

        sec.clear_session()
        assert sec.load_session() is None


def test_event_bus():
    """Tests event bus subscription and event dispatch."""
    bus = EventBus()
    received = []

    def callback(peer_id, text, **kwargs):
        received.append((peer_id, text))

    bus.subscribe(EventType.NEW_MESSAGE, callback)
    bus.emit(EventType.NEW_MESSAGE, peer_id=100, text="Test Message")

    assert len(received) == 1
    assert received[0] == (100, "Test Message")

    bus.unsubscribe(EventType.NEW_MESSAGE, callback)
    bus.emit(EventType.NEW_MESSAGE, peer_id=100, text="Another Message")
    assert len(received) == 1


async def test_database_manager():
    """Tests asynchronous SQLite database caching."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = DatabaseManager(db_path=db_path)
        await db.init_db()

        # Test saving and getting dialogs
        dialogs = [{
            "peer_id": 1,
            "title": "Pavel Durov",
            "avatar_url": "https://vk.com/avatar.jpg",
            "last_message_text": "Hey there!",
            "last_message_time": 1700000000,
            "unread_count": 2,
            "is_online": True,
            "is_outgoing": False,
            "is_read": False
        }]
        await db.save_dialogs(dialogs)
        cached_dialogs = await db.get_cached_dialogs()
        assert len(cached_dialogs) == 1
        assert cached_dialogs[0]["peer_id"] == 1
        assert cached_dialogs[0]["title"] == "Pavel Durov"
        assert cached_dialogs[0]["unread_count"] == 2

        # Test saving and getting messages
        messages = [{
            "id": 1001,
            "peer_id": 1,
            "from_id": 1,
            "date": 1700000000,
            "text": "Hey there!",
            "out": 0,
            "is_read": 0,
            "attachments": [],
            "fwd_messages": []
        }]
        await db.save_messages(messages)
        cached_msgs = await db.get_cached_messages(peer_id=1)
        assert len(cached_msgs) == 1
        assert cached_msgs[0]["id"] == 1001
        assert cached_msgs[0]["text"] == "Hey there!"


if __name__ == "__main__":
    test_formatters()
    test_models()
    test_security_manager()
    test_event_bus()
    asyncio.run(test_database_manager())
    print("All architecture tests passed successfully!")
