"""Theme Mode Selection modal dialog supporting Light, Dark, and AMOLED themes."""
from typing import Optional, Callable
from kivy.uix.modalview import ModalView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty
from src.core.logger import logger


class ThemeOptionItem(ButtonBehavior, BoxLayout):
    """Clickable row item for a theme choice."""
    mode_key = StringProperty("light")
    title_text = StringProperty("")
    desc_text = StringProperty("")
    icon_name = StringProperty("white-balance-sunny")
    is_selected = BooleanProperty(False)
    dialog = ObjectProperty(None)

    def on_release(self):
        if self.dialog:
            self.dialog.select_mode(self.mode_key)


class ThemeModeDialog(ModalView):
    """Modal dialog allowing selection between Light, Dark, and AMOLED themes."""

    selected_mode = StringProperty("light")
    on_select_callback = ObjectProperty(None)

    def __init__(self, current_mode: str = "light", on_select: Optional[Callable[[str], None]] = None, **kwargs):
        super().__init__(**kwargs)
        self.selected_mode = current_mode if current_mode in ("light", "dark", "amoled") else "light"
        self.on_select_callback = on_select
        self.auto_dismiss = True

    def select_mode(self, mode_key: str):
        """Sets selected theme mode, triggers callback and closes dialog."""
        if mode_key in ("light", "dark", "amoled"):
            self.selected_mode = mode_key
            if self.on_select_callback:
                self.on_select_callback(mode_key)
            self.dismiss()
