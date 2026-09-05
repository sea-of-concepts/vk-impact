"""Account selection screen for switching between multiple authenticated accounts."""
from typing import Dict, Any, List
from kivy.properties import ListProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivymd.uix.screen import MDScreen
from src.core.constants import ScreenName
from src.data.repositories.auth_repo import auth_repo
from src.utils.async_tools import run_async
from src.ui.components.avatar import CircularAvatar


class AccountCardItem(ButtonBehavior, BoxLayout):
    """Clickable account item in the selection list."""
    pass


class AccountSelectionScreen(MDScreen):
    """View displaying list of saved accounts and allowing switching or adding accounts."""

    accounts = ListProperty([])
    is_busy = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = ScreenName.ACCOUNT_SELECTION

    def on_enter(self, *args):
        """Reloads accounts on entering screen."""
        self.refresh_accounts()

    def refresh_accounts(self):
        """Fetches accounts from auth_repo and populates the container."""
        raw_accounts = auth_repo.get_accounts()
        self.accounts = raw_accounts
        self._populate_list(raw_accounts)

    def _populate_list(self, accounts: List[Dict[str, Any]]):
        """Dynamically creates UI cards for accounts."""
        if "accounts_container" not in self.ids:
            return

        container = self.ids.accounts_container
        container.clear_widgets()

        for acc in accounts:
            uid = acc.get("id") or acc.get("uid", 0)
            name = acc.get("name") or f"id{uid}"
            avatar_url = acc.get("avatar_url") or ""
            impact_style = acc.get("impact_style") or ""
            method = "Cookie" if acc.get("oauths_metod") == "cookie" else "Токен"
            is_active = bool(acc.get("is_active", False))

            card = AccountCardItem()
            card.user_id = uid
            card.user_name = name
            card.avatar_url = avatar_url
            card.impact_style = impact_style
            card.method = method
            card.is_active = is_active
            card.screen = self

            container.add_widget(card)

    def on_account_clicked(self, user_id: int):
        """Switches active account and navigates back to dialogs or settings."""
        if self.is_busy:
            return

        # Check if already active
        active = auth_repo.get_active_account()
        if active and int(active.get("id", 0)) == int(user_id):
            if self.manager:
                self.manager.current = ScreenName.SETTINGS
            return

        self.is_busy = True

        async def _switch():
            success = await auth_repo.switch_to_account(user_id)
            return success

        def _on_switched(success: bool):
            self.is_busy = False
            if self.manager:
                self.manager.current = ScreenName.DIALOGS

        def _on_error(exc: Exception):
            self.is_busy = False

        run_async(_switch(), on_success=_on_switched, on_error=_on_error)

    def on_add_account_pressed(self):
        """Navigates to AuthScreen in add-account mode."""
        if not self.manager:
            return
        auth_screen = self.manager.get_screen(ScreenName.AUTH)
        if hasattr(auth_screen, "set_add_account_mode"):
            auth_screen.set_add_account_mode(True)
        self.manager.current = ScreenName.AUTH

    def on_back_pressed(self):
        """Returns to account settings screen if active account exists, else auth screen."""
        if not self.manager:
            return
        active = auth_repo.get_active_account()
        if active and active.get("token"):
            self.manager.current = ScreenName.SETTINGS_ACCOUNT
        elif self.accounts:
            self.manager.current = ScreenName.SETTINGS_ACCOUNT
        else:
            self.manager.current = ScreenName.AUTH

