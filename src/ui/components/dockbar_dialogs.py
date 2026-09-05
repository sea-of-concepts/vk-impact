"""Dockbar style and selection modal dialogs."""
from typing import Optional, Callable
from kivy.uix.modalview import ModalView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty


class DockbarStyleOptionItem(ButtonBehavior, BoxLayout):
    """Clickable row item for dockbar style choice."""
    style_key = StringProperty("impact")
    title_text = StringProperty("")
    desc_text = StringProperty("")
    icon_name = StringProperty("dock-bottom")
    is_selected = BooleanProperty(False)
    dialog = ObjectProperty(None)

    def on_release(self):
        if self.dialog:
            self.dialog.select_style(self.style_key)


class DockbarStyleDialog(ModalView):
    """Modal dialog allowing selection between Impact, Telegram, Pinterest, and Incy."""

    selected_style = StringProperty("impact")
    on_select_callback = ObjectProperty(None)

    def __init__(self, current_style: str = "impact", on_select: Optional[Callable[[str], None]] = None, **kwargs):
        kwargs["selected_style"] = current_style if current_style in ("impact", "telegram", "pinterest", "incy") else "impact"
        kwargs["auto_dismiss"] = True
        super().__init__(**kwargs)
        self.on_select_callback = on_select

    def select_style(self, style_key: str):
        """Sets selected dockbar style, triggers callback and closes dialog."""
        if style_key in ("impact", "telegram", "pinterest", "incy"):
            self.selected_style = style_key
            if self.on_select_callback:
                self.on_select_callback(style_key)
            self.dismiss()


class DockbarSelectionOptionItem(ButtonBehavior, BoxLayout):
    """Clickable row item for dockbar selection/shape choice."""
    selection_key = StringProperty("none")
    title_text = StringProperty("")
    desc_text = StringProperty("")
    icon_name = StringProperty("circle-outline")
    is_selected = BooleanProperty(False)
    dialog = ObjectProperty(None)

    def on_release(self):
        if self.dialog:
            self.dialog.select_option(self.selection_key)


class DockbarSelectionDialog(ModalView):
    """Modal dialog allowing selection between oval, square, none, or squares, circles for Pinterest."""

    dockbar_style = StringProperty("impact")
    selected_option = StringProperty("none")
    dialog_title = StringProperty("Выделение вкладки")
    on_select_callback = ObjectProperty(None)
    options_container = ObjectProperty(None)

    def __init__(
        self,
        dockbar_style: str = "impact",
        current_selection: str = "none",
        on_select: Optional[Callable[[str], None]] = None,
        **kwargs
    ):
        clean_style = dockbar_style if dockbar_style in ("impact", "telegram", "pinterest", "incy") else "impact"
        kwargs["dockbar_style"] = clean_style

        if clean_style == "pinterest":
            kwargs["dialog_title"] = "Форма кнопок"
            kwargs["selected_option"] = current_selection if current_selection in ("squares", "circles") else "squares"
        else:
            kwargs["dialog_title"] = "Выделение активной вкладки"
            kwargs["selected_option"] = current_selection if current_selection in ("oval", "square", "none") else "none"

        kwargs["auto_dismiss"] = True
        super().__init__(**kwargs)
        self.on_select_callback = on_select

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        self.populate_options()

    def on_open(self):
        super().on_open()
        self.populate_options()

    def populate_options(self):
        """Populates only relevant options matching current dockbar style."""
        container = self.options_container or (self.ids.get("options_container") if hasattr(self, "ids") else None)
        if not container:
            return
        container.clear_widgets()

        if self.dockbar_style == "pinterest":
            items = [
                ("squares", "Квадраты", "Скругленные квадратные кнопки", "square-rounded-outline"),
                ("circles", "Кружки", "Круглые плавающие кнопки", "circle-outline"),
            ]
        else:
            items = [
                ("oval", "Овальное", "Капсульное выделение активной вкладки", "pill"),
                ("square", "Квадратное", "Скругленный прямоугольник", "square-rounded-outline"),
                ("none", "Без выделения", "Только цвет иконки и текста", "close-circle-outline"),
            ]

        for key, title, desc, icon in items:
            item = DockbarSelectionOptionItem()
            item.selection_key = key
            item.title_text = title
            item.desc_text = desc
            item.icon_name = icon
            item.is_selected = (self.selected_option == key)
            item.dialog = self
            container.add_widget(item)

    def select_option(self, option_key: str):
        """Sets selected option, triggers callback and closes dialog."""
        self.selected_option = option_key
        if self.on_select_callback:
            self.on_select_callback(option_key)
        self.dismiss()


class DockbarBgOptionItem(ButtonBehavior, BoxLayout):
    """Clickable row item for dockbar background choice."""
    bg_key = StringProperty("theme")
    title_text = StringProperty("")
    desc_text = StringProperty("")
    icon_name = StringProperty("palette-outline")
    is_selected = BooleanProperty(False)
    dialog = ObjectProperty(None)

    def on_release(self):
        if self.dialog:
            self.dialog.select_bg(self.bg_key)


class DockbarBgDialog(ModalView):
    """Modal dialog allowing selection between theme, liquid_glass, and glassy_ice."""

    selected_bg = StringProperty("theme")
    on_select_callback = ObjectProperty(None)
    options_container = ObjectProperty(None)

    def __init__(
        self,
        current_bg: str = "theme",
        on_select: Optional[Callable[[str], None]] = None,
        **kwargs
    ):
        clean_bg = current_bg if current_bg in ("theme", "liquid_glass", "glassy_ice") else "theme"
        kwargs["selected_bg"] = clean_bg
        kwargs["auto_dismiss"] = True
        super().__init__(**kwargs)
        self.on_select_callback = on_select

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        self.populate_options()

    def on_open(self):
        super().on_open()
        self.populate_options()

    def populate_options(self):
        """Populates the 3 background choices."""
        container = self.options_container or (self.ids.get("options_container") if hasattr(self, "ids") else None)
        if not container:
            return
        container.clear_widgets()

        items = [
            ("theme", "Согласно теме", "Стандартный цвет поверхности из темы", "palette-outline"),
            ("liquid_glass", "Liquid glass", "Шейдер жидкого стекла с волнами и преломлением", "water-outline"),
            ("glassy_ice", "Glassy ice", "Шейдер гранёного льда с трещинами и переливами", "snowflake"),
        ]

        for key, title, desc, icon in items:
            item = DockbarBgOptionItem()
            item.bg_key = key
            item.title_text = title
            item.desc_text = desc
            item.icon_name = icon
            item.is_selected = (self.selected_bg == key)
            item.dialog = self
            container.add_widget(item)

    def select_bg(self, bg_key: str):
        """Sets selected background, triggers callback and closes dialog."""
        if bg_key in ("theme", "liquid_glass", "glassy_ice"):
            self.selected_bg = bg_key
            if self.on_select_callback:
                self.on_select_callback(bg_key)
            self.dismiss()

