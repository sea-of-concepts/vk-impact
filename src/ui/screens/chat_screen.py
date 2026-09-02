from kivy.properties import ObjectProperty
from kivymd.uix.screen import MDScreen
from src.domain.chat_viewmodel import ChatViewModel
from src.core.constants import ScreenName


class ChatScreen(MDScreen):
    """View displaying single chat message stream."""
    vm = ObjectProperty(None)

    def __init__(self, **kwargs):
        self.vm = ChatViewModel()
        super().__init__(**kwargs)
        self.name = ScreenName.CHAT

    def setup_chat(self, peer_id: int, title: str, avatar_url: str = ""):
        """Initializes chat viewmodel for the selected conversation."""
        self.vm.open_chat(peer_id=peer_id, title=title, avatar_url=avatar_url)

    def on_back_pressed(self):
        """Returns to Dialogs screen."""
        if self.manager:
            self.manager.current = ScreenName.DIALOGS

    def on_send_pressed(self):
        """Sends the message typed in the input field."""
        self.vm.send_message()
