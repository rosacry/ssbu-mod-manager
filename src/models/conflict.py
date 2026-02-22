from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from enum import Enum


class ConflictSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ResolutionStrategy(Enum):
    KEEP_FIRST = "keep_first"
    KEEP_LAST = "keep_last"
    MERGE = "merge"
    MANUAL = "manual"
    IGNORE = "ignore"


@dataclass
class FileConflict:
    relative_path: str
    mods_involved: list[str] = field(default_factory=list)
    mod_paths: list[Path] = field(default_factory=list)
    severity: ConflictSeverity = ConflictSeverity.MEDIUM
    file_type: str = ""
    is_mergeable: bool = False
    resolution: Optional[ResolutionStrategy] = None
    resolved: bool = False


@dataclass
class ConflictGroup:
    group_name: str
    description: str
    conflicts: list[FileConflict] = field(default_factory=list)
    auto_resolvable: bool = False
