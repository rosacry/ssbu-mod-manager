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

        # ARCropolis needs a config.json to load _MergedResources
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

    # ------------------------------------------------------------------
    # Locale-specific MSBT rename utility
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Binary MSBT → XMSBT overlay generation (emulator-compatible)
    # ------------------------------------------------------------------
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

        # Disabled implementation kept below for historical reference.
        """
        if not self.mods_root.exists():
            return 0
        if self._scan_cancelled(cancel_event):
            return 0

        # NOTE: Locale-specific MSBT renaming (e.g. msg_bgm+us_en.msbt →
        # msg_bgm.msbt) is no longer done automatically here. It is now
        # triggered manually via the Conflicts page "Fix Locale MSBT
        # Files" button so users can review before renaming.

        # Restore any .xmsbt.managed files left by a previous version
        # of this tool.  These renames caused ARCropolis Error 2-0069.
        for managed in self.mods_root.rglob(XMSBT_MANAGED_GLOB):
            if self._scan_cancelled(cancel_event):
                return 0
            original = managed.parent / managed.name.replace(MANAGED_SUFFIX, "")
            try:
                if not original.exists():
                    managed.rename(original)
                    logger.info("ConflictResolver",
                                f"Restored managed XMSBT: {managed.name}")
                else:
                    managed.unlink()
            except OSError:
                pass

        # Remove stray XMSBT files that this tool placed into mod
        # folders (not _MergedResources) — they also cause Error 2-0069.
        for folder in self.mods_root.iterdir():
            if not folder.is_dir():
                continue
            if self._is_skipped_mod_folder(folder):
                continue
            for xmsbt in folder.rglob(XMSBT_GLOB):
                # If a matching .msbt exists in the same directory,
                # this XMSBT was likely injected by our tool.  Remove it
                # so only the _MergedResources overlay is active.
                msbt_sibling = xmsbt.parent / (xmsbt.stem + ".msbt")
                if msbt_sibling.exists():
                    # Check if the XMSBT looks like ours (contains SSBUModManager marker)
                    try:
                        content = xmsbt.read_text(encoding='utf-8', errors='ignore')
                        if 'SSBUModManager' in content or 'xmsbt' in content[:200]:
                            # Likely not a user-created XMSBT.
                            # Don't remove user XMSBTs that came with the mod.
                            pass  # Keep it — it might be from the mod itself
                    except OSError:
                        pass

        # Collect ALL binary MSBTs across active mods.
        # Key: relative path (e.g. "ui/message/msg_bgm+us_en.msbt")
        # Value: list of (mod_name, full_path) tuples
        msbt_providers: dict[str, list[tuple[str, Path]]] = {}

        # Also collect all XMSBT files across active mods so we
        # can merge their entries into the overlay. This prevents
        # other mods' XMSBTs from overriding entries.
        xmsbt_providers: dict[str, list[tuple[str, Path]]] = {}

        for folder in self.mods_root.iterdir():
            if self._scan_cancelled(cancel_event):
                return 0
            if not folder.is_dir():
                continue
            if self._is_skipped_mod_folder(folder):
                continue
            mod_name = folder.name
            for fpath in folder.rglob(MSBT_GLOB):
                if self._scan_cancelled(cancel_event):
                    return 0
                rel = str(fpath.relative_to(folder)).replace("\\", "/")
                if rel not in msbt_providers:
                    msbt_providers[rel] = []
                msbt_providers[rel].append((mod_name, fpath))
            for fpath in folder.rglob(XMSBT_GLOB):
                if self._scan_cancelled(cancel_event):
                    return 0
                rel = str(fpath.relative_to(folder)).replace("\\", "/")
                if rel not in xmsbt_providers:
                    xmsbt_providers[rel] = []
                xmsbt_providers[rel].append((mod_name, fpath))

        # Always clean up stale binary MSBT copies from older versions
        self._cleanup_stale_msbt_copies(msbt_providers, cancel_event=cancel_event)
        if self._scan_cancelled(cancel_event):
            return 0

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
            if self._scan_cancelled(cancel_event):
                return generated
            msbt_list = sources["msbt"]
            xmsbt_list = sources["xmsbt"]

            if not msbt_list and not xmsbt_list:
                continue

            xmsbt_rel = stem + ".xmsbt"
            output_path = self.merged_output_dir / xmsbt_rel

            # Determine if this is a BGM-related MSBT
            fname_lower = Path(stem).name.lower()
            is_bgm = fname_lower.startswith("msg_bgm") or fname_lower.startswith("msg_title")

            # Only extract entries from binary MSBTs when there are
            # MULTIPLE binary providers (a real conflict).  When a
            # single mod provides the only binary MSBT, leave it alone
            # — the emulator / ARCropolis will load it directly.
            # Extracting entries into an XMSBT overlay is harmful
            # because XMSBT overlays can only MODIFY existing labels
            # in the base MSBT; they cannot ADD new labels.  The binary
            # MSBT is what adds new labels, and generating an XMSBT
            # overlay from it can cause ARCropolis to skip loading the
            # binary replacement entirely.
            all_custom_entries: dict[str, str] = {}
            if len(msbt_list) >= 2:
                for mod_name, fpath in msbt_list:
                    if self._scan_cancelled(cancel_event):
                        return generated
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

            # Merge XMSBT entries from mods.  When there is only ONE
            # XMSBT provider AND it belongs to the same mod as the
            # sole binary MSBT, no overlay is needed — that mod's own
            # XMSBT will be applied by ARCropolis independently.
            xmsbt_only_entries: dict[str, str] = {}
            xmsbt_mod_names: list[str] = []
            for mod_name, fpath in xmsbt_list:
                if self._scan_cancelled(cancel_event):
                    return generated
                try:
                    xmsbt_entries = parse_xmsbt(fpath)
                    if xmsbt_entries:
                        logger.debug("ConflictResolver",
                                     f"Merged {len(xmsbt_entries)} entries "
                                     f"from {mod_name}/{Path(stem).name}.xmsbt")
                        xmsbt_only_entries.update(xmsbt_entries)
                        if mod_name not in xmsbt_mod_names:
                            xmsbt_mod_names.append(mod_name)
                except Exception as e:
                    logger.warn("ConflictResolver",
                                f"Failed to parse XMSBT {fpath}: {e}")

            # Decide whether an overlay is needed:
            need_overlay = False
            if len(msbt_list) >= 2:
                # Multiple binary MSBTs conflict — overlay preserves all
                need_overlay = True
                all_custom_entries.update(xmsbt_only_entries)
            elif len(xmsbt_mod_names) >= 2:
                # Multiple mods contribute XMSBT entries — overlay merges them
                need_overlay = True
                all_custom_entries.update(xmsbt_only_entries)
            elif len(xmsbt_mod_names) == 1 and len(msbt_list) == 0:
                # Single XMSBT provider, no binary MSBT — nothing to overlay
                need_overlay = False
            elif (len(xmsbt_mod_names) == 1 and len(msbt_list) == 1
                  and xmsbt_mod_names[0] == msbt_list[0][0]):
                # Same mod provides both MSBT and XMSBT — ARCropolis
                # handles this natively, no overlay needed.
                need_overlay = False
            elif len(xmsbt_mod_names) == 1 and len(msbt_list) >= 1:
                # One XMSBT mod, one different MSBT mod — overlay
                # adds XMSBT entries on top of binary MSBT
                need_overlay = True
                all_custom_entries.update(xmsbt_only_entries)
            # else: no entries, no overlay

            if not need_overlay or not all_custom_entries:
                # Clean up any previously generated overlay for this stem
                if output_path.exists():
                    try:
                        output_path.unlink()
                    except OSError:
                        pass
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

            if self._scan_cancelled(cancel_event):
                return generated

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

        if generated > 0 and not self._scan_cancelled(cancel_event):
            self._ensure_merged_config()

        return generated
        """

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



    def _ensure_merged_config(self) -> None:
        """No-op: merged overlay output is disabled."""
        return
