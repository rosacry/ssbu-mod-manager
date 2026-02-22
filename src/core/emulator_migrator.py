"""Emulator migration — copy/move all SSBU data between emulator SDMC roots.

Different Switch emulators (Eden, Ryujinx, Yuzu, Suyu, Sudachi, Citron) use
their own multiplayer/LDN networks, so online lobby rooms are NOT cross-
compatible. When a user needs to switch emulators (e.g., to play with friends
on a different LDN server), they must migrate ALL of their SSBU data — mods,
plugins, save data, shader caches, etc.

This module automates that migration so users don't have to manually copy
files between AppData directories.
"""

import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable
from src.paths import (
    EMULATOR_PATHS, SSBU_TITLE_ID,
    auto_detect_all_emulators, _expand_path,
    derive_mods_path, derive_plugins_path,
)
from src.utils.logger import logger


@dataclass
class MigrationItem:
    """A single directory/file category to migrate."""
    label: str
    src_rel: str          # Relative path inside SDMC root
    description: str
    file_count: int = 0
    total_size: int = 0
    exists: bool = False


@dataclass
class MigrationPlan:
    """A planned migration from one emulator to another."""
    source_name: str
    source_path: Path
    target_name: str
    target_path: Path
    items: list[MigrationItem] = field(default_factory=list)
    total_files: int = 0
    total_size: int = 0

    @property
    def total_size_mb(self) -> float:
        return self.total_size / (1024 * 1024)


@dataclass
class MigrationResult:
    """Result of a migration operation."""
    success: bool
    files_copied: int = 0
    bytes_copied: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


# Directories inside SDMC that contain SSBU-related data
SSBU_DATA_DIRS = [
    MigrationItem(
        label="Mods",
        src_rel="ultimate/mods",
        description="All mod folders (character skins, movesets, stages, UI, audio, etc.)",
    ),
    MigrationItem(
        label="Skyline Plugins",
        src_rel=f"atmosphere/contents/{SSBU_TITLE_ID}/romfs/skyline/plugins",
        description="Skyline plugins (ARCropolis, HDR, etc.)",
    ),
    MigrationItem(
        label="Skyline Framework",
        src_rel=f"atmosphere/contents/{SSBU_TITLE_ID}/exefs",
        description="Skyline runtime hooks (subsdk9, main.npdm)",
    ),
    MigrationItem(
        label="RomFS Overrides",
        src_rel=f"atmosphere/contents/{SSBU_TITLE_ID}/romfs",
        description="Complete romfs file overrides (outside of skyline/plugins)",
    ),
    MigrationItem(
        label="ExeFS Overrides",
        src_rel=f"atmosphere/contents/{SSBU_TITLE_ID}/exefs",
        description="ExeFS patches and overrides",
    ),
    MigrationItem(
        label="Save Data",
        src_rel="save",
        description="Game save data (unlocks, replays, spirits, custom stages)",
    ),
    MigrationItem(
        label="NAND System",
        src_rel="nand",
        description="NAND system data (user profiles, settings)",
    ),
]


def _count_dir(path: Path) -> tuple[int, int]:
    """Count files and total bytes in a directory tree."""
    count = 0
    size = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                count += 1
                try:
                    size += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except (PermissionError, OSError):
        pass
    return count, size


def get_emulator_sdmc_path(emulator_name: str) -> Optional[Path]:
    """Get the SDMC root path for a named emulator."""
    templates = EMULATOR_PATHS.get(emulator_name, [])
    for template in templates:
        path = _expand_path(template)
        if path:
            return path
    return None


def get_emulator_data_root(emulator_name: str) -> Optional[Path]:
    """Get the root data directory for a named emulator (parent of sdmc)."""
    templates = EMULATOR_PATHS.get(emulator_name, [])
    for template in templates:
        path = _expand_path(template)
        if path:
            return path.parent  # e.g. AppData/Roaming/Ryujinx
    return None


def scan_emulator_data(sdmc_path: Path) -> list[MigrationItem]:
    """Scan an emulator's SDMC for SSBU data and report what exists."""
    items = []
    seen_paths = set()

    for template in SSBU_DATA_DIRS:
        full = sdmc_path / template.src_rel
        # Deduplicate overlapping paths (romfs contains plugins)
        if str(full) in seen_paths:
            continue

        item = MigrationItem(
            label=template.label,
            src_rel=template.src_rel,
            description=template.description,
        )

        if full.exists() and full.is_dir():
            item.exists = True
            item.file_count, item.total_size = _count_dir(full)
            seen_paths.add(str(full))
        elif full.exists() and full.is_file():
            item.exists = True
            item.file_count = 1
            item.total_size = full.stat().st_size
            seen_paths.add(str(full))

        items.append(item)

    return items


def create_migration_plan(
    source_name: str,
    source_path: Path,
    target_name: str,
    target_path: Path,
    selected_categories: Optional[list[str]] = None,
) -> MigrationPlan:
    """Create a migration plan detailing what will be copied.

    Args:
        source_name: Name of source emulator
        source_path: SDMC root of source emulator
        target_name: Name of target emulator
        target_path: SDMC root of target emulator
        selected_categories: If provided, only migrate these item labels.
                             If None, migrate everything that exists.
    """
    all_items = scan_emulator_data(source_path)

    if selected_categories:
        items = [i for i in all_items if i.label in selected_categories and i.exists]
    else:
        items = [i for i in all_items if i.exists]

    plan = MigrationPlan(
        source_name=source_name,
        source_path=source_path,
        target_name=target_name,
        target_path=target_path,
        items=items,
        total_files=sum(i.file_count for i in items),
        total_size=sum(i.total_size for i in items),
    )
    return plan


def execute_migration(
    plan: MigrationPlan,
    overwrite: bool = False,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> MigrationResult:
    """Execute a migration plan, copying files from source to target.

    Args:
        plan: The migration plan to execute
        overwrite: If True, overwrite existing files at target
        progress_callback: Optional callback(message, fraction_complete)
    """
    result = MigrationResult(success=True)
    start = time.time()
    total = plan.total_files or 1
    copied = 0

    for item in plan.items:
        src_dir = plan.source_path / item.src_rel
        dst_dir = plan.target_path / item.src_rel

        if not src_dir.exists():
            continue

        if progress_callback:
            progress_callback(f"Migrating {item.label}...", copied / total)

        try:
            if src_dir.is_file():
                dst_dir.parent.mkdir(parents=True, exist_ok=True)
                if overwrite or not dst_dir.exists():
                    shutil.copy2(str(src_dir), str(dst_dir))
                    result.files_copied += 1
                    result.bytes_copied += src_dir.stat().st_size
                copied += 1
            else:
                for root, dirs, files in os.walk(src_dir):
                    rel = os.path.relpath(root, src_dir)
                    target_root = dst_dir / rel
                    target_root.mkdir(parents=True, exist_ok=True)

                    for fname in files:
                        src_file = Path(root) / fname
                        dst_file = target_root / fname

                        try:
                            if overwrite or not dst_file.exists():
                                shutil.copy2(str(src_file), str(dst_file))
                                result.files_copied += 1
                                result.bytes_copied += src_file.stat().st_size
                        except (PermissionError, OSError) as e:
                            result.errors.append(f"Failed to copy {src_file}: {e}")

                        copied += 1
                        if progress_callback and copied % 50 == 0:
                            progress_callback(
                                f"Migrating {item.label}... ({copied}/{total})",
                                copied / total,
                            )

        except Exception as e:
            result.errors.append(f"Error migrating {item.label}: {e}")
            result.success = False

    result.duration_seconds = time.time() - start

    if progress_callback:
        progress_callback("Migration complete!", 1.0)

    if result.errors:
        result.success = len(result.errors) < 5  # Partial success if few errors

    logger.info("Migrator", f"Migration complete: {result.files_copied} files, "
                f"{result.bytes_copied / (1024*1024):.1f} MB, "
                f"{result.duration_seconds:.1f}s, {len(result.errors)} errors")
    return result


def quick_migrate(
    source_name: str,
    target_name: str,
    overwrite: bool = False,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> MigrationResult:
    """One-call migration from one emulator to another.

    Detects paths automatically, creates plan, and executes.
    """
    source_path = get_emulator_sdmc_path(source_name)
    if not source_path:
        return MigrationResult(
            success=False,
            errors=[f"Could not find SDMC path for {source_name}"],
        )

    target_path = get_emulator_sdmc_path(target_name)
    if not target_path:
        # Try to create the target SDMC dir based on templates
        templates = EMULATOR_PATHS.get(target_name, [])
        for template in templates:
            expanded = template
            for var in ("APPDATA", "LOCALAPPDATA", "USERPROFILE"):
                val = os.environ.get(var, "")
                expanded = expanded.replace("{" + var + "}", val)
            candidate = Path(expanded)
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                target_path = candidate
                break
            except OSError:
                continue

    if not target_path:
        return MigrationResult(
            success=False,
            errors=[f"Could not determine or create SDMC path for {target_name}"],
        )

    plan = create_migration_plan(source_name, source_path, target_name, target_path)
    return execute_migration(plan, overwrite=overwrite, progress_callback=progress_callback)


def export_ssbu_data(
    sdmc_path: Path,
    export_path: Path,
    selected_categories: Optional[list[str]] = None,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> MigrationResult:
    """Export SSBU data from an emulator to a standalone directory.

    Useful for backing up or transferring data outside of emulator AppData.
    """
    plan = create_migration_plan(
        source_name="Current",
        source_path=sdmc_path,
        target_name="Export",
        target_path=export_path,
        selected_categories=selected_categories,
    )
    return execute_migration(plan, overwrite=True, progress_callback=progress_callback)


def import_ssbu_data(
    import_path: Path,
    sdmc_path: Path,
    selected_categories: Optional[list[str]] = None,
    overwrite: bool = False,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> MigrationResult:
    """Import SSBU data from an exported directory into an emulator.

    The import_path should have the same structure as an SDMC root.
    """
    plan = create_migration_plan(
        source_name="Import",
        source_path=import_path,
        target_name="Current",
        target_path=sdmc_path,
        selected_categories=selected_categories,
    )
    return execute_migration(plan, overwrite=overwrite, progress_callback=progress_callback)
