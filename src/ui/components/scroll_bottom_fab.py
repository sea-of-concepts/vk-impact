"""Scroll-to-bottom floating action button with unread count badge."""
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.floatlayout import FloatLayout
from kivy.properties import NumericProperty, StringProperty, BooleanProperty
from src.utils.formatters import format_unread_count


class ScrollBottomFab(ButtonBehavior, FloatLayout):
    """Floating action button that jumps to latest chat messages with unread badge."""

    unread_count = NumericProperty(0)
    unread_text = StringProperty("")
    is_at_bottom = BooleanProperty(False)

    def on_unread_count(self, instance, value):
        self.unread_text = format_unread_count(value) if value > 0 else ""
