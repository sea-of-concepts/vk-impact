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



def log_crash(exc_text: str):
    """Writes crash traceback to all accessible storage locations."""
    print("=== VK_IMPACT STARTUP CRASH ===")
    print(exc_text)

    paths = [
        "/sdcard/Download/vkimpact_crash.log",
        "/storage/emulated/0/Download/vkimpact_crash.log",
        "/sdcard/vkimpact_crash.log",
        os.path.expanduser("~/vkimpact_crash.log"),
        "vkimpact_crash.log"
    ]
    android_private = os.environ.get("ANDROID_PRIVATE")
    if android_private:
        paths.insert(0, os.path.join(android_private, "vkimpact_crash.log"))

    for p in paths:
        try:
            parent = os.path.dirname(p)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(exc_text)
            print(f"Logged crash to {p}")
            break
        except Exception:
            continue


def run_fallback_error_screen(exc_text: str):
    """Launches a pure Kivy crash display screen when main app initialization fails."""
    try:
        from kivy.app import App
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.label import Label
        from kivy.uix.textinput import TextInput
        from kivy.uix.button import Button
        from kivy.core.clipboard import Clipboard

        class CrashReportApp(App):
            def build(self):
                layout = BoxLayout(orientation="vertical", padding=16, spacing=10)
                
                header = Label(
                    text="[b][color=ff4444]VK IMPACT - Startup Error[/color][/b]",
                    markup=True,
                    size_hint_y=None,
                    height=48,
                    font_size="18sp"
                )
                
                info = Label(
                    text="The app encountered an error during initialization:",
                    size_hint_y=None,
                    height=32,
                    font_size="13sp"
                )

                txt = TextInput(
                    text=exc_text,
                    readonly=True,
                    font_size="11sp",
                    background_color=(0.12, 0.12, 0.14, 1),
                    foreground_color=(0.95, 0.95, 0.95, 1)
                )

                btn = Button(
                    text="Copy Error to Clipboard",
                    size_hint_y=None,
                    height=48,
                    background_color=(0.24, 0.48, 0.95, 1)
                )

                def on_copy(*_):
                    try:
                        Clipboard.copy(exc_text)
                        btn.text = "Copied to Clipboard!"
                    except Exception as ce:
                        btn.text = f"Copy error: {ce}"

                btn.bind(on_release=on_copy)

                layout.add_widget(header)
                layout.add_widget(info)
                layout.add_widget(txt)
                layout.add_widget(btn)
                return layout

        CrashReportApp().run()
    except Exception as e:
        log_crash(f"Failed to display crash screen: {e}\nOriginal error:\n{exc_text}")


def main():
    """Initializes window properties and runs the application."""
    # Only constrain window dimensions on desktop platforms
    try:
        from kivy.utils import platform
        if platform not in ("android", "ios"):
            from kivy.core.window import Window
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
