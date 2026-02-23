"""Resolve conflicts between mods - especially XMSBT merging."""
import hashlib
import json
import shutil
from pathlib import Path
from typing import Optional
from src.models.conflict import FileConflict, ResolutionStrategy
from src.utils.xmsbt_parser import (
    parse_xmsbt, write_xmsbt, merge_xmsbt_files,
)
from src.utils.file_utils import backup_file
from src.utils.logger import logger


class ConflictResolver:
    def __init__(self, mods_root: Path):
        self.mods_root = mods_root
        self.merged_output_dir = mods_root / "_MergedResources"

    def auto_merge_xmsbt(self, conflict: FileConflict, create_backup: bool = True) -> Optional[Path]:
        """Merge XMSBT files from multiple mods into _MergedResources.

        Uses a union strategy: all labels from all files are included.
        For overlapping labels (same label, different text), the last mod's value wins.

        The originals are left in place so ARCropolis can still process
        them individually.  The merged version in _MergedResources acts
        as an additional overlay that guarantees every label is present.
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

        # Ensure _MergedResources has a config.json so ARCropolis loads it
        self._ensure_merged_config()

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
    # Binary MSBT overlay generation (emulator-compatible)
    # ------------------------------------------------------------------
    def generate_msbt_overlays(self) -> int:
        """Scan mods for binary .msbt files and copy them to _MergedResources.

        Emulators (Eden, Ryujinx, Yuzu, etc.) use LayeredFS for mod
        loading — they can only replace files, **not** process XMSBT
        (XML-based) patches.  Generating XMSBT overlays is therefore
        useless on emulators and can even interfere with correct MSBT
        loading when the emulator or ARCropolis tries to apply them.

        This method takes the opposite approach: it copies the actual
        **binary** .msbt files into ``_MergedResources`` so that the
        emulator has a single authoritative copy of each message file.

        When multiple mods provide the same MSBT path, the largest file
        (most comprehensive) is chosen.  The originals in each mod
        folder are **never** moved or deleted.

        Old ``.xmsbt`` files in ``_MergedResources`` that correspond to
        binary MSBTs are cleaned up to prevent interference.

        Returns the number of binary MSBT files copied / updated.
        """
        if not self.mods_root.exists():
            return 0

        # Collect ALL binary MSBTs across active mods.
        # Key: relative path (e.g. "ui/message/msg_bgm+us_en.msbt")
        # Value: list of (mod_name, full_path) tuples
        msbt_providers: dict[str, list[tuple[str, Path]]] = {}

        for folder in self.mods_root.iterdir():
            if not folder.is_dir():
                continue
            if folder.name.startswith(".") or folder.name.startswith("_"):
                continue
            mod_name = folder.name
            for fpath in folder.rglob("*.msbt"):
                rel = str(fpath.relative_to(folder)).replace("\\", "/")
                if rel not in msbt_providers:
                    msbt_providers[rel] = []
                msbt_providers[rel].append((mod_name, fpath))

        if not msbt_providers:
            return 0

        generated = 0

        for rel_path, providers in msbt_providers.items():
            # Pick the best source file.
            # If only one mod has this MSBT, use it directly.
            # If multiple mods provide it, choose the largest file
            # (most likely to contain all entries including custom ones).
            best_path = None
            best_size = -1
            for _mod_name, fpath in providers:
                try:
                    fsize = fpath.stat().st_size
                except OSError:
                    fsize = 0
                if fsize > best_size:
                    best_size = fsize
                    best_path = fpath

            if best_path is None or best_size <= 0:
                continue

            output_path = self.merged_output_dir / rel_path
            # Skip if _MergedResources already has an identical copy
            if output_path.exists():
                try:
                    src_hash = hashlib.md5(best_path.read_bytes()).hexdigest()
                    dst_hash = hashlib.md5(output_path.read_bytes()).hexdigest()
                    if src_hash == dst_hash:
                        continue
                except OSError:
                    pass

            output_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(str(best_path), str(output_path))
                generated += 1
                if len(providers) > 1:
                    mod_list = ", ".join(m for m, _ in providers)
                    logger.info("ConflictResolver",
                                f"Merged MSBT from {len(providers)} mods → "
                                f"{rel_path} (source: {best_path.parent.name}) "
                                f"[mods: {mod_list}]")
                else:
                    logger.info("ConflictResolver",
                                f"Copied MSBT overlay: {rel_path} "
                                f"(from {best_path.parent.name})")
            except OSError as e:
                logger.warn("ConflictResolver",
                            f"Failed to copy {rel_path}: {e}")

        # Clean up old XMSBT files that correspond to binary MSBTs
        # we just copied.  These XMSBT files were generated by older
        # versions and can interfere on emulators or ARCropolis.
        self._cleanup_legacy_xmsbt(msbt_providers)

        if generated > 0:
            self._ensure_merged_config()

        return generated

    def _cleanup_legacy_xmsbt(self, msbt_providers: dict) -> None:
        """Remove XMSBT files from _MergedResources that are superseded
        by binary MSBTs.  Also removes non-locale XMSBT files (legacy)."""
        if not self.merged_output_dir.exists():
            return

        for xmsbt_file in list(self.merged_output_dir.rglob("*.xmsbt")):
            try:
                xmsbt_file.unlink()
                logger.info("ConflictResolver",
                            f"Cleaned up legacy XMSBT: {xmsbt_file.name}")
            except OSError:
                pass



    def _ensure_merged_config(self) -> None:
        """Create a minimal config.json in _MergedResources for ARCropolis.

        Without config.json, some ARCropolis versions may not recognise
        this folder as a mod and skip its XMSBT overlays.
        """
        config_path = self.merged_output_dir / "config.json"
        if config_path.exists():
            return
        self.merged_output_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "new-dir-infos": [],
            "new-dir-infos-base": "",
            "description": "Auto-generated merged resources from SSBU Mod Manager",
        }
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except OSError:
            pass
