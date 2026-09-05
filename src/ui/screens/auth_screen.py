"""Authentication screen view with dynamic mode rendering and add-account support."""
from kivy.properties import ObjectProperty, BooleanProperty
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.screen import MDScreen
from src.domain.auth_viewmodel import AuthViewModel
from src.core.constants import ScreenName


class BrowserModeContent(BoxLayout):
    auth_screen = ObjectProperty(None)


class CookiesModeContent(BoxLayout):
    auth_screen = ObjectProperty(None)


class WebModeContent(BoxLayout):
    auth_screen = ObjectProperty(None)


class AuthScreen(MDScreen):
    """View for user authentication (Browser OAuth / Cookies / Web)."""
    vm = ObjectProperty(None)
    is_add_account_mode = BooleanProperty(False)

    def __init__(self, **kwargs):
        self.vm = AuthViewModel()
        super().__init__(**kwargs)
        self.name = ScreenName.AUTH
        Clock.schedule_once(lambda dt: self._update_mode_content(), 0)

    def set_add_account_mode(self, enabled: bool = True):
        """Prepares auth screen for adding an additional account without auto-restoring."""
        self.is_add_account_mode = enabled
        self.vm.browser_input = ""
        self.vm.remixsid_input = ""
        self.vm.p_input = ""
        self.vm.token_input = ""
        self.vm.error_message = ""

    def on_enter(self, *args):
        """Called when navigating to auth screen."""
        self._update_mode_content()
        if not self.is_add_account_mode:
            self.vm.try_restore_session(on_success=self._on_auth_success)

    def on_login_pressed(self):
        """Triggers login based on active mode."""
        if self.vm.auth_mode == "browser":
            self.vm.submit_browser_link(on_success=self._on_auth_success)
        elif self.vm.auth_mode == "cookies":
            self.vm.submit_cookies(on_success=self._on_auth_success)
        elif self.vm.auth_mode == "web":
            self.vm.submit_direct_token(on_success=self._on_auth_success)

    def switch_mode(self, mode: str):
        """Switches between browser, cookies and web modes without widget overlap."""
        self.vm.switch_mode(mode)
        self._update_mode_content()

    def _update_mode_content(self):
        """Swaps the active mode container, completely eliminating dead zones and touch blockages."""
        if "mode_container" not in self.ids:
            return
        container = self.ids.mode_container
        container.clear_widgets()
        if self.vm.auth_mode == "browser":
            container.add_widget(BrowserModeContent(auth_screen=self))
        elif self.vm.auth_mode == "cookies":
            container.add_widget(CookiesModeContent(auth_screen=self))
        elif self.vm.auth_mode == "web":
            container.add_widget(WebModeContent(auth_screen=self))

    def open_browser(self):
        """Opens OAuth in default browser."""
        self.vm.open_browser_oauth()

    def on_back_pressed(self):
        """Cancels adding account and returns to settings."""
        self.is_add_account_mode = False
        if self.manager:
            self.manager.current = ScreenName.SETTINGS

    def _on_auth_success(self):
        """Navigates to Dialogs screen upon successful auth."""
        self.is_add_account_mode = False
        if self.manager:
            self.manager.current = ScreenName.DIALOGS
