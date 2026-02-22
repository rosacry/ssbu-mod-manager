from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from enum import Enum


class ModStatus(Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


@dataclass
class ModFile:
    relative_path: str
    absolute_path: Path
    file_size: int = 0


@dataclass
class ModMetadata:
    has_config_json: bool = False
    fighter_kind: Optional[str] = None
    name_id: Optional[str] = None
    display_name: Optional[str] = None
    costume_slots: list[int] = field(default_factory=list)
    has_css_data: bool = False
    has_music: bool = False
    has_xmsbt: bool = False
    has_msbt: bool = False
    has_prc: bool = False
    categories: list[str] = field(default_factory=list)


@dataclass
class Mod:
    name: str
    path: Path
    status: ModStatus = ModStatus.ENABLED
    metadata: ModMetadata = field(default_factory=ModMetadata)
    files: list[ModFile] = field(default_factory=list)
    file_count: int = 0
    total_size: int = 0
    conflicts_with: list[str] = field(default_factory=list)

    @property
    def original_name(self) -> str:
        name = self.name
        if name.startswith("."):
            name = name[1:]
        return name
