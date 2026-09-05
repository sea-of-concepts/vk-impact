"""Account settings sub-screen with profile info, account switcher, and logout actions."""
from kivymd.uix.screen import MDScreen
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from src.core.config import config
from src.core.constants import ScreenName
from src.data.repositories.auth_repo import auth_repo
from src.utils.async_tools import run_async
from src.core.logger import logger


class AccountSettingsScreen(MDScreen):
    """View displaying active account details, switch account, and logout."""

    user_id = StringProperty("")
    user_name = StringProperty("")
    avatar_url = StringProperty("")
    impact_style = StringProperty("")
    auth_method_label = StringProperty("")

    accounts_count = NumericProperty(1)
    can_switch_account = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = ScreenName.SETTINGS_ACCOUNT

    def on_enter(self, *args):
        """Refreshes account details upon entering."""
        self.refresh_account_info()

    def refresh_account_info(self):
        """Loads active account details and counts total accounts."""
        active = auth_repo.get_active_account()
        if active:
            self.user_id = str(active.get("id") or active.get("uid", ""))
            self.user_name = active.get("name", "") or f"id{self.user_id}"
            self.avatar_url = active.get("avatar_url", "")
            self.impact_style = active.get("impact_style", "")
            method = active.get("oauths_metod", "token")
            self.auth_method_label = "Вход через Cookie (веб)" if method == "cookie" else "Вход через токен"
        else:
            self.user_id = ""
            self.user_name = "Не авторизован"
            self.avatar_url = ""
            self.impact_style = ""
            self.auth_method_label = ""

        accounts = auth_repo.get_accounts()
        self.accounts_count = len(accounts)
        self.can_switch_account = (self.accounts_count > 1)

    def on_add_account_pressed(self):
        """Navigates to AuthScreen in add-account mode."""
        if not self.manager:
            return
        auth_screen = self.manager.get_screen(ScreenName.AUTH)
        if hasattr(auth_screen, "set_add_account_mode"):
            auth_screen.set_add_account_mode(True)
        self.manager.current = ScreenName.AUTH

    def on_switch_account_pressed(self):
        """Navigates to AccountSelectionScreen if multiple accounts exist."""
        if not self.can_switch_account or not self.manager:
            return
        self.manager.current = ScreenName.ACCOUNT_SELECTION

    def on_logout_pressed(self):
        """
        Removes current account and routes appropriately:
        - 1 account -> AuthScreen (login)
        - 2 accounts -> Automatically switch to the remaining 1 account
        - > 2 accounts -> AccountSelectionScreen
        """
        if not self.user_id:
            auth_repo.logout()
            if self.manager:
                self.manager.current = ScreenName.AUTH
            return

        current_uid = int(self.user_id)

        async def _do_delete():
            return await auth_repo.delete_account(current_uid)

        def _on_done(result):
            action, remaining = result
            if action == "auth":
                if self.manager:
                    self.manager.current = ScreenName.AUTH
            elif action == "switched":
                self.refresh_account_info()
            elif action == "select":
                if self.manager:
                    self.manager.current = ScreenName.ACCOUNT_SELECTION

        def _on_error(exc):
            logger.error("Error logging out/deleting account: %s", exc)

        run_async(_do_delete(), on_success=_on_done, on_error=_on_error)

    def on_back_pressed(self):
        """Navigates back to main settings menu."""
        if self.manager:
            self.manager.current = ScreenName.SETTINGS
