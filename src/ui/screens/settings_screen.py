"""Settings screen displaying application information, version, and account options."""
from kivymd.uix.screen import MDScreen
from kivy.properties import StringProperty
from src.core.config import config
from src.core.constants import ScreenName
from src.data.repositories.auth_repo import auth_repo


class SettingsScreen(MDScreen):
    """View displaying application settings, version, and account management."""

    app_version = StringProperty("0.0.2")
    app_name = StringProperty(config.APP_NAME)
    user_id = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = ScreenName.SETTINGS

    def on_enter(self, *args):
        """Refreshes settings info and synchronizes dockbar."""
        if hasattr(self.ids, "dockbar"):
            self.ids.dockbar.sync_with_screen()

        uid = auth_repo.current_user_id
        self.user_id = str(uid) if uid else ""

    def on_logout_pressed(self):
        """Clears auth session and returns to login screen."""
        auth_repo.logout()
        if self.manager:
            self.manager.current = ScreenName.AUTH
