"""Unit tests for messages.getItems response parsing, channels handling and caching."""
import os
import sys
import json
import asyncio
import tempfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.api.models import VKDialogItem, VKMessage
from src.data.repositories.dialogs_repo import DialogsRepository
from src.data.repositories.folders_repo import FoldersRepository
from src.data.database.db_manager import DatabaseManager


def test_channel_parsing():
    """Tests parsing channels from channel.md JSON structure."""
    channel_json_str = """
    {
        "channel": {
            "channel_id": -230887526,
            "sort_id": {
                "major_id": 1,
                "minor_id": 1788446457
            },
            "user_data": {
                "is_archived": false,
                "is_member": true,
                "notification_settings": {
                    "is_enabled": false
                },
                "read_state": {
                    "unread_count": 24
                }
            },
            "photo_base": "https://sun9-53.vkuserphoto.ru/test_avatar.jpg",
            "title": "Типичный ролевик〔ТР+〕"
        },
        "last_message": {
            "channel_id": -230887526,
            "cmid": 462,
            "time": 1788446457,
            "text": "Тестовое сообщение канала",
            "mute_notifications": true,
            "is_pinned": true
        }
    }
    """
    channel_item = json.loads(channel_json_str)
    
    repo = DialogsRepository()
    mock_data = {
        "conversations": {
            "items": [
                {
                    "conversation": {
                        "peer": {"id": 12345, "type": "user"},
                        "unread_count": 2,
                        "push_settings": {"disabled_forever": False}
                    },
                    "last_message": {
                        "id": 101,
                        "date": 1788446000,
                        "text": "Привет от пользователя"
                    }
                }
            ]
        },
        "channels": {
            "items": [channel_item]
        },
        "profiles": [
            {"id": 12345, "first_name": "Иван", "last_name": "Иванов", "photo_100": "https://vk.com/u1.jpg"}
        ],
        "groups": [],
        "next_from": "conversations_20,channels_1"
    }

    conv_items = mock_data["conversations"]["items"]
    channel_items = mock_data["channels"]["items"]

    dialog_items = []
    # 1. Parse conversations
    for item in conv_items:
        conv = item["conversation"]
        last_msg = item["last_message"]
        d = VKDialogItem(
            peer_id=conv["peer"]["id"],
            title="Иван Иванов",
            avatar_url="https://vk.com/u1.jpg",
            last_message_text=last_msg["text"],
            last_message_time=last_msg["date"],
            unread_count=conv["unread_count"],
            is_channel=False
        )
        dialog_items.append(d)

    # 2. Parse channels
    for item in channel_items:
        ch_data = item["channel"]
        last_msg = item["last_message"]
        user_data = ch_data.get("user_data", {})
        read_state = user_data.get("read_state", {})
        notif = user_data.get("notification_settings", {})
        sort_id = ch_data.get("sort_id", {})
        major_id = sort_id.get("major_id", 0)

        ch = VKDialogItem(
            peer_id=ch_data["channel_id"],
            title=ch_data["title"],
            avatar_url=ch_data["photo_base"],
            last_message_text=last_msg["text"],
            last_message_time=last_msg["time"],
            unread_count=read_state.get("unread_count", 0),
            is_muted=bool(isinstance(notif, dict) and notif.get("is_enabled") is False),
            is_pinned=bool(ch_data.get("is_pinned") or user_data.get("is_pinned") or major_id > 0),
            is_channel=True
        )
        dialog_items.append(ch)

    assert len(dialog_items) == 2
    # Verify regular conversation
    assert dialog_items[0].peer_id == 12345
    assert dialog_items[0].is_channel is False
    assert dialog_items[0].is_muted is False

    # Verify channel (notification_settings: is_enabled=false -> is_muted=True)
    assert dialog_items[1].peer_id == -230887526
    assert dialog_items[1].title == "Типичный ролевик〔ТР+〕"
    assert dialog_items[1].avatar_url == "https://sun9-53.vkuserphoto.ru/test_avatar.jpg"
    assert dialog_items[1].unread_count == 24
    assert dialog_items[1].is_muted is True
    assert dialog_items[1].is_pinned is True
    assert dialog_items[1].is_channel is True

    # Test channel with is_enabled=True -> is_muted=False
    notif_enabled = {"is_enabled": True}
    ch_unmuted = VKDialogItem(
        peer_id=-999,
        title="Канал с включенными уведомлениями",
        is_muted=bool(isinstance(notif_enabled, dict) and notif_enabled.get("is_enabled") is False),
        is_channel=True
    )
    assert ch_unmuted.is_muted is False
    print("Channel parsing and notification_settings tests passed!")


async def test_sqlite_channel_storage():
    """Tests saving and retrieving is_channel in SQLite."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_channels.db")
        db = DatabaseManager(db_path=db_path)
        await db.init_db()

        # Save dialogs with channel
        d1 = {
            "peer_id": 100,
            "title": "Обычный чат",
            "avatar_url": "",
            "last_message_text": "Привет",
            "last_message_time": 1000,
            "unread_count": 0,
            "is_channel": False
        }
        d2 = {
            "peer_id": -200,
            "title": "Мой канал",
            "avatar_url": "https://example.com/avatar.jpg",
            "last_message_text": "Пост",
            "last_message_time": 2000,
            "unread_count": 5,
            "is_channel": True
        }
        await db.save_dialogs([d1, d2])

        cached = await db.get_cached_dialogs()
        assert len(cached) == 2
        cached_by_peer = {r["peer_id"]: r for r in cached}

        assert bool(cached_by_peer[100]["is_channel"]) is False
        assert bool(cached_by_peer[-200]["is_channel"]) is True

        # Test mark_dialog_as_read
        await db.mark_dialog_as_read(-200)
        cached_after_read = await db.get_cached_dialogs()
        read_peer = {r["peer_id"]: r for r in cached_after_read}[-200]
        assert read_peer["unread_count"] == 0
        assert read_peer["is_read"] == 1

        # Test that re-saving dialog with same timestamp does NOT overwrite unread_count
        d2_incoming = {
            "peer_id": -200,
            "title": "Мой канал",
            "avatar_url": "https://example.com/avatar.jpg",
            "last_message_text": "Пост",
            "last_message_time": 2000,
            "unread_count": 5, # Old value from server
            "is_channel": True
        }
        await db.save_dialogs([d2_incoming])
        cached_after_resave = await db.get_cached_dialogs()
        still_read = {r["peer_id"]: r for r in cached_after_resave}[-200]
        assert still_read["unread_count"] == 0
        assert still_read["is_read"] == 1

        # Test that truly new message DOES update unread_count
        d2_newer = {
            "peer_id": -200,
            "title": "Мой канал",
            "avatar_url": "https://example.com/avatar.jpg",
            "last_message_text": "Новый Пост",
            "last_message_time": 3000,
            "unread_count": 1,
            "is_channel": True
        }
        await db.save_dialogs([d2_newer])
        cached_after_new = await db.get_cached_dialogs()
        new_peer = {r["peer_id"]: r for r in cached_after_new}[-200]
        assert new_peer["unread_count"] == 1
        print("SQLite is_channel storage and mark_as_read tests passed!")


def test_channel_history_normalization():
    """Tests normalising channel message keys (cmid -> id, time -> date)."""
    raw_channel_msg = {
        "channel_id": -230887526,
        "cmid": 454,
        "author_id": -230887526,
        "time": 1787994116,
        "text": "30.08.2026",
        "attachments": []
    }
    item = dict(raw_channel_msg)
    if "cmid" in item and "id" not in item:
        item["id"] = item["cmid"]
    if "author_id" in item and "from_id" not in item:
        item["from_id"] = item["author_id"]
    if "time" in item and "date" not in item:
        item["date"] = item["time"]
    if "channel_id" in item and "peer_id" not in item:
        item["peer_id"] = item["channel_id"]

    msg = VKMessage.model_validate(item)
    assert msg.id == 454
    assert msg.peer_id == -230887526
    assert msg.from_id == -230887526
    assert msg.date == 1787994116
    assert msg.text == "30.08.2026"
    print("Channel history normalization tests passed!")


def test_channel_notification_button_logic():
    """Tests channel notification button text and mode toggling logic."""
    from src.domain.chat_viewmodel import ChatViewModel
    vm = ChatViewModel()
    
    # When channel is opened with notifications disabled (is_muted=True)
    vm.open_chat(peer_id=-100, title="Тест Канал", is_channel=True, is_muted=True)
    assert vm.is_channel is True
    assert vm.is_muted is True
    assert vm.notification_button_text == "Включить уведомления"

    # When notifications are enabled (is_muted=False)
    vm.open_chat(peer_id=-100, title="Тест Канал", is_channel=True, is_muted=False)
    assert vm.is_channel is True
    assert vm.is_muted is False
    assert vm.notification_button_text == "Выключить уведомления"
    print("Channel notification button logic tests passed!")


def test_get_items_cursor_pagination():
    """Tests cursor-based pagination passing start_from from next_from."""
    from unittest.mock import AsyncMock, patch
    from src.data.api.client import api_client

    repo = DialogsRepository()
    mock_cursor = "conversations_8698758,channels_1788348817_-230844593"

    async def _run():
        # First page call
        with patch.object(api_client, "messages_get_items", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "conversations": {"count": 1, "items": [{"conversation": {"peer": {"id": 1, "type": "user"}}, "last_message": {"text": "hello"}}]},
                "channels": {"count": 0, "items": []},
                "next_from": mock_cursor
            }
            items = await repo.fetch_dialogs(count=20)
            assert len(items) == 1
            assert repo.last_next_from == mock_cursor
            # Ensure start_from was conversations_0,channels_0_0 on initial call
            mock_get.assert_called_once_with(filter="all", start_from="conversations_0,channels_0_0", target_count=20)

        # Second page call passing the cursor
        with patch.object(api_client, "messages_get_items", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "conversations": {"count": 1, "items": [{"conversation": {"peer": {"id": 2, "type": "user"}}, "last_message": {"text": "world"}}]},
                "channels": {"count": 0, "items": []},
                "next_from": ""  # No more items
            }
            items2 = await repo.fetch_dialogs(count=20, start_from=repo.last_next_from)
            assert len(items2) == 1
            assert repo.last_next_from == ""
            # Ensure start_from received the exact cursor
            mock_get.assert_called_once_with(filter="all", start_from=mock_cursor, target_count=20)

    asyncio.run(_run())
    print("test_get_items_cursor_pagination passed!")


if __name__ == "__main__":
    test_channel_parsing()
    asyncio.run(test_sqlite_channel_storage())
    test_channel_history_normalization()
    test_channel_notification_button_logic()
    test_get_items_cursor_pagination()
    print("All messages.getItems & channels tests passed successfully!")
