"""Resolve conflicts between mods - especially text-file safety fixes."""
import re
import shutil
import threading
from pathlib import Path
from typing import Optional
from src.models.conflict import FileConflict, ResolutionStrategy
from src.utils.xmsbt_parser import (
    parse_xmsbt, write_xmsbt, merge_xmsbt_files,
    extract_entries_from_msbt, filter_custom_entries,
)
from src.utils.file_utils import backup_file
from src.utils.logger import logger

# Regex to match locale-specific MSBT filenames like msg_bgm+us_en.msbt
_LOCALE_MSBT_RE = re.compile(r'^(.+)\+[a-z]{2}_[a-z]{2}(\.msbt)$', re.IGNORECASE)
MSBT_GLOB = "*.msbt"
XMSBT_GLOB = "*.xmsbt"
XMSBT_MERGED_GLOB = "*.xmsbt.merged"
XMSBT_MANAGED_GLOB = "*.xmsbt.managed"
MANAGED_SUFFIX = ".managed"
MERGED_SUFFIX = ".merged"
MOD_FOLDER_PREFIXES_TO_SKIP = (".", "_")
MERGED_OUTPUT_DIRNAME = "_MergedResources"
ORIGINALS_DIRNAME = ".originals"
MERGED_CONFIG_FILENAME = "config.json"
# User policy: do not generate gameplay-facing merged overlay folders.
ENABLE_MERGED_RESOURCES_OUTPUT = False


class ConflictResolver:
    def __init__(self, mods_root: Path):
        self.mods_root = mods_root
        # Kept for legacy cleanup/migration only.
        self.merged_output_dir = mods_root / MERGED_OUTPUT_DIRNAME

    @staticmethod
    def _scan_cancelled(cancel_event: Optional[threading.Event]) -> bool:
        try:
            return cancel_event is not None and bool(cancel_event.is_set())
        except Exception:
            return False

    @staticmethod
    def _is_skipped_mod_folder(folder: Path) -> bool:
        return folder.name.startswith(MOD_FOLDER_PREFIXES_TO_SKIP)

    def cleanup_legacy_merged_resources(self) -> int:
        """Remove legacy _MergedResources folder if present.

        Returns the number of files that were present before cleanup.
        """
        if not self.merged_output_dir.exists():
            return 0

        files_found = 0
        try:
            files_found = sum(1 for p in self.merged_output_dir.rglob("*") if p.is_file())
        except OSError:
            files_found = 0

        try:
            shutil.rmtree(self.merged_output_dir, ignore_errors=True)
        except OSError:
            pass

        if files_found:
            logger.info(
                "ConflictResolver",
                f"Removed legacy _MergedResources ({files_found} file(s)).",
            )
        return files_found

    def auto_merge_xmsbt(self, conflict: FileConflict, create_backup: bool = True) -> Optional[Path]:
        """Legacy API retained for compatibility.

        Merged overlay output is disabled by policy, so this method no-ops.
        """
        if not ENABLE_MERGED_RESOURCES_OUTPUT:
            logger.info(
                "ConflictResolver",
                "auto_merge_xmsbt skipped: _MergedResources generation is disabled.",
            )
            return None

        if not conflict.is_mergeable:
            return None

        merged_entries, overlapping = merge_xmsbt_files(conflict.mod_paths)

        if not merged_entries:
            return None

        if create_backup:
            self.backup_originals(conflict)

        output_path = self.merged_output_dir / conflict.relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_xmsbt(output_path, merged_entries)

        if overlapping:
            logger.info("ConflictResolver",
                        f"Merged {conflict.relative_path} with {len(overlapping)} "
                        f"overlapping label(s) (last-mod-wins). "
                        f"Total labels: {len(merged_entries)}")
        else:
            logger.info("ConflictResolver",
                        f"Merged {conflict.relative_path}: {len(merged_entries)} labels")

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
            if not ENABLE_MERGED_RESOURCES_OUTPUT:
                logger.info(
                    "ConflictResolver",
                    "KEEP_FIRST/KEEP_LAST skipped: _MergedResources generation is disabled.",
                )
                return None

            if create_backup:
                self.backup_originals(conflict)

            idx = 0 if strategy == ResolutionStrategy.KEEP_FIRST else -1
            source = conflict.mod_paths[idx]
            output_path = self.merged_output_dir / conflict.relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(source, output_path)
            conflict.resolution = strategy
            conflict.resolved = True
            return output_path
        elif strategy == ResolutionStrategy.MANUAL and winner_mod:
            if not ENABLE_MERGED_RESOURCES_OUTPUT:
                logger.info(
                    "ConflictResolver",
                    "MANUAL resolution skipped: _MergedResources generation is disabled.",
                )
                return None

            if winner_mod not in conflict.mods_involved:
                return None

            if create_backup:
                self.backup_originals(conflict)

            idx = conflict.mods_involved.index(winner_mod)
            source = conflict.mod_paths[idx]
            output_path = self.merged_output_dir / conflict.relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

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
        if not ENABLE_MERGED_RESOURCES_OUTPUT:
            return []

        resolved_paths = []
        for conflict in conflicts:
            if conflict.is_mergeable and not conflict.resolved:
                path = self.auto_merge_xmsbt(conflict, create_backup=create_backup)
                if path:
                    resolved_paths.append(path)
        return resolved_paths

    def restore_originals(self) -> int:
        """Restore original files from legacy merge outputs and remove legacy folder."""
        count = 0
        if not self.mods_root.exists():
            return count

        originals_dir = self.merged_output_dir / ORIGINALS_DIRNAME

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

            shutil.rmtree(str(originals_dir), ignore_errors=True)

        for merged_file in self.mods_root.rglob(XMSBT_MERGED_GLOB):
            original_path = merged_file.parent / merged_file.name.replace(MERGED_SUFFIX, "")
            try:
                if not original_path.exists():
                    merged_file.rename(original_path)
                    count += 1
                else:
                    merged_file.unlink()
                    count += 1
            except OSError as e:
                logger.warn("ConflictResolver", f"Could not restore {merged_file.name}: {e}")

        for managed_file in self.mods_root.rglob(XMSBT_MANAGED_GLOB):
            original_path = managed_file.parent / managed_file.name.replace(MANAGED_SUFFIX, "")
            try:
                if not original_path.exists():
                    managed_file.rename(original_path)
                    count += 1
                    logger.info("ConflictResolver",
                                f"Restored managed XMSBT: {managed_file.name}")
                else:
                    managed_file.unlink()
                    count += 1
            except OSError as e:
                logger.warn("ConflictResolver",
                            f"Could not restore {managed_file.name}: {e}")

        if self.merged_output_dir.exists():
            for xmsbt_file in self.merged_output_dir.rglob(XMSBT_GLOB):
                try:
                    xmsbt_file.unlink()
                    count += 1
                except OSError:
                    pass
            self._cleanup_empty_dirs(self.merged_output_dir)

        count += self.cleanup_legacy_merged_resources()
        logger.info("ConflictResolver", f"Restored/cleaned {count} file(s)")
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

    def rename_locale_msbt_files(self) -> int:
        """Rename locale-specific MSBT files to locale-independent names.

        ARCropolis loads MSBT files like ``msg_bgm+us_en.msbt`` only for
        the US-English locale.  When multiple mods provide locale-specific
        MSBTs at the same relative path, only one wins — causing custom
        track names to disappear for the losing mods.

        Renaming ``msg_bgm+us_en.msbt`` → ``msg_bgm.msbt`` (and similarly
        for ``msg_title+us_en.msbt`` → ``msg_title.msbt``) makes the file
        locale-independent.  ARCropolis uses locale-independent files as a
        fallback for *all* locales, which avoids the conflict.

        Only renames files whose base name (without locale suffix) does NOT
        already exist in the same directory — preventing data loss.

        Returns the number of files renamed.
        """
        if not self.mods_root.exists():
            return 0

        renamed = 0
        for folder in self.mods_root.iterdir():
            if not folder.is_dir():
                continue
            if self._is_skipped_mod_folder(folder):
                continue

            for msbt_file in folder.rglob(MSBT_GLOB):
                m = _LOCALE_MSBT_RE.match(msbt_file.name)
                if not m:
                    continue

                base_name = m.group(1) + m.group(2)  # e.g. msg_bgm.msbt
                target = msbt_file.parent / base_name

                if target.exists():
                    # A locale-independent version already exists; skip
                    logger.debug("ConflictResolver",
                                 f"Skipped rename (target exists): "
                                 f"{msbt_file.name} in {folder.name}")
                    continue

                try:
                    msbt_file.rename(target)
                    renamed += 1
                    logger.info("ConflictResolver",
                                f"Renamed locale MSBT: {msbt_file.name} → "
                                f"{base_name} in {folder.name}")
                except OSError as e:
                    logger.warn("ConflictResolver",
                                f"Failed to rename {msbt_file.name} in "
                                f"{folder.name}: {e}")

        if renamed:
            logger.info("ConflictResolver",
                        f"Renamed {renamed} locale-specific MSBT file(s) "
                        f"to locale-independent names")
        return renamed

    def detect_locale_msbts(self) -> list[tuple[str, str, Path]]:
        """Detect locale-specific MSBT files that should be renamed.

        Returns a list of (mod_name, original_filename, file_path) tuples
        for each locale-specific MSBT file found.
        """
        if not self.mods_root.exists():
            return []

        results = []
        for folder in self.mods_root.iterdir():
            if not folder.is_dir():
                continue
            if self._is_skipped_mod_folder(folder):
                continue

            for msbt_file in folder.rglob(MSBT_GLOB):
                m = _LOCALE_MSBT_RE.match(msbt_file.name)
                if not m:
                    continue
                base_name = m.group(1) + m.group(2)
                target = msbt_file.parent / base_name
                if target.exists():
                    continue  # Already has locale-independent version
                results.append((folder.name, msbt_file.name, msbt_file))

        return results

    def generate_msbt_overlays(self, cancel_event: Optional[threading.Event] = None) -> int:
        """Legacy API retained for compatibility.

        Overlay generation is disabled by policy. This method only cleans up
        old `_MergedResources` artifacts and returns 0.
        """
        if not self.mods_root.exists():
            return 0
        if self._scan_cancelled(cancel_event):
            return 0

        self.cleanup_legacy_merged_resources()
        return 0

    def _cleanup_stale_msbt_copies(
        self,
        msbt_providers: dict,
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        """Remove binary MSBT files from _MergedResources.

        Old versions of this tool copied binary MSBTs into
        _MergedResources.  These copies create ARCropolis conflicts
        (Error 2-0069) and are no longer needed since we now generate
        XMSBT overlays instead.  Remove ALL binary MSBTs from
        _MergedResources regardless of provider count.
        """
        if not self.merged_output_dir.exists():
            return

        removed = 0
        for msbt_file in list(self.merged_output_dir.rglob(MSBT_GLOB)):
            if self._scan_cancelled(cancel_event):
                return
            try:
                msbt_file.unlink()
                removed += 1
                rel = str(msbt_file.relative_to(self.merged_output_dir)).replace("\\", "/")
                logger.info("ConflictResolver",
                            f"Removed stale binary MSBT copy: {rel}")
            except OSError:
                pass

        if removed > 0:
            logger.info("ConflictResolver",
                        f"Cleaned up {removed} stale binary MSBT "
                        f"copies from _MergedResources")
            self._cleanup_empty_dirs(self.merged_output_dir)
