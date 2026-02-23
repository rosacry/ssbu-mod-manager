"""Emulator migration — copy/move all SSBU data between emulator SDMC roots.

Different Switch emulators (Eden, Ryujinx, Yuzu, Suyu, Sudachi, Citron) use
their own multiplayer/LDN networks, so online lobby rooms are NOT cross-
compatible. When a user needs to switch emulators (e.g., to play with friends
on a different LDN server), they must migrate ALL of their SSBU data — mods,
plugins, save data, shader caches, etc.

This module automates that migration so users don't have to manually copy
files between AppData directories. It also supports DIRECT data export —
reading data straight from emulator directories without requiring users
to go through the emulator's own export UI first.
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

# Extended data directories OUTSIDE SDMC — resolved relative to emulator data root.
# These let us export data directly without requiring the emulator's own export UI.
EMULATOR_EXTRA_DIRS: dict[str, list[MigrationItem]] = {
    # Ryujinx stores keys & profiles alongside sdmc
    "Ryujinx": [
        MigrationItem(label="Encryption Keys", src_rel="system",
                      description="prod.keys, title.keys, console.keys for game decryption"),
        MigrationItem(label="Registered Content", src_rel="bis/system/Contents/registered",
                      description="Firmware and system NCA files"),
        MigrationItem(label="User Profiles", src_rel="bis/system/save/8000000000000010",
                      description="Emulated Switch user profiles"),
    ],
    # Yuzu-family emulators (Yuzu, Suyu, Sudachi, Citron)
    "Yuzu": [
        MigrationItem(label="Encryption Keys", src_rel="keys",
                      description="prod.keys, title.keys for game decryption"),
        MigrationItem(label="Game Load Mods", src_rel=f"load/{SSBU_TITLE_ID}",
                      description="Alternative mod path used by Yuzu's load directory"),
        MigrationItem(label="Registered NAND Content", src_rel="nand/system/Contents/registered",
                      description="Installed firmware and system NCA files"),
    ],
}
# Copy/apply Yuzu template to its forks
for _fork in ("Suyu", "Sudachi", "Citron"):
    EMULATOR_EXTRA_DIRS[_fork] = EMULATOR_EXTRA_DIRS["Yuzu"]
# Eden layout is similar to Yuzu
EMULATOR_EXTRA_DIRS["Eden"] = [
    MigrationItem(label="Encryption Keys", src_rel="keys",
                  description="prod.keys, title.keys for game decryption"),
    MigrationItem(label="Game Load Mods", src_rel=f"load/{SSBU_TITLE_ID}",
                  description="Alternative mod path used by Eden's load directory"),
    MigrationItem(label="Registered NAND Content", src_rel="nand/system/Contents/registered",
                  description="Installed firmware and system NCA files"),
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


# ─── Direct Export (no emulator UI required) ──────────────────────────

def scan_emulator_extended_data(emulator_name: str) -> list[MigrationItem]:
    """Scan for extra data directories outside SDMC for a given emulator.

    This discovers keys, firmware, profiles, and other data that exists
    in the emulator's data root but outside the SDMC directory — data
    that would normally require using the emulator's own export tools.
    """
    data_root = get_emulator_data_root(emulator_name)
    if not data_root or not data_root.exists():
        return []

    templates = EMULATOR_EXTRA_DIRS.get(emulator_name, [])
    items = []

    for template in templates:
        full = data_root / template.src_rel
        item = MigrationItem(
            label=template.label,
            src_rel=template.src_rel,
            description=template.description,
        )
        if full.exists():
            item.exists = True
            if full.is_dir():
                item.file_count, item.total_size = _count_dir(full)
            else:
                item.file_count = 1
                item.total_size = full.stat().st_size
        items.append(item)

    return items


def direct_export_emulator_data(
    emulator_name: str,
    export_path: Path,
    include_sdmc: bool = True,
    include_extra: bool = True,
    selected_categories: Optional[list[str]] = None,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> MigrationResult:
    """Export ALL emulator data directly from its data directories.

    Unlike the emulator's built-in export tools, this reads data straight
    from AppData directories — no emulator GUI interaction required.

    Exports both SDMC data (mods, plugins, saves) and extended data
    (keys, firmware, profiles) into a structured directory.

    Args:
        emulator_name: Which emulator to export from
        export_path: Destination directory for the export
        include_sdmc: Whether to include standard SDMC data
        include_extra: Whether to include keys, firmware, profiles
        selected_categories: Only export these category labels (all if None)
        progress_callback: Optional (message, fraction) callback
    """
    result = MigrationResult(success=True)
    start = time.time()

    sdmc_path = get_emulator_sdmc_path(emulator_name)
    data_root = get_emulator_data_root(emulator_name)

    if not sdmc_path and not data_root:
        return MigrationResult(
            success=False,
            errors=[f"Could not find data directories for {emulator_name}"],
        )

    # Build the list of items to copy
    all_items: list[tuple[Path, MigrationItem]] = []

    if include_sdmc and sdmc_path and sdmc_path.exists():
        sdmc_items = scan_emulator_data(sdmc_path)
        for item in sdmc_items:
            if item.exists:
                if selected_categories is None or item.label in selected_categories:
                    all_items.append((sdmc_path, item))

    if include_extra and data_root and data_root.exists():
        extra_items = scan_emulator_extended_data(emulator_name)
        for item in extra_items:
            if item.exists:
                if selected_categories is None or item.label in selected_categories:
                    all_items.append((data_root, item))

    if not all_items:
        return MigrationResult(
            success=False,
            errors=["No data found to export."],
        )

    total_files = sum(i.file_count for _, i in all_items) or 1
    copied = 0

    # Export structure: export_path/sdmc/... for SDMC data,
    #                   export_path/extra/... for extended data
    for base_path, item in all_items:
        src_dir = base_path / item.src_rel

        if base_path == sdmc_path:
            dst_dir = export_path / "sdmc" / item.src_rel
        else:
            dst_dir = export_path / "extra" / item.src_rel

        if not src_dir.exists():
            continue

        if progress_callback:
            progress_callback(f"Exporting {item.label}...", copied / total_files)

        try:
            if src_dir.is_file():
                dst_dir.parent.mkdir(parents=True, exist_ok=True)
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
                            shutil.copy2(str(src_file), str(dst_file))
                            result.files_copied += 1
                            result.bytes_copied += src_file.stat().st_size
                        except (PermissionError, OSError) as e:
                            result.errors.append(f"Failed to copy {src_file}: {e}")

                        copied += 1
                        if progress_callback and copied % 50 == 0:
                            progress_callback(
                                f"Exporting {item.label}... ({copied}/{total_files})",
                                copied / total_files,
                            )
        except Exception as e:
            result.errors.append(f"Error exporting {item.label}: {e}")

    # Write a manifest file for the export
    try:
        manifest = {
            "emulator": emulator_name,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "files_exported": result.files_copied,
            "bytes_exported": result.bytes_copied,
            "categories": [item.label for _, item in all_items],
        }
        import json
        manifest_path = export_path / "export_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
    except Exception:
        pass

    result.duration_seconds = time.time() - start
    result.success = len(result.errors) < 5

    if progress_callback:
        progress_callback("Export complete!", 1.0)

    logger.info("Migrator",
        f"Direct export from {emulator_name}: {result.files_copied} files, "
        f"{result.bytes_copied / (1024*1024):.1f} MB, "
        f"{result.duration_seconds:.1f}s")

    return result


def direct_import_emulator_data(
    import_path: Path,
    emulator_name: str,
    overwrite: bool = False,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> MigrationResult:
    """Import data from a direct export into an emulator's directories.

    Reads the export_manifest.json and copies data into the correct
    SDMC and data root paths for the target emulator.
    """
    result = MigrationResult(success=True)
    start = time.time()

    sdmc_path = get_emulator_sdmc_path(emulator_name)
    data_root = get_emulator_data_root(emulator_name)

    if not sdmc_path and not data_root:
        # Try to create
        templates = EMULATOR_PATHS.get(emulator_name, [])
        for template in templates:
            expanded = template
            for var in ("APPDATA", "LOCALAPPDATA", "USERPROFILE"):
                val = os.environ.get(var, "")
                expanded = expanded.replace("{" + var + "}", val)
            candidate = Path(expanded)
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                sdmc_path = candidate
                data_root = candidate.parent
                break
            except OSError:
                continue

    if not sdmc_path:
        return MigrationResult(
            success=False,
            errors=[f"Could not find or create data directories for {emulator_name}"],
        )

    # Determine what to import
    import_sources = []

    sdmc_export = import_path / "sdmc"
    if sdmc_export.exists() and sdmc_path:
        import_sources.append((sdmc_export, sdmc_path, "SDMC"))

    extra_export = import_path / "extra"
    if extra_export.exists() and data_root:
        import_sources.append((extra_export, data_root, "Extra"))

    # Also support flat import (old export format without sdmc/extra split)
    if not import_sources:
        if sdmc_path:
            import_sources.append((import_path, sdmc_path, "Flat"))

    if not import_sources:
        return MigrationResult(
            success=False,
            errors=["No importable data found in the selected directory."],
        )

    # Count total files
    total_files = 0
    for src, _, _ in import_sources:
        cnt, _ = _count_dir(src)
        total_files += cnt
    total_files = total_files or 1
    copied = 0

    for src_root, dst_root, label in import_sources:
        if progress_callback:
            progress_callback(f"Importing {label} data...", copied / total_files)

        try:
            for root, dirs, files in os.walk(src_root):
                rel = os.path.relpath(root, src_root)
                target_dir = dst_root / rel
                target_dir.mkdir(parents=True, exist_ok=True)

                for fname in files:
                    if fname == "export_manifest.json":
                        continue

                    src_file = Path(root) / fname
                    dst_file = target_dir / fname

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
                            f"Importing {label}... ({copied}/{total_files})",
                            copied / total_files,
                        )
        except Exception as e:
            result.errors.append(f"Error importing {label}: {e}")

    result.duration_seconds = time.time() - start
    result.success = len(result.errors) < 5

    if progress_callback:
        progress_callback("Import complete!", 1.0)

    logger.info("Migrator",
        f"Direct import to {emulator_name}: {result.files_copied} files, "
        f"{result.bytes_copied / (1024*1024):.1f} MB, "
        f"{result.duration_seconds:.1f}s")

    return result


# ─── Emulator Version Upgrade ────────────────────────────────────────

# Emulator-specific config / settings directories and files.
# Paths are relative to the emulator's *data root* (parent of sdmc).
EMULATOR_CONFIG_PATHS: dict[str, list[MigrationItem]] = {
    "Eden": [
        MigrationItem(label="Config / Settings",
                      src_rel="config",
                      description="Emulator configuration, controller mappings, GUI settings"),
        MigrationItem(label="Shader Cache",
                      src_rel="shader",
                      description="Pre-compiled shader cache (speeds up game startup)"),
        MigrationItem(label="Pipeline Cache",
                      src_rel="pipeline",
                      description="GPU pipeline cache"),
        MigrationItem(label="Registered Content",
                      src_rel="nand/system/Contents/registered",
                      description="Installed firmware NCA files"),
        MigrationItem(label="Encryption Keys",
                      src_rel="keys",
                      description="prod.keys, title.keys for game decryption"),
    ],
    "Ryujinx": [
        MigrationItem(label="Config (Config.json)",
                      src_rel=".",
                      description="Emulator configuration (Config.json, profiles.json)"),
        MigrationItem(label="System Data",
                      src_rel="system",
                      description="Encryption keys (prod.keys, title.keys)"),
        MigrationItem(label="Shader Cache",
                      src_rel="games",
                      description="Per-game shader and pipeline cache"),
        MigrationItem(label="Registered Content",
                      src_rel="bis/system/Contents/registered",
                      description="Firmware NCA files"),
        MigrationItem(label="User Profiles",
                      src_rel="bis/system/save/8000000000000010",
                      description="Emulated Switch user profiles"),
    ],
    "Yuzu": [
        MigrationItem(label="Config / Settings",
                      src_rel="config",
                      description="qt-config.ini, custom.ini — emulator and per-game settings"),
        MigrationItem(label="Encryption Keys",
                      src_rel="keys",
                      description="prod.keys, title.keys for game decryption"),
        MigrationItem(label="Shader Cache",
                      src_rel="shader",
                      description="Pre-compiled shader cache"),
        MigrationItem(label="Pipeline Cache",
                      src_rel="pipeline",
                      description="GPU pipeline cache"),
        MigrationItem(label="Registered Content",
                      src_rel="nand/system/Contents/registered",
                      description="Firmware NCA files"),
        MigrationItem(label="Game Load Mods",
                      src_rel=f"load/{SSBU_TITLE_ID}",
                      description="Alternative mod path used by Yuzu's load directory"),
    ],
}
# Forks share structure with Yuzu
for _fork in ("Suyu", "Sudachi", "Citron"):
    EMULATOR_CONFIG_PATHS[_fork] = EMULATOR_CONFIG_PATHS["Yuzu"]


@dataclass
class UpgradeItem:
    """A single data category for version upgrade."""
    label: str
    src_path: Path
    dst_path: Path
    description: str
    file_count: int = 0
    total_size: int = 0
    exists: bool = False
    selected: bool = True   # default-on for upgrade


@dataclass
class UpgradePlan:
    """Plan for upgrading an emulator to a new version/path."""
    emulator_name: str
    old_root: Path          # Old emulator data root
    new_root: Path          # New emulator data root
    items: list[UpgradeItem] = field(default_factory=list)
    total_files: int = 0
    total_size: int = 0

    @property
    def total_size_mb(self) -> float:
        return self.total_size / (1024 * 1024)


def scan_upgrade_data(
    emulator_name: str,
    old_root: Path,
    new_root: Path,
) -> UpgradePlan:
    """Scan old emulator data root and build an upgrade plan.

    Covers SDMC data (mods, plugins, saves), extended data (keys, firmware),
    AND emulator-specific config files (settings, shader cache, profiles).
    """
    plan = UpgradePlan(
        emulator_name=emulator_name,
        old_root=old_root,
        new_root=new_root,
    )

    old_sdmc = old_root / "sdmc"
    new_sdmc = new_root / "sdmc"
    if not old_sdmc.exists():
        # Maybe the root IS the sdmc (user pointed directly at it)
        if (old_root / "ultimate").exists() or (old_root / "atmosphere").exists():
            old_sdmc = old_root
            new_sdmc = new_root

    # 1. SDMC data dirs (mods, plugins, saves, etc.)
    seen_paths: set[str] = set()
    for template in SSBU_DATA_DIRS:
        src = old_sdmc / template.src_rel
        src_str = str(src)
        if src_str in seen_paths:
            continue
        if src.exists():
            seen_paths.add(src_str)
            item = UpgradeItem(
                label=template.label,
                src_path=src,
                dst_path=new_sdmc / template.src_rel,
                description=template.description,
                exists=True,
            )
            item.file_count, item.total_size = _count_dir(src)
            plan.items.append(item)
            plan.total_files += item.file_count
            plan.total_size += item.total_size

    # 2. Extended data (keys, firmware, profiles — outside sdmc)
    extra_templates = EMULATOR_EXTRA_DIRS.get(emulator_name, [])
    for template in extra_templates:
        src = old_root / template.src_rel
        src_str = str(src)
        if src_str in seen_paths:
            continue
        if src.exists():
            seen_paths.add(src_str)
            item = UpgradeItem(
                label=template.label,
                src_path=src,
                dst_path=new_root / template.src_rel,
                description=template.description,
                exists=True,
            )
            item.file_count, item.total_size = _count_dir(src)
            plan.items.append(item)
            plan.total_files += item.file_count
            plan.total_size += item.total_size

    # 3. Emulator config/settings
    config_templates = EMULATOR_CONFIG_PATHS.get(emulator_name, [])
    for template in config_templates:
        src = old_root / template.src_rel
        src_str = str(src)
        if src_str in seen_paths:
            continue
        if src.exists():
            seen_paths.add(src_str)
            item = UpgradeItem(
                label=template.label,
                src_path=src,
                dst_path=new_root / template.src_rel,
                description=template.description,
                exists=True,
            )
            if src.is_dir():
                item.file_count, item.total_size = _count_dir(src)
            elif src.is_file():
                item.file_count = 1
                try:
                    item.total_size = src.stat().st_size
                except OSError:
                    pass
            plan.items.append(item)
            plan.total_files += item.file_count
            plan.total_size += item.total_size

    # Also look for standalone config files at root level
    for config_file in ("Config.json", "profiles.json", "qt-config.ini"):
        cfg = old_root / config_file
        cfg_str = str(cfg)
        if cfg.is_file() and cfg_str not in seen_paths:
            seen_paths.add(cfg_str)
            try:
                fsize = cfg.stat().st_size
            except OSError:
                fsize = 0
            item = UpgradeItem(
                label=f"Config: {config_file}",
                src_path=cfg,
                dst_path=new_root / config_file,
                description=f"Emulator configuration file ({config_file})",
                file_count=1,
                total_size=fsize,
                exists=True,
            )
            plan.items.append(item)
            plan.total_files += 1
            plan.total_size += fsize

    logger.info("Migrator",
        f"Upgrade scan for {emulator_name}: "
        f"{len(plan.items)} categories, {plan.total_files} files, "
        f"{plan.total_size_mb:.1f} MB")

    return plan


def execute_upgrade(
    plan: UpgradePlan,
    selected_labels: set[str] | None = None,
    overwrite: bool = False,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> MigrationResult:
    """Execute an emulator version upgrade.

    Copies data from old emulator location to new location.
    Source data is NEVER deleted — always a safe copy.

    Args:
        plan: The upgrade plan from scan_upgrade_data()
        selected_labels: Set of item labels to migrate (None = all)
        overwrite: If True, overwrite existing files in destination
        progress_callback: Optional (message, fraction) callback
    """
    result = MigrationResult(success=True)
    start = time.time()

    items_to_copy = [i for i in plan.items if i.exists]
    if selected_labels is not None:
        items_to_copy = [i for i in items_to_copy if i.label in selected_labels]

    if not items_to_copy:
        result.errors.append("No data categories selected for upgrade.")
        result.success = False
        return result

    total_files = sum(i.file_count for i in items_to_copy) or 1
    copied = 0

    for item in items_to_copy:
        if progress_callback:
            progress_callback(
                f"Copying {item.label}...",
                copied / total_files,
            )

        try:
            if item.src_path.is_file():
                # Single file copy
                item.dst_path.parent.mkdir(parents=True, exist_ok=True)
                if overwrite or not item.dst_path.exists():
                    shutil.copy2(str(item.src_path), str(item.dst_path))
                    result.files_copied += 1
                    result.bytes_copied += item.total_size
                copied += 1
            else:
                # Directory tree copy
                for root, dirs, files in os.walk(item.src_path):
                    rel = os.path.relpath(root, item.src_path)
                    target_dir = item.dst_path / rel
                    target_dir.mkdir(parents=True, exist_ok=True)

                    for fname in files:
                        src_file = Path(root) / fname
                        dst_file = target_dir / fname

                        try:
                            if overwrite or not dst_file.exists():
                                shutil.copy2(str(src_file), str(dst_file))
                                result.files_copied += 1
                                try:
                                    result.bytes_copied += src_file.stat().st_size
                                except OSError:
                                    pass
                        except (PermissionError, OSError) as e:
                            result.errors.append(f"Failed to copy {src_file}: {e}")

                        copied += 1
                        if progress_callback and copied % 50 == 0:
                            progress_callback(
                                f"Copying {item.label}... ({copied}/{total_files})",
                                copied / total_files,
                            )
        except Exception as e:
            result.errors.append(f"Error copying {item.label}: {e}")

    result.duration_seconds = time.time() - start
    result.success = len(result.errors) < 5

    if progress_callback:
        progress_callback("Upgrade complete!", 1.0)

    logger.info("Migrator",
        f"Upgrade {plan.emulator_name}: {result.files_copied} files, "
        f"{result.bytes_copied / (1024*1024):.1f} MB, "
        f"{result.duration_seconds:.1f}s, "
        f"{len(result.errors)} errors")

    return result
