"""Unit tests for folder filtering and real-time log collector."""
import os
import sys
import asyncio
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.api.models import VKDialogItem
from src.data.repositories.folders_repo import FoldersRepository, FolderItem
from src.core.log_collector import LogCollector


def test_folders_filtering():
    """Tests system folder filtering rules according to user specifications."""
    repo = FoldersRepository()

    # Sample dialog items
    d_user = VKDialogItem(peer_id=12345, title="Иван Иванов")
    d_chat = VKDialogItem(peer_id=2000000005, title="Беседа одноклассников")
    d_group = VKDialogItem(peer_id=-98765, title="Паблик Мемы", is_channel=False)
    d_channel = VKDialogItem(peer_id=-112233, title="Типичный ролевик", is_channel=True)
    
    dialogs = [d_user, d_chat, d_group, d_channel]

    # Rule 1: 'system_all' or None -> returns all dialogs (including channels)
    assert len(repo.filter_dialogs(dialogs, "system_all")) == 4
    assert len(repo.filter_dialogs(dialogs, None)) == 4

    # Rule 2: 'system_chats' -> peer_id > 2000000000 and not is_channel
    chats = repo.filter_dialogs(dialogs, "system_chats")
    assert len(chats) == 1
    assert chats[0].peer_id == 2000000005

    # Rule 3: 'system_pm' -> 0 < peer_id < 2000000000 and not is_channel
    pm = repo.filter_dialogs(dialogs, "system_pm")
    assert len(pm) == 1
    assert pm[0].peer_id == 12345

    # Rule 4: 'system_groups' -> peer_id < 0 and not is_channel
    groups = repo.filter_dialogs(dialogs, "system_groups")
    assert len(groups) == 1
    assert groups[0].peer_id == -98765

    # Rule 5: 'system_channels' -> is_channel == True
    channels = repo.filter_dialogs(dialogs, "system_channels")
    assert len(channels) == 1
    assert channels[0].title == "Типичный ролевик"
    assert channels[0].is_channel is True

    # Rule 6: 'system_archive' and 'system_business' -> empty for now
    assert len(repo.filter_dialogs(dialogs, "system_archive")) == 0
    assert len(repo.filter_dialogs(dialogs, "system_business")) == 0


def test_custom_folder_filtering():
    """Tests custom user folder matching by peer_ids."""
    repo = FoldersRepository()
    d1 = VKDialogItem(peer_id=100, title="Друг 1")
    d2 = VKDialogItem(peer_id=200, title="Друг 2")
    d3 = VKDialogItem(peer_id=300, title="Коллега")
    dialogs = [d1, d2, d3]

    # Simulate custom folder
    custom_f = FolderItem(id="custom_1", title="Избранное", is_system=False, peer_ids=[100, 300])
    repo._custom_folders = [custom_f]

    filtered = repo.filter_dialogs(dialogs, "custom_1")
    assert len(filtered) == 2
    assert {f.peer_id for f in filtered} == {100, 300}


def test_log_collector():
    """Tests in-memory log buffer and categorization."""
    collector = LogCollector(max_entries=10)

    collector.log_api("messages.getConversations", status=200, duration_ms=120.5)
    collector.log_longpoll("New Message", details="peer=123")
    collector.log_media("Avatar", "https://vk.com/photo.jpg", is_hit=True)

    all_logs = collector.get_entries("Все")
    assert len(all_logs) == 3

    api_logs = collector.get_entries("API")
    assert len(api_logs) == 1
    assert "messages.getConversations" in api_logs[0]["message"]

    lp_logs = collector.get_entries("LongPoll")
    assert len(lp_logs) == 1
    assert "New Message" in lp_logs[0]["message"]

    media_logs = collector.get_entries("Media")
    assert len(media_logs) == 1
    assert "HIT" in media_logs[0]["message"]


def test_pinned_sorting_and_local_reorder():
    """Tests that pinned dialogs stay at top and unpinned rise below pinned."""
    from src.domain.dialogs_viewmodel import DialogsViewModel
    vm = DialogsViewModel()

    d_pin = VKDialogItem(peer_id=1, title="Закреп", is_pinned=True, last_message_time=100)
    d_norm1 = VKDialogItem(peer_id=2, title="Обычный 1", is_pinned=False, last_message_time=200)
    d_norm2 = VKDialogItem(peer_id=3, title="Обычный 2", is_pinned=False, last_message_time=150)

    vm._sort_and_set_all_dialogs([d_norm1, d_pin, d_norm2])
    assert vm._all_dialogs[0].peer_id == 1
    assert vm._all_dialogs[1].peer_id == 2

    # Receive new message in d_norm2
    vm._on_new_message(peer_id=3, text="Привет", timestamp=300, is_out=False)
    # Must NOT overtake pinned chat!
    assert vm._all_dialogs[0].peer_id == 1
    assert vm._all_dialogs[1].peer_id == 3
    assert vm._all_dialogs[2].peer_id == 2


if __name__ == "__main__":
    test_folders_filtering()
    test_custom_folder_filtering()
    test_log_collector()
    test_pinned_sorting_and_local_reorder()
    print("All folder, log collector, and pinned sorting unit tests passed successfully!")

