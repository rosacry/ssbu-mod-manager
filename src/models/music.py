from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MusicTrack:
    track_id: str
    file_path: Path
    display_name: str = ""
    source_mod: str = ""
    file_size: int = 0
    is_custom: bool = True
    is_favorite: bool = False


@dataclass
class StageInfo:
    stage_id: str
    stage_name: str


@dataclass
class StagePlaylist:
    stage_id: str
    stage_name: str
    tracks: list[MusicTrack] = field(default_factory=list)


@dataclass
class MusicAssignment:
    track_id: str
    stage_id: str
    order_number: int = 0
    incidence: int = 50


@dataclass
class BgmDatabaseEntry:
    ui_bgm_id: str
    stream_set_id: str = ""
    name_id: str = ""
    save_no: int = 0
    menu_value: int = 0
    is_custom: bool = False
