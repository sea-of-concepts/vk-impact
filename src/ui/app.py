"""Main KivyMD Application class for VK_IMPACT."""
import os
from pathlib import Path
from kivy.lang import Builder
from kivymd.app import MDApp
from kivymd.uix.screenmanager import MDScreenManager

from src.core.config import config
from src.core.logger import logger
from src.core.constants import ScreenName, EventType
from src.core.events import event_bus
from src.data.database.db_manager import db_manager
from src.data.api.client import api_client
from src.data.api.longpoll import VKLongPollService
from src.data.repositories.auth_repo import auth_repo
from src.utils.async_tools import run_async

# UI Components and Screens
from src.ui.components.avatar import CircularAvatar
from src.ui.components.message_bubble import MessageBubble
from src.ui.components.dialog_item import DialogItemRow
from src.ui.components.dockbar import DockBar
from src.ui.components.folder_chip import FolderChip
from src.ui.screens.auth_screen import AuthScreen
from src.ui.screens.dialogs_screen import DialogsScreen
from src.ui.screens.chat_screen import ChatScreen
from src.ui.screens.logs_screen import LogsScreen
from src.ui.screens.settings_screen import SettingsScreen


class VKImpactApp(MDApp):
    """Core Application handling UI lifecycle, themes and screen navigation."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = config.APP_NAME
        self.longpoll_service = VKLongPollService(api_client)
        self.screen_manager: MDScreenManager = None

    def build(self):
        """Constructs UI hierarchy and themes."""
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "RoyalBlue"
        
        # Load KV files in dependency order
        kv_dir = Path(__file__).parent / "kv"
        Builder.load_file(str(kv_dir / "components.kv"))
        Builder.load_file(str(kv_dir / "dockbar.kv"))
        Builder.load_file(str(kv_dir / "auth_screen.kv"))
        Builder.load_file(str(kv_dir / "dialogs_screen.kv"))
        Builder.load_file(str(kv_dir / "chat_screen.kv"))
        Builder.load_file(str(kv_dir / "logs_screen.kv"))
        Builder.load_file(str(kv_dir / "settings_screen.kv"))

        # Setup Screen Manager
        self.screen_manager = MDScreenManager()
        self.screen_manager.add_widget(AuthScreen(name=ScreenName.AUTH))
        self.screen_manager.add_widget(DialogsScreen(name=ScreenName.DIALOGS))
        self.screen_manager.add_widget(ChatScreen(name=ScreenName.CHAT))
        self.screen_manager.add_widget(LogsScreen(name=ScreenName.LOGS))
        self.screen_manager.add_widget(SettingsScreen(name=ScreenName.SETTINGS))

        # Initial screen
        self.screen_manager.current = ScreenName.AUTH
        return self.screen_manager

    def on_start(self):
        """Called when Kivy event loop is ready."""
        # Subscribe to global events
        event_bus.subscribe(EventType.AUTH_SUCCESS, self._on_auth_success)
        event_bus.subscribe(EventType.AUTH_LOGOUT, self._on_auth_logout)

        # Initialize local database
        run_async(db_manager.init_db())

    def _on_auth_success(self, user_id: int = 0, **kwargs):
        """Starts Long Poll service on authentication."""
        logger.info("Auth success for user %s. Starting Long Poll...", user_id)
        run_async(self.longpoll_service.start())

    def _on_auth_logout(self, **kwargs):
        """Stops Long Poll and resets navigation."""
        logger.info("Logging out. Stopping Long Poll...")
        run_async(self.longpoll_service.stop())
        if self.screen_manager:
            self.screen_manager.current = ScreenName.AUTH

    def on_stop(self):
        """Cleanup when app is closed."""
        run_async(self.longpoll_service.stop())
        run_async(api_client.close())
