"""Bottom navigation dockbar widget with auto-synchronization."""
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty
from kivymd.app import MDApp
from src.core.constants import ScreenName
from src.ui.components.dockbar_shader import DockbarShaderRenderer


class DockItem(ButtonBehavior, AnchorLayout):
    """Clickable dockbar item supporting dynamic styles and highlight shapes."""
    tab_name = StringProperty("")
    is_active = BooleanProperty(False)


class DockBar(BoxLayout):
    """Bottom navigation bar switching between Dialogs, Logs (>/. ) and Settings."""

    active_tab = StringProperty("dialogs")

    def __init__(self, **kwargs):
        self.shader_renderer = DockbarShaderRenderer(self)
        super().__init__(**kwargs)
        self.bind(pos=self._on_geometry_change, size=self._on_geometry_change)

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        app = MDApp.get_running_app()
        if app:
            app.bind(
                dockbar_bg=self._on_app_bg_change,
                dockbar_style=self._on_geometry_change,
                dockbar_selection=self._on_geometry_change,
                accent_color=self._on_geometry_change,
                theme_mode=self._on_geometry_change,
            )
            if hasattr(self, "shader_renderer") and self.shader_renderer:
                self.shader_renderer.update_shader(getattr(app, "dockbar_bg", "theme"))

    def _on_app_bg_change(self, instance, value):
        self.shader_renderer.update_shader(value)

    def _on_geometry_change(self, *args):
        self.shader_renderer.update_geometry()

    def on_parent(self, *args):
        """Automatically syncs active_tab with the containing screen on attach."""
        self.sync_with_screen()
        app = MDApp.get_running_app()
        if app and getattr(app, "dockbar_bg", "theme") != "theme":
            self.shader_renderer.update_shader(app.dockbar_bg)

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
