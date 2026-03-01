"""Import helpers for mods and plugins."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import re
import shutil
import tempfile
from typing import Callable

from src.paths import SSBU_TITLE_ID
from src.core.archive_utils import extract_archive, is_archive_path
from src.core.skin_slot_utils import (
    SlotAnalysis,
    analyze_mod_directory,
    choose_open_target_slot,
    choose_primary_variant_root,
    copy_single_slot_variant,
    reslot_mod_directory,
)
from src.utils.xmsbt_parser import extract_entries_from_msbt, parse_xmsbt

_MOD_CONTENT_DIRS = {
    "fighter", "sound", "stage", "ui", "effect", "camera",
    "assist", "item", "param", "stream",
}
_MOD_SKIP_DIRS = {
    "_mergedresources", "_musicconfig", ".disabled", "disabled_mods", "disabled_plugins",
}
_GENERIC_FOLDER_NAMES = {
    "romfs", "exefs", "mods", "ultimate", "atmosphere",
    "contents", "sdmc", "plugin", "plugins",
}
_INVALID_NAME_CHARS = set('<>:"/\\|?*')
_SUPPORT_BACKUP_DIR_NAME = "_import_backups"
_METADATA_FILENAMES = {
    "config.json",
    "info.toml",
    "preview.webp",
    "preview.png",
    "preview.jpg",
    "preview.jpeg",
    "readme.txt",
    "readme.md",
}
_SUPPORT_KIND_TO_CATEGORY = {
    "voice": "sound",
    "effect": "effect",
    "camera": "camera",
}
_SUPPORT_KIND_LABELS = {
    "voice": "voice pack",
    "effect": "effect pack",
    "camera": "camera pack",
}
_MSG_NAME_ENTRY_PATTERN = re.compile(r"^nam_chr(?P<tier>[12])_(?P<slot>\d{2})_(?P<name_id>[a-z0-9_]+)$", re.IGNORECASE)
_PRCXML_CHARACALL_PATTERN = re.compile(
    r'characall_label_c(?P<slot>\d{2})"\s*>\s*vc_narration_characall_(?P<identifier>[^<]+)<',
    re.IGNORECASE,
)


@dataclass
class ImportSummary:
    """Aggregated import stats shown in UI after an import."""

    items_imported: int = 0
    files_copied: int = 0
    replaced_paths: int = 0
    flattened_mods: int = 0
    plugin_files: int = 0
    archives_processed: int = 0
    slot_reassignments: int = 0
    support_mod_adjustments: int = 0
    support_files_pruned: int = 0
    skipped_items: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SupportPackScopeInfo:
    support_kind: str
    fighter: str
    source_slots: list[int] = field(default_factory=list)
    recommended_source_slot: int = 0
    visual_slots: list[int] = field(default_factory=list)


@dataclass
class SupportPackScopeSummary:
    support_kind: str
    mod_name: str
    fighter: str
    source_slot: int
    target_slots: list[int] = field(default_factory=list)
    files_written: int = 0
    support_mod_adjustments: int = 0
    support_files_pruned: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class SlotConflictInfo:
    """Information provided to a caller when an import hits a slot overlap."""

    mod_name: str
    fighter: str
    requested_slot: int
    conflicting_mods: list[str]
    open_slots: list[int]


@dataclass(frozen=True)
class MultiSlotPackOption:
    option_id: str
    fighter: str
    slot: int
    label: str
    recommended: bool = False


@dataclass
class MultiSlotPackSelectionInfo:
    mod_name: str
    package_name: str
    options: list[MultiSlotPackOption] = field(default_factory=list)


@dataclass
class _PreparedModImport:
    source_dir: Path
    target_name: str
    package_name: str
    analysis: SlotAnalysis
    temp_paths: list[tempfile.TemporaryDirectory] = field(default_factory=list)


SlotConflictResolver = Callable[[SlotConflictInfo], str]
MultiSlotPackResolver = Callable[[MultiSlotPackSelectionInfo], list[str] | None]

VoicePackScopeInfo = SupportPackScopeInfo
VoicePackScopeSummary = SupportPackScopeSummary


def inspect_mod_support_pack(mod_path: Path, support_kind: str) -> SupportPackScopeInfo | None:
    mod_path = Path(mod_path)
    if not mod_path.exists() or not mod_path.is_dir():
        return None

    normalized_kind = _normalize_support_kind(support_kind)
    category = _SUPPORT_KIND_TO_CATEGORY[normalized_kind]
    analysis = analyze_mod_directory(mod_path, [mod_path.name])
    fighter_support_slots = {
        fighter: sorted(
            slot
            for slot in slots
            if category in analysis.categories_for_slot(fighter, slot)
        )
        for fighter, slots in analysis.fighter_slots.items()
    }
    fighter_support_slots = {
        fighter: slots
        for fighter, slots in fighter_support_slots.items()
        if slots
    }
    if not fighter_support_slots:
        return None

    if analysis.primary_fighter in fighter_support_slots:
        fighter = str(analysis.primary_fighter)
    elif len(fighter_support_slots) == 1:
        fighter = next(iter(fighter_support_slots))
    else:
        fighter = min(
            fighter_support_slots.keys(),
            key=lambda key: (
                len(fighter_support_slots[key]),
                min(fighter_support_slots[key]),
                key,
            ),
        )

    source_slots = fighter_support_slots[fighter]
    recommended = source_slots[0]
    if analysis.primary_slot in source_slots:
        recommended = int(analysis.primary_slot)

    return SupportPackScopeInfo(
        support_kind=normalized_kind,
        fighter=fighter,
        source_slots=source_slots,
        recommended_source_slot=recommended,
        visual_slots=list(analysis.visual_fighter_slots.get(fighter, [])),
    )


def inspect_mod_voice_pack(mod_path: Path) -> VoicePackScopeInfo | None:
    return inspect_mod_support_pack(mod_path, "voice")


def inspect_mod_effect_pack(mod_path: Path) -> SupportPackScopeInfo | None:
    return inspect_mod_support_pack(mod_path, "effect")


def inspect_mod_camera_pack(mod_path: Path) -> SupportPackScopeInfo | None:
    return inspect_mod_support_pack(mod_path, "camera")


def apply_mod_support_pack_scope(
    mod_path: Path,
    mods_path: Path,
    support_kind: str,
    mode: str,
    source_slot: int | None = None,
    target_slot: int | None = None,
) -> SupportPackScopeSummary:
    mod_path = Path(mod_path)
    mods_path = Path(mods_path)
    normalized_kind = _normalize_support_kind(support_kind)
    info = inspect_mod_support_pack(mod_path, normalized_kind)
    support_label = _SUPPORT_KIND_LABELS[normalized_kind].capitalize()
    if info is None:
        raise ValueError(f"This mod does not contain any slot-scoped fighter {normalized_kind} files.")

    fighter = str(info.fighter)
    chosen_source_slot = int(source_slot if source_slot is not None else info.recommended_source_slot)
    if chosen_source_slot not in info.source_slots:
        raise ValueError(
            f"{support_label} source slot {fighter} c{chosen_source_slot:02d} was not found in this mod."
        )

    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode == "single_slot":
        if target_slot is None:
            raise ValueError(f"Choose a target slot for single-slot {normalized_kind} assignment.")
        target_slots = [int(target_slot)]
    elif normalized_mode == "character_wide":
        target_slots = list(range(8))
    else:
        raise ValueError(f"Unsupported {normalized_kind} pack mode.")

    temp_dir = tempfile.TemporaryDirectory(prefix=f"ssbumm_{normalized_kind}_scope_")
    summary = ImportSummary()
    files_written = 0
    try:
        temp_root = Path(temp_dir.name) / mod_path.name
        shutil.copytree(mod_path, temp_root)
        _remove_support_files_for_fighter(temp_root, fighter, normalized_kind)
        files_written = _copy_support_files_from_source_slot(
            mod_path,
            temp_root,
            fighter,
            chosen_source_slot,
            target_slots,
            normalized_kind,
        )
        if files_written == 0:
            raise ValueError(
                f"No {normalized_kind} files for {fighter} c{chosen_source_slot:02d} were available to duplicate."
            )

        _resolve_support_path_conflicts(temp_root, mod_path.name, mods_path, summary)
        _replace_directory_from_temp(mod_path, temp_root)
    finally:
        temp_dir.cleanup()

    return SupportPackScopeSummary(
        support_kind=normalized_kind,
        mod_name=mod_path.name,
        fighter=fighter,
        source_slot=chosen_source_slot,
        target_slots=target_slots,
        files_written=files_written,
        support_mod_adjustments=summary.support_mod_adjustments,
        support_files_pruned=summary.support_files_pruned,
        warnings=list(summary.warnings),
    )


def apply_mod_voice_pack_scope(
    mod_path: Path,
    mods_path: Path,
    mode: str,
    source_slot: int | None = None,
    target_slot: int | None = None,
) -> VoicePackScopeSummary:
    return apply_mod_support_pack_scope(
        mod_path,
        mods_path,
        "voice",
        mode=mode,
        source_slot=source_slot,
        target_slot=target_slot,
    )


def apply_mod_effect_pack_scope(
    mod_path: Path,
    mods_path: Path,
    mode: str,
    source_slot: int | None = None,
    target_slot: int | None = None,
) -> SupportPackScopeSummary:
    return apply_mod_support_pack_scope(
        mod_path,
        mods_path,
        "effect",
        mode=mode,
        source_slot=source_slot,
        target_slot=target_slot,
    )


def apply_mod_camera_pack_scope(
    mod_path: Path,
    mods_path: Path,
    mode: str,
    source_slot: int | None = None,
    target_slot: int | None = None,
) -> SupportPackScopeSummary:
    return apply_mod_support_pack_scope(
        mod_path,
        mods_path,
        "camera",
        mode=mode,
        source_slot=source_slot,
        target_slot=target_slot,
    )


def import_mod_package(
    source_dir: Path,
    mods_path: Path,
    slot_conflict_resolver: SlotConflictResolver | None = None,
    multi_slot_pack_resolver: MultiSlotPackResolver | None = None,
) -> ImportSummary:
    """Import one or more mod folders from a chosen directory."""
    source_dir = Path(source_dir)
    mods_path = Path(mods_path)
    if not source_dir.exists():
        raise ValueError("Selected mod import path does not exist.")

    summary = ImportSummary()
    prepared_sources = _prepare_mod_import_sources(
        source_dir,
        summary,
        multi_slot_pack_resolver=multi_slot_pack_resolver,
    )
    if not prepared_sources:
        raise ValueError(
            "No importable mod folders or archives were found. "
            "Select a folder/archive that contains SSBU mod content."
        )

    mods_path.mkdir(parents=True, exist_ok=True)
    slot_index = _build_slot_index(mods_path)

    try:
        for prepared in prepared_sources:
            src = prepared.source_dir
            target_name = prepared.target_name
            analysis = prepared.analysis

            if analysis.has_visual_skin_slot:
                fighter = str(analysis.primary_fighter)
                source_slot = int(analysis.primary_slot)
                target_slot = source_slot
                conflicting_mods = [
                    mod_name
                    for mod_name in slot_index.get(fighter, {}).get(source_slot, [])
                    if mod_name != target_name
                ]
                if conflicting_mods:
                    open_slots = _available_base_slots(slot_index, fighter)
                    conflict = SlotConflictInfo(
                        mod_name=target_name,
                        fighter=fighter,
                        requested_slot=source_slot,
                        conflicting_mods=conflicting_mods,
                        open_slots=open_slots,
                    )
                    action = _resolve_slot_conflict(conflict, slot_conflict_resolver)

                    if action == "replace":
                        for mod_name in conflicting_mods:
                            _disable_conflicting_mod(mods_path, mod_name, summary, fighter, source_slot)
                        slot_index.setdefault(fighter, {}).pop(source_slot, None)
                    elif action == "move_existing":
                        if len(conflicting_mods) != 1 or not open_slots:
                            summary.skipped_items.append(
                                f"{target_name} ({fighter} c{source_slot:02d})"
                            )
                            summary.warnings.append(
                                f"Skipped '{target_name}' because slot {fighter} c{source_slot:02d} "
                                "was occupied and the existing mod could not be moved safely."
                            )
                            continue
                        existing_mod_name = conflicting_mods[0]
                        target_open_slot = choose_open_target_slot(fighter, source_slot, open_slots)
                        if target_open_slot is None:
                            summary.skipped_items.append(
                                f"{target_name} ({fighter} c{source_slot:02d})"
                            )
                            summary.warnings.append(
                                f"Skipped '{target_name}' because slot {fighter} c{source_slot:02d} "
                                "was occupied and no open replacement slot was available."
                            )
                            continue
                        _move_installed_mod_to_open_slot(
                            mods_path, existing_mod_name, fighter, source_slot, target_open_slot, summary
                        )
                        slot_index.setdefault(fighter, {}).pop(source_slot, None)
                        slot_index.setdefault(fighter, {}).setdefault(target_open_slot, []).append(existing_mod_name)
                    elif action == "move_incoming":
                        target_open_slot = choose_open_target_slot(fighter, source_slot, open_slots)
                        if target_open_slot is None:
                            summary.skipped_items.append(
                                f"{target_name} ({fighter} c{source_slot:02d})"
                            )
                            summary.warnings.append(
                                f"Skipped '{target_name}' because slot {fighter} c{source_slot:02d} "
                                "was occupied and no open base slot remained."
                            )
                            continue
                        target_slot = target_open_slot
                    else:
                        summary.skipped_items.append(
                            f"{target_name} ({fighter} c{source_slot:02d})"
                        )
                        summary.warnings.append(
                            f"Skipped '{target_name}' because slot {fighter} c{source_slot:02d} "
                            "was already occupied."
                        )
                        continue

                if target_slot != source_slot:
                    temp_dir = tempfile.TemporaryDirectory(prefix="ssbumm_reslot_")
                    prepared.temp_paths.append(temp_dir)
                    reslotted_path = Path(temp_dir.name) / target_name
                    reslot_mod_directory(src, reslotted_path, fighter, source_slot, target_slot)
                    src = reslotted_path
                    target_name = _rename_target_name_for_slot(target_name, source_slot, target_slot)
                    summary.slot_reassignments += 1
                    summary.warnings.append(
                        f"Imported '{target_name}' as {fighter} c{target_slot:02d} "
                        f"instead of c{source_slot:02d} to avoid a slot overlap."
                    )

            _resolve_support_path_conflicts(src, target_name, mods_path, summary)

            dest = mods_path / target_name
            if _same_path(src, dest):
                summary.warnings.append(f"Skipped '{target_name}' (already in mods folder).")
                continue

            _copy_dir_replace(src, dest, summary)
            summary.items_imported += 1
            summary.files_copied += _count_files(dest)

            if analysis.has_visual_skin_slot:
                fighter = str(analysis.primary_fighter)
                slot = _detect_installed_primary_slot(dest, analysis)
                if slot is not None:
                    slot_index.setdefault(fighter, {}).setdefault(slot, []).append(target_name)

            if _flatten_nested_mod(dest):
                summary.flattened_mods += 1
    finally:
        for prepared in prepared_sources:
            for temp_dir in prepared.temp_paths:
                try:
                    temp_dir.cleanup()
                except Exception:
                    pass

    if summary.items_imported == 0:
        skipped = ", ".join(summary.skipped_items[:5]) if summary.skipped_items else ""
        if skipped:
            raise ValueError(f"Nothing was imported. Skipped items: {skipped}")
        raise ValueError("Nothing was imported. The selected folder may already be in use.")
    return summary


def import_plugin_package(source_dir: Path, sdmc_path: Path, plugins_path: Path) -> ImportSummary:
    """Import Skyline plugin packages and related romfs/exefs payloads."""
    source_dir = Path(source_dir)
    sdmc_path = Path(sdmc_path)
    plugins_path = Path(plugins_path)

    if not source_dir.exists() or not source_dir.is_dir():
        raise ValueError("Selected plugin import path is not a valid folder.")
    if not sdmc_path.exists() or not sdmc_path.is_dir():
        raise ValueError("SDMC path is not configured.")

    plugins_path.mkdir(parents=True, exist_ok=True)
    disabled_plugins_path = plugins_path.parent / "disabled_plugins"
    contents_root = sdmc_path / "atmosphere" / "contents"
    contents_root.mkdir(parents=True, exist_ok=True)
    title_root = contents_root / SSBU_TITLE_ID
    title_root.mkdir(parents=True, exist_ok=True)

    summary = ImportSummary()
    copied_structured: set[tuple[str, str]] = set()
    copied_plugin_targets: set[str] = set()

    def copy_tree_once(src: Path, dst: Path) -> int:
        src_key = _norm_path(src)
        dst_key = _norm_path(dst)
        key = (src_key, dst_key)
        if key in copied_structured:
            return 0
        copied_structured.add(key)

        if _same_path(src, dst):
            summary.warnings.append(f"Skipped '{src.name}' (source equals destination).")
            return 0
        if _is_descendant(dst, src) or _is_descendant(src, dst):
            summary.warnings.append(
                f"Skipped '{src}' to avoid recursive/self copy with '{dst}'."
            )
            return 0

        copied = _copy_tree_contents(
            src,
            dst,
            summary,
            plugins_root=plugins_path,
            disabled_plugins_root=disabled_plugins_path,
            plugin_targets=copied_plugin_targets,
        )
        if copied:
            summary.items_imported += 1
        return copied

    def process_root(root: Path) -> None:
        # Atmosphere package root
        atm_contents = root / "atmosphere" / "contents"
        if atm_contents.exists() and atm_contents.is_dir():
            for title_dir in _iter_visible_dirs(atm_contents):
                copy_tree_once(title_dir, contents_root / title_dir.name)

        # Flat "contents" package root
        direct_contents = root / "contents"
        if direct_contents.exists() and direct_contents.is_dir():
            for title_dir in _iter_visible_dirs(direct_contents):
                copy_tree_once(title_dir, contents_root / title_dir.name)

        # Direct title-id folder package root
        for child in _iter_visible_dirs(root):
            if _looks_like_title_id(child.name):
                copy_tree_once(child, contents_root / child.name)

        # Loose romfs/exefs payload
        romfs = root / "romfs"
        if romfs.exists() and romfs.is_dir():
            copy_tree_once(romfs, title_root / "romfs")
        exefs = root / "exefs"
        if exefs.exists() and exefs.is_dir():
            copy_tree_once(exefs, title_root / "exefs")

        # Direct plugins folder package root
        plugins_dir = root / "plugins"
        if plugins_dir.exists() and plugins_dir.is_dir():
            copy_tree_once(plugins_dir, plugins_path)

    for root in _candidate_roots(source_dir):
        process_root(root)
        sdmc_sub = root / "sdmc"
        if sdmc_sub.exists() and sdmc_sub.is_dir():
            process_root(sdmc_sub)

    # Fallback: copy loose plugin binaries anywhere in the selected folder.
    for file_path in sorted(source_dir.rglob("*")):
        if not file_path.is_file():
            continue
        if not _is_plugin_binary(file_path.name):
            continue

        normalized_name, is_disabled = _normalize_plugin_binary_name(file_path.name)
        target_root = disabled_plugins_path if is_disabled else plugins_path
        target = target_root / normalized_name
        target_key = _norm_path(target)
        if target_key in copied_plugin_targets or _same_path(file_path, target):
            continue

        if target.exists():
            summary.replaced_paths += 1
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, target)
        copied_plugin_targets.add(target_key)
        summary.files_copied += 1
        summary.plugin_files += 1

    if summary.files_copied == 0:
        raise ValueError(
            "No importable plugin files or package payloads were found in that folder."
        )
    return summary


def _prepare_mod_import_sources(
    source_path: Path,
    summary: ImportSummary,
    multi_slot_pack_resolver: MultiSlotPackResolver | None = None,
) -> list[_PreparedModImport]:
    source_path = Path(source_path)
    prepared: list[_PreparedModImport] = []

    def add_from_mod_root(
        root: Path,
        package_name: str,
        owned_temp_dir: tempfile.TemporaryDirectory | None = None,
    ) -> None:
        sources = _collect_mod_sources(root)
        if not sources:
            if owned_temp_dir is not None:
                try:
                    owned_temp_dir.cleanup()
                except Exception:
                    pass
            return

        analyses = {
            str(src): analyze_mod_directory(src, [package_name, target_name, src.name])
            for src, target_name in sources
        }
        chosen_src, chosen_name = choose_primary_variant_root(sources, analyses, package_name)
        if owned_temp_dir is not None and (
            chosen_name.startswith("ssbumm_archive_")
            or chosen_name.lower() in _GENERIC_FOLDER_NAMES
        ):
            chosen_name = _sanitize_name(Path(package_name).stem)
        if len(sources) > 1:
            skipped_names = [name for src, name in sources if src != chosen_src]
            summary.warnings.append(
                f"Selected base variant '{chosen_name}' from '{package_name}' and skipped "
                f"{len(skipped_names)} other variant(s)."
            )

        temp_paths: list[tempfile.TemporaryDirectory] = []
        if owned_temp_dir is not None:
            temp_paths.append(owned_temp_dir)
        _append_prepared_visual_variants(
            prepared,
            chosen_src,
            chosen_name,
            package_name,
            analyses[str(chosen_src)],
            summary,
            temp_paths,
            multi_slot_pack_resolver=multi_slot_pack_resolver,
        )

    if source_path.is_file():
        if not is_archive_path(source_path):
            raise ValueError("Selected mod import path is not a supported archive or folder.")
        temp_dir = tempfile.TemporaryDirectory(prefix="ssbumm_archive_")
        extract_archive(source_path, Path(temp_dir.name))
        summary.archives_processed += 1
        add_from_mod_root(Path(temp_dir.name), source_path.name, temp_dir)
    elif source_path.is_dir():
        direct_sources = _collect_mod_sources(source_path)
        if direct_sources:
            for chosen_src, chosen_name in direct_sources:
                chosen_analysis = analyze_mod_directory(chosen_src, [source_path.name, chosen_name, chosen_src.name])
                _append_prepared_visual_variants(
                    prepared,
                    chosen_src,
                    chosen_name,
                    source_path.name,
                    chosen_analysis,
                    summary,
                    [],
                    multi_slot_pack_resolver=multi_slot_pack_resolver,
                )
        else:
            archives = sorted(
                child for child in source_path.iterdir()
                if child.is_file() and is_archive_path(child)
            )
            for archive in archives:
                temp_dir = tempfile.TemporaryDirectory(prefix="ssbumm_archive_")
                extract_archive(archive, Path(temp_dir.name))
                summary.archives_processed += 1
                add_from_mod_root(Path(temp_dir.name), archive.name, temp_dir)
    return prepared


def _append_prepared_visual_variants(
    prepared: list[_PreparedModImport],
    source_dir: Path,
    target_name: str,
    package_name: str,
    analysis: SlotAnalysis,
    summary: ImportSummary,
    base_temp_paths: list[tempfile.TemporaryDirectory],
    multi_slot_pack_resolver: MultiSlotPackResolver | None = None,
) -> None:
    visual_options = _build_multi_slot_pack_options(source_dir, analysis)
    if len(visual_options) <= 1:
        if analysis.has_visual_skin_slot and analysis.slot_count > 1:
            fighter = str(analysis.primary_fighter)
            slot = int(analysis.primary_slot)
            variant_temp = tempfile.TemporaryDirectory(prefix="ssbumm_variant_")
            variant_root = Path(variant_temp.name) / target_name
            copy_single_slot_variant(source_dir, variant_root, fighter, slot)
            if _count_files(variant_root) > 0:
                prepared.append(
                    _PreparedModImport(
                        source_dir=variant_root,
                        target_name=target_name,
                        package_name=package_name,
                        analysis=analyze_mod_directory(variant_root, [package_name, target_name]),
                        temp_paths=[*base_temp_paths, variant_temp],
                    )
                )
                summary.warnings.append(
                    f"Selected base skin {fighter} c{slot:02d} from '{target_name}' and omitted its other slots."
                )
                return
            variant_temp.cleanup()
        prepared.append(
            _PreparedModImport(
                source_dir=source_dir,
                target_name=target_name,
                package_name=package_name,
                analysis=analysis,
                temp_paths=list(base_temp_paths),
            )
        )
        return

    selection_info = MultiSlotPackSelectionInfo(
        mod_name=target_name,
        package_name=package_name,
        options=visual_options,
    )
    selected_options = _resolve_multi_slot_pack_selection(selection_info, multi_slot_pack_resolver)
    if not selected_options:
        summary.skipped_items.append(f"{target_name} (multi-slot package)")
        summary.warnings.append(
            f"Skipped '{target_name}' because no skins were selected from its multi-slot pack."
        )
        for temp_dir in base_temp_paths:
            try:
                temp_dir.cleanup()
            except Exception:
                pass
        return

    if multi_slot_pack_resolver is None and len(selected_options) == 1:
        option = selected_options[0]
        summary.warnings.append(
            f"Selected base skin {option.label} from '{target_name}' and omitted its other slots."
        )
    else:
        summary.warnings.append(
            f"Selected {len(selected_options)} skin(s) from '{target_name}' and omitted "
            f"{len(visual_options) - len(selected_options)} other slot(s)."
        )

    for option in selected_options:
        variant_temp = tempfile.TemporaryDirectory(prefix="ssbumm_variant_")
        variant_root_name = _build_multi_slot_variant_name(target_name, option.fighter, option.slot)
        variant_root = Path(variant_temp.name) / variant_root_name
        copy_single_slot_variant(source_dir, variant_root, option.fighter, option.slot)
        if _count_files(variant_root) == 0:
            variant_temp.cleanup()
            summary.skipped_items.append(f"{variant_root_name} (empty variant)")
            summary.warnings.append(
                f"Skipped '{variant_root_name}' because no files remained after splitting "
                f"{option.fighter} c{option.slot:02d}."
            )
            continue

        variant_analysis = analyze_mod_directory(
            variant_root,
            [package_name, target_name, variant_root_name],
        )
        if variant_analysis.visual_fighter_slots and variant_analysis.visual_slot_count > 1:
            variant_temp.cleanup()
            summary.skipped_items.append(f"{variant_root_name} (unsupported multi-slot package)")
            summary.warnings.append(
                f"Skipped '{variant_root_name}' because it still contains multiple fighter/slot targets "
                "after slot splitting."
            )
            continue

        prepared.append(
            _PreparedModImport(
                source_dir=variant_root,
                target_name=variant_root_name,
                package_name=package_name,
                analysis=variant_analysis,
                temp_paths=[*base_temp_paths, variant_temp],
            )
        )


def _build_multi_slot_pack_options(
    source_dir: Path,
    analysis: SlotAnalysis,
) -> list[MultiSlotPackOption]:
    options: list[MultiSlotPackOption] = []
    friendly_labels = _resolve_multi_slot_option_labels(source_dir, analysis)
    labeled_fighters = {fighter for fighter, _slot in friendly_labels}
    recommended_id = None
    if analysis.primary_fighter is not None and analysis.primary_slot is not None:
        recommended_id = f"{analysis.primary_fighter.lower()}:c{int(analysis.primary_slot):02d}"

    for fighter, slots in sorted(analysis.visual_fighter_slots.items()):
        fighter_name = str(fighter).lower()
        if labeled_fighters and fighter_name not in labeled_fighters:
            continue
        for slot in slots:
            option_id = f"{fighter_name}:c{int(slot):02d}"
            display_name = friendly_labels.get((fighter_name, int(slot)))
            fallback_label = f"{fighter_name} c{int(slot):02d}"
            label = fallback_label
            if display_name and display_name.lower() != fallback_label.lower():
                label = f"{display_name} ({fallback_label})"
            options.append(
                MultiSlotPackOption(
                    option_id=option_id,
                    fighter=fighter_name,
                    slot=int(slot),
                    label=label,
                    recommended=(option_id == recommended_id),
                )
            )
    return options


def _resolve_multi_slot_option_labels(
    source_dir: Path,
    analysis: SlotAnalysis,
) -> dict[tuple[str, int], str]:
    visual_slots = {
        str(fighter).lower(): {int(slot) for slot in slots}
        for fighter, slots in analysis.visual_fighter_slots.items()
        if slots
    }
    if not visual_slots:
        return {}

    labels = _extract_multi_slot_names_from_msg_name(source_dir, visual_slots)
    if len(visual_slots) == 1:
        for key, value in _extract_multi_slot_names_from_ui_chara_db(source_dir, visual_slots).items():
            labels.setdefault(key, value)
    return labels


def _extract_multi_slot_names_from_msg_name(
    source_dir: Path,
    visual_slots: dict[str, set[int]],
) -> dict[tuple[str, int], str]:
    message_dir = source_dir / "ui" / "message"
    xmsbt_path = message_dir / "msg_name.xmsbt"
    msbt_path = message_dir / "msg_name.msbt"
    entries: dict[str, str] = {}
    if xmsbt_path.is_file():
        entries = parse_xmsbt(xmsbt_path)
    elif msbt_path.is_file():
        entries = extract_entries_from_msbt(msbt_path)
    if not entries:
        return {}

    single_fighter = next(iter(visual_slots)) if len(visual_slots) == 1 else None
    fallback_names: dict[tuple[str, int], str] = {}
    preferred_names: dict[tuple[str, int], str] = {}
    for label, text in entries.items():
        match = _MSG_NAME_ENTRY_PATTERN.match(str(label).strip())
        if not match:
            continue
        slot = int(match.group("slot"))
        label_fighter = match.group("name_id").lower()
        if label_fighter in visual_slots:
            fighter = label_fighter
        elif single_fighter is not None and slot in visual_slots[single_fighter]:
            fighter = single_fighter
        else:
            continue
        if slot not in visual_slots.get(fighter, set()):
            continue

        display_name = _clean_multi_slot_label_text(text)
        if not display_name:
            continue

        key = (fighter, slot)
        if match.group("tier") == "1":
            preferred_names[key] = display_name
        else:
            fallback_names.setdefault(key, display_name)

    resolved = dict(fallback_names)
    resolved.update(preferred_names)
    return resolved


def _extract_multi_slot_names_from_ui_chara_db(
    source_dir: Path,
    visual_slots: dict[str, set[int]],
) -> dict[tuple[str, int], str]:
    prcxml_path = source_dir / "ui" / "param" / "database" / "ui_chara_db.prcxml"
    if not prcxml_path.is_file() or len(visual_slots) != 1:
        return {}

    fighter = next(iter(visual_slots))
    try:
        content = prcxml_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}

    labels: dict[tuple[str, int], str] = {}
    for match in _PRCXML_CHARACALL_PATTERN.finditer(content):
        slot = int(match.group("slot"))
        if slot not in visual_slots[fighter]:
            continue
        display_name = _humanize_support_identifier(match.group("identifier"))
        if display_name:
            labels[(fighter, slot)] = display_name
    return labels


def _clean_multi_slot_label_text(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", str(value or "")).strip()
    return collapsed


def _humanize_support_identifier(identifier: str) -> str:
    value = re.sub(r"(?i)^vc_narration_characall_", "", str(identifier or "")).strip(" _-")
    if not value:
        return ""

    parts = [part for part in re.split(r"[_\s]+", value) if part]
    if len(parts) == 1:
        token = parts[0]
        compact_match = re.fullmatch(r"([a-z]{1,3})([a-z]{4,})", token, re.IGNORECASE)
        if compact_match:
            parts = [compact_match.group(1), compact_match.group(2)]

    def _format_part(part: str) -> str:
        if len(part) <= 2 and part.isalpha():
            return part.upper()
        return part.capitalize()

    return " ".join(_format_part(part) for part in parts)


def _resolve_multi_slot_pack_selection(
    info: MultiSlotPackSelectionInfo,
    resolver: MultiSlotPackResolver | None,
) -> list[MultiSlotPackOption]:
    if not info.options:
        return []

    selected_ids: list[str] = []
    if resolver is not None:
        try:
            response = resolver(info)
        except Exception:
            response = None
        if response:
            selected_ids = [str(item).strip().lower() for item in response if str(item).strip()]
        elif response == []:
            return []

    if not selected_ids:
        recommended = next((option for option in info.options if option.recommended), None)
        return [recommended or info.options[0]]

    selected = [option for option in info.options if option.option_id.lower() in set(selected_ids)]
    if selected:
        return selected

    recommended = next((option for option in info.options if option.recommended), None)
    return [recommended or info.options[0]]


def _build_multi_slot_variant_name(base_name: str, fighter: str, slot: int) -> str:
    slot_token = f"c{int(slot):02d}"
    lowered = base_name.lower()
    has_fighter = re.search(rf"(?i)(?<![a-z0-9]){re.escape(fighter)}(?![a-z0-9])", lowered) is not None
    has_slot = re.search(rf"(?i)(?<![a-z0-9]){re.escape(slot_token)}(?!\d)", lowered) is not None
    if has_fighter and has_slot:
        return _sanitize_name(base_name)
    return _sanitize_name(f"{base_name} [{fighter} {slot_token}]")


def _resolve_slot_conflict(
    conflict: SlotConflictInfo,
    resolver: SlotConflictResolver | None,
) -> str:
    if resolver is not None:
        action = str(resolver(conflict) or "").strip().lower()
        if action in {"replace", "move_existing", "move_incoming", "skip"}:
            return action
    if conflict.open_slots:
        return "move_incoming"
    return "skip"


def _build_slot_index(mods_path: Path) -> dict[str, dict[int, list[str]]]:
    index: dict[str, dict[int, list[str]]] = {}
    if not mods_path.exists() or not mods_path.is_dir():
        return index
    for folder in sorted(mods_path.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir() or folder.name.startswith(".") or folder.name.startswith("_"):
            continue
        analysis = analyze_mod_directory(folder, [folder.name])
        if not analysis.visual_fighter_slots:
            continue
        for fighter, slots in analysis.visual_fighter_slots.items():
            for slot in slots:
                index.setdefault(str(fighter), {}).setdefault(int(slot), []).append(folder.name)
    return index


def _available_base_slots(slot_index: dict[str, dict[int, list[str]]], fighter: str) -> list[int]:
    used = set(slot_index.get(fighter, {}).keys())
    return [slot for slot in range(8) if slot not in used]


def _disable_conflicting_mod(mods_path: Path, mod_name: str, summary: ImportSummary, fighter: str, slot: int) -> None:
    src = mods_path / mod_name
    if not src.exists():
        return
    disabled_dir = mods_path.parent / "disabled_mods"
    disabled_dir.mkdir(parents=True, exist_ok=True)
    dest = disabled_dir / mod_name
    suffix = 1
    while dest.exists():
        dest = disabled_dir / f"{mod_name} ({suffix})"
        suffix += 1
    src.rename(dest)
    summary.warnings.append(
        f"Disabled existing mod '{mod_name}' so '{fighter} c{slot:02d}' could be replaced."
    )


def _move_installed_mod_to_open_slot(
    mods_path: Path,
    mod_name: str,
    fighter: str,
    source_slot: int,
    target_slot: int,
    summary: ImportSummary,
) -> None:
    src = mods_path / mod_name
    if not src.exists() or not src.is_dir():
        raise FileNotFoundError(f"Installed mod not found: {mod_name}")

    temp_dir = tempfile.TemporaryDirectory(prefix="ssbumm_existing_reslot_")
    try:
        reslotted_root = Path(temp_dir.name) / mod_name
        reslot_mod_directory(src, reslotted_root, fighter, source_slot, target_slot)
        backup = src.parent / f"{mod_name}.ssbumm-backup"
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        src.rename(backup)
        try:
            shutil.move(str(reslotted_root), str(src))
            shutil.rmtree(backup, ignore_errors=True)
        except Exception:
            if src.exists():
                shutil.rmtree(src, ignore_errors=True)
            backup.rename(src)
            raise
    finally:
        temp_dir.cleanup()

    summary.slot_reassignments += 1
    summary.warnings.append(
        f"Moved existing mod '{mod_name}' from {fighter} c{source_slot:02d} to c{target_slot:02d}."
    )


def _detect_installed_primary_slot(dest: Path, previous_analysis: SlotAnalysis) -> int | None:
    analysis = analyze_mod_directory(dest, [dest.name])
    if analysis.has_visual_skin_slot:
        return int(analysis.primary_slot)
    if previous_analysis.has_visual_skin_slot:
        return int(previous_analysis.primary_slot)
    return None


def _collect_mod_sources(source_dir: Path) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []

    # Case 1: selected folder is an exported SDMC/package root.
    for mods_root in (source_dir / "ultimate" / "mods", source_dir / "mods"):
        if mods_root.exists() and mods_root.is_dir():
            for child in _iter_visible_dirs(mods_root):
                if child.name.lower() in _MOD_SKIP_DIRS:
                    continue
                resolved = _unwrap_single_wrapper(child)
                if _contains_mod_content(resolved):
                    found.append((resolved, _pick_mod_target_name(child, resolved)))
            if found:
                return _dedupe_sources(found)

    # Case 2: selected folder itself is (or wraps) a single mod.
    root_resolved = _unwrap_single_wrapper(source_dir)
    if _contains_mod_content(root_resolved):
        found.append((root_resolved, _pick_mod_target_name(source_dir, root_resolved)))
        return _dedupe_sources(found)

    # Case 3: selected folder contains multiple mod folders.
    for child in _iter_visible_dirs(source_dir):
        if child.name.lower() in _MOD_SKIP_DIRS:
            continue
        resolved = _unwrap_single_wrapper(child)
        if _contains_mod_content(resolved):
            found.append((resolved, _pick_mod_target_name(child, resolved)))

    # Case 4: one extra wrapper above many mod folders.
    if not found:
        wrappers = [d for d in _iter_visible_dirs(source_dir) if d.name.lower() not in _MOD_SKIP_DIRS]
        if len(wrappers) == 1:
            wrapped_root = wrappers[0]
            for child in _iter_visible_dirs(wrapped_root):
                resolved = _unwrap_single_wrapper(child)
                if _contains_mod_content(resolved):
                    found.append((resolved, _pick_mod_target_name(child, resolved)))

    # Case 5: deeply nested mod collections inside an archive/package.
    if not found:
        try:
            for candidate in sorted(source_dir.rglob("*"), key=lambda p: len(p.parts)):
                if not candidate.is_dir() or candidate == source_dir:
                    continue
                if any(part.lower() in _MOD_SKIP_DIRS for part in candidate.relative_to(source_dir).parts):
                    continue
                resolved = _unwrap_single_wrapper(candidate)
                if _contains_mod_content(resolved):
                    found.append((resolved, _pick_mod_target_name(candidate, resolved)))
        except (PermissionError, OSError):
            pass

    return _dedupe_sources(found)


def _copy_dir_replace(src: Path, dst: Path, summary: ImportSummary) -> None:
    if dst.exists():
        _remove_path(dst)
        summary.replaced_paths += 1
    shutil.copytree(src, dst)


def _copy_tree_contents(
    src_root: Path,
    dst_root: Path,
    summary: ImportSummary,
    plugins_root: Path | None = None,
    disabled_plugins_root: Path | None = None,
    plugin_targets: set[str] | None = None,
) -> int:
    copied = 0
    if not src_root.exists() or not src_root.is_dir():
        return copied

    for file_path in sorted(src_root.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(src_root)
        out_path = dst_root / rel

        if (
            plugins_root is not None
            and disabled_plugins_root is not None
            and _is_plugin_binary(out_path.name)
            and _is_descendant(out_path, plugins_root)
        ):
            normalized_name, is_disabled = _normalize_plugin_binary_name(out_path.name)
            if is_disabled:
                plugin_rel = out_path.relative_to(plugins_root).with_name(normalized_name)
                out_path = disabled_plugins_root / plugin_rel

        if _same_path(file_path, out_path):
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists():
            summary.replaced_paths += 1
        shutil.copy2(file_path, out_path)
        copied += 1
        summary.files_copied += 1

        if (
            plugins_root is not None
            and plugin_targets is not None
            and _is_plugin_binary(out_path.name)
            and (
                _is_descendant(out_path, plugins_root)
                or (
                    disabled_plugins_root is not None
                    and _is_descendant(out_path, disabled_plugins_root)
                )
            )
        ):
            key = _norm_path(out_path)
            if key not in plugin_targets:
                plugin_targets.add(key)
                summary.plugin_files += 1

    return copied


def _resolve_support_path_conflicts(
    src: Path,
    target_name: str,
    mods_path: Path,
    summary: ImportSummary,
) -> None:
    support_paths = _collect_support_candidate_paths(src)
    if not support_paths:
        return

    path_index = _build_relative_path_index(mods_path)
    prune_map: dict[str, set[str]] = defaultdict(set)
    unresolved: dict[str, set[str]] = defaultdict(set)

    for rel in support_paths:
        for mod_name in path_index.get(rel, []):
            if mod_name == target_name:
                continue
            mod_path = mods_path / mod_name
            if not mod_path.exists() or not mod_path.is_dir():
                continue
            analysis = analyze_mod_directory(mod_path, [mod_name])
            if analysis.has_visual_skin_slot:
                unresolved[mod_name].add(rel)
                continue
            prune_map[mod_name].add(rel)

    for mod_name, rels in sorted(prune_map.items()):
        _prune_existing_support_files(mods_path, mod_name, sorted(rels), summary)

    for mod_name, rels in sorted(unresolved.items()):
        summary.warnings.append(
            f"'{target_name}' still shares {len(rels)} exact support file(s) with visual mod "
            f"'{mod_name}'. Review those support overrides manually if behavior looks wrong."
        )


def _normalize_support_kind(support_kind: str) -> str:
    normalized = str(support_kind or "").strip().lower()
    if normalized not in _SUPPORT_KIND_TO_CATEGORY:
        raise ValueError("Unsupported support pack type.")
    return normalized


def _remove_support_files_for_fighter(mod_root: Path, fighter: str, support_kind: str) -> None:
    normalized_kind = _normalize_support_kind(support_kind)
    fighter = str(fighter).lower()
    for file_path in list(mod_root.rglob("*")):
        if not file_path.is_file():
            continue
        rel = str(file_path.relative_to(mod_root)).replace("\\", "/")
        if not _is_support_file_for_fighter_slot(rel, fighter, normalized_kind):
            continue
        file_path.unlink()
        _prune_empty_parents(file_path.parent, mod_root)


def _remove_voice_files_for_fighter(mod_root: Path, fighter: str) -> None:
    _remove_support_files_for_fighter(mod_root, fighter, "voice")


def _copy_support_files_from_source_slot(
    source_root: Path,
    dest_root: Path,
    fighter: str,
    source_slot: int,
    target_slots: list[int],
    support_kind: str,
) -> int:
    normalized_kind = _normalize_support_kind(support_kind)
    fighter = str(fighter).lower()
    written = 0
    seen: set[str] = set()
    for file_path in source_root.rglob("*"):
        if not file_path.is_file():
            continue
        rel = str(file_path.relative_to(source_root)).replace("\\", "/")
        if not _is_support_file_for_fighter_slot(rel, fighter, normalized_kind, source_slot):
            continue
        for slot in target_slots:
            new_rel = _retarget_support_relative_path(rel, normalized_kind, fighter, source_slot, int(slot))
            if new_rel in seen:
                continue
            seen.add(new_rel)
            out_path = dest_root / new_rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, out_path)
            written += 1
    return written


def _copy_voice_files_from_source_slot(
    source_root: Path,
    dest_root: Path,
    fighter: str,
    source_slot: int,
    target_slots: list[int],
) -> int:
    return _copy_support_files_from_source_slot(
        source_root,
        dest_root,
        fighter,
        source_slot,
        target_slots,
        "voice",
    )


def _flatten_nested_mod(mod_path: Path) -> bool:
    flattened = False
    while True:
        nested = _find_single_nested_content_child(mod_path)
        if nested is None:
            return flattened

        moved_any = False
        for item in list(nested.iterdir()):
            dest = mod_path / item.name
            if dest.exists():
                continue
            item.rename(dest)
            moved_any = True

        try:
            if nested.exists() and not any(nested.iterdir()):
                nested.rmdir()
        except OSError:
            pass

        if not moved_any:
            return flattened
        flattened = True


def _find_single_nested_content_child(mod_path: Path) -> Path | None:
    if _contains_mod_content(mod_path):
        return None
    subdirs = [d for d in _iter_visible_dirs(mod_path)]
    if len(subdirs) != 1:
        return None
    child = subdirs[0]
    return child if _contains_mod_content(child) else None


def _unwrap_single_wrapper(folder: Path, max_depth: int = 4) -> Path:
    current = folder
    for _ in range(max_depth):
        if _contains_mod_content(current):
            break
        subdirs = [d for d in _iter_visible_dirs(current) if d.name.lower() not in _MOD_SKIP_DIRS]
        if len(subdirs) != 1:
            break
        current = subdirs[0]
    return current


def _contains_mod_content(path: Path) -> bool:
    try:
        for child in path.iterdir():
            child_name = child.name.lower()
            if child.is_dir() and child_name in _MOD_CONTENT_DIRS:
                return True
            if child.is_file() and child_name == "config.json":
                return True
    except (PermissionError, OSError):
        return False
    return False


def _pick_mod_target_name(base_dir: Path, resolved_dir: Path) -> str:
    name = resolved_dir.name.strip()
    if not name or name.lower() in _GENERIC_FOLDER_NAMES:
        name = base_dir.name.strip() or "Imported Mod"
    return _sanitize_name(name)


def _sanitize_name(name: str) -> str:
    cleaned = "".join("_" if ch in _INVALID_NAME_CHARS else ch for ch in name)
    cleaned = cleaned.strip().strip(".")
    return cleaned or "Imported Mod"


def _dedupe_sources(items: list[tuple[Path, str]]) -> list[tuple[Path, str]]:
    seen: set[str] = set()
    deduped: list[tuple[Path, str]] = []
    for src, name in items:
        key = _norm_path(src)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((src, name))
    return deduped


def _rename_target_name_for_slot(name: str, source_slot: int, target_slot: int) -> str:
    source_token = f"c{source_slot:02d}"
    target_token = f"c{target_slot:02d}"

    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        return target_token.upper() if token[:1].isupper() else target_token

    updated = re.sub(
        rf"(?i)(?<![a-z0-9]){re.escape(source_token)}(?!\d)",
        repl,
        name,
    )
    return _sanitize_name(updated)


def _build_relative_path_index(mods_path: Path) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    if not mods_path.exists() or not mods_path.is_dir():
        return {}
    for folder in sorted(mods_path.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir() or folder.name.startswith(".") or folder.name.startswith("_"):
            continue
        for file_path in folder.rglob("*"):
            if not file_path.is_file():
                continue
            rel = str(file_path.relative_to(folder)).replace("\\", "/")
            if rel.lower() in _METADATA_FILENAMES:
                continue
            index[rel].append(folder.name)
    return dict(index)


def _collect_support_candidate_paths(src: Path) -> set[str]:
    rels: set[str] = set()
    for file_path in src.rglob("*"):
        if not file_path.is_file():
            continue
        rel = str(file_path.relative_to(src)).replace("\\", "/")
        if _is_support_conflict_candidate(rel):
            rels.add(rel)
    return rels


def _is_support_conflict_candidate(relative_path: str) -> bool:
    rel = relative_path.replace("\\", "/").lower()
    if rel in _METADATA_FILENAMES:
        return False
    return (
        rel.startswith("sound/bank/fighter/")
        or rel.startswith("sound/bank/fighter_voice/")
        or rel.startswith("effect/fighter/")
        or rel.startswith("camera/fighter/")
    )


def _is_voice_file_for_fighter_slot(relative_path: str, fighter: str, slot: int | None = None) -> bool:
    rel = relative_path.replace("\\", "/").lower()
    fighter = str(fighter).lower()
    if not (
        rel.startswith("sound/bank/fighter/")
        or rel.startswith("sound/bank/fighter_voice/")
    ):
        return False
    if f"_{fighter}_" not in rel:
        return False
    if slot is None:
        return True
    return f"_c{int(slot):02d}" in rel


def _is_camera_file_for_fighter_slot(relative_path: str, fighter: str, slot: int | None = None) -> bool:
    rel = relative_path.replace("\\", "/").lower()
    fighter = str(fighter).lower()
    prefix = f"camera/fighter/{fighter}/"
    if not rel.startswith(prefix):
        return False
    if slot is None:
        return True
    return f"/c{int(slot):02d}/" in rel


def _is_effect_file_for_fighter_slot(relative_path: str, fighter: str, slot: int | None = None) -> bool:
    rel = relative_path.replace("\\", "/").lower()
    fighter = str(fighter).lower()
    prefix = f"effect/fighter/{fighter}/"
    if not rel.startswith(prefix):
        return False
    if slot is None:
        return re.search(r"(?i)(?<![a-z0-9])c\d{2,3}(?=[^0-9]|$)", rel) is not None or (
            re.search(r"(?i)(_|/)\d{2}(?=\.|/|_|$)", rel) is not None
        )
    slot_num = f"{int(slot):02d}"
    return (
        f"c{slot_num}" in rel
        or re.search(rf"(?i)(_|/){slot_num}(?=\.|/|_|$)", rel) is not None
    )


def _is_support_file_for_fighter_slot(
    relative_path: str,
    fighter: str,
    support_kind: str,
    slot: int | None = None,
) -> bool:
    normalized_kind = _normalize_support_kind(support_kind)
    if normalized_kind == "voice":
        return _is_voice_file_for_fighter_slot(relative_path, fighter, slot)
    if normalized_kind == "effect":
        return _is_effect_file_for_fighter_slot(relative_path, fighter, slot)
    return _is_camera_file_for_fighter_slot(relative_path, fighter, slot)


def _retarget_voice_relative_path(relative_path: str, source_slot: int, target_slot: int) -> str:
    source_num = f"{int(source_slot):02d}"
    target_num = f"{int(target_slot):02d}"
    return re.sub(
        rf"(?i)_c{source_num}(?=\.|_)",
        f"_c{target_num}",
        relative_path.replace("\\", "/"),
    )


def _retarget_camera_relative_path(relative_path: str, source_slot: int, target_slot: int) -> str:
    return _replace_path_segment_token(
        relative_path.replace("\\", "/"),
        f"c{int(source_slot):02d}",
        f"c{int(target_slot):02d}",
    )


def _retarget_effect_relative_path(relative_path: str, source_slot: int, target_slot: int) -> str:
    source_num = f"{int(source_slot):02d}"
    target_num = f"{int(target_slot):02d}"
    retargeted = re.sub(
        rf"(?i)(?<![a-z0-9])c{source_num}(?=[^0-9]|$)",
        f"c{target_num}",
        relative_path.replace("\\", "/"),
    )
    return re.sub(
        rf"(?i)(_|/){source_num}(?=\.|/|_|$)",
        lambda match: match.group(1) + target_num,
        retargeted,
    )


def _retarget_support_relative_path(
    relative_path: str,
    support_kind: str,
    fighter: str,
    source_slot: int,
    target_slot: int,
) -> str:
    normalized_kind = _normalize_support_kind(support_kind)
    if normalized_kind == "voice":
        return _retarget_voice_relative_path(relative_path, source_slot, target_slot)
    if normalized_kind == "camera":
        return _retarget_camera_relative_path(relative_path, source_slot, target_slot)
    return _retarget_effect_relative_path(relative_path, source_slot, target_slot)


def _replace_path_segment_token(path: str, source_token: str, target_token: str) -> str:
    parts = path.replace("\\", "/").split("/")
    return "/".join(
        target_token if part.lower() == source_token.lower() else part
        for part in parts
    )


def _prune_existing_support_files(
    mods_path: Path,
    mod_name: str,
    relative_paths: list[str],
    summary: ImportSummary,
) -> None:
    mod_root = mods_path / mod_name
    if not mod_root.exists() or not mod_root.is_dir():
        return

    backup_root = mods_path.parent / _SUPPORT_BACKUP_DIR_NAME / mod_name
    removed = 0
    for rel in relative_paths:
        file_path = mod_root / rel
        if not file_path.exists() or not file_path.is_file():
            continue
        backup_path = backup_root / rel
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        if not backup_path.exists():
            shutil.copy2(file_path, backup_path)
        file_path.unlink()
        _prune_empty_parents(file_path.parent, mod_root)
        removed += 1

    if removed == 0:
        return

    summary.support_mod_adjustments += 1
    summary.support_files_pruned += removed
    summary.warnings.append(
        f"Pruned {removed} exact support file(s) from '{mod_name}' so a more specific imported override can win cleanly."
    )

    if not _has_effective_mod_content(mod_root):
        _disable_support_only_mod(mods_path, mod_name, summary)


def _disable_support_only_mod(mods_path: Path, mod_name: str, summary: ImportSummary) -> None:
    src = mods_path / mod_name
    if not src.exists():
        return
    disabled_dir = mods_path.parent / "disabled_mods"
    disabled_dir.mkdir(parents=True, exist_ok=True)
    dest = disabled_dir / mod_name
    suffix = 1
    while dest.exists():
        dest = disabled_dir / f"{mod_name} ({suffix})"
        suffix += 1
    src.rename(dest)
    summary.warnings.append(
        f"Disabled support mod '{mod_name}' after all effective conflicting files were pruned."
    )


def _replace_directory_from_temp(dest: Path, replacement_root: Path) -> None:
    dest = Path(dest)
    replacement_root = Path(replacement_root)
    backup = dest.parent / f"{dest.name}.ssbumm-backup"
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    dest.rename(backup)
    try:
        shutil.move(str(replacement_root), str(dest))
        shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        if backup.exists():
            backup.rename(dest)
        raise


def _has_effective_mod_content(mod_root: Path) -> bool:
    try:
        for file_path in mod_root.rglob("*"):
            if not file_path.is_file():
                continue
            rel = str(file_path.relative_to(mod_root)).replace("\\", "/").lower()
            if rel in _METADATA_FILENAMES:
                continue
            return True
    except (PermissionError, OSError):
        return True
    return False


def _prune_empty_parents(path: Path, stop_at: Path) -> None:
    current = path
    stop_at = stop_at.resolve()
    while True:
        try:
            resolved = current.resolve()
        except OSError:
            break
        if resolved == stop_at:
            break
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _candidate_roots(source_dir: Path) -> list[Path]:
    roots = [source_dir]
    current = source_dir
    for _ in range(4):
        children = [d for d in _iter_visible_dirs(current)]
        if len(children) != 1:
            break
        current = children[0]
        roots.append(current)
    # de-duplicate while preserving order
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = _norm_path(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


def _looks_like_title_id(name: str) -> bool:
    return len(name) == 16 and all(c in "0123456789abcdefABCDEF" for c in name)


def _is_plugin_binary(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith(".nro") or lowered.endswith(".nro.disabled")


def _normalize_plugin_binary_name(name: str) -> tuple[str, bool]:
    """Return `(normalized_name, is_disabled_plugin)` for plugin binaries."""
    lowered = name.lower()
    if lowered.endswith(".nro.disabled"):
        return name[:-len(".disabled")], True
    return name, False


def _iter_visible_dirs(path: Path):
    try:
        for child in path.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                yield child
    except (PermissionError, OSError):
        return


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _count_files(path: Path) -> int:
    count = 0
    try:
        for child in path.rglob("*"):
            if child.is_file():
                count += 1
    except (PermissionError, OSError):
        pass
    return count


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def _is_descendant(path: Path, parent: Path) -> bool:
    try:
        resolved_path = path.resolve()
        resolved_parent = parent.resolve()
        return resolved_path == resolved_parent or resolved_parent in resolved_path.parents
    except OSError:
        return False


def _norm_path(path: Path) -> str:
    try:
        return str(path.resolve()).lower()
    except OSError:
        return str(path).lower()
