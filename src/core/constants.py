"""Application constants and enumerations."""
from enum import Enum


class EventType(str, Enum):
    """Global event bus event types."""
    AUTH_SUCCESS = "auth_success"
    AUTH_LOGOUT = "auth_logout"
    NEW_MESSAGE = "new_message"
    MESSAGE_READ = "message_read"
    USER_TYPING = "user_typing"
    USER_ONLINE_CHANGE = "user_online_change"
    DIALOG_UPDATED = "dialog_updated"
    NETWORK_STATUS_CHANGE = "network_status_change"
    LOG_ENTRY = "log_entry"


class ScreenName(str, Enum):
    """Screen identifiers for MDScreenManager."""
    AUTH = "auth_screen"
    DIALOGS = "dialogs_screen"
    CHAT = "chat_screen"
    LOGS = "logs_screen"
    FEED = "feed_screen"
    PROFILE = "profile_screen"
    SETTINGS = "settings_screen"
    SETTINGS_ACCOUNT = "settings_account_screen"
    SETTINGS_PERSONALIZATION = "settings_personalization_screen"
    SETTINGS_ABOUT = "settings_about_screen"
    ACCOUNT_SELECTION = "account_selection_screen"
    PROFILE_EDIT = "profile_edit_screen"





class ThemePalette(str, Enum):
    """Material Design 3 color palette defaults."""
    PRIMARY = "RoyalBlue"
    ACCENT = "LightBlue"
    DARK_MODE = "Dark"
    LIGHT_MODE = "Light"
