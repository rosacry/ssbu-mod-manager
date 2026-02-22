"""Resolve conflicts between mods - especially XMSBT merging."""
from pathlib import Path
from typing import Optional
from src.models.conflict import FileConflict, ResolutionStrategy
from src.utils.xmsbt_parser import parse_xmsbt, write_xmsbt, merge_xmsbt_files
from src.utils.file_utils import backup_file
from src.utils.logger import logger


class ConflictResolver:
    def __init__(self, mods_root: Path):
        self.mods_root = mods_root
        self.merged_output_dir = mods_root / "_MergedResources"

    def auto_merge_xmsbt(self, conflict: FileConflict, create_backup: bool = True) -> Optional[Path]:
        """Merge XMSBT files from multiple mods into _MergedResources and disable originals.

        Uses a union strategy: all labels from all files are included.
        For overlapping labels (same label, different text), the last mod's value wins.
        After merging, original XMSBT files are moved to
        _MergedResources/.originals/<mod_name>/ so that ARCropolis
        only loads the single merged version.
        """
        if not conflict.is_mergeable:
            return None

        merged_entries, overlapping = merge_xmsbt_files(conflict.mod_paths)

        if not merged_entries:
            return None

        # Backup originals before merge
        if create_backup:
            self.backup_originals(conflict)

        # Write merged output
        output_path = self.merged_output_dir / conflict.relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_xmsbt(output_path, merged_entries)

        # Move the original conflicting files out of their mod folders
        # into _MergedResources/.originals/<mod_name>/<relative_path> so that
        # ARCropolis doesn't see them at all (renaming in-place still causes
        # ARCropolis to detect the renamed files as conflicts).
        originals_dir = self.merged_output_dir / ".originals"
        disabled_count = 0
        for mod_name, mod_path in zip(conflict.mods_involved, conflict.mod_paths):
            try:
                if not mod_path.exists():
                    continue
                backup_dest = originals_dir / mod_name / conflict.relative_path
                backup_dest.parent.mkdir(parents=True, exist_ok=True)
                if not backup_dest.exists():
                    import shutil
                    shutil.move(str(mod_path), str(backup_dest))
                    disabled_count += 1
                    # Clean up empty parent directories in the mod folder
                    parent = mod_path.parent
                    mod_root = self.mods_root / mod_name
                    while parent != mod_root and parent.exists():
                        try:
                            if not any(parent.iterdir()):
                                parent.rmdir()
                                parent = parent.parent
                            else:
                                break
                        except OSError:
                            break
            except OSError as e:
                logger.warn("ConflictResolver",
                            f"Could not disable original: {mod_path.name} - {e}")

        if overlapping:
            logger.info("ConflictResolver",
                        f"Merged {conflict.relative_path} with {len(overlapping)} "
                        f"overlapping label(s) (last-mod-wins). "
                        f"Total labels: {len(merged_entries)}")
        else:
            logger.info("ConflictResolver",
                        f"Merged {conflict.relative_path}: {len(merged_entries)} labels")

        logger.info("ConflictResolver",
                    f"Disabled {disabled_count} original file(s) to prevent double-loading")

        conflict.resolution = ResolutionStrategy.MERGE
        conflict.resolved = True
        return output_path

    def backup_originals(self, conflict: FileConflict) -> list[Path]:
        """Backup original files before resolution."""
        backups = []
        for mod_path in conflict.mod_paths:
            backup = backup_file(mod_path)
            backups.append(backup)
        return backups

    def apply_resolution(self, conflict: FileConflict, strategy: ResolutionStrategy,
                         winner_mod: Optional[str] = None, create_backup: bool = True) -> Optional[Path]:
        """Apply a resolution strategy to a conflict. Always creates backups before modifying files."""
        if strategy == ResolutionStrategy.MERGE:
            return self.auto_merge_xmsbt(conflict, create_backup=create_backup)
        elif strategy == ResolutionStrategy.IGNORE:
            conflict.resolution = ResolutionStrategy.IGNORE
            conflict.resolved = True
            return None
        elif strategy in (ResolutionStrategy.KEEP_FIRST, ResolutionStrategy.KEEP_LAST):
            # Backup before resolution
            if create_backup:
                self.backup_originals(conflict)

            idx = 0 if strategy == ResolutionStrategy.KEEP_FIRST else -1
            source = conflict.mod_paths[idx]
            output_path = self.merged_output_dir / conflict.relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            import shutil
            shutil.copy2(source, output_path)
            conflict.resolution = strategy
            conflict.resolved = True
            return output_path
        elif strategy == ResolutionStrategy.MANUAL and winner_mod:
            if winner_mod not in conflict.mods_involved:
                return None

            # Backup before resolution
            if create_backup:
                self.backup_originals(conflict)

            idx = conflict.mods_involved.index(winner_mod)
            source = conflict.mod_paths[idx]
            output_path = self.merged_output_dir / conflict.relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            import shutil
            shutil.copy2(source, output_path)
            conflict.resolution = ResolutionStrategy.MANUAL
            conflict.resolved = True
            return output_path

        return None

    def preview_merge(self, conflict: FileConflict) -> dict:
        """Preview what a merge would look like."""
        if not conflict.is_mergeable:
            return {"error": "This conflict type cannot be merged"}

        merged_entries, overlapping = merge_xmsbt_files(conflict.mod_paths)

        per_mod = {}
        for mod_name, mod_path in zip(conflict.mods_involved, conflict.mod_paths):
            per_mod[mod_name] = parse_xmsbt(mod_path)

        return {
            "merged_entries": merged_entries,
            "overlapping_labels": list(overlapping),
            "total_entries": len(merged_entries),
            "per_mod_counts": {name: len(entries) for name, entries in per_mod.items()},
            "auto_mergeable": len(overlapping) == 0,
        }

    def resolve_all_auto(self, conflicts: list[FileConflict], create_backup: bool = True) -> list[Path]:
        """Auto-resolve all auto-resolvable conflicts. Creates backups before each merge."""
        resolved_paths = []
        for conflict in conflicts:
            if conflict.is_mergeable and not conflict.resolved:
                path = self.auto_merge_xmsbt(conflict, create_backup=create_backup)
                if path:
                    resolved_paths.append(path)
        return resolved_paths

    def restore_originals(self) -> int:
        """Restore original XMSBT files from _MergedResources/.originals/ back
        to their mod folders, undoing previous merges.

        Also removes the merged XMSBT files from _MergedResources.
        Returns count of files restored.
        """
        import shutil
        count = 0
        if not self.mods_root.exists():
            return count

        originals_dir = self.merged_output_dir / ".originals"

        # Restore originals from _MergedResources/.originals/<mod_name>/<path>
        if originals_dir.exists():
            for mod_dir in originals_dir.iterdir():
                if not mod_dir.is_dir():
                    continue
                mod_name = mod_dir.name
                target_mod = self.mods_root / mod_name
                for orig_file in mod_dir.rglob("*"):
                    if not orig_file.is_file():
                        continue
                    rel = orig_file.relative_to(mod_dir)
                    dest = target_mod / rel
                    try:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        if not dest.exists():
                            shutil.move(str(orig_file), str(dest))
                            count += 1
                        else:
                            orig_file.unlink()
                            count += 1
                    except OSError as e:
                        logger.warn("ConflictResolver",
                                    f"Could not restore {rel} to {mod_name}: {e}")

            # Clean up the .originals directory
            shutil.rmtree(str(originals_dir), ignore_errors=True)

        # Also handle legacy .xmsbt.merged files from older versions
        for merged_file in self.mods_root.rglob("*.xmsbt.merged"):
            original_path = merged_file.parent / merged_file.name.replace(".merged", "")
            try:
                if not original_path.exists():
                    merged_file.rename(original_path)
                    count += 1
                else:
                    merged_file.unlink()
                    count += 1
            except OSError as e:
                logger.warn("ConflictResolver", f"Could not restore {merged_file.name}: {e}")

        # Clean up merged XMSBT files from _MergedResources
        if self.merged_output_dir.exists():
            for xmsbt_file in self.merged_output_dir.rglob("*.xmsbt"):
                try:
                    xmsbt_file.unlink()
                    count += 1
                except OSError:
                    pass
            # Remove empty directories
            self._cleanup_empty_dirs(self.merged_output_dir)

        logger.info("ConflictResolver", f"Restored {count} original files")
        return count

    def _cleanup_empty_dirs(self, root: Path) -> None:
        """Recursively remove empty directories under root."""
        for dirpath in sorted(root.rglob("*"), reverse=True):
            if dirpath.is_dir():
                try:
                    if not any(dirpath.iterdir()):
                        dirpath.rmdir()
                except OSError:
                    pass
