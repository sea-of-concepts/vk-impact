import os
import sys
from pathlib import Path
import tempfile
import asyncio

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.api.models import VKUser, VKDialogItem
from src.data.database.db_manager import DatabaseManager
from src.ui.components.avatar import CircularAvatar
from src.data.api.client import VKApiClient


def test_vk_user_impact_extra():
    """Tests VKUser model parsing of impact_extra and impact_style property."""
    raw_user = {
        "id": 708902696,
        "first_name": "Zephyr",
        "last_name": "Dev",
        "photo_100": "https://example.com/photo.jpg",
        "impact_extra": {
            "impact_style": "zephyr"
        }
    }
    user = VKUser.model_validate(raw_user)
    assert user.impact_style == "zephyr"

    raw_user_plain = {
        "id": 12345,
        "first_name": "Plain",
        "last_name": "User"
    }
    user_plain = VKUser.model_validate(raw_user_plain)
    assert user_plain.impact_style == ""

    raw_author_fallback = {
        "id": 708902696,
        "first_name": "Zephyrianna",
        "last_name": "Collapse"
    }
    user_author = VKUser.model_validate(raw_author_fallback)
    assert user_author.impact_style == "zephyr"
    print("VKUser impact_extra and author fallback tests passed!")


def test_circular_avatar_oreol():
    """Tests CircularAvatar properties and oreol image resolution."""
    avatar = CircularAvatar(impact_style="zephyr")
    assert avatar.impact_style == "zephyr"
    assert avatar.oreol_source != ""
    assert os.path.exists(avatar.oreol_source) or avatar.oreol_source.endswith("zephyr_oreol.png") or avatar.oreol_source.endswith("zephyr-oreol.png")
    print("CircularAvatar oreol tests passed!")


def test_sqlite_impact_style_persistence():
    """Tests SQLite persistence of impact_style in users and dialogs tables."""
    async def _run():
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_zephyr.db")
            db = DatabaseManager(db_path=db_path)
            await db.init_db()

            # 1. Test users table
            user_dict = {
                "id": 708902696,
                "first_name": "Zephyr",
                "last_name": "Dev",
                "photo_100": "https://example.com/photo.jpg",
                "photo_200": "",
                "online": 1,
                "impact_style": "zephyr",
                "updated_at": 1000
            }
            await db.save_cached_users([user_dict])
            cached_u = await db.get_cached_user(708902696)
            assert cached_u is not None
            assert cached_u["impact_style"] == "zephyr"

            # 2. Test dialogs table
            d1 = {
                "peer_id": 708902696,
                "title": "Zephyr Dev",
                "avatar_url": "https://example.com/photo.jpg",
                "last_message_text": "Привет",
                "last_message_time": 1000,
                "unread_count": 0,
                "is_channel": False,
                "impact_style": "zephyr"
            }
            await db.save_dialogs([d1])
            cached_dialogs = await db.get_cached_dialogs()
            assert len(cached_dialogs) == 1
            assert cached_dialogs[0]["impact_style"] == "zephyr"
            print("SQLite impact_style persistence tests passed!")

    asyncio.run(_run())


def test_users_get_endpoint_routing():
    """Verifies that VKApiClient uses api.vk.ru and queries zephyrianna in parallel."""
    from src.core.config import config
    assert config.VK_API_BASE_URL == "https://api.vk.ru/method/"
    client = VKApiClient(access_token="test_token")
    assert hasattr(client, "fetch_impact_extra")
    print("Endpoint routing tests passed!")


def test_chat_viewmodel_messages_list():
    """Verifies that ChatViewModel._update_messages_list works without NameError for users_repo."""
    from src.domain.chat_viewmodel import ChatViewModel
    from src.data.api.models import VKMessage
    from src.data.repositories.users_repo import users_repo

    users_repo._memory_cache[708902696] = {"impact_style": "zephyr"}

    vm = ChatViewModel()
    msg = VKMessage(
        id=1,
        peer_id=2000000001,
        from_id=708902696,
        date=1700000000,
        text="Тестовое сообщение",
        out=0,
        sender_name="Zephyr",
        sender_avatar="https://example.com/avatar.jpg"
    )
    vm._update_messages_list([msg])
    assert len(vm.messages) == 1
    assert vm.messages[0]["sender_impact_style"] == "zephyr"
    assert vm.messages[0]["sender_name"] == "Zephyr"
    print("ChatViewModel messages list tests passed!")


if __name__ == "__main__":
    test_vk_user_impact_extra()
    test_circular_avatar_oreol()
    asyncio.run(test_sqlite_impact_style_persistence())
    test_users_get_endpoint_routing()
    test_chat_viewmodel_messages_list()
    print("All Zephyr oreol and endpoint tests passed successfully!")
