from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AppSettings:
    eden_sdmc_path: Optional[Path] = None
    mods_path: Optional[Path] = None
    plugins_path: Optional[Path] = None
    css_mod_folder: Optional[Path] = None
    mod_disable_method: str = "move"
    theme: str = "Dark"
    window_geometry: str = "1400x900"
    last_opened_page: str = "dashboard"
    auto_detect_eden: bool = True
    backup_before_merge: bool = True
    emulator: str = ""  # Empty = auto-detect
    debug_mode: bool = False
    ui_scale: float = 1.2  # 100% baseline (matches previous 120% density)
    use_plugin_friendly_names: bool = True
    plugin_name_overrides: dict[str, str] = field(default_factory=dict)
    plugin_description_overrides: dict[str, str] = field(default_factory=dict)
    show_plugin_descriptions: bool = True
    mod_name_overrides: dict[str, str] = field(default_factory=dict)
