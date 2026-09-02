"""Bottom navigation dockbar widget with auto-synchronization."""
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty
from src.core.constants import ScreenName


class DockItem(ButtonBehavior, AnchorLayout):
    """Clickable dockbar item perfectly centered."""
    pass


class DockBar(BoxLayout):
    """Bottom navigation bar switching between Dialogs, Logs (>/. ) and Settings."""

    active_tab = StringProperty("dialogs")

    def on_parent(self, *args):
        """Automatically syncs active_tab with the containing screen on attach."""
        self.sync_with_screen()

    def sync_with_screen(self):
        """Inspects parent MDScreen and sets active_tab accurately."""
        screen = self.parent
        while screen and not hasattr(screen, "name"):
            screen = screen.parent

        if screen:
            if screen.name == ScreenName.DIALOGS:
                self.active_tab = "dialogs"
            elif screen.name == ScreenName.LOGS:
                self.active_tab = "logs"
            elif screen.name == ScreenName.SETTINGS:
                self.active_tab = "settings"

    def switch_tab(self, tab_name: str):
        """Switches active section and triggers screen change."""
        self.active_tab = tab_name
        
        # Traverse parent hierarchy to find MDScreenManager
        screen = self.parent
        while screen and not hasattr(screen, "manager"):
            screen = screen.parent

        if screen and screen.manager:
            sm = screen.manager
            if tab_name == "dialogs":
                sm.current = ScreenName.DIALOGS
            elif tab_name == "logs":
                sm.current = ScreenName.LOGS
            elif tab_name == "settings":
                if sm.has_screen(ScreenName.SETTINGS):
                    sm.current = ScreenName.SETTINGS
