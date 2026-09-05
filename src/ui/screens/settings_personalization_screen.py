from typing import List, Dict, Any, Optional
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivy.properties import BooleanProperty, ListProperty, StringProperty, ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior

from src.core.constants import ScreenName
from src.data.repositories.personalization_repo import personalization_repo
from src.ui.components.add_profile_dialog import AddProfileDialog
from src.core.logger import logger


class CustomProfileCardItem(ButtonBehavior, BoxLayout):
    """Custom profile row item with selection, edit (pencil) and delete (trash) buttons."""
    profile_id = StringProperty("")
    profile_name = StringProperty("")
    is_active = BooleanProperty(False)
    screen = ObjectProperty(None)


class SystemProfileCardItem(ButtonBehavior, BoxLayout):
    """System profile row item."""
    pass


class PersonalizationSettingsScreen(MDScreen):
    """View managing system and custom personalization profiles."""

    system_is_active = BooleanProperty(True)
    profiles = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = ScreenName.SETTINGS_PERSONALIZATION
        self._add_dialog = None

    def on_enter(self, *args):
        """Refreshes profiles list on entering."""
        self.refresh_profiles()

    def refresh_profiles(self):
        """Loads profiles from repository and populates custom items."""
        all_profiles = personalization_repo.load_profiles()
        self.profiles = all_profiles

        # Find system profile active state
        for p in all_profiles:
            if p.get("id") == "system":
                self.system_is_active = bool(p.get("is_active", False))
                break

        self._populate_custom_profiles(all_profiles)

    def _populate_custom_profiles(self, all_profiles: List[Dict[str, Any]]):
        """Dynamically builds custom profile cards."""
        if "custom_profiles_container" not in self.ids:
            return

        container = self.ids.custom_profiles_container
        container.clear_widgets()

        for p in all_profiles:
            if p.get("is_system"):
                continue

            card = CustomProfileCardItem()
            card.profile_id = p.get("id", "")
            card.profile_name = p.get("name", "")
            card.is_active = bool(p.get("is_active", False))
            card.screen = self

            container.add_widget(card)

    def on_system_profile_clicked(self):
        """Activates default system profile."""
        personalization_repo.set_active_profile("system")
        self.refresh_profiles()
        app = MDApp.get_running_app()
        if app and hasattr(app, "refresh_active_theme"):
            app.refresh_active_theme()

    def on_profile_select(self, profile_id: str):
        """Activates the chosen profile."""
        personalization_repo.set_active_profile(profile_id)
        self.refresh_profiles()
        app = MDApp.get_running_app()
        if app and hasattr(app, "refresh_active_theme"):
            app.refresh_active_theme()

    def on_edit_profile(self, profile_id: str):
        """Navigates to profile edit screen."""
        if not self.manager:
            return
        edit_screen = self.manager.get_screen(ScreenName.PROFILE_EDIT)
        if hasattr(edit_screen, "set_profile"):
            edit_screen.set_profile(profile_id)
        self.manager.current = ScreenName.PROFILE_EDIT

    def on_delete_profile(self, profile_id: str):
        """Deletes custom profile and resets active to system if needed."""
        try:
            personalization_repo.delete_profile(profile_id)
            self.refresh_profiles()
            app = MDApp.get_running_app()
            if app and hasattr(app, "refresh_active_theme"):
                app.refresh_active_theme()
        except Exception as e:
            logger.error("Error deleting profile: %s", e)

    def on_add_profile_pressed(self):
        """Opens AddProfileDialog for creating or importing a profile."""
        if self._add_dialog is None:
            self._add_dialog = AddProfileDialog(on_success=self.refresh_profiles)
        self._add_dialog.open()

    def on_back_pressed(self):
        """Navigates back to main settings menu."""
        if self.manager:
            self.manager.current = ScreenName.SETTINGS
