"""Main Settings Hub screen displaying clickable categories (inspired by SOVA/VK client)."""
from kivymd.uix.screen import MDScreen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import StringProperty
from src.core.constants import ScreenName


class SettingsMenuItem(ButtonBehavior, BoxLayout):
    """Clickable settings category row with icon and title."""
    icon_name = StringProperty("")
    title_text = StringProperty("")
    target_screen = StringProperty("")


class SettingsScreen(MDScreen):
    """Main settings categories hub."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = ScreenName.SETTINGS

    def on_enter(self, *args):
        """Synchronizes dockbar on enter."""
        if hasattr(self.ids, "dockbar"):
            self.ids.dockbar.sync_with_screen()

    def open_section(self, section_name: str):
        """Navigates to the selected settings sub-screen."""
        if not self.manager:
            return

        if section_name == "account":
            self.manager.current = ScreenName.SETTINGS_ACCOUNT
        elif section_name == "personalization":
            self.manager.current = ScreenName.SETTINGS_PERSONALIZATION
        elif section_name == "about":
            self.manager.current = ScreenName.SETTINGS_ABOUT
