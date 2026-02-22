"""Resolve conflicts between mods - especially XMSBT merging."""
import re
import shutil
from pathlib import Path
from typing import Optional
from src.models.conflict import FileConflict, ResolutionStrategy
from src.utils.xmsbt_parser import (
    parse_xmsbt, write_xmsbt, merge_xmsbt_files,
    extract_entries_from_msbt, filter_custom_entries,
)
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

    # ------------------------------------------------------------------
    # Binary MSBT → XMSBT overlay generation
    # ------------------------------------------------------------------
    def generate_msbt_overlays(self) -> int:
        """Scan mods for binary .msbt files and generate XMSBT overlays.

        Some mods ship binary MSBT replacements instead of XMSBT overlays.
        Binary replacement often doesn't work on emulators, but XMSBT
        overlays do.  This method:

        1. Finds all binary .msbt files across enabled mods.
        2. Groups them by base message file name (strip locale suffix).
        3. Extracts custom entries (mod-added labels) from the preferred
           locale (+us_en) or the first available file.
        4. Merges the extracted entries into _MergedResources/<path>.xmsbt,
           combining with any existing merged XMSBT.

        Returns the number of XMSBT overlay files generated / updated.
        """
        if not self.mods_root.exists():
            return 0

        # Collect binary MSBT files, grouped by base name
        # e.g. "ui/message/msg_bgm" → [("Sonic Extended Tracklist", Path(…+us_en.msbt)), ...]
        msbt_groups: dict[str, list[tuple[str, Path]]] = {}

        for folder in self.mods_root.iterdir():
            if not folder.is_dir():
                continue
            if folder.name.startswith(".") or folder.name.startswith("_"):
                continue
            mod_name = folder.name
            for fpath in folder.rglob("*.msbt"):
                # Only process locale-specific MSBTs (e.g. msg_bgm+us_en.msbt).
                # Non-locale MSBTs are typically handled correctly by ARCropolis
                # and don't need XMSBT fallback overlays.
                if '+' not in fpath.stem:
                    continue
                # Compute the base name without locale suffix
                rel = str(fpath.relative_to(folder)).replace("\\", "/")
                # Strip locale suffix: msg_bgm+us_en.msbt → msg_bgm
                base = re.sub(r'\+[a-z]{2}_[a-z]{2}\.msbt$', '', rel, flags=re.I)
                if base.endswith('.msbt'):
                    base = base[:-5]  # Remove .msbt extension
                if base not in msbt_groups:
                    msbt_groups[base] = []
                msbt_groups[base].append((mod_name, fpath))

        if not msbt_groups:
            return 0

        generated = 0
        for base_name, providers in msbt_groups.items():
            # Prefer +us_en variant; fall back to first available
            chosen_path = None
            for _mod, p in providers:
                if '+us_en' in p.name:
                    chosen_path = p
                    break
            if chosen_path is None:
                chosen_path = providers[0][1]

            # Extract entries from the binary MSBT
            all_entries = extract_entries_from_msbt(chosen_path)
            if not all_entries:
                continue

            # Determine output XMSBT path (no locale suffix → applies to all locales)
            xmsbt_rel = base_name + ".xmsbt"
            output_path = self.merged_output_dir / xmsbt_rel

            # If a merged XMSBT already exists, only add entries that are
            # NOT yet present.  This fills in gaps (e.g. custom BGM track
            # names from binary MSBTs) without duplicating or overriding
            # anything already merged from XMSBT mods.
            if output_path.exists():
                existing = parse_xmsbt(output_path)
                new_entries = {k: v for k, v in all_entries.items()
                               if k not in existing}
                if not new_entries:
                    logger.info("ConflictResolver",
                                f"No new entries from {chosen_path.name} "
                                f"(all {len(all_entries)} already in merged XMSBT)")
                    continue
                # Also apply custom-entry filter to avoid dumping thousands
                # of vanilla labels that are already in the base game MSBT
                new_entries = filter_custom_entries(new_entries)
                if not new_entries:
                    logger.info("ConflictResolver",
                                f"No custom entries to add from {chosen_path.name}")
                    continue
                existing.update(new_entries)
                final_entries = existing
            else:
                # No existing XMSBT — only keep custom (mod-added) entries
                final_entries = filter_custom_entries(all_entries)
                if not final_entries:
                    logger.info("ConflictResolver",
                                f"No custom entries found in {chosen_path.name}")
                    continue

            output_path.parent.mkdir(parents=True, exist_ok=True)
            write_xmsbt(output_path, final_entries)
            generated += 1
            logger.info("ConflictResolver",
                        f"Generated XMSBT overlay from {chosen_path.name}: "
                        f"{len(final_entries)} entries → {xmsbt_rel}")

        return generated
