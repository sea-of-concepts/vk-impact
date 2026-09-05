"""Accent Color Picker modal dialog supporting RGB sliders, presets, and hex input without alpha channel."""
import re
from typing import Optional, Callable
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import StringProperty, ListProperty, NumericProperty, ObjectProperty
from kivy.utils import get_color_from_hex
from src.core.logger import logger


PRESET_COLORS = [
    "#3D7BF5",  # VK Impact Default Blue
    "#0077FF",  # Classic VK Blue
    "#2979FF",  # Bright Blue
    "#00BCD4",  # Cyan
    "#009688",  # Teal
    "#4CAF50",  # Green
    "#8BC34A",  # Light Green
    "#FFC107",  # Amber
    "#FF9800",  # Orange
    "#FF5722",  # Deep Orange
    "#F44336",  # Red
    "#E91E63",  # Pink
    "#9C27B0",  # Purple
    "#673AB7",  # Deep Purple
    "#3F51B5",  # Indigo
    "#607D8B",  # Blue Grey
]


class ColorPresetChip(ButtonBehavior, Widget):
    """Clickable color circle preset."""
    color_hex = StringProperty("#3D7BF5")
    color_rgba = ListProperty([0.24, 0.48, 0.95, 1.0])

    def on_color_hex(self, instance, value):
        try:
            rgba = get_color_from_hex(value)
            self.color_rgba = [rgba[0], rgba[1], rgba[2], 1.0]
        except Exception:
            pass


class ColorPickerDialog(ModalView):
    """RGB-only modal color picker without alpha channel."""

    selected_hex = StringProperty("#3D7BF5")
    selected_rgba = ListProperty([0.24, 0.48, 0.95, 1.0])

    r_val = NumericProperty(61)
    g_val = NumericProperty(123)
    b_val = NumericProperty(245)

    hex_input_text = StringProperty("#3D7BF5")
    error_message = StringProperty("")

    on_select_callback = ObjectProperty(None)

    _updating_internally = False

    def __init__(self, initial_hex: str = "#3D7BF5", on_select: Optional[Callable[[str], None]] = None, **kwargs):
        super().__init__(**kwargs)
        self.on_select_callback = on_select
        self.auto_dismiss = True
        self.set_color(initial_hex)

    def set_color(self, hex_val: str):
        """Sets picker state from hex value (#RRGGBB)."""
        clean = hex_val.strip().upper()
        if not clean.startswith("#"):
            clean = f"#{clean}"

        if not re.match(r"^#[0-9A-F]{6}$", clean):
            clean = "#3D7BF5"

        self._updating_internally = True
        try:
            r = int(clean[1:3], 16)
            g = int(clean[3:5], 16)
            b = int(clean[5:7], 16)

            self.r_val = r
            self.g_val = g
            self.b_val = b
            self.selected_hex = clean
            self.hex_input_text = clean
            self.selected_rgba = [r / 255.0, g / 255.0, b / 255.0, 1.0]
            self.error_message = ""
        except Exception as e:
            logger.error("Failed setting color from hex %s: %s", clean, e)
        finally:
            self._updating_internally = False

    def on_slider_change(self):
        """Called when R, G, or B slider values change."""
        if self._updating_internally:
            return

        r = int(self.r_val)
        g = int(self.g_val)
        b = int(self.b_val)
        hex_code = f"#{r:02X}{g:02X}{b:02X}"

        self._updating_internally = True
        self.selected_hex = hex_code
        self.hex_input_text = hex_code
        self.selected_rgba = [r / 255.0, g / 255.0, b / 255.0, 1.0]
        self.error_message = ""
        self._updating_internally = False

    def on_hex_text_input(self, text: str):
        """Called when user types into the hex text field."""
        if self._updating_internally:
            return

        clean = text.strip().upper()
        if not clean.startswith("#"):
            clean = f"#{clean}"

        if re.match(r"^#[0-9A-F]{6}$", clean):
            self.error_message = ""
            r = int(clean[1:3], 16)
            g = int(clean[3:5], 16)
            b = int(clean[5:7], 16)

            self._updating_internally = True
            self.r_val = r
            self.g_val = g
            self.b_val = b
            self.selected_hex = clean
            self.selected_rgba = [r / 255.0, g / 255.0, b / 255.0, 1.0]
            self._updating_internally = False
        else:
            self.error_message = "Формат: #RRGGBB"

    def select_preset(self, hex_val: str):
        """Applies a preset chip color."""
        self.set_color(hex_val)

    def confirm_selection(self):
        """Confirms the selected color and calls callback."""
        if self.on_select_callback:
            self.on_select_callback(self.selected_hex)
        self.dismiss()
