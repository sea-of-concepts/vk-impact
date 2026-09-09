"""Message bubble component with pre-calculated height for smooth scrolling."""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty, DictProperty
from kivy.metrics import dp
from kivymd.app import MDApp
from src.core.constants import ScreenName
from src.ui.components.avatar import CircularAvatar


class ForwardedMessageItem(BoxLayout):
    """Single item in forwarded messages list with colored stripe, author header, and text."""
    sender_name = StringProperty("")
    sender_avatar = StringProperty("")
    time_text = StringProperty("")
    text = StringProperty("")
    stripe_color = ListProperty([0.3, 0.6, 1.0, 1.0])
    nickname_color = ListProperty([1.0, 1.0, 1.0, 1.0])
    is_outgoing = BooleanProperty(False)
    indent_dp = NumericProperty(0)


class MessageBubble(RecycleDataViewBehavior, BoxLayout):
    """Chat message bubble with exact pre-calculated size, reply preview, and forward support."""

    index = None
    text = StringProperty("")
    sender_name = StringProperty("")
    sender_avatar = StringProperty("")
    sender_impact_style = StringProperty("")
    time_text = StringProperty("")
    is_outgoing = BooleanProperty(False)
    is_read = BooleanProperty(True)
    message_id = NumericProperty(0)
    show_new_divider = BooleanProperty(False)
    reply_message = DictProperty({})
    fwd_messages = ListProperty([])
    msg_size = ListProperty([None, dp(64)])
    stripe_color = ListProperty([0.3, 0.6, 1.0, 1.0])
    nickname_color = ListProperty([1.0, 1.0, 1.0, 1.0])
    swipe_x = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._touch_start_x = 0
        self._touch_start_y = 0
        self._is_swiping = False

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        self.swipe_x = 0
        self._is_swiping = False
        super().refresh_view_attrs(rv, index, data)
        self.update_colors()
        self.rebuild_fwd_messages(data.get("fwd_messages", []))

    def on_is_outgoing(self, instance, value):
        self.update_colors()

    def update_colors(self, *args):
        app = MDApp.get_running_app()
        acc = getattr(app, "accent_color", (0.3, 0.6, 1.0, 1.0)) if app else (0.3, 0.6, 1.0, 1.0)
        bg = acc if self.is_outgoing else (getattr(app, "bubble_incoming_bg", (0.9, 0.9, 0.9, 1.0)) if app else (0.9, 0.9, 0.9, 1.0))
        diff = abs(bg[0] - acc[0]) + abs(bg[1] - acc[1]) + abs(bg[2] - acc[2])
        if diff < 0.15:
            # Accent matches bubble background (outgoing bubble):
            # Stripe according to theme: light theme -> white, dark theme -> white
            # Nickname is pure white regardless of theme
            self.stripe_color = [1.0, 1.0, 1.0, 1.0]
            self.nickname_color = [1.0, 1.0, 1.0, 1.0]
        else:
            # Incoming bubble: stripe and nickname both use accent color
            self.stripe_color = list(acc)
            self.nickname_color = list(acc)

    def get_stripe_color(self):
        self.update_colors()
        return self.stripe_color

    def get_nickname_color(self):
        self.update_colors()
        return self.nickname_color

    def on_fwd_messages(self, instance, value):
        self.rebuild_fwd_messages(value)

    def rebuild_fwd_messages(self, fwds):
        container = self.ids.get("fwd_container")
        if not container:
            return
        container.clear_widgets()
        if not fwds or not isinstance(fwds, list):
            return

        self.update_colors()

        def _flatten_fwds(items, depth=0):
            res = []
            for it in items:
                if isinstance(it, dict):
                    res.append((it, depth))
                    rep = it.get("reply_message")
                    if rep and isinstance(rep, dict):
                        res.extend(_flatten_fwds([rep], depth + 1))
                    nested = it.get("fwd_messages")
                    if nested and isinstance(nested, list):
                        res.extend(_flatten_fwds(nested, depth + 1))
            return res

        flat_fwds = _flatten_fwds(fwds)
        for fwd, depth in flat_fwds:
            try:
                s_name = str(fwd.get("sender_name") or "Сообщение")
                s_avatar = str(fwd.get("sender_avatar") or "")
                s_time = str(fwd.get("time_text") or "")
                s_text = str(fwd.get("text") or "")
                item = ForwardedMessageItem(
                    sender_name=s_name,
                    sender_avatar=s_avatar,
                    time_text=s_time,
                    text=s_text,
                    stripe_color=self.stripe_color,
                    nickname_color=self.nickname_color,
                    is_outgoing=self.is_outgoing,
                    indent_dp=dp(depth * 12)
                )
                container.add_widget(item)
            except Exception as e:
                from src.core.logger import logger
                logger.error("Failed adding forwarded message item: %s", e)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            r_box = self.ids.get("reply_preview_box")
            if r_box and r_box.opacity > 0 and r_box.collide_point(*touch.pos):
                self._reply_clicked_down = True
                return True
            self._touch_start_x = touch.x
            self._touch_start_y = touch.y
            self._is_swiping = False
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if getattr(self, "_touch_start_x", 0) != 0:
            dx = touch.x - self._touch_start_x
            dy = abs(touch.y - self._touch_start_y)
            if not getattr(self, "_is_swiping", False):
                if dx < -dp(8) and dy < dp(18) and abs(dx) > dy * 1.1:
                    self._is_swiping = True
                    touch.grab(self)
            if getattr(self, "_is_swiping", False) and touch.grab_current is self:
                self.swipe_x = max(-dp(55), min(0.0, dx))
                return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if getattr(self, "_reply_clicked_down", False):
            self._reply_clicked_down = False
            r_box = self.ids.get("reply_preview_box")
            if r_box and r_box.collide_point(*touch.pos):
                self.on_reply_preview_clicked()
                return True

        if getattr(self, "_is_swiping", False) or touch.grab_current is self:
            self._is_swiping = False
            if touch.grab_current is self:
                touch.ungrab(self)
            if self.swipe_x <= -dp(35):
                self.trigger_reply()
            from kivy.animation import Animation
            Animation(swipe_x=0, d=0.16, t="out_quad").start(self)
            self._touch_start_x = 0
            self._touch_start_y = 0
            return True

        self._touch_start_x = 0
        self._touch_start_y = 0
        return super().on_touch_up(touch)

    def trigger_reply(self):
        app = MDApp.get_running_app()
        if app and app.root:
            try:
                chat_screen = app.root.get_screen(ScreenName.CHAT)
                if chat_screen and hasattr(chat_screen, "start_reply"):
                    author = self.sender_name if (self.sender_name and not self.is_outgoing) else "Вы"
                    chat_screen.start_reply({
                        "message_id": self.message_id,
                        "sender_name": author,
                        "text": self.text
                    })
            except Exception:
                pass

    def on_reply_preview_clicked(self):
        if not self.reply_message:
            return
        target_id = self.reply_message.get("id") or self.reply_message.get("conversation_message_id")
        if not target_id:
            return
        app = MDApp.get_running_app()
        if app and app.root:
            try:
                chat_screen = app.root.get_screen(ScreenName.CHAT)
                if chat_screen and hasattr(chat_screen, "on_reply_clicked"):
                    chat_screen.on_reply_clicked(target_id)
            except Exception:
                pass
