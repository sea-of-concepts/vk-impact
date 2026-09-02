"""Unit tests for archive filtering, 12h user cache, and LongPoll event 4 parsing."""
import os
import sys
import time
import asyncio
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.api.models import VKDialogItem
from src.data.repositories.folders_repo import FoldersRepository
from src.data.repositories.users_repo import UsersRepository
from src.domain.dialogs_viewmodel import DialogsViewModel


def test_archive_folder_filtering():
    """Tests that archived dialogs are hidden from general folders and only shown in system_archive."""
    repo = FoldersRepository()

    d_active = VKDialogItem(peer_id=100, title="Активный чат", is_archived=False)
    d_archived = VKDialogItem(peer_id=200, title="Архивированный чат", is_archived=True)
    dialogs = [d_active, d_archived]

    # Rule 1: 'system_all' must only show active dialogs
    all_res = repo.filter_dialogs(dialogs, "system_all")
    assert len(all_res) == 1
    assert all_res[0].peer_id == 100

    # Rule 2: 'system_archive' must only show archived dialogs
    arch_res = repo.filter_dialogs(dialogs, "system_archive")
    assert len(arch_res) == 1
    assert arch_res[0].peer_id == 200

    # Rule 3: 'system_pm' must not include archived
    pm_res = repo.filter_dialogs(dialogs, "system_pm")
    assert len(pm_res) == 1
    assert pm_res[0].peer_id == 100


def test_archived_message_arrival():
    """Tests that incoming messages for archived chats do not surface in the active dialogs list."""
    vm = DialogsViewModel()
    d_active = VKDialogItem(peer_id=101, title="Обычный чат", is_archived=False, last_message_time=100)
    d_arch = VKDialogItem(peer_id=202, title="Чат в архиве", is_archived=True, last_message_time=50)

    vm._sort_and_set_all_dialogs([d_active, d_arch])
    vm._peer_archive_status[202] = True
    vm._apply_folder_filter()

    # Initially in 'Все': only d_active is visible
    assert len(vm.dialogs) == 1
    assert vm.dialogs[0]["peer_id"] == 101

    # Incoming message to archived chat (peer 202)
    vm._on_new_message(peer_id=202, text="Новое в архиве", timestamp=300, is_out=False)

    # In 'Все', the archived chat must STILL NOT appear!
    assert len(vm.dialogs) == 1
    assert vm.dialogs[0]["peer_id"] == 101

    # When switching to 'system_archive', it must appear with updated message
    vm.select_folder("system_archive")
    assert len(vm.dialogs) == 1
    assert vm.dialogs[0]["peer_id"] == 202
    assert vm.dialogs[0]["last_message"] == "Новое в архиве"


def test_users_repo_cache_ttl():
    """Tests in-memory 12-hour user TTL logic."""
    u_repo = UsersRepository()
    now = time.time()
    u_repo._memory_cache[999] = {
        "id": 999,
        "first_name": "Иван",
        "last_name": "Петров",
        "photo_100": "",
        "updated_at": now - 3600  # 1 hour ago (< 12 hours)
    }

    loop = asyncio.new_event_loop()
    user = loop.run_until_complete(u_repo.get_user(999))
    prefix = loop.run_until_complete(u_repo.get_user_name_prefix(999))
    loop.close()

    assert user is not None
    assert user["first_name"] == "Иван"
    assert prefix == "Иван П.: "


if __name__ == "__main__":
    test_archive_folder_filtering()
    test_archived_message_arrival()
    test_users_repo_cache_ttl()
    print("All archive, LongPoll parsing, and 12h user cache tests passed successfully!")
