"""Personalization repository managing UI appearance profiles and persistence."""
import os
import json
import uuid
from typing import List, Dict, Any, Optional
from pathlib import Path
from src.core.config import config
from src.core.logger import logger


DEFAULT_SYSTEM_PROFILE = {
    "id": "system",
    "name": "системный профиль",
    "description": "Стандартная тема оформления приложения",
    "is_system": True,
    "config": {
        "accent_color": "#3D7BF5",
        "theme_mode": "light",
        "dockbar_style": "impact",
        "dockbar_selection": "none",
        "dockbar_show_labels": True,
        "dockbar_bg": "theme"
    },
    "is_active": True
}


class PersonalizationRepository:
    """Manages custom and system personalization profiles."""

    def __init__(self, storage_file: Optional[Path] = None):
        self.storage_file = storage_file or (config.DATA_DIR / "personalization_profiles.json")

    def load_profiles(self) -> List[Dict[str, Any]]:
        """
        Loads all profiles from disk.
        Ensures the default system profile is always present as the first item.
        """
        if not self.storage_file.exists():
            default_list = [dict(DEFAULT_SYSTEM_PROFILE)]
            self.save_profiles(default_list)
            return default_list

        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = []

            # Check if system profile exists
            has_system = any(p.get("id") == "system" for p in data)
            if not has_system:
                data.insert(0, dict(DEFAULT_SYSTEM_PROFILE))

            # Ensure at least one profile is active
            has_active = any(p.get("is_active") for p in data)
            if not has_active and data:
                data[0]["is_active"] = True

            return data
        except Exception as e:
            logger.error("Failed to read personalization profiles: %s", e)
            default_list = [dict(DEFAULT_SYSTEM_PROFILE)]
            return default_list

    def save_profiles(self, profiles: List[Dict[str, Any]]) -> bool:
        """Saves profiles list to storage file."""
        try:
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(profiles, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error("Failed to save personalization profiles: %s", e)
            return False

    def get_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Returns a profile by its ID."""
        profiles = self.load_profiles()
        for p in profiles:
            if p.get("id") == profile_id:
                return p
        return None

    def get_active_profile(self) -> Dict[str, Any]:
        """Returns currently active profile or system profile."""
        profiles = self.load_profiles()
        for p in profiles:
            if p.get("is_active"):
                return p
        return profiles[0]

    def set_active_profile(self, profile_id: str) -> bool:
        """Sets the specified profile active and deactivates others."""
        profiles = self.load_profiles()
        found = False
        for p in profiles:
            if p.get("id") == profile_id:
                p["is_active"] = True
                found = True
            else:
                p["is_active"] = False

        if found:
            return self.save_profiles(profiles)
        return False

    def create_profile(self, name: str, config_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Creates a new profile with the given name and default or specified config.
        """
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Название профиля не может быть пустым")

        profiles = self.load_profiles()

        # Check for duplicate names (optional numbering)
        config_dict = dict(config_data or {})
        if "accent_color" not in config_dict:
            config_dict["accent_color"] = "#3D7BF5"
        if "theme_mode" not in config_dict:
            config_dict["theme_mode"] = "light"
        if "dockbar_style" not in config_dict:
            config_dict["dockbar_style"] = "impact"
        if "dockbar_selection" not in config_dict:
            config_dict["dockbar_selection"] = "none"
        if "dockbar_show_labels" not in config_dict:
            config_dict["dockbar_show_labels"] = True

        new_id = f"custom_{uuid.uuid4().hex[:8]}"
        new_profile = {
            "id": new_id,
            "name": clean_name,
            "is_system": False,
            "config": config_dict,
            "is_active": False
        }

        profiles.append(new_profile)
        self.save_profiles(profiles)
        logger.info("Created new personalization profile: %s (id=%s)", clean_name, new_id)
        return new_profile

    def get_profile_accent(self, profile_id: str) -> str:
        """Returns the accent color hex for the given profile, defaulting to #3D7BF5."""
        p = self.get_profile(profile_id)
        if p and isinstance(p.get("config"), dict):
            return p["config"].get("accent_color", "#3D7BF5")
        return "#3D7BF5"

    def get_active_accent_color(self) -> str:
        """Returns the accent color hex of the currently active profile."""
        active = self.get_active_profile()
        if active and isinstance(active.get("config"), dict):
            return active["config"].get("accent_color", "#3D7BF5")
        return "#3D7BF5"

    def update_profile_accent(self, profile_id: str, accent_hex: str) -> bool:
        """Updates the accent color hex for a profile."""
        clean_hex = accent_hex.strip().upper()
        if not clean_hex.startswith("#"):
            clean_hex = f"#{clean_hex}"
        if len(clean_hex) != 7:
            raise ValueError(f"Некорректный формат hex цвета (ожидается #RRGGBB): {accent_hex}")

        profiles = self.load_profiles()
        for p in profiles:
            if p.get("id") == profile_id:
                if not isinstance(p.get("config"), dict):
                    p["config"] = {}
                p["config"]["accent_color"] = clean_hex
                self.save_profiles(profiles)
                logger.info("Updated accent color for profile %s to %s", profile_id, clean_hex)
                return True
        return False

    def get_profile_theme_mode(self, profile_id: str) -> str:
        """Returns theme mode for profile ('light' | 'dark' | 'amoled'), defaulting to 'light'."""
        p = self.get_profile(profile_id)
        if p and isinstance(p.get("config"), dict):
            mode = p["config"].get("theme_mode", "light")
            if mode in ("light", "dark", "amoled"):
                return mode
        return "light"

    def get_active_theme_mode(self) -> str:
        """Returns theme mode for currently active profile."""
        active = self.get_active_profile()
        if active and isinstance(active.get("config"), dict):
            mode = active["config"].get("theme_mode", "light")
            if mode in ("light", "dark", "amoled"):
                return mode
        return "light"

    def get_active_profile_id(self) -> str:
        """Returns the ID of the currently active profile, defaulting to 'system'."""
        active = self.get_active_profile()
        return active.get("id", "system") if active else "system"

    def update_profile_theme_mode(self, profile_id: str, theme_mode: str) -> bool:
        """Updates theme mode ('light' | 'dark' | 'amoled') for a profile."""
        clean_mode = theme_mode.strip().lower()
        if clean_mode not in ("light", "dark", "amoled"):
            raise ValueError(f"Недопустимая тема '{theme_mode}'. Доступны: 'light', 'dark', 'amoled'")

        profiles = self.load_profiles()
        for p in profiles:
            if p.get("id") == profile_id:
                if not isinstance(p.get("config"), dict):
                    p["config"] = {}
                p["config"]["theme_mode"] = clean_mode
                self.save_profiles(profiles)
                logger.info("Updated theme_mode for profile %s to %s", profile_id, clean_mode)
                return True
        return False

    def get_profile_dockbar_style(self, profile_id: str) -> str:
        """Returns dockbar style ('impact' | 'telegram' | 'pinterest' | 'incy'), defaulting to 'impact'."""
        p = self.get_profile(profile_id)
        if p and isinstance(p.get("config"), dict):
            style = p["config"].get("dockbar_style", "impact")
            if style in ("impact", "telegram", "pinterest", "incy"):
                return style
        return "impact"

    def get_active_dockbar_style(self) -> str:
        """Returns dockbar style for currently active profile."""
        active = self.get_active_profile()
        if active and isinstance(active.get("config"), dict):
            style = active["config"].get("dockbar_style", "impact")
            if style in ("impact", "telegram", "pinterest", "incy"):
                return style
        return "impact"

    def update_profile_dockbar_style(self, profile_id: str, dockbar_style: str) -> bool:
        """Updates dockbar style ('impact' | 'telegram' | 'pinterest' | 'incy') for a profile."""
        clean_style = dockbar_style.strip().lower()
        if clean_style not in ("impact", "telegram", "pinterest", "incy"):
            raise ValueError(f"Недопустимый стиль докбара '{dockbar_style}'. Доступны: 'impact', 'telegram', 'pinterest', 'incy'")

        profiles = self.load_profiles()
        for p in profiles:
            if p.get("id") == profile_id:
                if not isinstance(p.get("config"), dict):
                    p["config"] = {}
                p["config"]["dockbar_style"] = clean_style
                # Validate selection consistency if switching to/from pinterest
                current_sel = p["config"].get("dockbar_selection", "none")
                if clean_style == "pinterest" and current_sel not in ("squares", "circles"):
                    p["config"]["dockbar_selection"] = "squares"
                elif clean_style != "pinterest" and current_sel not in ("oval", "square", "none"):
                    p["config"]["dockbar_selection"] = "oval" if clean_style == "telegram" else ("square" if clean_style == "incy" else "none")
                self.save_profiles(profiles)
                logger.info("Updated dockbar_style for profile %s to %s", profile_id, clean_style)
                return True
        return False

    def get_profile_dockbar_selection(self, profile_id: str) -> str:
        """Returns dockbar selection/shape for profile."""
        style = self.get_profile_dockbar_style(profile_id)
        p = self.get_profile(profile_id)
        if p and isinstance(p.get("config"), dict):
            sel = p["config"].get("dockbar_selection", "")
            if style == "pinterest":
                return sel if sel in ("squares", "circles") else "squares"
            else:
                return sel if sel in ("oval", "square", "none") else ("oval" if style == "telegram" else ("square" if style == "incy" else "none"))
        return "squares" if style == "pinterest" else ("oval" if style == "telegram" else ("square" if style == "incy" else "none"))

    def get_active_dockbar_selection(self) -> str:
        """Returns dockbar selection/shape for currently active profile."""
        active = self.get_active_profile()
        if active:
            return self.get_profile_dockbar_selection(active.get("id", "system"))
        return "none"

    def update_profile_dockbar_selection(self, profile_id: str, dockbar_selection: str) -> bool:
        """Updates dockbar selection/shape for a profile."""
        clean_sel = dockbar_selection.strip().lower()
        style = self.get_profile_dockbar_style(profile_id)
        if style == "pinterest":
            if clean_sel not in ("squares", "circles"):
                raise ValueError(f"Для стиля Pinterest доступны формы: 'squares', 'circles' (получено '{dockbar_selection}')")
        else:
            if clean_sel not in ("oval", "square", "none"):
                raise ValueError(f"Для стиля {style} доступны выделения: 'oval', 'square', 'none' (получено '{dockbar_selection}')")

        profiles = self.load_profiles()
        for p in profiles:
            if p.get("id") == profile_id:
                if not isinstance(p.get("config"), dict):
                    p["config"] = {}
                p["config"]["dockbar_selection"] = clean_sel
                self.save_profiles(profiles)
                logger.info("Updated dockbar_selection for profile %s to %s", profile_id, clean_sel)
                return True
        return False

    def get_profile_dockbar_show_labels(self, profile_id: str) -> bool:
        """Returns whether dockbar tab labels are enabled for profile (default: True)."""
        p = self.get_profile(profile_id)
        if p and isinstance(p.get("config"), dict):
            return bool(p["config"].get("dockbar_show_labels", True))
        return True

    def get_active_dockbar_show_labels(self) -> bool:
        """Returns whether dockbar tab labels are enabled for currently active profile."""
        active = self.get_active_profile()
        if active and isinstance(active.get("config"), dict):
            return bool(active["config"].get("dockbar_show_labels", True))
        return True

    def update_profile_dockbar_show_labels(self, profile_id: str, show_labels: bool) -> bool:
        """Updates dockbar_show_labels setting for a profile."""
        val = bool(show_labels)
        profiles = self.load_profiles()
        for p in profiles:
            if p.get("id") == profile_id:
                if not isinstance(p.get("config"), dict):
                    p["config"] = {}
                p["config"]["dockbar_show_labels"] = val
                self.save_profiles(profiles)
                logger.info("Updated dockbar_show_labels for profile %s to %s", profile_id, val)
                return True
        return False

    def get_profile_dockbar_bg(self, profile_id: str) -> str:
        """Returns dockbar background type for profile ('theme', 'liquid_glass', 'glassy_ice')."""
        p = self.get_profile(profile_id)
        if p and isinstance(p.get("config"), dict):
            bg = p["config"].get("dockbar_bg", "theme")
            return bg if bg in ("theme", "liquid_glass", "glassy_ice") else "theme"
        return "theme"

    def get_active_dockbar_bg(self) -> str:
        """Returns dockbar background type for currently active profile."""
        active = self.get_active_profile()
        if active and isinstance(active.get("config"), dict):
            bg = active["config"].get("dockbar_bg", "theme")
            return bg if bg in ("theme", "liquid_glass", "glassy_ice") else "theme"
        return "theme"

    def update_profile_dockbar_bg(self, profile_id: str, dockbar_bg: str) -> bool:
        """Updates dockbar_bg setting for a profile."""
        clean_bg = dockbar_bg.strip().lower()
        if clean_bg not in ("theme", "liquid_glass", "glassy_ice"):
            raise ValueError(
                f"Недопустимый фон докбара: '{dockbar_bg}'. "
                f"Допустимы: 'theme', 'liquid_glass', 'glassy_ice'"
            )

        profiles = self.load_profiles()
        for p in profiles:
            if p.get("id") == profile_id:
                if not isinstance(p.get("config"), dict):
                    p["config"] = {}
                p["config"]["dockbar_bg"] = clean_bg
                self.save_profiles(profiles)
                logger.info("Updated dockbar_bg for profile %s to %s", profile_id, clean_bg)
                return True
        return False

    def import_profile_json(self, json_str: str, fallback_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Parses and validates JSON string config, creating a new profile.
        """
        if not json_str or not json_str.strip():
            raise ValueError("Текст JSON пуст")

        try:
            parsed = json.loads(json_str.strip())
        except Exception as e:
            raise ValueError(f"Некорректный синтаксис JSON: {e}")

        if not isinstance(parsed, dict):
            raise ValueError("Конфиг профиля должен быть JSON-объектом (словарем)")

        # Determine name
        name = parsed.get("name") or parsed.get("title") or (fallback_name.strip() if fallback_name else "") or "Импортированный профиль"
        
        return self.create_profile(name=str(name), config_data=parsed)

    def update_profile_name(self, profile_id: str, new_name: str) -> bool:
        """Renames a custom profile."""
        clean_name = new_name.strip()
        if not clean_name:
            raise ValueError("Название профиля не может быть пустым")

        profiles = self.load_profiles()
        for p in profiles:
            if p.get("id") == profile_id:
                if p.get("is_system"):
                    raise ValueError("Нельзя переименовать системный профиль")
                p["name"] = clean_name
                self.save_profiles(profiles)
                logger.info("Renamed profile %s to '%s'", profile_id, clean_name)
                return True
        return False

    def delete_profile(self, profile_id: str) -> bool:
        """
        Deletes a custom profile.
        If the deleted profile was active, resets active profile to 'system'.
        """
        if profile_id == "system":
            raise ValueError("Нельзя удалить системный профиль")

        profiles = self.load_profiles()
        was_active = False
        new_list = []

        for p in profiles:
            if p.get("id") == profile_id:
                if p.get("is_system"):
                    raise ValueError("Нельзя удалить системный профиль")
                if p.get("is_active"):
                    was_active = True
            else:
                new_list.append(p)

        # If active was deleted, make system active
        if was_active:
            for p in new_list:
                if p.get("id") == "system":
                    p["is_active"] = True
                else:
                    p["is_active"] = False

        success = self.save_profiles(new_list)
        logger.info("Deleted personalization profile: %s", profile_id)
        return success


personalization_repo = PersonalizationRepository()
