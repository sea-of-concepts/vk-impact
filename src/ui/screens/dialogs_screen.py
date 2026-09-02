"""Screen displaying list of conversations with folder navigation and dockbar."""
from typing import Optional, List
from kivy.properties import ObjectProperty
from kivy.clock import Clock
from kivymd.uix.screen import MDScreen
from kivymd.uix.dialog import MDDialog, MDDialogHeadlineText, MDDialogSupportingText, MDDialogContentContainer, MDDialogButtonContainer
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText
from src.ui.components.folder_chip import FolderChip
from src.domain.dialogs_viewmodel import DialogsViewModel
from src.core.constants import ScreenName


class DialogsScreen(MDScreen):
    """View displaying list of conversations, folder tabs and dockbar."""
    vm = ObjectProperty(None)

    def __init__(self, **kwargs):
        self.vm = DialogsViewModel()
        super().__init__(**kwargs)
        self.name = ScreenName.DIALOGS
        self._add_folder_dialog: Optional[MDDialog] = None
        self._folder_input: Optional[MDTextField] = None

        # Bind reactive properties for folder chips
        self.vm.bind(folders=self._render_folder_chips, active_folder_id=self._update_active_chip)

    def on_enter(self, *args):
        """Called each time the screen is displayed."""
        if hasattr(self.ids, "dockbar"):
            self.ids.dockbar.sync_with_screen()
        self._render_folder_chips()
        if not self.vm._all_dialogs:
            self.vm.load_dialogs()
        else:
            self.vm._apply_folder_filter()

    def open_chat(self, peer_id: int, title: str, avatar_url: str = ""):
        """Navigates to the chat screen."""
        if not self.manager:
            return
            
        chat_screen = self.manager.get_screen(ScreenName.CHAT)
        if chat_screen:
            chat_screen.setup_chat(peer_id=peer_id, title=title, avatar_url=avatar_url)
            self.manager.current = ScreenName.CHAT

    def on_rv_scroll(self, scroll_y: float):
        """Called when user scrolls near the bottom of a scrollable conversations list."""
        if scroll_y <= 0.08 and len(self.vm.dialogs) >= 15 and not self.vm.is_loading_more and self.vm.has_more:
            self.vm.load_more_dialogs()

    def _render_folder_chips(self, *args):
        """Renders folder chips inside the horizontal scroll container."""
        if "folder_container" not in self.ids:
            return
        
        container = self.ids.folder_container
        container.clear_widgets()

        for f in self.vm.folders:
            f_id = f["id"]
            title = f["title"]
            is_active = (f_id == self.vm.active_folder_id)

            chip = FolderChip(
                folder_id=f_id,
                title=title,
                is_active=is_active,
                is_system=f["is_system"]
            )
            chip.bind(on_release=lambda instance, fid=f_id: self.vm.select_folder(fid))
            container.add_widget(chip)

        # Add '+' button at the end for custom folder creation
        from kivy.uix.behaviors import ButtonBehavior
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.label import Label
        from kivy.metrics import dp

        class AddBtn(ButtonBehavior, BoxLayout):
            pass

        add_btn = AddBtn(
            size_hint=(None, None),
            size=(dp(32), dp(32)),
            padding=[dp(6), dp(2)]
        )
        add_lbl = Label(
            text="+",
            font_size="22sp",
            bold=True,
            color=(0.24, 0.48, 0.95, 1)
        )
        add_btn.add_widget(add_lbl)
        add_btn.bind(on_release=lambda x: self.show_add_folder_dialog())
        container.add_widget(add_btn)

    def _update_active_chip(self, *args):
        """Updates is_active flag on existing chips."""
        if "folder_container" not in self.ids:
            return
        for child in self.ids.folder_container.children:
            if isinstance(child, FolderChip):
                child.is_active = (child.folder_id == self.vm.active_folder_id)

    def show_add_folder_dialog(self):
        """Opens modal dialog to create a custom folder."""
        self._folder_input = MDTextField(
            mode="outlined",
            size_hint_x=1
        )
        self._folder_input.add_widget(MDTextFieldHintText(text="Название папки"))

        self._add_folder_dialog = MDDialog(
            MDDialogHeadlineText(text="Новая папка"),
            MDDialogSupportingText(text="Введите название для локальной папки чатов:"),
            MDDialogContentContainer(
                self._folder_input,
                orientation="vertical",
                padding=[0, 10, 0, 10]
            ),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text="Отмена"),
                    style="tonal",
                    on_release=lambda x: self._add_folder_dialog.dismiss()
                ),
                MDButton(
                    MDButtonText(text="Создать"),
                    style="filled",
                    on_release=lambda x: self._create_custom_folder()
                ),
                spacing="8dp"
            )
        )
        self._add_folder_dialog.open()

    def _create_custom_folder(self):
        """Handles confirmation of custom folder creation."""
        if not self._folder_input or not self._folder_input.text.strip():
            return
        
        name = self._folder_input.text.strip()
        if self._add_folder_dialog:
            self._add_folder_dialog.dismiss()
            
        # Creates custom folder
        self.vm.add_custom_folder(title=name, peer_ids=[])
