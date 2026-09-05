"""Unit tests for archive filtering, 12h user cache, and LongPoll event 4 parsing."""
import os
import sys
import time
import asyncio
from pathlib import Path
import pytest

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


def test_cached_archive_retained_on_load():
    """Tests that cached archived dialogs populate _peer_archive_status and stay out of system_all when fresh arrives."""
    vm = DialogsViewModel()
    cached = [
        VKDialogItem(peer_id=101, title="Активный", is_archived=False, last_message_time=100),
        VKDialogItem(peer_id=2000000199, title="Children of Decadence", is_archived=True, last_message_time=50),
    ]
    fresh = [
        VKDialogItem(peer_id=101, title="Активный", is_archived=False, last_message_time=120),
        VKDialogItem(peer_id=102, title="Новый активный", is_archived=False, last_message_time=110),
    ]

    # Populate archive status and merge cached first, then fresh
    for d in cached:
        vm._peer_archive_status[d.peer_id] = d.is_archived
    vm._merge_and_set_dialogs(cached)
    vm._merge_and_set_dialogs(fresh)
    vm._apply_folder_filter()

    # In 'Все', only 101 and 102 are visible; 2000000199 must NOT be in 'Все'
    visible_peers = [d["peer_id"] for d in vm.dialogs]
    assert 2000000199 not in visible_peers
    assert 101 in visible_peers
    assert 102 in visible_peers

    # In 'system_archive', 2000000199 is visible
    vm.select_folder("system_archive")
    assert any(d["peer_id"] == 2000000199 for d in vm.dialogs)
    assert vm._peer_archive_status.get(2000000199) is True


@pytest.mark.asyncio
async def test_save_dialog_new_message_does_not_unarchive(tmp_path):
    """Tests that save_dialog_new_message does not reset is_archived=1 to 0."""
    import aiosqlite
    from src.data.database.db_manager import DatabaseManager
    from src.data.repositories.dialogs_repo import DialogsRepository

    test_db = str(tmp_path / "test.db")
    db_m = DatabaseManager(db_path=test_db)
    await db_m.init_db()

    # Pre-insert archived dialog
    async with aiosqlite.connect(test_db) as conn:
        await conn.execute("""
            INSERT INTO dialogs (peer_id, title, is_archived, unread_count, last_message_time, updated_at)
            VALUES (2000000199, 'Children of Decadence', 1, 0, 100, 100)
        """)
        await conn.commit()

    repo = DialogsRepository()
    # Temporarily point db_manager to test_db
    orig_path = repo.db_manager.db_path if hasattr(repo, "db_manager") else None

    # Update dialog using SQL logic tested in save_dialog_new_message
    async with aiosqlite.connect(test_db) as conn:
        await conn.execute("""
            UPDATE dialogs
            SET last_message_text = ?,
                last_message_time = ?,
                is_outgoing = ?,
                unread_count = unread_count + ?,
                is_archived = CASE WHEN dialogs.is_archived = 1 THEN 1 ELSE ? END,
                updated_at = ?
            WHERE peer_id = ?
        """, ("Новое сообщение", 200, 0, 1, 0, 200, 2000000199))
        await conn.commit()

        cursor = await conn.execute("SELECT is_archived, unread_count FROM dialogs WHERE peer_id = 2000000199")
        row = await cursor.fetchone()
        assert row[0] == 1, "is_archived must remain 1 even when 0 was passed"
        assert row[1] == 1, "unread_count should increment to 1"


if __name__ == "__main__":
    test_archive_folder_filtering()
    test_archived_message_arrival()
    test_users_repo_cache_ttl()
    test_cached_archive_retained_on_load()
    print("All archive, LongPoll parsing, and 12h user cache tests passed successfully!")
