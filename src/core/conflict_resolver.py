"""Resolve conflicts between mods - especially XMSBT merging."""
import json
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
    # Binary MSBT → XMSBT overlay generation (emulator-compatible)
    # ------------------------------------------------------------------
    def generate_msbt_overlays(self) -> int:
        """Scan mods for binary .msbt files and generate XMSBT overlays.

        Emulators (Eden, Ryujinx, Yuzu, etc.) use LayeredFS for mod
        loading.  Binary .msbt files need to be at exactly the right
        path for the emulator's LayeredFS to pick them up.  When many
        mods are active, binary file loading can be unreliable.

        Instead of copying binary MSBTs (which causes ARCropolis
        Error 2-0069 for single-provider files), this method
        **extracts** custom text entries from binary MSBTs and writes
        them as XMSBT (XML overlay) files into ``_MergedResources``.
        ARCropolis processes XMSBTs to overlay/inject labels into the
        game's built-in MSBT files, which is more reliable than binary
        replacement.

        If ``_MergedResources`` already contains XMSBT files from
        ``auto_merge_xmsbt()`` (XMSBT conflict resolution), the
        entries are merged (union) so both sources are preserved.

        Returns the number of XMSBT overlay files generated / updated.
        """
        if not self.mods_root.exists():
            return 0

        # Collect ALL binary MSBTs across active mods.
        # Key: relative path (e.g. "ui/message/msg_bgm+us_en.msbt")
        # Value: list of (mod_name, full_path) tuples
        msbt_providers: dict[str, list[tuple[str, Path]]] = {}

        # Also collect all XMSBT files across active mods so we
        # can merge their entries into the overlay. This prevents
        # other mods' XMSBTs from overriding entries.
        xmsbt_providers: dict[str, list[tuple[str, Path]]] = {}

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
            for fpath in folder.rglob("*.xmsbt"):
                rel = str(fpath.relative_to(folder)).replace("\\", "/")
                if rel not in xmsbt_providers:
                    xmsbt_providers[rel] = []
                xmsbt_providers[rel].append((mod_name, fpath))

        # Always clean up stale binary MSBT copies from older versions
        self._cleanup_stale_msbt_copies(msbt_providers)

        if not msbt_providers and not xmsbt_providers:
            return 0

        generated = 0

        # Build a unified set of message stems (e.g. "ui/message/msg_bgm+us_en")
        # combining both MSBT and XMSBT sources.
        all_stems: dict[str, dict] = {}  # stem -> {"msbt": [...], "xmsbt": [...]}
        for rel_path, providers in msbt_providers.items():
            stem = rel_path.rsplit(".", 1)[0]
            if stem not in all_stems:
                all_stems[stem] = {"msbt": [], "xmsbt": []}
            all_stems[stem]["msbt"] = providers

        for rel_path, providers in xmsbt_providers.items():
            stem = rel_path.rsplit(".", 1)[0]
            if stem not in all_stems:
                all_stems[stem] = {"msbt": [], "xmsbt": []}
            all_stems[stem]["xmsbt"] = providers

        for stem, sources in all_stems.items():
            msbt_list = sources["msbt"]
            xmsbt_list = sources["xmsbt"]

            if not msbt_list and not xmsbt_list:
                continue

            xmsbt_rel = stem + ".xmsbt"
            output_path = self.merged_output_dir / xmsbt_rel

            # Determine if this is a BGM-related MSBT
            fname_lower = Path(stem).name.lower()
            is_bgm = fname_lower.startswith("msg_bgm") or fname_lower.startswith("msg_title")

            # Extract entries from ALL binary MSBT providers and merge
            all_custom_entries: dict[str, str] = {}
            for mod_name, fpath in msbt_list:
                entries = extract_entries_from_msbt(fpath)
                if not entries:
                    continue
                # Filter to custom entries only (inclusive for BGM keeps ALL)
                custom = filter_custom_entries(entries, inclusive=is_bgm)
                if custom:
                    logger.debug("ConflictResolver",
                                 f"Extracted {len(custom)} custom entries "
                                 f"from {mod_name}/{Path(stem).name}.msbt")
                    all_custom_entries.update(custom)

            # Also merge entries from XMSBT files across mods
            for mod_name, fpath in xmsbt_list:
                try:
                    xmsbt_entries = parse_xmsbt(fpath)
                    if xmsbt_entries:
                        logger.debug("ConflictResolver",
                                     f"Merged {len(xmsbt_entries)} entries "
                                     f"from {mod_name}/{Path(stem).name}.xmsbt")
                        all_custom_entries.update(xmsbt_entries)
                except Exception as e:
                    logger.warn("ConflictResolver",
                                f"Failed to parse XMSBT {fpath}: {e}")

            if not all_custom_entries:
                continue

            # If there's an existing merged XMSBT from auto_merge_xmsbt(),
            # merge entries (existing XMSBT entries take priority for
            # overlapping labels since they were explicitly resolved)
            if output_path.exists():
                try:
                    existing = parse_xmsbt(output_path)
                    merged = dict(all_custom_entries)
                    merged.update(existing)
                    all_custom_entries = merged
                except Exception:
                    pass

            # Write the merged XMSBT overlay into _MergedResources
            output_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                write_xmsbt(output_path, all_custom_entries)
                generated += 1
                all_mods = list(set(
                    [m for m, _ in msbt_list] + [m for m, _ in xmsbt_list]
                ))
                mod_list = ", ".join(all_mods)
                logger.info("ConflictResolver",
                            f"Generated XMSBT overlay: {xmsbt_rel} "
                            f"({len(all_custom_entries)} entries from "
                            f"{len(all_mods)} mod(s): {mod_list})")
            except Exception as e:
                logger.warn("ConflictResolver",
                            f"Failed to write XMSBT overlay {xmsbt_rel}: {e}")

            # Also place a copy of the XMSBT inside each mod that has
            # a binary MSBT for this message. This guarantees ARCropolis
            # picks up the overlay regardless of which mod is active or
            # what load-order it uses. Mods that already ship their own
            # XMSBT are skipped (their entries are already merged above).
            mods_with_own_xmsbt = set(m for m, _ in xmsbt_list)
            for mod_name, fpath in msbt_list:
                if mod_name in mods_with_own_xmsbt:
                    continue
                in_mod_xmsbt = fpath.parent / (fpath.stem + ".xmsbt")
                if in_mod_xmsbt.exists():
                    continue
                try:
                    write_xmsbt(in_mod_xmsbt, all_custom_entries)
                    logger.info("ConflictResolver",
                                f"Placed XMSBT overlay in {mod_name}/"
                                f"{in_mod_xmsbt.name}")
                except Exception as e:
                    logger.warn("ConflictResolver",
                                f"Failed to write XMSBT to mod folder: {e}")

            # If multiple mods have XMSBT files for the same message,
            # disable the per-mod XMSBTs (rename to .xmsbt.managed)
            # so only _MergedResources overlay is active.
            # This prevents ARCropolis load-order issues.
            if len(xmsbt_list) > 1:
                for mod_name, fpath in xmsbt_list:
                    managed = fpath.parent / (fpath.name + ".managed")
                    if not managed.exists():
                        try:
                            fpath.rename(managed)
                            logger.info("ConflictResolver",
                                        f"Disabled conflicting XMSBT: "
                                        f"{mod_name}/{fpath.name} → "
                                        f"{managed.name}")
                        except OSError as e:
                            logger.warn("ConflictResolver",
                                        f"Could not disable {fpath.name}: {e}")

        if generated > 0:
            self._ensure_merged_config()

        return generated

    def _cleanup_stale_msbt_copies(self, msbt_providers: dict) -> None:
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
        for msbt_file in list(self.merged_output_dir.rglob("*.msbt")):
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



    def _ensure_merged_config(self) -> None:
        """Create / update config.json in _MergedResources for ARCropolis.

        ARCropolis needs ``new-dir-infos`` entries so it scans the
        folder for XMSBT overlays.  We register every directory that
        contains a generated XMSBT so ARCropolis recognises them as
        part of the mod and applies the overlays at load time.
        """
        self.merged_output_dir.mkdir(parents=True, exist_ok=True)
        config_path = self.merged_output_dir / "config.json"

        # Collect every directory (relative to merged root) that
        # contains an XMSBT file we generated.
        dir_infos: list[dict] = []
        seen_dirs: set[str] = set()
        for xmsbt_file in self.merged_output_dir.rglob("*.xmsbt"):
            rel_dir = str(
                xmsbt_file.parent.relative_to(self.merged_output_dir)
            ).replace("\\", "/")
            if rel_dir == ".":
                continue
            if rel_dir not in seen_dirs:
                seen_dirs.add(rel_dir)
                dir_infos.append({"path": rel_dir})

        config = {
            "new-dir-infos": dir_infos,
            "new-dir-infos-base": "",
            "description": "Auto-generated merged resources from SSBU Mod Manager",
        }
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except OSError:
            pass
