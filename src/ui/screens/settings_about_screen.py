"""About settings sub-screen with application version and metadata."""
from kivymd.uix.screen import MDScreen
from kivy.properties import StringProperty
from src.core.config import config
from src.core.constants import ScreenName


class AboutSettingsScreen(MDScreen):
    """View displaying application version and metadata."""

    app_version = StringProperty(config.VERSION)
    app_name = StringProperty(config.APP_NAME)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = ScreenName.SETTINGS_ABOUT

    def on_back_pressed(self):
        """Navigates back to main settings menu."""
        if self.manager:
            self.manager.current = ScreenName.SETTINGS
