"""Robust Android clipboard provider and safe patches for Kivy Clipboard and TextInput."""
import traceback
from kivy import Logger
from kivy.utils import platform


def get_system_clipboard_text() -> str:
    """Reads text from system clipboard with direct PyJnius Android support and multi-fallback."""
    if platform == "android":
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Context = autoclass("android.content.Context")
            activity = PythonActivity.mActivity
            if activity:
                clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE)
                if clipboard:
                    primary_clip = clipboard.getPrimaryClip()
                    if primary_clip and primary_clip.getItemCount() > 0:
                        item = primary_clip.getItemAt(0)
                        if item:
                            char_seq = item.coerceToText(activity.getApplicationContext())
                            if char_seq is not None:
                                return str(char_seq)
            return ""
        except Exception as e:
            Logger.warning(f"AndroidClipboard: PyJnius read failed: {e}")

    # Fallback to Kivy's core clipboard
    try:
        from kivy.core.clipboard import Clipboard
        if hasattr(Clipboard, "_orig_paste"):
            val = Clipboard._orig_paste()
        else:
            val = Clipboard.paste()
        if val is not None:
            if isinstance(val, bytes):
                return val.decode("utf-8", "ignore")
            return str(val)
    except Exception as e:
        Logger.warning(f"AndroidClipboard: Kivy paste fallback failed: {e}")

    return ""


def set_system_clipboard_text(text: str) -> bool:
    """Writes text to system clipboard with direct PyJnius Android support and multi-fallback."""
    text_str = str(text) if text is not None else ""
    success = False
    if platform == "android":
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Context = autoclass("android.content.Context")
            ClipData = autoclass("android.content.ClipData")
            String = autoclass("java.lang.String")
            activity = PythonActivity.mActivity
            if activity:
                clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE)
                if clipboard:
                    clip = ClipData.newPlainText(String("VK IMPACT"), String(text_str))
                    clipboard.setPrimaryClip(clip)
                    success = True
                    Logger.info("AndroidClipboard: Direct PyJnius setPrimaryClip succeeded")
        except Exception as e:
            Logger.warning(f"AndroidClipboard: Direct PyJnius write failed: {e}")

    # Also set Kivy's core clipboard
    try:
        from kivy.core.clipboard import Clipboard
        if hasattr(Clipboard, "_orig_copy"):
            Clipboard._orig_copy(text_str)
        else:
            Clipboard.copy(text_str)
        success = True
    except Exception as e:
        Logger.warning(f"AndroidClipboard: Kivy copy fallback failed: {e}")

    return success



def safe_textinput_paste(self):
    """Drop-in replacement for TextInput.paste that never crashes on Android CharSequence or null values."""
    try:
        self._ensure_clipboard()
        data = get_system_clipboard_text()
        if not data:
            return
        self.delete_selection()
        if not self.multiline:
            data = data.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        self.insert_text(data)
    except Exception as e:
        Logger.error(f"TextInput: safe paste error: {e}\n{traceback.format_exc()}")


def install_clipboard_patches():
    """Patches Kivy's Clipboard, TextInput, and TextInputCutCopyPaste to use robust handlers."""
    from kivy.uix.textinput import TextInput, TextInputCutCopyPaste
    from kivy.core.clipboard import Clipboard
    from kivy.metrics import dp

    # Save original references if not already saved
    if not hasattr(Clipboard, "_orig_paste"):
        Clipboard._orig_paste = Clipboard.paste
    if not hasattr(Clipboard, "_orig_copy"):
        Clipboard._orig_copy = Clipboard.copy

    # Patch TextInput.paste
    TextInput.paste = safe_textinput_paste

    # Patch Clipboard.paste and Clipboard.copy
    Clipboard.paste = staticmethod(get_system_clipboard_text)
    Clipboard.copy = staticmethod(set_system_clipboard_text)

    # Suppress Kivy's custom cut/copy/paste bubble on Android since Android native contextual Action Mode is active
    if platform == "android":
        TextInput.show_cut_copy_paste = lambda *args, **kwargs: None
    else:
        # On desktop, patch TextInputCutCopyPaste init for Russian labels, proper size, and arrow removal
        orig_cut_copy_paste_init = TextInputCutCopyPaste.__init__

        def custom_cut_copy_paste_init(self, **kwargs):
            orig_cut_copy_paste_init(self, **kwargs)
            self.show_arrow = False
            self.size_hint = (None, None)
            self.size = (dp(290), dp(44))
            if hasattr(self, "but_cut") and self.but_cut:
                self.but_cut.text = "Вырезать"
            if hasattr(self, "but_copy") and self.but_copy:
                self.but_copy.text = "Копировать"
            if hasattr(self, "but_paste") and self.but_paste:
                self.but_paste.text = "Вставить"
                self.but_paste.color = (0.32, 0.64, 1.0, 1)
            if hasattr(self, "but_selectall") and self.but_selectall:
                self.but_selectall.text = "Выбрать всё"

        TextInputCutCopyPaste.__init__ = custom_cut_copy_paste_init

    # Patch TextInput.on_focus to sync text buffer to Android InputConnection
    orig_on_focus = TextInput.on_focus
    def safe_on_focus(self, instance, value):
        if orig_on_focus:
            orig_on_focus(self, instance, value)
        if platform == "android":
            if value:
                reset_android_input(self.text)
            else:
                reset_android_input("")
    TextInput.on_focus = safe_on_focus

    # Ensure Android soft keyboard allows toolbar, clipboard, and suggestions
    # (TYPE_CLASS_TEXT = 1, TYPE_TEXT_FLAG_AUTO_CORRECT = 0x8000, TYPE_TEXT_FLAG_CAP_SENTENCES = 0x4000)
    if platform == "android":
        try:
            from jnius import autoclass
            full_input_type = 1 | 0x8000 | 0x4000
            SDLActivity = autoclass("org.libsdl.app.SDLActivity")
            SDLActivity.keyboardInputType = full_input_type
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            if hasattr(PythonActivity, "changeKeyboard"):
                PythonActivity.changeKeyboard(full_input_type)
            Logger.info(f"AndroidClipboard: Set keyboardInputType to {full_input_type}")
        except Exception as e:
            Logger.warning(f"AndroidClipboard: Failed to set keyboard input type: {e}")

    Logger.info("AndroidClipboard: Patches installed successfully")


def reset_android_input(text=""):
    """Resets the native Android InputConnection buffer with the current text or empty string."""
    if platform == "android":
        try:
            from jnius import autoclass
            SDLActivity = autoclass("org.libsdl.app.SDLActivity")
            if hasattr(SDLActivity, "resetInputConnection"):
                SDLActivity.resetInputConnection(text or "")
        except Exception as e:
            Logger.warning(f"AndroidClipboard: Failed to reset input connection: {e}")


def update_android_selection_colors(rgba):
    """Updates Android selection handles and highlight color to match the app's current theme."""
    if platform == "android":
        try:
            from jnius import autoclass
            r = int(rgba[0] * 255) & 0xFF
            g = int(rgba[1] * 255) & 0xFF
            b = int(rgba[2] * 255) & 0xFF
            a = int(rgba[3] * 255) & 0xFF if len(rgba) > 3 else 255
            val = (a << 24) | (r << 16) | (g << 8) | b
            if val >= 0x80000000:
                val -= 0x100000000
            SDLActivity = autoclass("org.libsdl.app.SDLActivity")
            if hasattr(SDLActivity, "setSelectionHandleColor"):
                SDLActivity.setSelectionHandleColor(val)
                Logger.info(f"AndroidClipboard: Updated handle color to {hex(val & 0xFFFFFFFF)}")
        except Exception as e:
            Logger.warning(f"AndroidClipboard: Failed to update selection handle color: {e}")


