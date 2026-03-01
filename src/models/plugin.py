from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from enum import Enum


class PluginStatus(Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


@dataclass
class KnownPluginInfo:
    filename: str
    display_name: str
    description: str
    url: str = ""
    required: bool = False
    stable_mode_keep: bool = False


@dataclass
class Plugin:
    filename: str
    path: Path
    status: PluginStatus = PluginStatus.ENABLED
    file_size: int = 0
    known_info: Optional[KnownPluginInfo] = None

    @property
    def display_name(self) -> str:
        if self.known_info:
            return self.known_info.display_name
        return self.filename

    @property
    def description(self) -> str:
        if self.known_info:
            return self.known_info.description
        return "Unknown plugin"
