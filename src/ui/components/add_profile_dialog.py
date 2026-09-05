"""Add Profile modal dialog supporting manual creation, JSON text paste, and file drop/picker."""
import os
import platform
from pathlib import Path
from typing import Optional, Callable
from kivy.core.window import Window
from kivy.uix.modalview import ModalView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import StringProperty, ObjectProperty
from src.data.repositories.personalization_repo import personalization_repo
from src.core.logger import logger


class DropZoneCard(ButtonBehavior, BoxLayout):
    """Clickable drop zone card."""
    pass


class AddProfileDialog(ModalView):

    """Modal dialog for creating or importing personalization profiles."""

    active_mode = StringProperty("create")  # "create" | "json" | "file"
    profile_name_input = StringProperty("")
    json_text_input = StringProperty("")
    file_path_input = StringProperty("")
    file_name_display = StringProperty("")
    file_content = StringProperty("")
    error_message = StringProperty("")

    on_success_callback = ObjectProperty(None)

    def __init__(self, on_success: Optional[Callable] = None, **kwargs):
        super().__init__(**kwargs)
        self.on_success_callback = on_success
        self.auto_dismiss = True

    def on_open(self):
        """Binds Window drop file event upon opening."""
        Window.bind(on_drop_file=self._on_drop_file)

    def on_dismiss(self):
        """Unbinds Window drop file event on close."""
        Window.unbind(on_drop_file=self._on_drop_file)

    def switch_mode(self, mode: str):
        """Switches between create, json text, and file modes."""
        self.active_mode = mode
        self.error_message = ""

    def _on_drop_file(self, window, file_path, *args):
        """Handles file drop from OS onto the application window."""
        if isinstance(file_path, bytes):
            try:
                file_path = file_path.decode("utf-8")
            except Exception:
                file_path = file_path.decode("cp1251", errors="ignore")

        file_path_str = str(file_path).strip()
        if not file_path_str:
            return

        self.active_mode = "file"
        try:
            with open(file_path_str, "r", encoding="utf-8") as f:
                content = f.read()

            self.file_path_input = file_path_str
            self.file_name_display = os.path.basename(file_path_str)
            self.file_content = content
            self.error_message = ""
            logger.info("File dropped into profile dialog: %s", self.file_name_display)
        except Exception as e:
            self.error_message = f"Не удалось прочесть файл: {e}"

    def browse_file(self):
        """Opens native file chooser on Windows or Android."""
        self.error_message = ""
        sys_name = platform.system()

        if sys_name == "Windows":
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                selected = filedialog.askopenfilename(
                    title="Выберите JSON файл профиля",
                    filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
                )
                root.destroy()
                if selected:
                    with open(selected, "r", encoding="utf-8") as f:
                        content = f.read()
                    self.file_path_input = selected
                    self.file_name_display = os.path.basename(selected)
                    self.file_content = content
                    self.error_message = ""
            except Exception as e:
                self.error_message = f"Ошибка выбора файла: {e}"
        else:
            try:
                from plyer import filechooser
                def _on_selection(selection):
                    if selection and selection[0]:
                        path_sel = selection[0]
                        with open(path_sel, "r", encoding="utf-8") as f:
                            content = f.read()
                        self.file_path_input = path_sel
                        self.file_name_display = os.path.basename(path_sel)
                        self.file_content = content
                        self.error_message = ""
                filechooser.open_file(on_selection=_on_selection, filters=[("*.json",)])
            except Exception as e:
                self.error_message = f"Проводник недоступен: {e}"

    def submit(self):
        """Validates input according to active mode and creates/imports the profile."""
        self.error_message = ""

        try:
            if self.active_mode == "create":
                name = self.profile_name_input.strip()
                if not name:
                    self.error_message = "Введите название профиля"
                    return
                personalization_repo.create_profile(name)

            elif self.active_mode == "json":
                text = self.json_text_input.strip()
                if not text:
                    self.error_message = "Вставьте JSON с конфигом"
                    return
                personalization_repo.import_profile_json(text)

            elif self.active_mode == "file":
                if not self.file_content.strip():
                    self.error_message = "Перетащите файл в окно или нажмите для выбора"
                    return
                fallback = Path(self.file_path_input).stem if self.file_path_input else None
                personalization_repo.import_profile_json(self.file_content, fallback_name=fallback)

            if self.on_success_callback:
                self.on_success_callback()

            self.dismiss()

        except ValueError as e:
            self.error_message = str(e)
        except Exception as e:
            self.error_message = f"Ошибка сохранения: {e}"
