"""Detect file conflicts across mods."""
from pathlib import Path
from src.models.conflict import FileConflict, ConflictSeverity, ConflictGroup
from src.core.file_scanner import FileScanner
from src.constants import MERGEABLE_EXTENSIONS

_SKIP_MOD_FOLDERS = {"_MergedResources", "_MusicConfig", ".disabled", "__pycache__"}
_MOD_CONTENT_DIRS = {
    "fighter", "sound", "stage", "ui", "effect", "camera",
    "assist", "item", "param", "stream",
}


class ConflictDetector:
    def __init__(self):
        self.scanner = FileScanner()

    def detect_conflicts(self, mods_root: Path) -> list[FileConflict]:
        """Detect all file conflicts across enabled mods."""
        file_index = self.scanner.build_file_index(mods_root)
        conflicts = []

        for relative_path, providers in file_index.items():
            if len(providers) < 2:
                continue

            ext = Path(relative_path).suffix.lower()
            severity = self._classify_severity(ext, relative_path)
            is_mergeable = ext in MERGEABLE_EXTENSIONS

            conflict = FileConflict(
                relative_path=relative_path,
                mods_involved=[p[0] for p in providers],
                mod_paths=[p[1] for p in providers],
                severity=severity,
                file_type=ext,
                is_mergeable=is_mergeable,
            )
            conflicts.append(conflict)

        # Also surface folder-structure issues that break mod loading
        # even without overlapping files (e.g. one extra wrapper folder).
        conflicts.extend(self._detect_structure_conflicts(mods_root))

        # Sort by severity (critical first)
        severity_order = {
            ConflictSeverity.CRITICAL: 0,
            ConflictSeverity.HIGH: 1,
            ConflictSeverity.MEDIUM: 2,
            ConflictSeverity.LOW: 3,
        }
        conflicts.sort(key=lambda c: (
            severity_order.get(c.severity, 99),
            str(c.relative_path).lower(),
        ))
        return conflicts

    def group_conflicts(self, conflicts: list[FileConflict]) -> list[ConflictGroup]:
        """Group related conflicts together."""
        groups = {}

        for c in conflicts:
            if c.file_type in (".xmsbt", ".msbt"):
                key = "Text/Message Conflicts"
                desc = "XMSBT/MSBT text file conflicts. These cause missing text in-game."
                auto = c.is_mergeable
            elif c.file_type == ".prc":
                key = "Parameter Conflicts"
                desc = "PRC parameter file conflicts. May cause crashes or incorrect behavior."
                auto = False
            elif c.file_type in (".bntx", ".nutexb"):
                key = "Texture Conflicts"
                desc = "Texture file conflicts. Last-loaded mod wins."
                auto = False
            elif c.file_type == ".nus3audio":
                key = "Audio Conflicts"
                desc = "Audio file conflicts. Last-loaded mod wins."
                auto = False
            else:
                key = "Other Conflicts"
                desc = "Miscellaneous file conflicts."
                auto = False

            if key not in groups:
                groups[key] = ConflictGroup(
                    group_name=key,
                    description=desc,
                    auto_resolvable=auto,
                )
            groups[key].conflicts.append(c)

        return list(groups.values())

    def _classify_severity(self, ext: str, relative_path: str) -> ConflictSeverity:
        """Classify conflict severity based on file type and path."""
        rel_lower = relative_path.lower()

        if ext in (".xmsbt", ".msbt"):
            return ConflictSeverity.HIGH

        if ext == ".prc":
            if "ui_chara_db" in rel_lower or "ui_bgm_db" in rel_lower:
                return ConflictSeverity.CRITICAL
            return ConflictSeverity.MEDIUM

        if ext in (".bntx", ".nutexb", ".nus3audio"):
            return ConflictSeverity.LOW

        return ConflictSeverity.MEDIUM

    def _detect_structure_conflicts(self, mods_root: Path) -> list[FileConflict]:
        """Detect nested-mod folder structure issues as conflict entries."""
        conflicts: list[FileConflict] = []
        try:
            folders = sorted(
                [f for f in mods_root.iterdir() if f.is_dir()],
                key=lambda p: p.name.lower(),
            )
        except (PermissionError, OSError):
            return conflicts

        for folder in folders:
            name = folder.name
            if name.startswith(".") or name in _SKIP_MOD_FOLDERS:
                continue

            nested_child = self._find_single_nested_content_child(folder)
            if nested_child is None:
                continue

            rel = f"structure/{name}.nestedmod"
            conflicts.append(FileConflict(
                relative_path=rel,
                mods_involved=[name],
                mod_paths=[folder],
                severity=ConflictSeverity.HIGH,
                file_type=".nestedmod",
                is_mergeable=False,
            ))

        return conflicts

    def _has_direct_mod_content(self, folder: Path) -> bool:
        """Return True when folder already contains expected SSBU mod roots."""
        try:
            for child in folder.iterdir():
                child_name = child.name.lower()
                if child.is_dir() and child_name in _MOD_CONTENT_DIRS:
                    return True
                if child.is_file() and child_name == "config.json":
                    return True
        except (PermissionError, OSError):
            return False
        return False

    def _find_single_nested_content_child(self, folder: Path) -> Path | None:
        """Detect one wrapper directory that contains actual mod content."""
        if self._has_direct_mod_content(folder):
            return None

        try:
            visible_children = [c for c in folder.iterdir() if not c.name.startswith(".")]
        except (PermissionError, OSError):
            return None

        subdirs = [c for c in visible_children if c.is_dir()]
        if len(subdirs) != 1:
            return None

        nested = subdirs[0]
        return nested if self._has_direct_mod_content(nested) else None
