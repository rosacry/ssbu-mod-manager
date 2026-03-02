from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_INCIDENCE = 50  # Default BGM incidence/weighting in SSBU


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
class StageTrackSlot:
    stage_id: str
    stage_name: str
    slot_key: str
    ui_bgm_id: str
    filename: str
    display_name: str = ""
    incidence: int = DEFAULT_INCIDENCE
    order_number: int = 0
    is_likely_vanilla: bool = False


@dataclass
class MusicReplacementAssignment:
    stage_id: str
    slot_key: str
    replacement_track_id: str


@dataclass
class MusicAssignment:
    track_id: str
    stage_id: str
    order_number: int = 0
    incidence: int = DEFAULT_INCIDENCE


@dataclass
class BgmDatabaseEntry:
    ui_bgm_id: str
    stream_set_id: str = ""
    name_id: str = ""
    save_no: int = 0
    menu_value: int = 0
    is_custom: bool = False
