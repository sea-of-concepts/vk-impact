"""Entry point for VK_IMPACT application with fallback crash reporter."""
import os
import sys
import traceback

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Register cairo mock if native cairo is not present (required by KivyMD 2.0 FitImage / materialshapes on Android)
if "cairo" not in sys.modules:
    try:
        import cairo
    except ImportError:
        class _DummyCairoObject:
            def __init__(self, *args, **kwargs):
                pass
            def __getattr__(self, name):
                return _DummyCairoObject()
            def __call__(self, *args, **kwargs):
                return _DummyCairoObject()

        import types
        cairo_mod = types.ModuleType("cairo")
        cairo_mod.FORMAT_ARGB32 = 0
        cairo_mod.FORMAT_RGB24 = 1
        cairo_mod.FORMAT_A8 = 2
        cairo_mod.FORMAT_A1 = 3
        cairo_mod.FORMAT_RGB16_565 = 4
        cairo_mod.FORMAT_RGB30 = 5
        cairo_mod.Context = _DummyCairoObject
        cairo_mod.ImageSurface = _DummyCairoObject
        cairo_mod.SurfacePattern = _DummyCairoObject
        cairo_mod.Format = _DummyCairoObject
        sys.modules["cairo"] = cairo_mod



def log_crash(exc_text: str) -> str:
    """Writes crash traceback to all accessible storage locations and returns the primary saved path."""
    print("=== VK_IMPACT CRASH ===")
    print(exc_text)

    saved_paths = []

    # 1. Try Java FileOutputStream to public Downloads and Documents (accessible without root)
    try:
        from jnius import autoclass
        Environment = autoclass("android.os.Environment")
        File = autoclass("java.io.File")
        FileOutputStream = autoclass("java.io.FileOutputStream")
        String = autoclass("java.lang.String")
        for dir_type in [Environment.DIRECTORY_DOWNLOADS, Environment.DIRECTORY_DOCUMENTS]:
            try:
                public_dir = Environment.getExternalStoragePublicDirectory(dir_type)
                if public_dir:
                    public_dir.mkdirs()
                    target_file = File(public_dir, "vkimpact_crash.log")
                    fos = FileOutputStream(target_file)
                    fos.write(String(exc_text).getBytes("UTF-8"))
                    fos.flush()
                    fos.close()
                    saved_paths.append(target_file.getAbsolutePath())
                    print(f"Logged crash via Java to {target_file.getAbsolutePath()}")
            except Exception as e_pub:
                print(f"Failed Java write for {dir_type}: {e_pub}")
    except Exception:
        pass

    candidates = [
        "/storage/emulated/0/Download/vkimpact_crash.log",
        "/sdcard/Download/vkimpact_crash.log",
        "/storage/emulated/0/Documents/vkimpact_crash.log",
        "/sdcard/Documents/vkimpact_crash.log",
        "/storage/emulated/0/Android/data/org.impact.vkimpact/files/vkimpact_crash.log",
        "/sdcard/Android/data/org.impact.vkimpact/files/vkimpact_crash.log",
        "/sdcard/vkimpact_crash.log",
        os.path.expanduser("~/vkimpact_crash.log"),
        "vkimpact_crash.log"
    ]
    android_private = os.environ.get("ANDROID_PRIVATE")
    if android_private:
        candidates.append(os.path.join(android_private, "vkimpact_crash.log"))

    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        if activity:
            ext_dir = activity.getExternalFilesDir(None)
            if ext_dir:
                candidates.append(os.path.join(ext_dir.getAbsolutePath(), "vkimpact_crash.log"))
    except Exception:
        pass

    for p in candidates:
        try:
            parent = os.path.dirname(p)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(exc_text)
            if p not in saved_paths:
                saved_paths.append(p)
            print(f"Logged crash to {p}")
        except Exception:
            continue

    return saved_paths[0] if saved_paths else "Локальное хранилище"


def share_crash_text(text: str) -> bool:
    """Triggers Android system share sheet for crash traceback."""
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        if activity:
            Intent = autoclass("android.content.Intent")
            String = autoclass("java.lang.String")
            intent = Intent(Intent.ACTION_SEND)
            intent.setType("text/plain")
            intent.putExtra(Intent.EXTRA_SUBJECT, String("VK IMPACT Crash Log"))
            intent.putExtra(Intent.EXTRA_TEXT, String(text))
            chooser = Intent.createChooser(intent, String("Поделиться отчетом об ошибке"))
            activity.startActivity(chooser)
            return True
    except Exception as e:
        print(f"Failed to trigger Android share sheet: {e}")
    return False


def run_fallback_error_screen(exc_text: str):
    """Launches a pure Kivy crash display screen when main app initialization fails."""
    saved_path = log_crash(exc_text)
    try:
        from kivy.app import App
        from kivy.metrics import dp
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.label import Label
        from kivy.uix.textinput import TextInput
        from kivy.uix.button import Button
        from src.utils.android_clipboard import set_system_clipboard_text

        class CrashReportApp(App):
            def build(self):
                layout = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
                
                header = Label(
                    text="[b][color=ff4444]VK IMPACT - Ошибка приложения[/color][/b]",
                    markup=True,
                    size_hint_y=None,
                    height=dp(48),
                    font_size="18sp"
                )
                
                info = Label(
                    text=f"Лог ошибки сохранен в:\n{saved_path}",
                    size_hint_y=None,
                    height=dp(42),
                    font_size="11sp",
                    halign="center"
                )

                txt = TextInput(
                    text=exc_text,
                    readonly=False,
                    font_size="10sp",
                    background_color=(0.12, 0.12, 0.14, 1),
                    foreground_color=(0.95, 0.95, 0.95, 1)
                )

                btn_box = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(8))

                btn_share = Button(
                    text="Поделиться",
                    size_hint_x=0.35,
                    background_color=(0.18, 0.72, 0.42, 1),
                    font_size="12sp",
                    bold=True
                )
                btn_share.bind(on_release=lambda *_: share_crash_text(exc_text))

                btn_copy = Button(
                    text="Скопировать",
                    size_hint_x=0.4,
                    background_color=(0.24, 0.48, 0.95, 1),
                    font_size="12sp",
                    bold=True
                )

                def on_copy(*_):
                    try:
                        ok = set_system_clipboard_text(exc_text)
                        if ok:
                            btn_copy.text = "Скопировано!"
                        else:
                            btn_copy.text = "Буфер Kivy"
                    except Exception as ce:
                        btn_copy.text = f"Ошибка: {ce}"

                btn_copy.bind(on_release=on_copy)

                btn_exit = Button(
                    text="Закрыть",
                    size_hint_x=0.25,
                    background_color=(0.85, 0.25, 0.25, 1),
                    font_size="12sp",
                    bold=True
                )
                btn_exit.bind(on_release=lambda *_: sys.exit(0))

                btn_box.add_widget(btn_share)
                btn_box.add_widget(btn_copy)
                btn_box.add_widget(btn_exit)

                layout.add_widget(header)
                layout.add_widget(info)
                layout.add_widget(txt)
                layout.add_widget(btn_box)
                return layout

        CrashReportApp().run()
    except Exception as e:
        print(f"Failed to display crash screen: {e}\nOriginal error:\n{exc_text}")


def main():
    """Initializes window properties and runs the application."""
    # Window and keyboard configuration
    try:
        from kivy.utils import platform
        from kivy.core.window import Window
        Window.softinput_mode = "below_target"
        Window.keyboard_anim_args = {"t": "in_out_quart", "d": 0.25}
        if platform not in ("android", "ios"):
            Window.size = (420, 780)
            Window.minimum_width = 360
            Window.minimum_height = 600
    except Exception:
        pass

    try:
        from src.ui.app import VKImpactApp
        app = VKImpactApp()
        app.run()
    except Exception:
        err = traceback.format_exc()
        log_crash(err)
        run_fallback_error_screen(err)


if __name__ == "__main__":
    main()
