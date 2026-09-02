"""Message bubble component with pre-calculated height for smooth scrolling."""
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty


class MessageBubble(BoxLayout):
    """Chat message bubble with static pre-calculated size."""
    
    text = StringProperty("")
    sender_name = StringProperty("")
    sender_avatar = StringProperty("")
    time_text = StringProperty("")
    is_outgoing = BooleanProperty(False)
    is_read = BooleanProperty(True)
    message_id = NumericProperty(0)
    msg_size = ListProperty([None, 64])
