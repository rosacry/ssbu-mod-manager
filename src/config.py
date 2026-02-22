"""Application configuration manager."""
import json
from pathlib import Path
from typing import Optional
from src.models.settings import AppSettings

CONFIG_DIR = Path.home() / ".ssbu-mod-manager"
CONFIG_FILE = CONFIG_DIR / "config.json"

class ConfigManager:
    def __init__(self):
        self.settings = AppSettings()

    def load(self) -> AppSettings:
        """Load settings from config file."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                self.settings = AppSettings(
                    eden_sdmc_path=Path(data["eden_sdmc_path"]) if data.get("eden_sdmc_path") else None,
                    mods_path=Path(data["mods_path"]) if data.get("mods_path") else None,
                    plugins_path=Path(data["plugins_path"]) if data.get("plugins_path") else None,
                    css_mod_folder=Path(data["css_mod_folder"]) if data.get("css_mod_folder") else None,
                    mod_disable_method=data.get("mod_disable_method", "rename"),
                    theme=data.get("theme", "Dark"),
                    window_geometry=data.get("window_geometry", "1400x900"),
                    last_opened_page=data.get("last_opened_page", "dashboard"),
                    auto_detect_eden=data.get("auto_detect_eden", True),
                    backup_before_merge=data.get("backup_before_merge", True),
                    emulator=data.get("emulator", ""),
                    debug_mode=data.get("debug_mode", False),
                )
            except (json.JSONDecodeError, KeyError, TypeError):
                self.settings = AppSettings()
        return self.settings

    def save(self, settings: Optional[AppSettings] = None) -> None:
        """Save settings to config file."""
        if settings:
            self.settings = settings
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            "eden_sdmc_path": str(self.settings.eden_sdmc_path) if self.settings.eden_sdmc_path else None,
            "mods_path": str(self.settings.mods_path) if self.settings.mods_path else None,
            "plugins_path": str(self.settings.plugins_path) if self.settings.plugins_path else None,
            "css_mod_folder": str(self.settings.css_mod_folder) if self.settings.css_mod_folder else None,
            "mod_disable_method": self.settings.mod_disable_method,
            "theme": self.settings.theme,
            "window_geometry": self.settings.window_geometry,
            "last_opened_page": self.settings.last_opened_page,
            "auto_detect_eden": self.settings.auto_detect_eden,
            "backup_before_merge": self.settings.backup_before_merge,
            "emulator": self.settings.emulator,
            "debug_mode": self.settings.debug_mode,
        }

        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=2)

    def update_setting(self, key: str, value) -> None:
        """Update a single setting and save."""
        if hasattr(self.settings, key):
            setattr(self.settings, key, value)
            self.save()
