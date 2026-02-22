"""Detect file conflicts across mods."""
from pathlib import Path
from src.models.conflict import FileConflict, ConflictSeverity, ConflictGroup
from src.core.file_scanner import FileScanner
from src.constants import CONFLICT_EXTENSIONS, MERGEABLE_EXTENSIONS


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

        # Sort by severity (critical first)
        severity_order = {
            ConflictSeverity.CRITICAL: 0,
            ConflictSeverity.HIGH: 1,
            ConflictSeverity.MEDIUM: 2,
            ConflictSeverity.LOW: 3,
        }
        conflicts.sort(key=lambda c: severity_order.get(c.severity, 99))
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
