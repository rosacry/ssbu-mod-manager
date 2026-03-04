"""Application configuration manager."""
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional
from src.models.settings import AppSettings, DEFAULT_WINDOW_GEOMETRY, DEFAULT_PAGE, DEFAULT_UI_SCALE

CONFIG_DIR = Path.home() / ".ssbu-mod-manager"
CONFIG_FILE = CONFIG_DIR / "config.json"

UI_SCALE_MIN = 0.6
UI_SCALE_MAX = 2.0

class ConfigManager:
    def __init__(self):
        self._lock = threading.Lock()
        self.settings = AppSettings()

    def load(self) -> AppSettings:
        """Load settings from config file."""
        with self._lock:
            return self._load_locked()

    def _load_locked(self) -> AppSettings:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                raw_overrides = data.get("plugin_name_overrides", {})
                if not isinstance(raw_overrides, dict):
                    raw_overrides = {}
                raw_desc_overrides = data.get("plugin_description_overrides", {})
                if not isinstance(raw_desc_overrides, dict):
                    raw_desc_overrides = {}
                raw_mod_overrides = data.get("mod_name_overrides", {})
                if not isinstance(raw_mod_overrides, dict):
                    raw_mod_overrides = {}
                self.settings = AppSettings(
                    eden_sdmc_path=Path(data["eden_sdmc_path"]) if data.get("eden_sdmc_path") else None,
                    mods_path=Path(data["mods_path"]) if data.get("mods_path") else None,
                    plugins_path=Path(data["plugins_path"]) if data.get("plugins_path") else None,
                    css_mod_folder=Path(data["css_mod_folder"]) if data.get("css_mod_folder") else None,
                    mod_disable_method=data.get("mod_disable_method", "move"),
                    theme=data.get("theme", "Dark"),
                    window_geometry=data.get("window_geometry", DEFAULT_WINDOW_GEOMETRY),
                    last_opened_page=data.get("last_opened_page", DEFAULT_PAGE),
                    auto_detect_eden=data.get("auto_detect_eden", True),
                    backup_before_merge=data.get("backup_before_merge", True),
                    emulator=data.get("emulator", ""),
                    emulator_version=str(data.get("emulator_version", "") or ""),
                    game_version=str(data.get("game_version", "") or ""),
                    debug_mode=data.get("debug_mode", False),
                    ui_scale=max(UI_SCALE_MIN, min(UI_SCALE_MAX, float(data.get("ui_scale", DEFAULT_UI_SCALE)))),
                    use_plugin_friendly_names=bool(data.get("use_plugin_friendly_names", True)),
                    plugin_name_overrides={
                        str(k): str(v)
                        for k, v in raw_overrides.items()
                        if str(v).strip()
                    },
                    plugin_description_overrides={
                        str(k): str(v)
                        for k, v in raw_desc_overrides.items()
                        if str(v).strip()
                    },
                    show_plugin_descriptions=bool(data.get("show_plugin_descriptions", True)),
                    mod_name_overrides={
                        str(k): str(v)
                        for k, v in raw_mod_overrides.items()
                        if str(v).strip()
                    },
                    online_strict_audio_sync=bool(data.get("online_strict_audio_sync", False)),
                    online_strict_environment_match=bool(
                        data.get("online_strict_environment_match", False)
                    ),
                    experimental_spotify_enabled=bool(
                        data.get("experimental_spotify_enabled", False)
                    ),
                    spotify_client_id=str(data.get("spotify_client_id", "") or ""),
                    spotify_access_token=str(data.get("spotify_access_token", "") or ""),
                    spotify_refresh_token=str(data.get("spotify_refresh_token", "") or ""),
                    spotify_token_expires_at=max(
                        0,
                        int(data.get("spotify_token_expires_at", 0) or 0),
                    ),
                    spotify_user_id=str(data.get("spotify_user_id", "") or ""),
                    spotify_display_name=str(data.get("spotify_display_name", "") or ""),
                    spotify_last_playlist_id=str(data.get("spotify_last_playlist_id", "") or ""),
                    music_scan_disabled_mods=bool(
                        data.get("music_scan_disabled_mods", True)
                    ),
                    music_extra_track_dirs=[
                        str(d) for d in (data.get("music_extra_track_dirs") or [])
                        if str(d).strip()
                    ],
                )
            except (json.JSONDecodeError, KeyError, TypeError, OSError,
                    ValueError, UnicodeDecodeError) as e:
                try:
                    from src.utils.logger import logger
                    logger.warn("Config", f"Failed to parse config, using defaults: {e}")
                except Exception:
                    pass
                self.settings = AppSettings()
        return self.settings

    def save(self, settings: Optional[AppSettings] = None) -> None:
        """Save settings to config file."""
        with self._lock:
            self._save_locked(settings)

    def _save_locked(self, settings: Optional[AppSettings] = None) -> None:
        if settings:
            self.settings = settings

        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            from src.utils.logger import logger
            logger.error("Config", f"Failed to create config directory: {e}")
            return

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
            "emulator_version": str(self.settings.emulator_version or ""),
            "game_version": str(self.settings.game_version or ""),
            "debug_mode": self.settings.debug_mode,
            "ui_scale": self.settings.ui_scale,
            "use_plugin_friendly_names": self.settings.use_plugin_friendly_names,
            "plugin_name_overrides": dict(self.settings.plugin_name_overrides or {}),
            "plugin_description_overrides": dict(self.settings.plugin_description_overrides or {}),
            "show_plugin_descriptions": bool(self.settings.show_plugin_descriptions),
            "mod_name_overrides": dict(self.settings.mod_name_overrides or {}),
            "online_strict_audio_sync": bool(self.settings.online_strict_audio_sync),
            "online_strict_environment_match": bool(
                self.settings.online_strict_environment_match
            ),
            "experimental_spotify_enabled": bool(
                self.settings.experimental_spotify_enabled
            ),
            "spotify_client_id": str(self.settings.spotify_client_id or ""),
            "spotify_access_token": str(self.settings.spotify_access_token or ""),
            "spotify_refresh_token": str(self.settings.spotify_refresh_token or ""),
            "spotify_token_expires_at": int(self.settings.spotify_token_expires_at or 0),
            "spotify_user_id": str(self.settings.spotify_user_id or ""),
            "spotify_display_name": str(self.settings.spotify_display_name or ""),
            "spotify_last_playlist_id": str(self.settings.spotify_last_playlist_id or ""),
            "music_scan_disabled_mods": bool(self.settings.music_scan_disabled_mods),
            "music_extra_track_dirs": list(self.settings.music_extra_track_dirs or []),
        }

        try:
            # Atomic write: write to temp file then rename to prevent corruption
            fd, tmp_path = tempfile.mkstemp(dir=str(CONFIG_DIR), suffix='.tmp')
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp_path, str(CONFIG_FILE))
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as e:
            from src.utils.logger import logger
            logger.error("Config", f"Failed to save config: {e}")

    def update_setting(self, key: str, value) -> None:
        """Update a single setting and save."""
        with self._lock:
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
                self._save_locked()
