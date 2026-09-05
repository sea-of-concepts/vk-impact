from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import StringProperty, ListProperty, ObjectProperty, BooleanProperty
from kivy.utils import get_color_from_hex

from src.core.constants import ScreenName
from src.data.repositories.personalization_repo import personalization_repo
from src.ui.components.color_picker_dialog import ColorPickerDialog
from src.ui.components.theme_mode_dialog import ThemeModeDialog
from src.ui.components.dockbar_dialogs import DockbarStyleDialog, DockbarSelectionDialog, DockbarBgDialog
from src.core.logger import logger


class ProfileAccentSettingRow(ButtonBehavior, BoxLayout):
    """Clickable setting row for accent color."""
    screen = ObjectProperty(None)
    accent_rgba = ListProperty([0.24, 0.48, 0.95, 1.0])


class ProfileThemeSettingRow(ButtonBehavior, BoxLayout):
    """Clickable setting row for theme mode."""
    screen = ObjectProperty(None)
    theme_label = StringProperty("Светлая")


class ProfileDockbarStyleSettingRow(ButtonBehavior, BoxLayout):
    """Clickable setting row for dockbar style."""
    screen = ObjectProperty(None)
    style_label = StringProperty("Impact")


class ProfileDockbarSelectionSettingRow(ButtonBehavior, BoxLayout):
    """Clickable setting row for dockbar selection/shape."""
    screen = ObjectProperty(None)
    title_text = StringProperty("Выделение вкладки")
    selection_label = StringProperty("Без выделения")


class ProfileDockbarBgSettingRow(ButtonBehavior, BoxLayout):
    """Clickable setting row for dockbar background shader."""
    screen = ObjectProperty(None)
    bg_label = StringProperty("Согласно теме")


class ProfileDockbarLabelsSettingRow(ButtonBehavior, BoxLayout):
    """Clickable setting row for toggling dockbar tab labels."""
    screen = ObjectProperty(None)
    is_active = BooleanProperty(True)
    is_disabled = BooleanProperty(False)


class ProfileEditScreen(MDScreen):
    """View allowing customization of a personalization profile (name, accent color, theme, dockbar, etc.)."""

    profile_id = StringProperty("")
    profile_name = StringProperty("")
    accent_color_hex = StringProperty("#3D7BF5")
    accent_color_rgba = ListProperty([0.24, 0.48, 0.95, 1.0])
    theme_mode = StringProperty("light")
    theme_mode_label = StringProperty("Светлая")
    dockbar_style = StringProperty("impact")
    dockbar_style_label = StringProperty("Impact")
    dockbar_selection = StringProperty("none")
    dockbar_selection_title = StringProperty("Выделение вкладки")
    dockbar_selection_label = StringProperty("Без выделения")
    dockbar_show_labels = BooleanProperty(True)
    dockbar_bg = StringProperty("theme")
    dockbar_bg_label = StringProperty("Согласно теме")
    error_message = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = ScreenName.PROFILE_EDIT

    def set_profile(self, profile_id: str):
        """Loads profile data for editing."""
        self.profile_id = profile_id
        self.error_message = ""
        p = personalization_repo.get_profile(profile_id)
        if p:
            self.profile_name = p.get("name", "")
            accent_hex = personalization_repo.get_profile_accent(profile_id)
            self._apply_accent_hex(accent_hex)
            self.theme_mode = personalization_repo.get_profile_theme_mode(profile_id)
            self.dockbar_style = personalization_repo.get_profile_dockbar_style(profile_id)
            self.dockbar_selection = personalization_repo.get_profile_dockbar_selection(profile_id)
            self.dockbar_show_labels = personalization_repo.get_profile_dockbar_show_labels(profile_id)
            self.dockbar_bg = personalization_repo.get_profile_dockbar_bg(profile_id)
        else:
            self.profile_name = ""
            self._apply_accent_hex("#3D7BF5")
            self.theme_mode = "light"
            self.dockbar_style = "impact"
            self.dockbar_selection = "none"
            self.dockbar_show_labels = True
            self.dockbar_bg = "theme"

        self._update_theme_label()
        self._update_dockbar_labels()

    def _update_theme_label(self):
        """Updates human-readable theme label."""
        labels = {"light": "Светлая", "dark": "Тёмная", "amoled": "AMOLED"}
        self.theme_mode_label = labels.get(self.theme_mode, "Светлая")
        if hasattr(self, "ids") and "theme_setting_row" in self.ids:
            self.ids.theme_setting_row.theme_label = self.theme_mode_label

    def _update_dockbar_labels(self):
        """Updates human-readable dockbar style, selection, background and labels switch state."""
        style_labels = {
            "impact": "Impact",
            "telegram": "Telegram",
            "pinterest": "Pinterest",
            "incy": "Incy"
        }
        self.dockbar_style_label = style_labels.get(self.dockbar_style, "Impact")
        if hasattr(self, "ids") and "dockbar_style_setting_row" in self.ids:
            self.ids.dockbar_style_setting_row.style_label = self.dockbar_style_label

        if self.dockbar_style == "pinterest":
            self.dockbar_selection_title = "Форма кнопок"
            sel_labels = {"squares": "Квадраты", "circles": "Кружки"}
            self.dockbar_selection_label = sel_labels.get(self.dockbar_selection, "Квадраты")
        else:
            self.dockbar_selection_title = "Выделение вкладки"
            sel_labels = {"oval": "Овальное", "square": "Квадратное", "none": "Без выделения"}
            self.dockbar_selection_label = sel_labels.get(self.dockbar_selection, "Без выделения")

        if hasattr(self, "ids") and "dockbar_selection_setting_row" in self.ids:
            self.ids.dockbar_selection_setting_row.title_text = self.dockbar_selection_title
            self.ids.dockbar_selection_setting_row.selection_label = self.dockbar_selection_label

        bg_labels = {
            "theme": "Согласно теме",
            "liquid_glass": "Liquid glass",
            "glassy_ice": "Glassy ice"
        }
        self.dockbar_bg_label = bg_labels.get(self.dockbar_bg, "Согласно теме")
        if hasattr(self, "ids") and "dockbar_bg_setting_row" in self.ids:
            self.ids.dockbar_bg_setting_row.bg_label = self.dockbar_bg_label

        # Pinterest locks the labels switch in the OFF state
        if hasattr(self, "ids") and "dockbar_labels_setting_row" in self.ids:
            row = self.ids.dockbar_labels_setting_row
            if self.dockbar_style == "pinterest":
                row.is_disabled = True
                row.is_active = False
            else:
                row.is_disabled = False
                row.is_active = self.dockbar_show_labels

    def _apply_accent_hex(self, hex_val: str):
        """Updates internal accent properties."""
        try:
            rgba = get_color_from_hex(hex_val)
            self.accent_color_hex = hex_val.upper()
            self.accent_color_rgba = [rgba[0], rgba[1], rgba[2], 1.0]
        except Exception:
            self.accent_color_hex = "#3D7BF5"
            self.accent_color_rgba = [0.24, 0.48, 0.95, 1.0]

        if hasattr(self, "ids") and "accent_setting_row" in self.ids:
            self.ids.accent_setting_row.accent_rgba = list(self.accent_color_rgba)

    def open_color_picker(self):
        """Opens ColorPickerDialog for choosing accent color."""
        dialog = ColorPickerDialog(
            initial_hex=self.accent_color_hex,
            on_select=self.on_accent_selected
        )
        dialog.open()

    def on_accent_selected(self, new_hex: str):
        """Callback when user selects a new accent color."""
        self._apply_accent_hex(new_hex)
        logger.info("New accent selected for profile %s: %s", self.profile_id, new_hex)

    def open_theme_dialog(self):
        """Opens ThemeModeDialog for choosing theme."""
        dialog = ThemeModeDialog(
            current_mode=self.theme_mode,
            on_select=self.on_theme_selected
        )
        dialog.open()

    def on_theme_selected(self, new_mode: str):
        """Callback when user selects a new theme mode."""
        self.theme_mode = new_mode
        self._update_theme_label()
        logger.info("New theme mode selected for profile %s: %s", self.profile_id, new_mode)

    def open_dockbar_style_dialog(self):
        """Opens DockbarStyleDialog for choosing dockbar style."""
        dialog = DockbarStyleDialog(
            current_style=self.dockbar_style,
            on_select=self.on_dockbar_style_selected
        )
        dialog.open()

    def on_dockbar_style_selected(self, new_style: str):
        """Callback when user selects a new dockbar style."""
        self.dockbar_style = new_style
        # Adjust default selection if switching between Pinterest and others
        if new_style == "pinterest" and self.dockbar_selection not in ("squares", "circles"):
            self.dockbar_selection = "squares"
        elif new_style != "pinterest" and self.dockbar_selection in ("squares", "circles"):
            self.dockbar_selection = "oval" if new_style == "telegram" else ("square" if new_style == "incy" else "none")

        self._update_dockbar_labels()
        logger.info("New dockbar style selected for profile %s: %s", self.profile_id, new_style)

    def open_dockbar_selection_dialog(self):
        """Opens DockbarSelectionDialog for choosing active tab highlight/shape."""
        dialog = DockbarSelectionDialog(
            dockbar_style=self.dockbar_style,
            current_selection=self.dockbar_selection,
            on_select=self.on_dockbar_selection_selected
        )
        dialog.open()

    def on_dockbar_selection_selected(self, new_selection: str):
        """Callback when user selects a dockbar tab highlight or button shape."""
        if self.dockbar_style == "pinterest":
            if new_selection not in ("squares", "circles"):
                new_selection = "squares"
        else:
            if new_selection not in ("oval", "square", "none"):
                new_selection = "none"
        self.dockbar_selection = new_selection
        self._update_dockbar_labels()
        logger.info("New dockbar selection selected for profile %s: %s", self.profile_id, new_selection)

    def toggle_dockbar_labels(self):
        """Toggles show/hide dockbar tab labels (disabled for Pinterest)."""
        if self.dockbar_style == "pinterest":
            return
        self.dockbar_show_labels = not self.dockbar_show_labels
        if hasattr(self, "ids") and "dockbar_labels_setting_row" in self.ids:
            self.ids.dockbar_labels_setting_row.is_active = self.dockbar_show_labels
        logger.info("Toggled dockbar_show_labels for profile %s to %s", self.profile_id, self.dockbar_show_labels)

    def set_dockbar_labels(self, value: bool):
        """Sets show/hide dockbar tab labels (disabled for Pinterest)."""
        if self.dockbar_style == "pinterest":
            return
        self.dockbar_show_labels = bool(value)
        if hasattr(self, "ids") and "dockbar_labels_setting_row" in self.ids:
            self.ids.dockbar_labels_setting_row.is_active = self.dockbar_show_labels
        logger.info("Set dockbar_show_labels for profile %s to %s", self.profile_id, self.dockbar_show_labels)

    def open_dockbar_bg_dialog(self):
        """Opens DockbarBgDialog for choosing dockbar background shader."""
        dialog = DockbarBgDialog(
            current_bg=self.dockbar_bg,
            on_select=self.on_dockbar_bg_selected
        )
        dialog.open()

    def on_dockbar_bg_selected(self, new_bg: str):
        """Callback when user selects a dockbar background."""
        if new_bg in ("theme", "liquid_glass", "glassy_ice"):
            self.dockbar_bg = new_bg
            self._update_dockbar_labels()
            logger.info("New dockbar background selected for profile %s: %s", self.profile_id, new_bg)

    def on_save_pressed(self):
        """Saves updated profile name, accent color, theme and dockbar settings, then returns to personalization screen."""
        clean = self.profile_name.strip()
        if not clean:
            self.error_message = "Название профиля не может быть пустым"
            return

        try:
            personalization_repo.update_profile_name(self.profile_id, clean)
            personalization_repo.update_profile_accent(self.profile_id, self.accent_color_hex)
            personalization_repo.update_profile_theme_mode(self.profile_id, self.theme_mode)
            personalization_repo.update_profile_dockbar_style(self.profile_id, self.dockbar_style)
            personalization_repo.update_profile_dockbar_selection(self.profile_id, self.dockbar_selection)
            personalization_repo.update_profile_dockbar_show_labels(self.profile_id, self.dockbar_show_labels)
            personalization_repo.update_profile_dockbar_bg(self.profile_id, self.dockbar_bg)

            # If this edited profile is currently active, immediately update active app theme, accent & dockbar
            p = personalization_repo.get_profile(self.profile_id)
            if p and p.get("is_active"):
                app = MDApp.get_running_app()
                if app:
                    if hasattr(app, "apply_profile_accent"):
                        app.apply_profile_accent(self.accent_color_hex)
                    if hasattr(app, "apply_theme_mode"):
                        app.apply_theme_mode(self.theme_mode)
                    if hasattr(app, "apply_dockbar_settings"):
                        app.apply_dockbar_settings(
                            self.dockbar_style,
                            self.dockbar_selection,
                            self.dockbar_show_labels,
                            bg=self.dockbar_bg
                        )

            if self.manager:
                self.manager.current = ScreenName.SETTINGS_PERSONALIZATION
        except Exception as e:
            self.error_message = str(e)

    def on_back_pressed(self):
        """Returns to personalization settings screen without saving."""
        if self.manager:
            self.manager.current = ScreenName.SETTINGS_PERSONALIZATION

