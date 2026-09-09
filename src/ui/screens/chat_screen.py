from kivy.properties import ObjectProperty, BooleanProperty, DictProperty
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.utils import platform
from kivymd.uix.screen import MDScreen
from src.domain.chat_viewmodel import ChatViewModel
from src.core.constants import ScreenName


class ChatScreen(MDScreen):
    """View displaying single chat message stream with bidirectional pagination, unread tracking, and scroll fab."""
    vm = ObjectProperty(None)
    is_at_bottom = BooleanProperty(True)
    replying_to = DictProperty(None, allownone=True)

    def __init__(self, **kwargs):
        self.vm = ChatViewModel()
        super().__init__(**kwargs)
        self.name = ScreenName.CHAT
        self._has_scrolled_to_initial = False
        self.vm.bind(messages=self._on_messages_changed)

    def on_touch_down(self, touch):
        """Allows ScrollBottomFab to intercept touch even during scroll momentum/animation."""
        fab = self.ids.get("fab_scroll_bottom")
        if fab and not fab.disabled and fab.opacity > 0 and fab.collide_point(*touch.pos):
            if fab.on_touch_down(touch):
                return True
        return super().on_touch_down(touch)

    def setup_chat(self, peer_id: int, title: str, avatar_url: str = "", is_channel: bool = False, is_muted: bool = False, unread_count: int = 0):
        """Initializes chat viewmodel for the selected conversation."""
        self._has_scrolled_to_initial = False
        self.is_at_bottom = True
        self.vm.open_chat(
            peer_id=peer_id,
            title=title,
            avatar_url=avatar_url,
            is_channel=is_channel,
            is_muted=is_muted,
            unread_count=unread_count
        )

    def _on_messages_changed(self, *args):
        """Scrolls to the boundary of read/unread messages or bottom upon initial load."""
        if not self._has_scrolled_to_initial and self.vm.messages:
            Clock.schedule_once(lambda dt: self.scroll_to_unread_or_bottom(), 0.05)

    def scroll_to_unread_or_bottom(self):
        """Positions viewport at the first unread message if unread_count > 0, otherwise at the latest message."""
        rv = self.ids.get("rv_messages")
        if not rv or not self.vm.messages:
            return

        unread_count = getattr(self.vm, "initial_unread_count", 0)
        total_msgs = len(self.vm.messages)

        if unread_count <= 0:
            rv.scroll_y = 0.0
            self._has_scrolled_to_initial = True
            self.is_at_bottom = True
            self.vm.unread_below_count = 0
            if self.vm.messages:
                self.vm.highest_read_cmid = self.vm.messages[-1].get("message_id", 0)
            return

        if unread_count >= 10:
            target_idx = 10
        else:
            target_idx = max(0, total_msgs - unread_count)

        spacing = dp(6)
        padding_top = dp(8)
        padding_bottom = dp(8)

        total_h = sum(
            (m.get("msg_size", [None, dp(64)])[1] or dp(64)) + spacing
            for m in self.vm.messages
        ) + padding_top + padding_bottom

        h_above = sum(
            (self.vm.messages[i].get("msg_size", [None, dp(64)])[1] or dp(64)) + spacing
            for i in range(target_idx)
        ) + padding_top

        v_h = rv.height or dp(600)
        if total_h <= v_h:
            rv.scroll_y = 0.0
            self.is_at_bottom = True
        else:
            scrollable = total_h - v_h
            target_offset_from_top = max(0.0, h_above - dp(24))
            target_scroll_y = 1.0 - (target_offset_from_top / scrollable)
            rv.scroll_y = max(0.0, min(1.0, target_scroll_y))
            self.is_at_bottom = (rv.scroll_y <= 0.03)

        self._has_scrolled_to_initial = True
        self._update_viewport_read_status(rv.scroll_y)

    def _update_viewport_read_status(self, scroll_y: float):
        """Updates highest_read_cmid for messages in viewport and computes unread_below_count."""
        rv = self.ids.get("rv_messages")
        if not rv or not self.vm.messages:
            return

        spacing = dp(6)
        padding_top = dp(8)
        padding_bottom = dp(8)
        v_h = rv.height or dp(600)

        if scroll_y <= 0.03:
            self.is_at_bottom = True
            self.vm.unread_below_count = 0
            if self.vm.messages:
                last_id = self.vm.messages[-1].get("message_id", 0)
                if last_id > self.vm.highest_read_cmid:
                    self.vm.highest_read_cmid = last_id
            for m in self.vm.messages:
                m["is_read"] = True
                if not m.get("is_outgoing", False):
                    self.vm._read_message_ids.add(m.get("message_id", 0))
            return

        self.is_at_bottom = False

        total_h = sum(
            (m.get("msg_size", [None, dp(64)])[1] or dp(64)) + spacing
            for m in self.vm.messages
        ) + padding_top + padding_bottom

        if total_h <= v_h:
            self.is_at_bottom = True
            self.vm.unread_below_count = 0
            return

        scrollable = total_h - v_h
        top_pos = (1.0 - scroll_y) * scrollable
        bottom_pos = top_pos + v_h

        accum = padding_top
        highest_seen = self.vm.highest_read_cmid
        for m in self.vm.messages:
            m_h = (m.get("msg_size", [None, dp(64)])[1] or dp(64)) + spacing
            m_top = accum
            accum += m_h

            if m_top <= bottom_pos:
                if not m.get("is_outgoing", False):
                    msg_id = m.get("message_id", 0)
                    if msg_id > highest_seen:
                        highest_seen = msg_id
                    if not m.get("is_read", False):
                        m["is_read"] = True
                        self.vm._read_message_ids.add(msg_id)

        self.vm.highest_read_cmid = highest_seen
        read_count = len(self.vm._read_message_ids)
        self.vm.unread_below_count = max(0, self.vm.initial_unread_count - read_count)

    def on_rv_scroll(self, scroll_y: float):
        """Handles scrolling: viewport tracking, unread counting, and bidirectional history loading."""
        rv = self.ids.get("rv_messages")
        if not rv or not self.vm.messages:
            return

        self._update_viewport_read_status(scroll_y)

        spacing = dp(6)
        padding_top = dp(8)
        padding_bottom = dp(8)
        v_h = rv.height or dp(600)

        # UP: Load older messages
        if scroll_y >= 0.90 and len(self.vm.messages) >= 20 and not self.vm.is_loading_history and self.vm.has_more_older:
            def _on_older_ready(rv_older):
                if rv_older and rv:
                    curr_sy = rv.scroll_y
                    h_old = sum(
                        (m.get("msg_size", [None, dp(64)])[1] or dp(64)) + spacing
                        for m in self.vm.messages
                    ) + padding_top + padding_bottom
                    h_prepended = sum(
                        (m.get("msg_size", [None, dp(64)])[1] or dp(64)) + spacing
                        for m in rv_older
                    )
                    h_new = h_old + h_prepended
                    if h_old > v_h and h_new > v_h:
                        pos_from_bottom = curr_sy * (h_old - v_h)
                        new_scroll_y = max(0.0, min(1.0, pos_from_bottom / (h_new - v_h)))
                        if getattr(rv, "_anim_y", None):
                            rv._anim_y.stop(rv)
                            rv._anim_y = None
                        self.vm.messages = rv_older + list(self.vm.messages)
                        rv.scroll_y = new_scroll_y
                        if hasattr(rv, "_update_effect_y_bounds"):
                            rv._update_effect_y_bounds()
                        Clock.schedule_once(lambda dt: setattr(rv, "scroll_y", new_scroll_y), 0)
                    else:
                        self.vm.messages = rv_older + list(self.vm.messages)

            self.vm.load_older_messages(on_data_ready=_on_older_ready)

        # DOWN: Load newer messages
        elif scroll_y <= 0.10 and not self.is_at_bottom and not self.vm.is_loading_history and self.vm.has_more_newer:
            def _on_newer_ready(rv_newer):
                if rv_newer and rv:
                    curr_sy = rv.scroll_y
                    h_old = sum(
                        (m.get("msg_size", [None, dp(64)])[1] or dp(64)) + spacing
                        for m in self.vm.messages
                    ) + padding_top + padding_bottom
                    h_appended = sum(
                        (m.get("msg_size", [None, dp(64)])[1] or dp(64)) + spacing
                        for m in rv_newer
                    )
                    h_new = h_old + h_appended
                    if h_old > v_h and h_new > v_h:
                        offset_top = (1.0 - curr_sy) * (h_old - v_h)
                        new_scroll_y = max(0.0, min(1.0, 1.0 - (offset_top / (h_new - v_h))))
                        if getattr(rv, "_anim_y", None):
                            rv._anim_y.stop(rv)
                            rv._anim_y = None
                        self.vm.messages = list(self.vm.messages) + rv_newer
                        rv.scroll_y = new_scroll_y
                        if hasattr(rv, "_update_effect_y_bounds"):
                            rv._update_effect_y_bounds()
                        Clock.schedule_once(lambda dt: setattr(rv, "scroll_y", new_scroll_y), 0)
                    else:
                        self.vm.messages = list(self.vm.messages) + rv_newer

            self.vm.load_newer_messages(on_data_ready=_on_newer_ready)

    def on_scroll_to_bottom_pressed(self):
        """Scrolls to bottom of conversation, loading latest if necessary."""
        rv = self.ids.get("rv_messages")
        if rv:
            if getattr(rv, "_anim_y", None):
                rv._anim_y.stop(rv)
                rv._anim_y = None
            if hasattr(rv, "effect_y") and rv.effect_y:
                rv.effect_y.velocity = 0

        if self.vm.has_more_newer:
            def _jump_done():
                if rv:
                    rv.scroll_y = 0.0
                    if hasattr(rv, "_update_effect_y_bounds"):
                        rv._update_effect_y_bounds()
                self.is_at_bottom = True
            self.vm.jump_to_bottom(on_complete=_jump_done)
        else:
            if rv:
                rv.scroll_y = 0.0
                if hasattr(rv, "_update_effect_y_bounds"):
                    rv._update_effect_y_bounds()
            self.is_at_bottom = True
            self.vm.jump_to_bottom()

    def on_enter(self, *args):
        """Resets native Android input state to the current text when entering chat."""
        super().on_enter(*args)
        if platform == "android":
            from src.utils.android_clipboard import reset_android_input
            current_text = self.ids.message_input.text if "message_input" in self.ids else ""
            reset_android_input(current_text)

    def on_leave(self, *args):
        """Syncs read progress upon leaving the screen and clears native input state."""
        self.vm.sync_read_progress()
        if platform == "android":
            from src.utils.android_clipboard import reset_android_input
            reset_android_input("")

    def on_back_pressed(self):
        """Returns to Dialogs screen and syncs read progress."""
        self.vm.sync_read_progress()
        if self.manager:
            self.manager.current = ScreenName.DIALOGS

    def start_reply(self, msg_data: dict):
        """Activates reply banner above input bar for the swiped message."""
        self.replying_to = msg_data
        if "message_input" in self.ids:
            self.ids.message_input.focus = True

    def cancel_reply(self):
        """Dismisses the active reply preview banner."""
        self.replying_to = None

    def on_reply_clicked(self, target_msg_id: int):
        """Navigates to the replied message, loading surrounding history from API if needed."""
        rv = self.ids.get("rv_messages")
        if not rv:
            return

        messages = self.vm.messages
        target_idx = -1
        for idx, m in enumerate(messages):
            if m.get("message_id") == target_msg_id:
                target_idx = idx
                break

        if target_idx != -1:
            total = len(messages)
            if total > 1:
                target_scroll_y = max(0.0, min(1.0, 1.0 - (target_idx / (total - 1))))
                rv.scroll_y = target_scroll_y
                if hasattr(rv, "_update_effect_y_bounds"):
                    rv._update_effect_y_bounds()
            self.is_at_bottom = (target_idx >= total - 3)
        else:
            # Message is outside currently loaded window: fetch history centered on target message
            def _jump_after_load():
                Clock.schedule_once(lambda dt: self.on_reply_clicked(target_msg_id), 0.25)

            self.vm.load_history_around_message(target_msg_id, on_complete=_jump_after_load)

    def on_send_pressed(self):
        """Sends the message typed in the input field with optional reply_to and preserves soft keyboard focus."""
        reply_to = None
        reply_preview = None
        if self.replying_to:
            reply_to = self.replying_to.get("message_id")
            reply_preview = dict(self.replying_to)
            self.replying_to = None

        self.vm.send_message(reply_to=reply_to, reply_preview=reply_preview)
        if "message_input" in self.ids:
            inp = self.ids.message_input
            inp.focus = True
            from src.utils.android_clipboard import reset_android_input
            reset_android_input("")
            Clock.schedule_once(lambda dt: setattr(inp, "focus", True), 0.05)
