from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_WINDOW_GEOMETRY = "1400x900"
DEFAULT_PAGE = "dashboard"
DEFAULT_UI_SCALE = 1.2


@dataclass
class AppSettings:
    eden_sdmc_path: Optional[Path] = None
    mods_path: Optional[Path] = None
    plugins_path: Optional[Path] = None
    css_mod_folder: Optional[Path] = None
    mod_disable_method: str = "move"
    theme: str = "Dark"
    window_geometry: str = DEFAULT_WINDOW_GEOMETRY
    last_opened_page: str = DEFAULT_PAGE
    auto_detect_eden: bool = True
    backup_before_merge: bool = True
    emulator: str = ""
    emulator_version: str = ""
    game_version: str = ""
    debug_mode: bool = False
    ui_scale: float = DEFAULT_UI_SCALE
    use_plugin_friendly_names: bool = True
    plugin_name_overrides: dict[str, str] = field(default_factory=dict)
    plugin_description_overrides: dict[str, str] = field(default_factory=dict)
    show_plugin_descriptions: bool = True
    mod_name_overrides: dict[str, str] = field(default_factory=dict)
    # Online compatibility checker policy.
    online_strict_audio_sync: bool = False
    online_strict_environment_match: bool = False
    experimental_spotify_enabled: bool = False
    spotify_client_id: str = ""
    spotify_access_token: str = ""
    spotify_refresh_token: str = ""
    spotify_token_expires_at: int = 0
    spotify_user_id: str = ""
    spotify_display_name: str = ""
    spotify_last_playlist_id: str = ""
    # Music scanning options
    music_scan_disabled_mods: bool = True
    music_extra_track_dirs: list[str] = field(default_factory=list)
