"""Dialog row item widget for RecycleView."""
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty, NumericProperty


class DialogItemRow(ButtonBehavior, BoxLayout):
    """Clickable dialog item in the conversations list."""
    
    peer_id = NumericProperty(0)
    title = StringProperty("")
    avatar_url = StringProperty("")
    initials = StringProperty("")
    last_message = StringProperty("")
    time_text = StringProperty("")
    unread_count = NumericProperty(0)
    unread_text = StringProperty("")
    is_online = BooleanProperty(False)
    is_read = BooleanProperty(True)
    is_outgoing = BooleanProperty(False)
    is_pinned = BooleanProperty(False)
    is_muted = BooleanProperty(False)
    is_channel = BooleanProperty(False)
    impact_style = StringProperty("")


    def on_release(self):
        """Notifies the parent screen to open this chat."""
        parent_widget = self.parent
        while parent_widget and not hasattr(parent_widget, "open_chat"):
            parent_widget = parent_widget.parent
        if parent_widget and hasattr(parent_widget, "open_chat"):
            parent_widget.open_chat(
                peer_id=self.peer_id,
                title=self.title,
                avatar_url=self.avatar_url,
                is_channel=self.is_channel,
                is_muted=self.is_muted,
                unread_count=self.unread_count
            )
