from dataclasses import dataclass, field
from typing import Optional

PROFILE_VERSION = "1.0"


@dataclass
class ProfileModEntry:
    name: str
    enabled: bool = True
    file_hash: str = ""
    download_url: Optional[str] = None


@dataclass
class ProfilePluginEntry:
    filename: str
    enabled: bool = True
    file_size: int = 0
    file_hash: str = ""
    embedded_data: Optional[str] = None


@dataclass
class ProfileMusicConfig:
    exclude_vanilla: bool = False
    stage_assignments: dict = field(default_factory=dict)


@dataclass
class ShareProfile:
    version: str = PROFILE_VERSION
    profile_name: str = ""
    created_by: str = ""
    created_at: str = ""
    description: str = ""
    mods: list[ProfileModEntry] = field(default_factory=list)
    plugins: list[ProfilePluginEntry] = field(default_factory=list)
    music_config: Optional[ProfileMusicConfig] = None
    css_character_names: list[str] = field(default_factory=list)
