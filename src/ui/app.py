"""Main KivyMD Application class for VK_IMPACT."""
import os
from typing import Optional
from pathlib import Path
from kivy.lang import Builder
from kivymd.app import MDApp
from kivymd.uix.screenmanager import MDScreenManager

from kivy.properties import ListProperty, StringProperty, BooleanProperty
from kivy.utils import get_color_from_hex

from src.core.config import config
from src.core.logger import logger
from src.core.constants import ScreenName, EventType
from src.core.events import event_bus
from src.data.database.db_manager import db_manager
from src.data.api.client import api_client
from src.data.api.longpoll import VKLongPollService
from src.data.repositories.auth_repo import auth_repo
from src.data.repositories.personalization_repo import personalization_repo
from src.utils.async_tools import run_async

# UI Components and Screens
from src.ui.components.avatar import CircularAvatar
from src.ui.components.message_bubble import MessageBubble
from src.ui.components.dialog_item import DialogItemRow
from src.ui.components.dockbar import DockBar
from src.ui.components.folder_chip import FolderChip
from src.ui.components.scroll_bottom_fab import ScrollBottomFab
from src.ui.components.color_picker_dialog import ColorPickerDialog
from src.ui.components.theme_mode_dialog import ThemeModeDialog
from src.ui.screens.auth_screen import AuthScreen
from src.ui.screens.dialogs_screen import DialogsScreen
from src.ui.screens.chat_screen import ChatScreen
from src.ui.screens.logs_screen import LogsScreen
from src.ui.screens.settings_screen import SettingsScreen
from src.ui.screens.settings_account_screen import AccountSettingsScreen
from src.ui.screens.settings_personalization_screen import PersonalizationSettingsScreen
from src.ui.screens.settings_about_screen import AboutSettingsScreen
from src.ui.screens.account_selection_screen import AccountSelectionScreen
from src.ui.screens.profile_edit_screen import ProfileEditScreen


def compute_halftone(color_a: list, color_b: list, weight_b: float = 0.5) -> list:
    """
    Computes intermediate tone (average / blend) between two RGBA colors.
    weight_b: 0.5 computes the exact mathematical mean (среднее).
    """
    r = color_a[0] * (1.0 - weight_b) + color_b[0] * weight_b
    g = color_a[1] * (1.0 - weight_b) + color_b[1] * weight_b
    b = color_a[2] * (1.0 - weight_b) + color_b[2] * weight_b
    a = color_a[3] * (1.0 - weight_b) + color_b[3] * weight_b if len(color_a) > 3 and len(color_b) > 3 else 1.0
    return [round(r, 4), round(g, 4), round(b, 4), round(a, 4)]


class VKImpactApp(MDApp):
    """Core Application handling UI lifecycle, themes and screen navigation."""

    # Dynamic Accent Color (defaults to #3D7BF5 / [0.24, 0.48, 0.95, 1.0])
    accent_color = ListProperty([0.24, 0.48, 0.95, 1.0])

    # Theme mode: "light" | "dark" | "amoled"
    theme_mode = StringProperty("light")

    # Dynamic Theme Colors
    bg_color = ListProperty([0.96, 0.97, 0.98, 1.0])
    surface_color = ListProperty([1.0, 1.0, 1.0, 1.0])
    card_bg = ListProperty([1.0, 1.0, 1.0, 1.0])
    text_color = ListProperty([0.1, 0.12, 0.16, 1.0])
    secondary_text_color = ListProperty([0.45, 0.48, 0.54, 1.0])
    divider_color = ListProperty([0.88, 0.90, 0.93, 1.0])
    bubble_incoming_bg = ListProperty([0.92, 0.93, 0.96, 1.0])
    bubble_incoming_text = ListProperty([0.12, 0.12, 0.14, 1.0])
    input_bg = ListProperty([0.94, 0.95, 0.97, 1.0])

    # Dockbar Style, Selection & Background
    dockbar_style = StringProperty("impact")
    dockbar_selection = StringProperty("none")
    show_dockbar_labels = BooleanProperty(True)
    dockbar_bg = StringProperty("theme")
    dockbar_halftone_color = ListProperty([0.2, 0.3, 0.5, 1.0])
    dockbar_highlight_color = ListProperty([0.2, 0.3, 0.5, 1.0])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = config.APP_NAME
        self.longpoll_service = VKLongPollService(api_client)
        self.screen_manager: MDScreenManager = None

    def update_dockbar_halftones(self):
        """Recalculates halftone (exact mean) and highlight blend colors between current theme and accent."""
        self.dockbar_halftone_color = compute_halftone(self.surface_color, self.accent_color, weight_b=0.5)
        tint_weight = 0.22 if self.theme_mode == "light" else 0.28
        base_color = self.surface_color if self.dockbar_style != "pinterest" else self.card_bg
        self.dockbar_highlight_color = compute_halftone(base_color, self.accent_color, weight_b=tint_weight)

    def apply_dockbar_settings(
        self,
        style: str,
        selection: str,
        show_labels: Optional[bool] = None,
        bg: Optional[str] = None
    ):
        """Applies dockbar style, selection shape, tab labels visibility, and background shader type."""
        clean_style = style.lower() if style in ("impact", "telegram", "pinterest", "incy") else "impact"
        self.dockbar_style = clean_style
        self.dockbar_selection = selection
        if show_labels is not None:
            self.show_dockbar_labels = bool(show_labels)
        if bg is not None and bg in ("theme", "liquid_glass", "glassy_ice"):
            self.dockbar_bg = bg
        self.update_dockbar_halftones()
        logger.info(
            "Applied dockbar settings: style=%s, selection=%s, show_labels=%s, bg=%s",
            clean_style, selection, self.show_dockbar_labels, self.dockbar_bg
        )

    def apply_profile_accent(self, hex_color: str):
        """Applies an accent color hex string to the global reactive accent_color property."""
        try:
            rgba = get_color_from_hex(hex_color)
            self.accent_color = [rgba[0], rgba[1], rgba[2], 1.0]
            self.update_dockbar_halftones()
            logger.info("Applied accent color: %s -> %s", hex_color, self.accent_color)
        except Exception as e:
            logger.error("Failed to apply accent color %s: %s", hex_color, e)

    def apply_theme_mode(self, mode: str):
        """Applies theme palette for 'light', 'dark', or 'amoled'."""
        clean_mode = mode.lower() if mode in ("light", "dark", "amoled") else "light"
        self.theme_mode = clean_mode

        if clean_mode == "light":
            self.theme_cls.theme_style = "Light"
            self.bg_color = [0.96, 0.97, 0.98, 1.0]
            self.surface_color = [1.0, 1.0, 1.0, 1.0]
            self.card_bg = [1.0, 1.0, 1.0, 1.0]
            self.text_color = [0.1, 0.12, 0.16, 1.0]
            self.secondary_text_color = [0.45, 0.48, 0.54, 1.0]
            self.divider_color = [0.88, 0.90, 0.93, 1.0]
            self.bubble_incoming_bg = [0.92, 0.93, 0.96, 1.0]
            self.bubble_incoming_text = [0.12, 0.12, 0.14, 1.0]
            self.input_bg = [0.94, 0.95, 0.97, 1.0]
        elif clean_mode == "dark":
            self.theme_cls.theme_style = "Dark"
            self.bg_color = [0.08, 0.08, 0.09, 1.0]
            self.surface_color = [0.13, 0.13, 0.14, 1.0]
            self.card_bg = [0.16, 0.16, 0.18, 1.0]
            self.text_color = [0.92, 0.93, 0.95, 1.0]
            self.secondary_text_color = [0.55, 0.58, 0.62, 1.0]
            self.divider_color = [0.22, 0.23, 0.25, 1.0]
            self.bubble_incoming_bg = [0.18, 0.19, 0.21, 1.0]
            self.bubble_incoming_text = [0.92, 0.93, 0.95, 1.0]
            self.input_bg = [0.14, 0.15, 0.16, 1.0]
        elif clean_mode == "amoled":
            self.theme_cls.theme_style = "Dark"
            self.bg_color = [0.0, 0.0, 0.0, 1.0]
            self.surface_color = [0.05, 0.05, 0.05, 1.0]
            self.card_bg = [0.08, 0.08, 0.08, 1.0]
            self.text_color = [1.0, 1.0, 1.0, 1.0]
            self.secondary_text_color = [0.55, 0.55, 0.58, 1.0]
            self.divider_color = [0.16, 0.16, 0.18, 1.0]
            self.bubble_incoming_bg = [0.12, 0.12, 0.14, 1.0]
            self.bubble_incoming_text = [1.0, 1.0, 1.0, 1.0]
            self.input_bg = [0.07, 0.07, 0.08, 1.0]

        self.update_dockbar_halftones()
        logger.info("Theme mode applied: %s", clean_mode)

    def refresh_active_theme(self):
        """Loads and applies theme and dockbar settings from the currently active profile."""
        try:
            accent_hex = personalization_repo.get_active_accent_color()
            self.apply_profile_accent(accent_hex)
            mode = personalization_repo.get_active_theme_mode()
            self.apply_theme_mode(mode)
            style = personalization_repo.get_active_dockbar_style()
            selection = personalization_repo.get_active_dockbar_selection()
            show_labels = personalization_repo.get_active_dockbar_show_labels()
            bg = personalization_repo.get_active_dockbar_bg()
            self.apply_dockbar_settings(style, selection, show_labels, bg=bg)
        except Exception as e:
            logger.error("Failed refreshing active theme: %s", e)

    def build(self):
        """Constructs UI hierarchy and themes."""
        self.theme_cls.primary_palette = "RoyalBlue"

        # Initialize accent color and theme from active personalization profile
        self.refresh_active_theme()

        # Load KV files in dependency order
        kv_dir = Path(__file__).parent / "kv"
        Builder.load_file(str(kv_dir / "components.kv"))
        Builder.load_file(str(kv_dir / "dockbar.kv"))
        Builder.load_file(str(kv_dir / "color_picker_dialog.kv"))
        Builder.load_file(str(kv_dir / "theme_mode_dialog.kv"))
        Builder.load_file(str(kv_dir / "dockbar_dialogs.kv"))
        Builder.load_file(str(kv_dir / "add_profile_dialog.kv"))
        Builder.load_file(str(kv_dir / "auth_screen.kv"))
        Builder.load_file(str(kv_dir / "dialogs_screen.kv"))
        Builder.load_file(str(kv_dir / "chat_screen.kv"))
        Builder.load_file(str(kv_dir / "logs_screen.kv"))
        Builder.load_file(str(kv_dir / "settings_screen.kv"))
        Builder.load_file(str(kv_dir / "settings_account_screen.kv"))
        Builder.load_file(str(kv_dir / "settings_personalization_screen.kv"))
        Builder.load_file(str(kv_dir / "settings_about_screen.kv"))
        Builder.load_file(str(kv_dir / "account_selection_screen.kv"))
        Builder.load_file(str(kv_dir / "profile_edit_screen.kv"))

        # Setup Screen Manager
        self.screen_manager = MDScreenManager()
        self.screen_manager.add_widget(AuthScreen(name=ScreenName.AUTH))
        self.screen_manager.add_widget(DialogsScreen(name=ScreenName.DIALOGS))
        self.screen_manager.add_widget(ChatScreen(name=ScreenName.CHAT))
        self.screen_manager.add_widget(LogsScreen(name=ScreenName.LOGS))
        self.screen_manager.add_widget(SettingsScreen(name=ScreenName.SETTINGS))
        self.screen_manager.add_widget(AccountSettingsScreen(name=ScreenName.SETTINGS_ACCOUNT))
        self.screen_manager.add_widget(PersonalizationSettingsScreen(name=ScreenName.SETTINGS_PERSONALIZATION))
        self.screen_manager.add_widget(AboutSettingsScreen(name=ScreenName.SETTINGS_ABOUT))
        self.screen_manager.add_widget(AccountSelectionScreen(name=ScreenName.ACCOUNT_SELECTION))
        self.screen_manager.add_widget(ProfileEditScreen(name=ScreenName.PROFILE_EDIT))




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
