"""Message bubble component with pre-calculated height for smooth scrolling."""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty, DictProperty
from kivy.metrics import dp
from kivymd.app import MDApp
from kivy.uix.relativelayout import RelativeLayout
from src.core.constants import ScreenName
from src.ui.components.avatar import CircularAvatar
from src.data.cache.media_cache import media_cache


class PhotoItem(RelativeLayout):
    """Single photo thumbnail with cached loading, rounded corners, and optional floating timestamp badge."""
    url = StringProperty("")
    local_source = StringProperty("")
    radius = ListProperty([dp(12), dp(12), dp(12), dp(12)])
    time_text = StringProperty("")
    is_outgoing = BooleanProperty(False)
    is_read = BooleanProperty(True)
    show_time_badge = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(url=self._on_url)
        if self.url:
            self._load()

    def _on_url(self, instance, value):
        self._load()

    def _load(self):
        if not self.url:
            self.local_source = ""
            return
        local = media_cache.get_local_path(self.url)
        if local:
            self.local_source = local
        else:
            self.local_source = ""
            def _on_ready(path, target_url=self.url):
                if path and self.url == target_url:
                    self.local_source = path
            media_cache.fetch_image_async(self.url, on_ready=_on_ready)


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


from kivy.clock import Clock


class MessageBubble(RecycleDataViewBehavior, BoxLayout):
    """Chat message bubble with exact pre-calculated size, reply preview, and forward support."""

    index = None
    text = StringProperty("")
    display_text = StringProperty("")
    photos = ListProperty([])
    from_id = NumericProperty(0)
    is_group_chat = BooleanProperty(False)
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
    time_needs_own_line = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._touch_start_x = 0
        self._touch_start_y = 0
        self._is_swiping = False
        self.rv = None

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        self.rv = rv
        self.swipe_x = 0
        self._is_swiping = False
        super().refresh_view_attrs(rv, index, data)
        sz = data.get("msg_size")
        if sz and sz[1]:
            self.height = sz[1]
        self.from_id = data.get("from_id", 0)
        self.is_group_chat = bool(data.get("is_group_chat", False))
        self.time_needs_own_line = bool(data.get("time_needs_own_line", False))
        self.photos = data.get("photos", [])
        self.update_display_text()
        self.update_colors()
        self.rebuild_photos(self.photos)
        self.rebuild_fwd_messages(data.get("fwd_messages", []))
        av_w = self.ids.get("avatar_widget")
        if av_w and av_w.source:
            av_w.reload_avatar_if_needed()
        Clock.schedule_once(self._sync_rendered_height, 0.05)

    def update_display_text(self):
        if not self.text:
            self.display_text = ""
            return
        t = clean_message_text(self.text)
        if not self.time_needs_own_line:
            # Append non-breaking margin so text never collides with inline timestamp
            self.display_text = t + ("       " if self.is_outgoing else "     ")
        else:
            self.display_text = t

    def _sync_rendered_height(self, dt=0):
        c_box = self.ids.get("content_box")
        if not c_box:
            return
        real_h = c_box.minimum_height + (dp(28) if self.show_new_divider else 0) + dp(4)
        if real_h > dp(24) and abs(self.height - real_h) > dp(6):
            self.height = real_h
            if self.rv and self.index is not None and self.index < len(self.rv.data):
                self.rv.data[self.index]["msg_size"] = [None, real_h]
                Clock.schedule_once(lambda _dt: self.rv.refresh_from_data(), 0)

    def on_photos(self, instance, value):
        self.rebuild_photos(value)

    def rebuild_photos(self, photos):
        container = self.ids.get("photos_container")
        if not container:
            return
        container.clear_widgets()
        if not photos or not isinstance(photos, list):
            return

        has_text = bool(self.text and self.text.strip())
        show_time_badge = (not has_text) and (not bool(self.fwd_messages))
        bubble_radius = [dp(16), dp(16), dp(4) if self.is_outgoing else dp(16), dp(16) if self.is_outgoing else dp(4)]

        from src.utils.formatters import estimate_photos_height
        n = len(photos)

        if n == 1:
            p = photos[0]
            item_h = estimate_photos_height([p])
            item = PhotoItem(
                url=p.get("url", ""),
                size_hint=(1, None),
                height=dp(item_h),
                radius=bubble_radius if (not has_text and not self.sender_name) else [dp(12), dp(12), dp(12), dp(12)],
                time_text=self.time_text,
                is_outgoing=self.is_outgoing,
                is_read=self.is_read,
                show_time_badge=show_time_badge
            )
            container.add_widget(item)

        elif n == 2:
            row = BoxLayout(orientation="horizontal", spacing=dp(3), size_hint=(1, None), height=dp(140))
            p1 = PhotoItem(url=photos[0].get("url", ""), size_hint=(0.5, 1), radius=[dp(12), dp(12), dp(12), dp(12)])
            p2 = PhotoItem(
                url=photos[1].get("url", ""),
                size_hint=(0.5, 1),
                radius=[dp(12), dp(12), dp(12), dp(12)],
                time_text=self.time_text,
                is_outgoing=self.is_outgoing,
                is_read=self.is_read,
                show_time_badge=show_time_badge
            )
            row.add_widget(p1)
            row.add_widget(p2)
            container.add_widget(row)

        elif n == 3:
            p1 = PhotoItem(url=photos[0].get("url", ""), size_hint=(1, None), height=dp(125), radius=[dp(12), dp(12), dp(12), dp(12)])
            container.add_widget(p1)
            row2 = BoxLayout(orientation="horizontal", spacing=dp(3), size_hint=(1, None), height=dp(95))
            p2 = PhotoItem(url=photos[1].get("url", ""), size_hint=(0.5, 1), radius=[dp(12), dp(12), dp(12), dp(12)])
            p3 = PhotoItem(
                url=photos[2].get("url", ""),
                size_hint=(0.5, 1),
                radius=[dp(12), dp(12), dp(12), dp(12)],
                time_text=self.time_text,
                is_outgoing=self.is_outgoing,
                is_read=self.is_read,
                show_time_badge=show_time_badge
            )
            row2.add_widget(p2)
            row2.add_widget(p3)
            container.add_widget(row2)

        elif n == 4:
            row1 = BoxLayout(orientation="horizontal", spacing=dp(3), size_hint=(1, None), height=dp(100))
            row1.add_widget(PhotoItem(url=photos[0].get("url", ""), size_hint=(0.5, 1), radius=[dp(10), dp(10), dp(10), dp(10)]))
            row1.add_widget(PhotoItem(url=photos[1].get("url", ""), size_hint=(0.5, 1), radius=[dp(10), dp(10), dp(10), dp(10)]))
            container.add_widget(row1)

            row2 = BoxLayout(orientation="horizontal", spacing=dp(3), size_hint=(1, None), height=dp(100))
            row2.add_widget(PhotoItem(url=photos[2].get("url", ""), size_hint=(0.5, 1), radius=[dp(10), dp(10), dp(10), dp(10)]))
            row2.add_widget(PhotoItem(
                url=photos[3].get("url", ""),
                size_hint=(0.5, 1),
                radius=[dp(10), dp(10), dp(10), dp(10)],
                time_text=self.time_text,
                is_outgoing=self.is_outgoing,
                is_read=self.is_read,
                show_time_badge=show_time_badge
            ))
            container.add_widget(row2)

        else:
            chunk_size = 3 if n >= 6 else 2
            idx = 0
            while idx < n:
                chunk = photos[idx:idx + chunk_size]
                row = BoxLayout(orientation="horizontal", spacing=dp(3), size_hint=(1, None), height=dp(85))
                for c_i, p_item in enumerate(chunk):
                    is_last = (idx + c_i == n - 1)
                    pi = PhotoItem(
                        url=p_item.get("url", ""),
                        size_hint=(1.0 / len(chunk), 1),
                        radius=[dp(8), dp(8), dp(8), dp(8)],
                        time_text=self.time_text if is_last else "",
                        is_outgoing=self.is_outgoing if is_last else False,
                        is_read=self.is_read if is_last else True,
                        show_time_badge=show_time_badge if is_last else False
                    )
                    row.add_widget(pi)
                container.add_widget(row)
                idx += chunk_size

    def on_text(self, instance, value):
        from src.utils.formatters import check_time_needs_own_line
        self.time_needs_own_line = check_time_needs_own_line(value, self.is_outgoing)

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
