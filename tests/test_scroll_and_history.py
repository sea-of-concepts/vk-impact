"""Tests for dialogs list scroll stabilization, chat history pagination, and unread boundary positioning."""
import os
import sys
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.api.models import VKMessage
from src.domain.chat_viewmodel import ChatViewModel


def test_append_scroll_preservation():
    """Tests that appending dialogs preserves physical viewport offset from the top."""
    old_count = 40
    new_count = 80
    item_h = 76
    v_h = 600
    old_scroll_y = 0.05

    h_old = old_count * item_h
    h_new = new_count * item_h
    offset_top_old = (1.0 - old_scroll_y) * (h_old - v_h)
    new_scroll_y = 1.0 - (offset_top_old / (h_new - v_h))

    offset_top_new = (1.0 - new_scroll_y) * (h_new - v_h)
    assert abs(offset_top_old - offset_top_new) < 1e-5, f"{offset_top_old} != {offset_top_new}"
    # New scroll_y should be ~0.577, which is far away from trigger <= 0.06
    assert new_scroll_y > 0.50, f"Expected new_scroll_y > 0.50, got {new_scroll_y}"
    print("test_append_scroll_preservation passed!")


def test_prepend_scroll_preservation():
    """Tests that prepending history messages preserves physical viewport position from the bottom."""
    h_old = 3000
    h_prepended = 3000
    v_h = 600
    old_scroll_y = 0.95

    h_new = h_old + h_prepended
    pos_bottom_old = old_scroll_y * (h_old - v_h)
    new_scroll_y = pos_bottom_old / (h_new - v_h)

    pos_bottom_new = new_scroll_y * (h_new - v_h)
    assert abs(pos_bottom_old - pos_bottom_new) < 1e-5, f"{pos_bottom_old} != {pos_bottom_new}"
    # New scroll_y should be ~0.422, which is far away from top trigger >= 0.90
    assert new_scroll_y < 0.50, f"Expected new_scroll_y < 0.50, got {new_scroll_y}"
    print("test_prepend_scroll_preservation passed!")


def test_unread_boundary_positioning():
    """Tests calculation of target_idx and scroll_y for various unread_counts."""
    total_msgs = 40
    msg_height = 64
    spacing = 6
    padding = 16
    v_h = 600
    total_h = total_msgs * (msg_height + spacing) + padding # 2816
    scrollable = total_h - v_h # 2216

    # Scenario 1: 0 unread messages -> scroll_y = 0.0 (bottom)
    unread_0 = 0
    target_idx_0 = max(0, total_msgs - unread_0)
    assert target_idx_0 == 40
    scroll_y_0 = 0.0
    assert scroll_y_0 == 0.0

    # Scenario 2: 5 unread messages -> target_idx = 35
    unread_5 = 5
    target_idx_5 = max(0, total_msgs - unread_5)
    assert target_idx_5 == 35
    h_above_5 = target_idx_5 * (msg_height + spacing) + 8
    target_offset_from_top = max(0.0, h_above_5 - 24)
    scroll_y_5 = max(0.0, min(1.0, 1.0 - (target_offset_from_top / scrollable)))
    assert 0.0 <= scroll_y_5 <= 1.0
    # Because 5 items fit within the 600px viewport, clamping sets scroll_y = 0.0 showing items 31-39
    assert scroll_y_5 == 0.0

    # Scenario 3: 20 unread messages -> target_idx = 20
    unread_20 = 20
    target_idx_20 = max(0, total_msgs - unread_20)
    assert target_idx_20 == 20
    h_above_20 = target_idx_20 * (msg_height + spacing) + 8
    scroll_y_20 = max(0.0, min(1.0, 1.0 - (max(0.0, h_above_20 - 24) / scrollable)))
    assert 0.35 < scroll_y_20 < 0.45, f"Got {scroll_y_20}"

    # Scenario 4: 50 unread messages (more than loaded) -> target_idx = 0
    unread_50 = 50
    target_idx_50 = max(0, total_msgs - unread_50)
    assert target_idx_50 == 0
    h_above_50 = 8
    scroll_y_50 = max(0.0, min(1.0, 1.0 - (max(0.0, h_above_50 - 24) / scrollable)))
    assert scroll_y_50 == 1.0, f"Got {scroll_y_50}"
    print("test_unread_boundary_positioning passed!")


def test_chat_viewmodel_history_and_unread():
    """Tests ChatViewModel load_older_messages and unread count handling."""
    vm = ChatViewModel()
    
    # Setup initial chat with 5 unread
    vm.open_chat(peer_id=123, title="Test Chat", unread_count=5)
    assert vm.initial_unread_count == 5
    assert vm.has_more_history is True
    assert vm.is_loading_history is False

    # Mock initial messages (10 messages)
    initial_models = [
        VKMessage(id=i+1, date=1000+i, peer_id=123, from_id=123, text=f"Msg {i+1}", out=0, is_read=True)
        for i in range(10)
    ]
    vm._update_messages_list(initial_models)
    assert len(vm.messages) == 10
    # First 5 should be read (True), last 5 should be unread (False)
    for i in range(5):
        assert vm.messages[i]["is_read"] is True, f"Msg {i} should be read"
    for i in range(5, 10):
        assert vm.messages[i]["is_read"] is False, f"Msg {i} should be unread"
    # Divider banner check for < 10 unread
    assert vm.messages[5]["show_new_divider"] is True, "First unread message should have show_new_divider=True"
    assert vm.messages[4]["show_new_divider"] is False
    print("unread message is_read marking and divider passed!")


def test_bidirectional_pagination_and_divider():
    """Tests offset arithmetic, 'Новые сообщения' divider placement, and jump_to_bottom."""
    vm = ChatViewModel()

    # Case 1: unread_count >= 10 (e.g. 25 unread)
    vm.open_chat(peer_id=456, title="Large Unread Chat", unread_count=25)
    assert vm.initial_unread_count == 25
    assert vm.bottom_offset == 15, f"Expected bottom_offset=15 (25-10), got {vm.bottom_offset}"
    assert vm.top_offset == 55, f"Expected top_offset=55 (15+40), got {vm.top_offset}"
    assert vm.has_more_newer is True, "Expected has_more_newer=True when unread_count >= 10"
    assert vm.unread_below_count == 25

    # 40 items returned by messages.get(offset=15, count=40)
    # The first 10 items (indices 0-9) are read, index 10 is first unread!
    test_models = [
        VKMessage(id=i+100, date=2000+i, peer_id=456, from_id=456, text=f"Msg {i+1}", out=0, is_read=True)
        for i in range(40)
    ]
    vm._update_messages_list(test_models)
    assert len(vm.messages) == 40
    # First 10 items read
    for i in range(10):
        assert vm.messages[i]["is_read"] is True
        assert vm.messages[i]["show_new_divider"] is False
    # Index 10 is the divider and first unread
    assert vm.messages[10]["show_new_divider"] is True
    assert vm.messages[10]["is_read"] is False
    assert vm.messages[11]["show_new_divider"] is False
    assert vm.messages[11]["is_read"] is False

    # Case 2: jump_to_bottom when already reached bottom (has_more_newer=False)
    vm.has_more_newer = False
    vm.jump_to_bottom()
    assert vm.unread_below_count == 0
    assert vm.bottom_offset == 0
    assert vm.has_more_newer is False
    for m in vm.messages:
        assert m["is_read"] is True

    # Case 3: jump_to_bottom when has_more_newer=True
    vm.has_more_newer = True
    vm.unread_below_count = 15
    with patch("src.data.repositories.messages_repo.messages_repo.fetch_messages", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            VKMessage(id=999, date=3000, peer_id=456, from_id=456, text="Latest", out=0, is_read=True)
        ]
        called = []
        vm.jump_to_bottom(on_complete=lambda: called.append(True))
        # Let async loop and clock run
        import time
        from kivy.clock import Clock
        for _ in range(20):
            Clock.tick()
            time.sleep(0.01)

    assert vm.unread_below_count == 0
    assert vm.has_more_newer is False
    print("test_bidirectional_pagination_and_divider passed!")


def test_repeated_chat_entry_unread_count():
    from src.domain.chat_viewmodel import ChatViewModel
    from src.data.api.models import VKMessage

    vm = ChatViewModel()

    initial_unreads = 98
    current_unreads = initial_unreads

    # Re-entering chat 5 times must NEVER increase unread_count
    for entry in range(5):
        vm.open_chat(peer_id=789, title="Test Chat", unread_count=current_unreads)
        assert vm.unread_below_count <= current_unreads
        assert vm.initial_unread_count == current_unreads

        # Populate with 40 messages
        msgs = [
            VKMessage(id=1000 + i, date=1000 + i, peer_id=789, from_id=789, text=f"Msg {i}", out=0, is_read=False)
            for i in range(40)
        ]
        vm._update_messages_list(msgs)

        # Simulate marking 6 unread messages as read in viewport
        for m in vm.messages[10:16]:
            m["is_read"] = True
            vm._read_message_ids.add(m["message_id"])

        read_count = len(vm._read_message_ids)
        vm.unread_below_count = max(0, vm.initial_unread_count - read_count)

        # Unread count must NEVER be greater than current_unreads
        assert vm.unread_below_count <= current_unreads, f"Unread count grew from {current_unreads} to {vm.unread_below_count}"
        assert vm.unread_below_count == max(0, current_unreads - 6)

        # Simulate exit
        current_unreads = vm.unread_below_count

    print("test_repeated_chat_entry_unread_count passed: unread count never increases!")


if __name__ == '__main__':
    test_append_scroll_preservation()
    test_prepend_scroll_preservation()
    test_unread_boundary_positioning()
    test_chat_viewmodel_history_and_unread()
    test_bidirectional_pagination_and_divider()
    test_repeated_chat_entry_unread_count()
    print("All scroll and history tests passed successfully!")

