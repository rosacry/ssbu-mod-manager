"""Targeted emulator runtime cleanup and reset helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import shutil

from src.paths import SSBU_TITLE_ID

_TITLE_ID_LOWER = SSBU_TITLE_ID.lower()
_RUNTIME_BACKUP_DIR_NAME = "_ssbumm_runtime_backups"
_STABLE_YUZU_PROFILE = """[Renderer]
use_disk_shader_cache\\use_global=false
use_disk_shader_cache=true
use_asynchronous_gpu_emulation\\use_global=false
use_asynchronous_gpu_emulation=true
use_asynchronous_shaders\\use_global=false
use_asynchronous_shaders=true
async_presentation\\use_global=false
async_presentation=true
use_vulkan_driver_pipeline_cache\\use_global=false
use_vulkan_driver_pipeline_cache=true
enable_compute_pipelines\\use_global=false
enable_compute_pipelines=true
gpu_accuracy\\use_global=false
gpu_accuracy=1
use_reactive_flushing\\use_global=false
use_reactive_flushing=true
"""


@dataclass
class RuntimeRepairSummary:
    emulator_name: str = ""
    backup_root: Path | None = None
    title_profile_backed_up: bool = False
    title_profile_written: bool = False
    shader_files_cleared: int = 0
    pipeline_files_cleared: int = 0
    arcropolis_cache_files_cleared: int = 0
    warnings: list[str] = field(default_factory=list)


def repair_yuzu_runtime_for_smash(mods_path: Path) -> RuntimeRepairSummary:
    """Back up and reset risky Yuzu per-game runtime state for Smash."""
    mods_path = Path(mods_path)
    yuzu_root = derive_yuzu_root_from_mods_path(mods_path)
    if yuzu_root is None:
        raise ValueError("Could not locate the Yuzu data root from the configured mods path.")

    summary = RuntimeRepairSummary(emulator_name="Yuzu")
    summary.backup_root = yuzu_root / _RUNTIME_BACKUP_DIR_NAME / datetime.now().strftime("%Y%m%d_%H%M%S")

    title_profile = yuzu_root / "config" / "custom" / f"{SSBU_TITLE_ID}.ini"
    if title_profile.exists():
        backup_path = summary.backup_root / "config" / "custom" / title_profile.name
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(title_profile, backup_path)
        summary.title_profile_backed_up = True
    title_profile.parent.mkdir(parents=True, exist_ok=True)
    title_profile.write_text(_STABLE_YUZU_PROFILE, encoding="utf-8")
    summary.title_profile_written = True

    summary.shader_files_cleared += _move_tree_to_backup(
        yuzu_root / "shader" / _TITLE_ID_LOWER,
        summary.backup_root / "shader" / _TITLE_ID_LOWER,
    )
    summary.pipeline_files_cleared += _move_tree_to_backup(
        yuzu_root / "pipeline" / _TITLE_ID_LOWER,
        summary.backup_root / "pipeline" / _TITLE_ID_LOWER,
    )
    summary.pipeline_files_cleared += _move_tree_to_backup(
        yuzu_root / "pipeline" / SSBU_TITLE_ID,
        summary.backup_root / "pipeline" / SSBU_TITLE_ID,
    )
    summary.arcropolis_cache_files_cleared += _clear_arcropolis_runtime_cache(mods_path)
    summary.arcropolis_cache_files_cleared += _remove_plugin_junk_files(mods_path)
    return summary


def derive_yuzu_root_from_mods_path(mods_path: Path) -> Path | None:
    mods_path = Path(mods_path)
    for ancestor in (mods_path, *mods_path.parents):
        if (ancestor / "config" / "qt-config.ini").exists() and (ancestor / "sdmc").exists():
            return ancestor
    return None


def _move_tree_to_backup(source: Path, backup: Path) -> int:
    if not source.exists():
        return 0
    file_count = _count_files(source)
    backup.parent.mkdir(parents=True, exist_ok=True)
    if backup.exists():
        if backup.is_dir():
            shutil.rmtree(backup, ignore_errors=True)
        else:
            backup.unlink(missing_ok=True)
    shutil.move(str(source), str(backup))
    return file_count


def _count_files(path: Path) -> int:
    if path.is_file():
        return 1
    return sum(1 for file_path in path.rglob("*") if file_path.is_file())


def _clear_arcropolis_runtime_cache(mods_path: Path) -> int:
    cleared = 0
    arcropolis_root = Path(mods_path).parent / "arcropolis"
    if not arcropolis_root.exists():
        return 0

    conflicts_path = arcropolis_root / "conflicts.json"
    if conflicts_path.exists():
        conflicts_path.unlink(missing_ok=True)
        cleared += 1

    for cache_path in arcropolis_root.rglob("mod_cache"):
        if not cache_path.is_file():
            continue
        cache_path.unlink(missing_ok=True)
        cleared += 1
    return cleared


def _remove_plugin_junk_files(mods_path: Path) -> int:
    yuzu_root = derive_yuzu_root_from_mods_path(mods_path)
    if yuzu_root is None:
        return 0
    sdmc_root = yuzu_root / "sdmc"
    plugins_root = (
        sdmc_root
        / "atmosphere"
        / "contents"
        / SSBU_TITLE_ID
        / "romfs"
        / "skyline"
        / "plugins"
    )
    removed = 0
    junk_path = plugins_root / ".DS_Store"
    if junk_path.exists():
        junk_path.unlink(missing_ok=True)
        removed += 1
    return removed
