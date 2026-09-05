"""Unit tests for PersonalizationRepository and profile management rules."""
import os
import sys
import tempfile
from pathlib import Path
import pytest

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.repositories.personalization_repo import PersonalizationRepository


def test_default_system_profile_initialization():
    """Verifies that default system profile is initialized if storage file is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "profiles.json"
        repo = PersonalizationRepository(storage_file=storage_file)

        profiles = repo.load_profiles()
        assert len(profiles) == 1
        sys_prof = profiles[0]
        assert sys_prof["id"] == "system"
        assert sys_prof["name"] == "системный профиль"
        assert sys_prof["is_system"] is True
        assert sys_prof["is_active"] is True


def test_create_custom_profile():
    """Verifies creating a custom profile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "profiles.json"
        repo = PersonalizationRepository(storage_file=storage_file)

        # Empty name should raise ValueError
        with pytest.raises(ValueError, match="не может быть пустым"):
            repo.create_profile("   ")

        p = repo.create_profile("Ночной стиль")
        assert p["name"] == "Ночной стиль"
        assert p["is_system"] is False
        assert p["id"].startswith("custom_")

        profiles = repo.load_profiles()
        assert len(profiles) == 2
        assert profiles[0]["id"] == "system"
        assert profiles[1]["name"] == "Ночной стиль"


def test_import_profile_json_valid_and_invalid():
    """Verifies JSON import validation rules."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "profiles.json"
        repo = PersonalizationRepository(storage_file=storage_file)

        # 1. Valid JSON with name
        valid_json = '{"name": "Amoled Dark", "accent": "#ff9900", "font_scale": 1.1}'
        p1 = repo.import_profile_json(valid_json)
        assert p1["name"] == "Amoled Dark"
        assert p1["config"]["accent"] == "#ff9900"

        # 2. Valid JSON without name, uses fallback
        valid_json_no_name = '{"accent": "#0099ff"}'
        p2 = repo.import_profile_json(valid_json_no_name, fallback_name="Blue Theme")
        assert p2["name"] == "Blue Theme"

        # 3. Invalid JSON syntax
        with pytest.raises(ValueError, match="Некорректный синтаксис JSON"):
            repo.import_profile_json('{"name": broken json')

        # 4. JSON is not an object/dict
        with pytest.raises(ValueError, match="JSON-объектом"):
            repo.import_profile_json('[1, 2, 3]')

        # 5. Empty JSON
        with pytest.raises(ValueError, match="пуст"):
            repo.import_profile_json('')


def test_set_active_profile():
    """Verifies profile activation and switching."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "profiles.json"
        repo = PersonalizationRepository(storage_file=storage_file)

        p1 = repo.create_profile("Тема 1")
        p2 = repo.create_profile("Тема 2")

        # By default, system is active
        assert repo.get_active_profile()["id"] == "system"

        # Activate Тема 1
        repo.set_active_profile(p1["id"])
        active = repo.get_active_profile()
        assert active["id"] == p1["id"]
        assert active["name"] == "Тема 1"

        # Check in full list
        for p in repo.load_profiles():
            if p["id"] == p1["id"]:
                assert p["is_active"] is True
            else:
                assert p["is_active"] is False

        # Activate Тема 2
        repo.set_active_profile(p2["id"])
        assert repo.get_active_profile()["id"] == p2["id"]


def test_rename_profile():
    """Verifies renaming custom profiles and prohibiting renaming of system profile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "profiles.json"
        repo = PersonalizationRepository(storage_file=storage_file)

        p = repo.create_profile("Старое имя")
        repo.update_profile_name(p["id"], "Новое имя")

        updated = repo.get_profile(p["id"])
        assert updated["name"] == "Новое имя"

        # Renaming system profile must raise ValueError
        with pytest.raises(ValueError, match="Нельзя переименовать системный профиль"):
            repo.update_profile_name("system", "Взлом системы")


def test_delete_profile_and_reset_to_system():
    """Verifies deleting custom profiles and resetting active to system if deleted was active."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "profiles.json"
        repo = PersonalizationRepository(storage_file=storage_file)

        # Deleting system profile must raise ValueError
        with pytest.raises(ValueError, match="Нельзя удалить системный профиль"):
            repo.delete_profile("system")

        p1 = repo.create_profile("Профиль для удаления")
        repo.set_active_profile(p1["id"])
        assert repo.get_active_profile()["id"] == p1["id"]

        # Delete active profile
        repo.delete_profile(p1["id"])

        # System profile must now be active
        assert repo.get_profile(p1["id"]) is None
        assert repo.get_active_profile()["id"] == "system"
        assert len(repo.load_profiles()) == 1


def test_profile_accent_color_management():
    """Verifies accent color retrieval, updates, and validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "profiles.json"
        repo = PersonalizationRepository(storage_file=storage_file)

        # Default system profile accent
        assert repo.get_profile_accent("system") == "#3D7BF5"
        assert repo.get_active_accent_color() == "#3D7BF5"

        # Create custom profile
        custom = repo.create_profile("Зеленая тема")
        assert repo.get_profile_accent(custom["id"]) == "#3D7BF5"

        # Update accent color
        assert repo.update_profile_accent(custom["id"], "#4CAF50") is True
        assert repo.get_profile_accent(custom["id"]) == "#4CAF50"

        # Activate custom profile and check get_active_accent_color
        repo.set_active_profile(custom["id"])
        assert repo.get_active_accent_color() == "#4CAF50"

        # Invalid hex codes should raise ValueError
        with pytest.raises(ValueError, match="Некорректный формат hex"):
            repo.update_profile_accent(custom["id"], "123")

        with pytest.raises(ValueError, match="Некорректный формат hex"):
            repo.update_profile_accent(custom["id"], "#12345")


def test_color_picker_dialog_logic():
    """Verifies ColorPickerDialog RGB without alpha conversion logic."""
    from src.ui.components.color_picker_dialog import ColorPickerDialog

    dialog = ColorPickerDialog(initial_hex="#3D7BF5")
    assert dialog.selected_hex == "#3D7BF5"
    assert dialog.r_val == 61
    assert dialog.g_val == 123
    assert dialog.b_val == 245
    assert len(dialog.selected_rgba) == 4
    assert dialog.selected_rgba[3] == 1.0  # Strictly opaque (no alpha)

    # Test slider adjustment
    dialog.r_val = 255
    dialog.g_val = 0
    dialog.b_val = 128
    dialog.on_slider_change()
    assert dialog.selected_hex == "#FF0080"
    assert dialog.hex_input_text == "#FF0080"

    # Test preset selection
    dialog.select_preset("#4CAF50")
    assert dialog.selected_hex == "#4CAF50"
    assert dialog.r_val == 76
    assert dialog.g_val == 175
    assert dialog.b_val == 80

    # Test hex input typing
    dialog.on_hex_text_input("#00E676")
    assert dialog.selected_hex == "#00E676"
    assert dialog.error_message == ""

    # Test invalid hex input
    dialog.on_hex_text_input("invalid")
    assert "Формат" in dialog.error_message


def test_profile_theme_mode_management():
    """Verifies theme mode retrieval, updates, and validation in PersonalizationRepository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "profiles.json"
        repo = PersonalizationRepository(storage_file=storage_file)

        # Default system profile theme mode
        assert repo.get_profile_theme_mode("system") == "light"
        assert repo.get_active_theme_mode() == "light"

        # Create custom profile
        custom = repo.create_profile("Темный стиль")
        assert repo.get_profile_theme_mode(custom["id"]) == "light"

        # Update to dark
        assert repo.update_profile_theme_mode(custom["id"], "dark") is True
        assert repo.get_profile_theme_mode(custom["id"]) == "dark"

        # Update to amoled
        assert repo.update_profile_theme_mode(custom["id"], "amoled") is True
        assert repo.get_profile_theme_mode(custom["id"]) == "amoled"

        # Activate custom profile and verify active theme
        repo.set_active_profile(custom["id"])
        assert repo.get_active_theme_mode() == "amoled"

        # Invalid theme mode should raise ValueError
        with pytest.raises(ValueError, match="neon"):
            repo.update_profile_theme_mode(custom["id"], "neon")


def test_theme_mode_dialog_logic():
    """Verifies ThemeModeDialog selection and callback dispatch."""
    from src.ui.components.theme_mode_dialog import ThemeModeDialog

    selected = []

    def on_select(mode):
        selected.append(mode)

    dialog = ThemeModeDialog(current_mode="light", on_select=on_select)
    assert dialog.selected_mode == "light"

    # Select dark
    dialog.select_mode("dark")
    assert dialog.selected_mode == "dark"
    assert selected == ["dark"]

    # Select amoled
    dialog.select_mode("amoled")
    assert dialog.selected_mode == "amoled"
    assert selected == ["dark", "amoled"]


def test_app_theme_mode_palettes():
    """Verifies that VKImpactApp sets exact color palettes for Light, Dark, and AMOLED modes."""
    from src.ui.app import VKImpactApp

    app = VKImpactApp()

    # 1. Light Mode
    app.apply_theme_mode("light")
    assert app.theme_mode == "light"
    assert app.theme_cls.theme_style == "Light"
    assert app.bg_color == [0.96, 0.97, 0.98, 1.0]
    assert app.surface_color == [1.0, 1.0, 1.0, 1.0]
    assert app.card_bg == [1.0, 1.0, 1.0, 1.0]
    assert app.text_color == [0.1, 0.12, 0.16, 1.0]

    # 2. Dark Mode (VK Web graphite)
    app.apply_theme_mode("dark")
    assert app.theme_mode == "dark"
    assert app.theme_cls.theme_style == "Dark"
    assert app.bg_color == [0.08, 0.08, 0.09, 1.0]
    assert app.surface_color == [0.13, 0.13, 0.14, 1.0]
    assert app.card_bg == [0.16, 0.16, 0.18, 1.0]
    assert app.text_color == [0.92, 0.93, 0.95, 1.0]
    assert app.bubble_incoming_bg == [0.18, 0.19, 0.21, 1.0]

    # 3. AMOLED Mode (Pure Black)
    app.apply_theme_mode("amoled")
    assert app.theme_mode == "amoled"
    assert app.theme_cls.theme_style == "Dark"
    assert app.bg_color == [0.0, 0.0, 0.0, 1.0]
    assert app.surface_color == [0.05, 0.05, 0.05, 1.0]
    assert app.card_bg == [0.08, 0.08, 0.08, 1.0]
    assert app.text_color == [1.0, 1.0, 1.0, 1.0]
    assert app.bubble_incoming_bg == [0.12, 0.12, 0.14, 1.0]


def test_profile_edit_screen_theme_flow():
    """Verifies that ProfileEditScreen initializes with default 'light' theme and updates on selection."""
    from src.ui.screens.profile_edit_screen import ProfileEditScreen
    from src.data.repositories.personalization_repo import PersonalizationRepository

    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "profiles.json"
        repo = PersonalizationRepository(storage_file=storage_file)
        custom = repo.create_profile("Мой профиль")

        screen = ProfileEditScreen()
        # Mock personalization_repo inside profile_edit_screen module
        import src.ui.screens.profile_edit_screen as pes_module
        old_repo = pes_module.personalization_repo
        pes_module.personalization_repo = repo
        try:
            screen.set_profile(custom["id"])
            assert screen.theme_mode == "light"
            assert screen.theme_mode_label == "Светлая"

            # Change theme to amoled
            screen.on_theme_selected("amoled")
            assert screen.theme_mode == "amoled"
            assert screen.theme_mode_label == "AMOLED"

            # Save
            screen.on_save_pressed()
            saved_mode = repo.get_profile_theme_mode(custom["id"])
            assert saved_mode == "amoled"
        finally:
            pes_module.personalization_repo = old_repo


def test_compute_halftone_formula():
    """Verifies mathematical mean and tint blend formula."""
    from src.ui.app import compute_halftone

    black = [0.0, 0.0, 0.0, 1.0]
    white = [1.0, 1.0, 1.0, 1.0]
    mid = compute_halftone(black, white, weight_b=0.5)
    assert mid == [0.5, 0.5, 0.5, 1.0]

    # Halfway between dark surface and blue accent
    surface = [0.1, 0.1, 0.2, 1.0]
    accent = [0.2, 0.5, 1.0, 1.0]
    half = compute_halftone(surface, accent, weight_b=0.5)
    assert half[0] == 0.15
    assert half[1] == 0.3
    assert half[2] == 0.6
    assert half[3] == 1.0


def test_dockbar_profile_management():
    """Verifies dockbar style and selection getting, updating, validation and consistency."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "profiles.json"
        repo = PersonalizationRepository(storage_file=storage_file)

        # Default system profile
        assert repo.get_profile_dockbar_style("system") == "impact"
        assert repo.get_profile_dockbar_selection("system") == "none"

        # Create custom profile
        custom = repo.create_profile("Мой стиль")
        assert repo.get_profile_dockbar_style(custom["id"]) == "impact"
        assert repo.get_profile_dockbar_selection(custom["id"]) == "none"

        # Update style to telegram
        assert repo.update_profile_dockbar_style(custom["id"], "telegram") is True
        assert repo.get_profile_dockbar_style(custom["id"]) == "telegram"
        assert repo.update_profile_dockbar_selection(custom["id"], "oval") is True
        assert repo.get_profile_dockbar_selection(custom["id"]) == "oval"

        # Update style to pinterest -> selection automatically adjusts to squares
        assert repo.update_profile_dockbar_style(custom["id"], "pinterest") is True
        assert repo.get_profile_dockbar_style(custom["id"]) == "pinterest"
        assert repo.get_profile_dockbar_selection(custom["id"]) == "squares"
        # Update selection to circles
        assert repo.update_profile_dockbar_selection(custom["id"], "circles") is True
        assert repo.get_profile_dockbar_selection(custom["id"]) == "circles"

        # Update style to incy -> selection adjusts from circles to square
        assert repo.update_profile_dockbar_style(custom["id"], "incy") is True
        assert repo.get_profile_dockbar_style(custom["id"]) == "incy"
        assert repo.get_profile_dockbar_selection(custom["id"]) == "square"

        # Invalid style should raise ValueError
        with pytest.raises(ValueError, match="Недопустимый стиль"):
            repo.update_profile_dockbar_style(custom["id"], "unknown_style")

        # Verify dockbar_show_labels default and updating
        assert repo.get_profile_dockbar_show_labels("system") is True
        assert repo.get_profile_dockbar_show_labels(custom["id"]) is True
        assert repo.update_profile_dockbar_show_labels(custom["id"], False) is True
        assert repo.get_profile_dockbar_show_labels(custom["id"]) is False
        assert repo.update_profile_dockbar_show_labels(custom["id"], True) is True
        assert repo.get_profile_dockbar_show_labels(custom["id"]) is True


def test_dockbar_dialogs_logic():
    """Verifies DockbarStyleDialog and DockbarSelectionDialog callbacks, immediate selection and option population."""
    from src.ui.components.dockbar_dialogs import DockbarStyleDialog, DockbarSelectionDialog

    selected_style = []
    style_dialog = DockbarStyleDialog(current_style="incy", on_select=lambda s: selected_style.append(s))
    assert style_dialog.selected_style == "incy"
    style_dialog.select_style("telegram")
    assert selected_style == ["telegram"]

    # Pinterest selection dialog - immediate selected_option without flashing 'none'
    selected_sel = []
    sel_dialog = DockbarSelectionDialog(dockbar_style="pinterest", current_selection="circles", on_select=lambda s: selected_sel.append(s))
    assert sel_dialog.selected_option == "circles"
    assert sel_dialog.dialog_title == "Форма кнопок"
    sel_dialog.populate_options()
    if sel_dialog.options_container:
        keys = [child.selection_key for child in sel_dialog.options_container.children]
        assert "squares" in keys
        assert "circles" in keys
        assert "square" not in keys
        assert "oval" not in keys
    sel_dialog.select_option("circles")
    assert selected_sel == ["circles"]

    # Impact selection dialog - immediate selected_option square
    selected_impact = []
    impact_dialog = DockbarSelectionDialog(dockbar_style="impact", current_selection="square", on_select=lambda s: selected_impact.append(s))
    assert impact_dialog.selected_option == "square"
    assert impact_dialog.dialog_title == "Выделение активной вкладки"
    impact_dialog.populate_options()
    if impact_dialog.options_container:
        keys = [child.selection_key for child in impact_dialog.options_container.children]
        assert "square" in keys
        assert "oval" in keys
        assert "none" in keys
        assert "squares" not in keys
        assert "circles" not in keys
    impact_dialog.select_option("square")
    assert selected_impact == ["square"]


def test_app_dockbar_settings_and_halftones():
    """Verifies app-level dockbar settings, labels visibility, and halftone computation."""
    from src.ui.app import VKImpactApp

    app = VKImpactApp()
    app.apply_theme_mode("dark")
    app.apply_profile_accent("#3D7BF5")
    app.apply_dockbar_settings("telegram", "oval", show_labels=False)

    assert app.dockbar_style == "telegram"
    assert app.dockbar_selection == "oval"
    assert app.show_dockbar_labels is False
    assert len(app.dockbar_halftone_color) == 4
    assert len(app.dockbar_highlight_color) == 4
    assert app.dockbar_halftone_color[3] == 1.0
    assert app.dockbar_highlight_color[3] == 1.0

    app.apply_dockbar_settings("incy", "square", show_labels=True)
    assert app.dockbar_style == "incy"
    assert app.dockbar_selection == "square"
    assert app.show_dockbar_labels is True


def test_profile_edit_screen_labels_flow():
    """Verifies toggling and saving show_dockbar_labels in ProfileEditScreen."""
    from src.ui.screens.profile_edit_screen import ProfileEditScreen
    from src.data.repositories.personalization_repo import PersonalizationRepository
    import src.ui.screens.profile_edit_screen as pes_module

    from kivymd.app import MDApp
    from src.ui.app import VKImpactApp
    _app = MDApp.get_running_app() or VKImpactApp()

    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "profiles.json"
        repo = PersonalizationRepository(storage_file=storage_file)
        custom = repo.create_profile("Профиль тест лейблов")

        screen = ProfileEditScreen()
        old_repo = pes_module.personalization_repo
        pes_module.personalization_repo = repo
        try:
            screen.set_profile(custom["id"])
            assert screen.dockbar_show_labels is True

            # Toggle labels off
            screen.toggle_dockbar_labels()
            assert screen.dockbar_show_labels is False

            # Save
            screen.on_save_pressed()
            assert repo.get_profile_dockbar_show_labels(custom["id"]) is False

            # Set labels on
            screen.set_dockbar_labels(True)
            assert screen.dockbar_show_labels is True
            screen.on_save_pressed()
            assert repo.get_profile_dockbar_show_labels(custom["id"]) is True
        finally:
            pes_module.personalization_repo = old_repo


def test_dockbar_bg_repo_management():
    """Verifies dockbar_bg getters, setters, and validation in PersonalizationRepository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "profiles.json"
        repo = PersonalizationRepository(storage_file=storage_file)

        # Default system profile has 'theme'
        assert repo.get_profile_dockbar_bg("system") == "theme"
        assert repo.get_active_dockbar_bg() == "theme"

        custom = repo.create_profile("Профиль шейдер")
        assert repo.get_profile_dockbar_bg(custom["id"]) == "theme"

        # Update to liquid_glass
        assert repo.update_profile_dockbar_bg(custom["id"], "liquid_glass") is True
        assert repo.get_profile_dockbar_bg(custom["id"]) == "liquid_glass"

        # Update to glassy_ice
        assert repo.update_profile_dockbar_bg(custom["id"], "glassy_ice") is True
        assert repo.get_profile_dockbar_bg(custom["id"]) == "glassy_ice"

        # Invalid value raises ValueError
        with pytest.raises(ValueError, match="Недопустимый фон докбара"):
            repo.update_profile_dockbar_bg(custom["id"], "neon_matrix")


def test_dockbar_bg_dialog_logic():
    """Verifies DockbarBgDialog options and selection callback."""
    from src.ui.components.dockbar_dialogs import DockbarBgDialog

    selected = []
    dialog = DockbarBgDialog(current_bg="liquid_glass", on_select=lambda bg: selected.append(bg))
    assert dialog.selected_bg == "liquid_glass"

    dialog.select_bg("glassy_ice")
    assert dialog.selected_bg == "glassy_ice"
    assert selected == ["glassy_ice"]


def test_profile_edit_screen_pinterest_labels_lock_and_bg():
    """Verifies that selecting Pinterest locks dockbar labels switch to OFF and dockbar_bg works."""
    from src.ui.app import VKImpactApp
    from src.core.constants import ScreenName
    from src.data.repositories.personalization_repo import PersonalizationRepository
    import src.ui.screens.profile_edit_screen as pes_module

    app = VKImpactApp()
    sm = app.build()
    screen = sm.get_screen(ScreenName.PROFILE_EDIT)

    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "profiles.json"
        repo = PersonalizationRepository(storage_file=storage_file)
        custom = repo.create_profile("Профиль тест Pinterest Lock")

        old_repo = pes_module.personalization_repo
        pes_module.personalization_repo = repo
        try:
            screen.set_profile(custom["id"])
            assert screen.dockbar_style == "impact"
            labels_row = screen.ids.dockbar_labels_setting_row
            assert labels_row.is_disabled is False
            assert labels_row.is_active is True

            # Switch style to Pinterest
            screen.on_dockbar_style_selected("pinterest")
            assert screen.dockbar_style == "pinterest"
            assert labels_row.is_disabled is True
            assert labels_row.is_active is False

            # Toggling or setting labels while Pinterest is active should be blocked
            screen.toggle_dockbar_labels()
            assert labels_row.is_active is False
            screen.set_dockbar_labels(True)
            assert labels_row.is_active is False

            # Switch to glassy_ice background
            screen.on_dockbar_bg_selected("glassy_ice")
            assert screen.dockbar_bg == "glassy_ice"
            assert screen.dockbar_bg_label == "Glassy ice"

            # Save
            screen.on_save_pressed()
            assert repo.get_profile_dockbar_bg(custom["id"]) == "glassy_ice"
            assert repo.get_profile_dockbar_style(custom["id"]) == "pinterest"

            # Switch back to Telegram -> switch must unlock and restore user active state
            screen.on_dockbar_style_selected("telegram")
            assert screen.dockbar_style == "telegram"
            assert labels_row.is_disabled is False
            assert labels_row.is_active is True
        finally:
            pes_module.personalization_repo = old_repo


def test_dockbar_shaders_compilation():
    """Verifies that liquid_glass and glassy_ice GLSL shaders compile successfully without OpenGL errors."""
    from kivy.graphics import RenderContext
    from src.ui.components.dockbar_shader import SHADER_VS, LIQUID_GLASS_FS, GLASSY_ICE_FS

    # Liquid Glass
    rc1 = RenderContext(use_parent_projection=True, use_parent_modelview=True)
    rc1.shader.vs = SHADER_VS
    rc1.shader.fs = LIQUID_GLASS_FS
    assert rc1.shader.success == 1, f"Liquid Glass compilation failed: {rc1.shader.log}"

    # Glassy Ice
    rc2 = RenderContext(use_parent_projection=True, use_parent_modelview=True)
    rc2.shader.vs = SHADER_VS
    rc2.shader.fs = GLASSY_ICE_FS
    assert rc2.shader.success == 1, f"Glassy Ice compilation failed: {rc2.shader.log}"




