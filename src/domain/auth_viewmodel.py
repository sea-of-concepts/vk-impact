"""Authentication ViewModel managing Web Client, Browser OAuth, Cookies and Token input."""
from typing import Optional, Callable
from kivy.properties import StringProperty, BooleanProperty
from src.domain.base_viewmodel import BaseViewModel
from src.data.repositories.auth_repo import auth_repo
from src.data.api.auth_web import VKWebAuthEngine
from src.core.events import event_bus
from src.core.constants import EventType
from src.core.logger import logger


class AuthViewModel(BaseViewModel):
    """Manages authentication screen state, web cookies, browser OAuth and token input."""

    auth_mode = StringProperty("browser")  # "browser", "cookies", or "token"
    browser_input = StringProperty("")
    remixsid_input = StringProperty("")
    p_input = StringProperty("")
    token_input = StringProperty("")
    
    is_authenticated = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_authenticated = auth_repo.is_authenticated

    def try_restore_session(self, on_success: Optional[Callable] = None, on_failure: Optional[Callable] = None):
        """Attempts to restore previous login session from encrypted storage."""
        async def _restore():
            return await auth_repo.restore_session()

        def _handle_result(success: bool):
            self.is_authenticated = success
            if success:
                event_bus.emit(EventType.AUTH_SUCCESS, user_id=auth_repo.current_user_id)
                if on_success:
                    on_success()
            else:
                if on_failure:
                    on_failure()

        self.run_task(_restore(), on_success=_handle_result, show_loader=True)

    def switch_mode(self, mode: str):
        """Switches between browser, cookies and token auth modes."""
        self.auth_mode = mode
        self.error_message = ""

    def open_browser_oauth(self):
        """Opens official VK OAuth in user's default browser."""
        VKWebAuthEngine.open_oauth_in_browser()

    def submit_browser_link(self, on_success: Optional[Callable] = None):
        """Authenticates via link or token obtained from browser."""
        raw = self.browser_input.strip()
        if not raw or len(raw) < 15:
            self.error_message = "Вставьте ссылку из адресной строки браузера или токен"
            return

        async def _verify():
            return await auth_repo.login_via_string_or_token(raw)

        def _on_verified(res: dict):
            self.is_authenticated = True
            event_bus.emit(EventType.AUTH_SUCCESS, user_id=res.get("user_id"))
            if on_success:
                on_success()

        def _on_error(exc: Exception):
            self.error_message = str(exc)

        self.run_task(_verify(), on_success=_on_verified, on_error=_on_error, show_loader=True)

    def submit_cookies(self, on_success: Optional[Callable] = None):
        """Authenticates via remixsid and p cookies."""
        remixsid = self.remixsid_input.strip()
        p_val = self.p_input.strip()

        if not remixsid:
            self.error_message = "Введите cookie remixsid (или полную строку cookies)"
            return

        async def _verify():
            return await auth_repo.login_via_cookies(remixsid, p_cookie=p_val)

        def _on_verified(res: dict):
            self.is_authenticated = True
            event_bus.emit(EventType.AUTH_SUCCESS, user_id=res.get("user_id"))
            if on_success:
                on_success()

        def _on_error(exc: Exception):
            self.error_message = str(exc)

        self.run_task(_verify(), on_success=_on_verified, on_error=_on_error, show_loader=True)

    def submit_direct_token(self, on_success: Optional[Callable] = None):
        """Authenticates directly via token."""
        raw = self.token_input.strip()
        if not raw or len(raw) < 15:
            self.error_message = "Введите Access Token"
            return

        async def _verify():
            return await auth_repo.login_via_string_or_token(raw)

        def _on_verified(res: dict):
            self.is_authenticated = True
            event_bus.emit(EventType.AUTH_SUCCESS, user_id=res.get("user_id"))
            if on_success:
                on_success()

        def _on_error(exc: Exception):
            self.error_message = str(exc)

        self.run_task(_verify(), on_success=_on_verified, on_error=_on_error, show_loader=True)
