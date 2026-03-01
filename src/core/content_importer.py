"""Import helpers for mods and plugins."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import json
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
    iter_slot_matches,
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
_INSTALLED_REPAIR_BACKUP_DIR_NAME = "_installed_repair"
_METADATA_FILENAMES = {
    "config.json",
    "config.txt",
    "info.toml",
    "preview.webp",
    "preview.png",
    "preview.jpg",
    "preview.jpeg",
    "readme.txt",
    "readme.md",
}
_NON_EFFECTIVE_SUPPORT_LEFTOVERS = {
    "ui/message/msg_name.xmsbt",
    "ui/message/msg_name.msbt",
    "ui/param/database/ui_chara_db.prcxml",
    "ui/param/database/ui_chara_db.prc",
}
_MERGE_SAFE_EXACT_OVERLAP_PATHS = {
    "ui/message/msg_name.xmsbt",
    "ui/message/msg_name.msbt",
    "ui/param/database/ui_chara_db.prcxml",
    "ui/param/database/ui_chara_db.prc",
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
_UI_CHARA_PORTRAIT_RE = re.compile(
    r"^ui/(?P<replace_kind>replace|replace_patch)/chara/chara_(?P<size>\d)/(?P<filename>[^/]+)_(?P<fighter>[^_/]+)_(?P<slot>\d{2})\.bntx$",
    re.IGNORECASE,
)
_REQUIRED_UI_PORTRAIT_SIZES = (0, 1, 2, 3, 4, 5, 6, 7)
_UI_PORTRAIT_FALLBACK_ORDER = {
    0: (1, 2, 3, 4, 5, 6, 7),
    1: (0, 2, 3, 4, 5, 6, 7),
    2: (1, 0, 3, 4, 5, 6, 7),
    3: (4, 2, 1, 5, 0, 6, 7),
    4: (3, 5, 2, 1, 6, 0, 7),
    5: (4, 6, 3, 7, 2, 1, 0),
    6: (7, 5, 4, 3, 2, 1, 0),
    7: (6, 5, 4, 3, 2, 1, 0),
}


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
    manifest_repairs: int = 0
    ui_portrait_repairs: int = 0
    identical_files_pruned: int = 0
    remaining_exact_overlaps: int = 0
    skipped_items: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class InstalledModsRepairSummary:
    mods_scanned: int = 0
    mods_changed: int = 0
    flattened_mods: int = 0
    configs_normalized: int = 0
    configs_created: int = 0
    configs_updated: int = 0
    ui_portrait_repairs: int = 0
    support_mod_adjustments: int = 0
    support_files_pruned: int = 0
    identical_files_pruned: int = 0
    resolved_exact_overlaps: int = 0
    remaining_exact_overlaps: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class SupportPackScopeInfo:
    support_kind: str
    fighter: str
    source_slots: list[int] = field(default_factory=list)
    recommended_source_slot: int = 0
    visual_slots: list[int] = field(default_factory=list)
    slot_labels: dict[int, str] = field(default_factory=dict)


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
    requested_label: str = ""
    conflicting_mod_descriptions: dict[str, str] = field(default_factory=dict)
    open_slot_descriptions: dict[int, str] = field(default_factory=dict)


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
    config_source_dir: Path | None = None
    config_source_fighter: str | None = None
    config_source_slot: int | None = None
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
    labels = resolve_mod_slot_labels(mod_path, fighter_support_slots, analysis=analysis)
    fighter_labels = {
        slot: label
        for (label_fighter, slot), label in labels.items()
        if label_fighter == fighter
    }

    return SupportPackScopeInfo(
        support_kind=normalized_kind,
        fighter=fighter,
        source_slots=source_slots,
        recommended_source_slot=recommended,
        visual_slots=list(analysis.visual_fighter_slots.get(fighter, [])),
        slot_labels=fighter_labels,
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
    imported_mod_names: set[str] = set()

    try:
        for prepared in prepared_sources:
            src = prepared.source_dir
            target_name = prepared.target_name
            analysis = prepared.analysis
            config_source_dir = prepared.config_source_dir or prepared.source_dir
            config_source_fighter = prepared.config_source_fighter
            config_source_slot = prepared.config_source_slot
            final_fighter: str | None = None
            final_slot: int | None = None

            if analysis.has_visual_skin_slot:
                fighter = str(analysis.primary_fighter)
                source_slot = int(analysis.primary_slot)
                target_slot = source_slot
                final_fighter = fighter
                final_slot = target_slot
                source_display_name = _resolve_visual_slot_display_name(
                    src,
                    fighter,
                    source_slot,
                    analysis=analysis,
                    fallback_name=target_name,
                )
                source_slot_text = _format_visual_slot_reference(fighter, source_slot, source_display_name)
                conflicting_mods = [
                    mod_name
                    for mod_name in slot_index.get(fighter, {}).get(source_slot, [])
                    if mod_name != target_name
                ]
                if conflicting_mods:
                    open_slots = _available_base_slots(slot_index, fighter)
                    conflicting_mod_descriptions = {
                        mod_name: _describe_installed_visual_slot(mods_path, mod_name, fighter, source_slot)
                        for mod_name in conflicting_mods
                    }
                    conflict = SlotConflictInfo(
                        mod_name=target_name,
                        fighter=fighter,
                        requested_slot=source_slot,
                        conflicting_mods=conflicting_mods,
                        open_slots=open_slots,
                        requested_label=source_slot_text,
                        conflicting_mod_descriptions=conflicting_mod_descriptions,
                        open_slot_descriptions={
                            slot: _format_open_visual_slot_reference(slot)
                            for slot in open_slots
                        },
                    )
                    action = _resolve_slot_conflict(conflict, slot_conflict_resolver)

                    if action == "replace":
                        for mod_name in conflicting_mods:
                            _disable_conflicting_mod(
                                mods_path,
                                mod_name,
                                summary,
                                source_slot_text,
                                conflicting_mod_descriptions.get(mod_name),
                            )
                        slot_index.setdefault(fighter, {}).pop(source_slot, None)
                    elif action == "move_existing":
                        if len(conflicting_mods) != 1 or not open_slots:
                            summary.skipped_items.append(
                                f"{target_name} ({source_slot_text})"
                            )
                            summary.warnings.append(
                                f"Skipped '{target_name}' because {source_slot_text} "
                                "was occupied and the existing mod could not be moved safely."
                            )
                            continue
                        existing_mod_name = conflicting_mods[0]
                        target_open_slot = choose_open_target_slot(fighter, source_slot, open_slots)
                        if target_open_slot is None:
                            summary.skipped_items.append(
                                f"{target_name} ({source_slot_text})"
                            )
                            summary.warnings.append(
                                f"Skipped '{target_name}' because {source_slot_text} "
                                "was occupied and no open replacement slot was available."
                            )
                            continue
                        _move_installed_mod_to_open_slot(
                            mods_path,
                            existing_mod_name,
                            fighter,
                            source_slot,
                            target_open_slot,
                            summary,
                        )
                        slot_index.setdefault(fighter, {}).pop(source_slot, None)
                        slot_index.setdefault(fighter, {}).setdefault(target_open_slot, []).append(existing_mod_name)
                    elif action == "move_incoming":
                        target_open_slot = choose_open_target_slot(fighter, source_slot, open_slots)
                        if target_open_slot is None:
                            summary.skipped_items.append(
                                f"{target_name} ({source_slot_text})"
                            )
                            summary.warnings.append(
                                f"Skipped '{target_name}' because {source_slot_text} "
                                "was occupied and no open base slot remained."
                            )
                            continue
                        target_slot = target_open_slot
                    else:
                        summary.skipped_items.append(
                            f"{target_name} ({source_slot_text})"
                        )
                        summary.warnings.append(
                            f"Skipped '{target_name}' because {source_slot_text} "
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
                    target_slot_text = _format_visual_slot_reference(
                        fighter,
                        target_slot,
                        source_display_name,
                    )
                    summary.warnings.append(
                        f"Imported '{target_name}' as {target_slot_text} "
                        f"instead of {source_slot_text} to avoid a slot overlap."
                    )
                final_slot = target_slot

            _resolve_support_path_conflicts(src, target_name, mods_path, summary)

            dest = mods_path / target_name
            if _same_path(src, dest):
                summary.warnings.append(f"Skipped '{target_name}' (already in mods folder).")
                continue

            _copy_dir_replace(src, dest, summary)
            summary.items_imported += 1
            summary.files_copied += _count_files(dest)
            imported_mod_names.add(target_name)

            _repair_imported_mod_metadata(
                dest,
                config_source_dir=config_source_dir,
                fighter=final_fighter or config_source_fighter,
                source_slot=config_source_slot,
                target_slot=final_slot,
            )

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

    if imported_mod_names:
        repair_summary = repair_installed_mods(
            mods_path,
            focus_mod_names=imported_mod_names,
            include_disabled=False,
        )
        summary.support_mod_adjustments += repair_summary.support_mod_adjustments
        summary.support_files_pruned += repair_summary.support_files_pruned
        summary.manifest_repairs += (
            repair_summary.configs_normalized
            + repair_summary.configs_created
            + repair_summary.configs_updated
        )
        summary.ui_portrait_repairs += repair_summary.ui_portrait_repairs
        summary.identical_files_pruned += repair_summary.identical_files_pruned
        summary.remaining_exact_overlaps += repair_summary.remaining_exact_overlaps
        summary.warnings.extend(repair_summary.warnings)

    if summary.items_imported > 0:
        _invalidate_arcropolis_mod_cache(mods_path)

    if summary.items_imported == 0:
        skipped = ", ".join(summary.skipped_items[:5]) if summary.skipped_items else ""
        if skipped:
            raise ValueError(f"Nothing was imported. Skipped items: {skipped}")
        raise ValueError("Nothing was imported. The selected folder may already be in use.")
    return summary


def repair_installed_mods(
    mods_path: Path,
    focus_mod_names: set[str] | None = None,
    include_disabled: bool = True,
) -> InstalledModsRepairSummary:
    mods_path = Path(mods_path)
    summary = InstalledModsRepairSummary()
    if not mods_path.exists() or not mods_path.is_dir():
        return summary

    focus_names = {str(name) for name in (focus_mod_names or set()) if str(name)}
    changed_mods: set[str] = set()

    for mod_root in _iter_repair_mod_roots(mods_path, include_disabled=include_disabled):
        should_repair_root = not focus_names or mod_root.name in focus_names
        summary.mods_scanned += 1
        if not should_repair_root:
            continue

        config_txt = mod_root / "config.txt"
        config_json = mod_root / "config.json"
        before_txt_exists = config_txt.exists()
        before_json_exists = config_json.exists()
        before_payload = _load_optional_mod_config(mod_root)
        before_payload_text = json.dumps(before_payload, sort_keys=True) if before_payload is not None else None

        if _flatten_nested_mod(mod_root):
            summary.flattened_mods += 1
            changed_mods.add(mod_root.name)

        analysis = analyze_mod_directory(mod_root, [mod_root.name])
        fighter = str(analysis.primary_fighter) if analysis.has_visual_skin_slot and analysis.primary_fighter else None
        slot = int(analysis.primary_slot) if analysis.has_visual_skin_slot and analysis.primary_slot is not None else None
        _repair_imported_mod_metadata(
            mod_root,
            fighter=fighter,
            source_slot=slot,
            target_slot=slot,
        )

        after_txt_exists = (mod_root / "config.txt").exists()
        after_json_exists = (mod_root / "config.json").exists()
        after_payload = _load_optional_mod_config(mod_root)
        after_payload_text = json.dumps(after_payload, sort_keys=True) if after_payload is not None else None

        if before_txt_exists and not after_txt_exists and after_json_exists:
            summary.configs_normalized += 1
            changed_mods.add(mod_root.name)
        if not before_json_exists and not before_txt_exists and after_json_exists:
            summary.configs_created += 1
            changed_mods.add(mod_root.name)
        if before_payload_text is not None and after_payload_text is not None and before_payload_text != after_payload_text:
            summary.configs_updated += 1
            changed_mods.add(mod_root.name)
        elif before_payload_text is None and before_json_exists and after_payload_text is not None:
            summary.configs_updated += 1
            changed_mods.add(mod_root.name)

        portrait_repairs = _repair_missing_ui_portraits(mod_root)
        if portrait_repairs:
            summary.ui_portrait_repairs += portrait_repairs
            changed_mods.add(mod_root.name)

    _resolve_installed_exact_overlaps(
        mods_path,
        summary,
        focus_mod_names=focus_names or None,
    )
    summary.mods_changed = len(changed_mods)
    if summary.mods_changed or summary.resolved_exact_overlaps or summary.support_files_pruned:
        _invalidate_arcropolis_mod_cache(mods_path)
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
                        config_source_dir=source_dir,
                        config_source_fighter=str(fighter),
                        config_source_slot=int(slot),
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
                config_source_dir=source_dir,
                config_source_fighter=str(analysis.primary_fighter) if analysis.primary_fighter else None,
                config_source_slot=int(analysis.primary_slot) if analysis.primary_slot is not None else None,
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
                config_source_dir=source_dir,
                config_source_fighter=str(option.fighter),
                config_source_slot=int(option.slot),
                temp_paths=[*base_temp_paths, variant_temp],
            )
        )


def _build_multi_slot_pack_options(
    source_dir: Path,
    analysis: SlotAnalysis,
) -> list[MultiSlotPackOption]:
    options: list[MultiSlotPackOption] = []
    friendly_labels = resolve_mod_slot_labels(source_dir, analysis.visual_fighter_slots, analysis=analysis)
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


def resolve_mod_slot_labels(
    mod_path: Path,
    fighter_slots: dict[str, list[int]] | dict[str, set[int]] | None = None,
    analysis: SlotAnalysis | None = None,
) -> dict[tuple[str, int], str]:
    mod_path = Path(mod_path)
    resolved_analysis = analysis or analyze_mod_directory(mod_path, [mod_path.name])
    slot_scope = fighter_slots if fighter_slots is not None else (
        resolved_analysis.visual_fighter_slots or resolved_analysis.fighter_slots
    )
    normalized_slots = {
        str(fighter).lower(): {int(slot) for slot in slots}
        for fighter, slots in slot_scope.items()
        if slots
    }
    if not normalized_slots:
        return {}

    labels = _extract_multi_slot_names_from_msg_name(mod_path, normalized_slots)
    if len(normalized_slots) == 1:
        for key, value in _extract_multi_slot_names_from_ui_chara_db(mod_path, normalized_slots).items():
            labels.setdefault(key, value)
    return labels


def _resolve_visual_slot_display_name(
    mod_path: Path,
    fighter: str,
    slot: int,
    analysis: SlotAnalysis | None = None,
    fallback_name: str | None = None,
) -> str | None:
    fighter_name = str(fighter).lower()
    resolved_analysis = analysis or analyze_mod_directory(Path(mod_path), [Path(mod_path).name])
    labels = resolve_mod_slot_labels(
        mod_path,
        {fighter_name: [int(slot)]},
        analysis=resolved_analysis,
    )
    display_name = labels.get((fighter_name, int(slot)))
    if display_name:
        return display_name

    if fallback_name and len(resolved_analysis.visual_fighter_slots) == 1:
        slots = resolved_analysis.visual_fighter_slots.get(fighter_name, [])
        if len(slots) == 1 and int(slots[0]) == int(slot):
            return str(fallback_name).strip() or None
    return None


def _format_visual_slot_reference(fighter: str, slot: int, display_name: str | None = None) -> str:
    fighter_name = str(fighter).lower()
    slot_token = f"{fighter_name} c{int(slot):02d}"
    clean_name = str(display_name or "").strip()
    if not clean_name:
        return slot_token
    return f"{clean_name} ({slot_token})"


def _format_open_visual_slot_reference(slot: int) -> str:
    return f"Open default slot (c{int(slot):02d})"


def _describe_installed_visual_slot(mods_path: Path, mod_name: str, fighter: str, slot: int) -> str:
    mod_path = Path(mods_path) / mod_name
    if not mod_path.exists():
        return _format_visual_slot_reference(fighter, slot)
    display_name = _resolve_visual_slot_display_name(
        mod_path,
        fighter,
        slot,
        fallback_name=mod_name,
    )
    return _format_visual_slot_reference(fighter, slot, display_name)


def _describe_slot_targets_from_paths(mod_root: Path, relative_paths: list[str], fallback_name: str | None = None) -> list[str]:
    slot_map: dict[str, set[int]] = defaultdict(set)
    for rel in relative_paths:
        for fighter, slot in iter_slot_matches(rel):
            slot_map[str(fighter).lower()].add(int(slot))
    if not slot_map:
        return []

    analysis = analyze_mod_directory(mod_root, [mod_root.name])
    labels = resolve_mod_slot_labels(mod_root, slot_map, analysis=analysis)
    descriptions: list[str] = []
    single_target = sum(len(slots) for slots in slot_map.values()) == 1
    for fighter, slots in sorted(slot_map.items()):
        for slot in sorted(slots):
            fallback = fallback_name if single_target else None
            display_name = labels.get((fighter, slot))
            if not display_name and fallback:
                display_name = str(fallback).strip() or None
            descriptions.append(_format_visual_slot_reference(fighter, slot, display_name))
    return descriptions


def _format_slot_description_list(descriptions: list[str], max_items: int = 3) -> str:
    cleaned = [str(item).strip() for item in descriptions if str(item).strip()]
    if not cleaned:
        return ""
    if len(cleaned) <= max_items:
        return ", ".join(cleaned)
    shown = ", ".join(cleaned[:max_items])
    return f"{shown}, and {len(cleaned) - max_items} more"


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


def _disable_conflicting_mod(
    mods_path: Path,
    mod_name: str,
    summary: ImportSummary,
    requested_slot_text: str,
    existing_slot_text: str | None = None,
) -> None:
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
    if existing_slot_text and existing_slot_text != requested_slot_text:
        detail = f"{existing_slot_text} so '{requested_slot_text}' could take that slot"
    else:
        detail = f"{requested_slot_text} could be replaced"
    summary.warnings.append(
        f"Disabled existing mod '{mod_name}' so {detail}."
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
    slot_display_name = _resolve_visual_slot_display_name(
        src,
        fighter,
        source_slot,
        fallback_name=mod_name,
    )

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
    source_slot_text = _format_visual_slot_reference(fighter, source_slot, slot_display_name)
    target_slot_text = _format_visual_slot_reference(fighter, target_slot, slot_display_name)
    summary.warnings.append(
        f"Moved existing mod '{mod_name}' from {source_slot_text} to {target_slot_text}."
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


def _iter_repair_mod_roots(mods_path: Path, include_disabled: bool = True) -> list[Path]:
    roots: list[Path] = []
    for folder in sorted(mods_path.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir() or folder.name.startswith("_") or folder.name.startswith("."):
            continue
        roots.append(folder)

    if include_disabled:
        disabled_dir = mods_path.parent / "disabled_mods"
        if disabled_dir.exists() and disabled_dir.is_dir():
            for folder in sorted(disabled_dir.iterdir(), key=lambda p: p.name.lower()):
                if folder.is_dir():
                    roots.append(folder)

        legacy_disabled = mods_path / ".disabled"
        if legacy_disabled.exists() and legacy_disabled.is_dir():
            for folder in sorted(legacy_disabled.iterdir(), key=lambda p: p.name.lower()):
                if folder.is_dir():
                    roots.append(folder)
    return roots


def _build_active_file_occurrences(
    mods_path: Path,
    focus_mod_names: set[str] | None = None,
) -> dict[str, list[tuple[str, Path]]]:
    occurrences: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    focus_names = {str(name) for name in (focus_mod_names or set()) if str(name)}
    if not mods_path.exists() or not mods_path.is_dir():
        return {}
    for folder in sorted(mods_path.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir() or folder.name.startswith("_") or folder.name.startswith("."):
            continue
        for file_path in folder.rglob("*"):
            if not file_path.is_file():
                continue
            rel = str(file_path.relative_to(folder)).replace("\\", "/")
            if rel.lower() in _METADATA_FILENAMES:
                continue
            if rel.lower() in _MERGE_SAFE_EXACT_OVERLAP_PATHS:
                continue
            occurrences[rel].append((folder.name, file_path))
    if not focus_names:
        return dict(occurrences)
    return {
        rel: items
        for rel, items in occurrences.items()
        if any(name in focus_names for name, _path in items)
    }


def _resolve_installed_exact_overlaps(
    mods_path: Path,
    summary: InstalledModsRepairSummary,
    focus_mod_names: set[str] | None = None,
) -> None:
    occurrences_by_rel = _build_active_file_occurrences(mods_path, focus_mod_names=focus_mod_names)
    if not occurrences_by_rel:
        return

    analysis_cache: dict[str, SlotAnalysis] = {}
    hash_cache: dict[str, str] = {}

    for rel in sorted(occurrences_by_rel):
        current = _existing_occurrences_for_rel(mods_path, rel, occurrences_by_rel[rel])
        if len(current) < 2:
            continue

        if _is_support_conflict_candidate(rel):
            focus_visual_mods: list[str] = []
            visual_mods: list[str] = []
            support_only_mods: list[str] = []
            for mod_name, _file_path in current:
                analysis = _cached_mod_analysis(mods_path, mod_name, analysis_cache)
                if analysis.has_visual_skin_slot:
                    visual_mods.append(mod_name)
                    if focus_mod_names and mod_name in focus_mod_names:
                        focus_visual_mods.append(mod_name)
                else:
                    support_only_mods.append(mod_name)
            prunable_support_mods: list[str] = []
            if focus_visual_mods:
                prunable_support_mods = [
                    mod_name for mod_name in support_only_mods
                    if not focus_mod_names or mod_name not in focus_mod_names
                ]
            elif visual_mods and support_only_mods and not focus_mod_names:
                prunable_support_mods = [
                    mod_name
                    for mod_name in support_only_mods
                    if _is_broad_support_only_mod(mods_path, mod_name, rel, analysis_cache)
                ]
            if prunable_support_mods:
                removed_any = False
                for mod_name in sorted(set(prunable_support_mods)):
                    removed_any = _prune_existing_support_files(mods_path, mod_name, [rel], summary) or removed_any
                if removed_any:
                    summary.resolved_exact_overlaps += 1
                current = _existing_occurrences_for_rel(mods_path, rel, current)
                if len(current) < 2:
                    continue

        if _all_occurrence_files_identical(current, hash_cache):
            kept_mod = _choose_overlap_winner(
                mods_path,
                current,
                focus_mod_names=focus_mod_names,
                analysis_cache=analysis_cache,
            )
            pruned = 0
            for mod_name, _file_path in current:
                if mod_name == kept_mod:
                    continue
                if _backup_and_remove_installed_overlap_file(mods_path, mod_name, rel):
                    pruned += 1
            if pruned:
                summary.identical_files_pruned += pruned
                summary.resolved_exact_overlaps += 1
                summary.warnings.append(
                    f"Deduped {pruned} byte-identical exact overlap file(s) for '{rel}' and kept "
                    f"'{kept_mod}' as the active copy. Backups were saved under "
                    f"'{_SUPPORT_BACKUP_DIR_NAME}/{_INSTALLED_REPAIR_BACKUP_DIR_NAME}/'."
                )
            continue

        summary.remaining_exact_overlaps += 1
        summary.warnings.append(
            f"Remaining exact overlap for '{rel}' across {', '.join(name for name, _path in current[:4])}"
            f"{'...' if len(current) > 4 else ''}. Automatic repair skipped because the files differ."
        )


def _existing_occurrences_for_rel(
    mods_path: Path,
    relative_path: str,
    occurrences: list[tuple[str, Path]],
) -> list[tuple[str, Path]]:
    current: list[tuple[str, Path]] = []
    for mod_name, file_path in occurrences:
        candidate = mods_path / mod_name / relative_path
        if candidate.exists() and candidate.is_file():
            current.append((mod_name, candidate))
        elif file_path.exists() and file_path.is_file():
            current.append((mod_name, file_path))
    return current


def _cached_mod_analysis(
    mods_path: Path,
    mod_name: str,
    analysis_cache: dict[str, SlotAnalysis],
) -> SlotAnalysis:
    cached = analysis_cache.get(mod_name)
    if cached is not None:
        return cached
    mod_root = mods_path / mod_name
    analysis = analyze_mod_directory(mod_root, [mod_name])
    analysis_cache[mod_name] = analysis
    return analysis


def _all_occurrence_files_identical(
    occurrences: list[tuple[str, Path]],
    hash_cache: dict[str, str],
) -> bool:
    if len(occurrences) < 2:
        return False
    digests = {
        _hash_file_sha256(path, hash_cache)
        for _mod_name, path in occurrences
    }
    return len(digests) == 1


def _hash_file_sha256(path: Path, cache: dict[str, str]) -> str:
    key = _norm_path(path)
    cached = cache.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    cache[key] = digest
    return digest


def _choose_overlap_winner(
    mods_path: Path,
    occurrences: list[tuple[str, Path]],
    focus_mod_names: set[str] | None,
    analysis_cache: dict[str, SlotAnalysis],
) -> str:
    focus_names = {str(name) for name in (focus_mod_names or set()) if str(name)}

    def rank(item: tuple[str, Path]) -> tuple[int, int, str]:
        mod_name, _path = item
        analysis = _cached_mod_analysis(mods_path, mod_name, analysis_cache)
        return (
            0 if mod_name in focus_names else 1,
            0 if analysis.has_visual_skin_slot else 1,
            mod_name.lower(),
        )

    return min(occurrences, key=rank)[0]


def _backup_and_remove_installed_overlap_file(mods_path: Path, mod_name: str, relative_path: str) -> bool:
    mod_root = mods_path / mod_name
    file_path = mod_root / relative_path
    if not file_path.exists() or not file_path.is_file():
        return False
    backup_root = mods_path.parent / _SUPPORT_BACKUP_DIR_NAME / _INSTALLED_REPAIR_BACKUP_DIR_NAME / mod_name
    backup_path = backup_root / relative_path
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if not backup_path.exists():
        shutil.copy2(file_path, backup_path)
    file_path.unlink()
    _prune_empty_parents(file_path.parent, mod_root)
    return True


def _repair_missing_ui_portraits(mod_root: Path) -> int:
    portrait_map = _collect_ui_portrait_paths(mod_root)
    created = 0
    for key, size_map in portrait_map.items():
        for target_size in _REQUIRED_UI_PORTRAIT_SIZES:
            if target_size in size_map:
                continue
            source_size = _choose_ui_portrait_fallback_size(size_map, target_size)
            if source_size is None:
                continue
            source_path = size_map[source_size]
            dest_path = _retarget_ui_portrait_path(source_path, source_size, target_size)
            if dest_path.exists():
                size_map[target_size] = dest_path
                continue
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, dest_path)
            size_map[target_size] = dest_path
            created += 1
    return created


def _invalidate_arcropolis_mod_cache(mods_path: Path) -> None:
    arcropolis_root = Path(mods_path).parent / "arcropolis"
    if not arcropolis_root.exists() or not arcropolis_root.is_dir():
        return
    conflicts_path = arcropolis_root / "conflicts.json"
    if conflicts_path.exists():
        try:
            conflicts_path.unlink()
        except OSError:
            pass
    for cache_path in arcropolis_root.rglob("mod_cache"):
        try:
            if cache_path.is_file():
                cache_path.unlink()
        except OSError:
            continue


def _collect_ui_portrait_paths(mod_root: Path) -> dict[tuple[str, int, str], dict[int, Path]]:
    portrait_map: dict[tuple[str, int, str], dict[int, Path]] = defaultdict(dict)
    for file_path in mod_root.rglob("*.bntx"):
        if not file_path.is_file():
            continue
        rel = str(file_path.relative_to(mod_root)).replace("\\", "/")
        match = _UI_CHARA_PORTRAIT_RE.match(rel)
        if match is None:
            continue
        key = (
            str(match.group("fighter")).lower(),
            int(match.group("slot")),
            str(match.group("replace_kind")).lower(),
        )
        portrait_map[key][int(match.group("size"))] = file_path
    return portrait_map


def _choose_ui_portrait_fallback_size(size_map: dict[int, Path], target_size: int) -> int | None:
    for candidate in _UI_PORTRAIT_FALLBACK_ORDER.get(int(target_size), ()):
        if candidate in size_map:
            return candidate
    available = sorted(size_map.keys())
    return available[0] if available else None


def _retarget_ui_portrait_path(source_path: Path, source_size: int, target_size: int) -> Path:
    source_text = f"chara_{int(source_size)}"
    target_text = f"chara_{int(target_size)}"
    rel = str(source_path).replace("\\", "/")
    rel = rel.replace(f"/{source_text}/", f"/{target_text}/")
    rel = rel.replace(f"{source_text}_", f"{target_text}_")
    return Path(rel)


def _is_broad_support_only_mod(
    mods_path: Path,
    mod_name: str,
    relative_path: str,
    analysis_cache: dict[str, SlotAnalysis],
) -> bool:
    support_kind = _support_kind_from_relative_path(relative_path)
    if support_kind is None:
        return False
    info = inspect_mod_support_pack(mods_path / mod_name, support_kind)
    return info is not None and len(info.source_slots) > 1


def _support_kind_from_relative_path(relative_path: str) -> str | None:
    rel = relative_path.replace("\\", "/").lower()
    if rel.startswith("sound/bank/fighter/") or rel.startswith("sound/bank/fighter_voice/"):
        return "voice"
    if rel.startswith("effect/fighter/"):
        return "effect"
    if rel.startswith("camera/fighter/"):
        return "camera"
    return None


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


def _repair_imported_mod_metadata(
    dest_root: Path,
    config_source_dir: Path | None = None,
    fighter: str | None = None,
    source_slot: int | None = None,
    target_slot: int | None = None,
) -> None:
    dest_root = Path(dest_root)
    _normalize_legacy_config_filename(dest_root)
    existing_config = _load_optional_mod_config(dest_root)

    normalized_fighter = str(fighter or "").lower().strip() or None
    if normalized_fighter is None or source_slot is None or target_slot is None:
        if existing_config is not None:
            sanitized_config = _sanitize_config_payload_paths(dest_root, existing_config)
            if sanitized_config != existing_config or not (dest_root / "config.json").exists():
                _write_config_json(dest_root / "config.json", sanitized_config)
        if not (dest_root / "config.json").exists():
            fallback = _build_minimal_slot_effect_config(dest_root)
            if fallback is not None:
                _write_config_json(dest_root / "config.json", fallback)
        return

    if existing_config is not None and int(source_slot) == int(target_slot):
        if _config_payload_has_existing_files(dest_root, existing_config):
            return

    source_config = _load_optional_mod_config(Path(config_source_dir or dest_root))
    repaired = None
    if source_config is not None:
        repaired = _build_repaired_visual_slot_config(
            dest_root,
            source_config,
            normalized_fighter,
            int(source_slot),
            int(target_slot),
        )
    if repaired is None:
        repaired = _build_minimal_slot_effect_config(dest_root, normalized_fighter, int(target_slot))
    if repaired is not None:
        _write_config_json(dest_root / "config.json", _sanitize_config_payload_paths(dest_root, repaired))


def _normalize_legacy_config_filename(mod_root: Path) -> None:
    config_json = mod_root / "config.json"
    config_txt = mod_root / "config.txt"
    if config_json.exists() or not config_txt.exists():
        return
    try:
        json.loads(config_txt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    config_txt.rename(config_json)


def _load_optional_mod_config(mod_root: Path) -> dict | None:
    for filename in ("config.json", "config.txt"):
        config_path = Path(mod_root) / filename
        if not config_path.is_file():
            continue
        try:
            parsed = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _write_config_json(config_path: Path, payload: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")


def _sanitize_config_payload_paths(mod_root: Path, payload: dict) -> dict:
    sanitized: dict[str, object] = {}
    for key, value in payload.items():
        if key not in {
            "new-dir-files",
            "new_dir_files",
            "share-to-vanilla",
            "share_to_vanilla",
            "share-to-added",
            "share_to_added",
        } or not isinstance(value, dict):
            sanitized[key] = value
            continue

        sanitized_section: dict[str, list[str]] = {}
        for alias, values in value.items():
            alias_text = str(alias or "").replace("\\", "/")
            if not isinstance(values, list):
                continue
            filtered_values: list[str] = []
            seen: set[str] = set()
            for item in values:
                rel = str(item or "").replace("\\", "/").strip()
                if not rel or rel in seen:
                    continue
                if (Path(mod_root) / rel).exists():
                    filtered_values.append(rel)
                    seen.add(rel)
            if filtered_values or len(values) == 0:
                sanitized_section[alias_text] = filtered_values
        sanitized[key] = sanitized_section
    return sanitized


def _config_payload_has_existing_files(mod_root: Path, payload: dict) -> bool:
    found_any = False
    for key in (
        "new-dir-files",
        "new_dir_files",
        "share-to-vanilla",
        "share_to_vanilla",
        "share-to-added",
        "share_to_added",
    ):
        section = payload.get(key)
        if not isinstance(section, dict):
            continue
        for values in section.values():
            if not isinstance(values, list):
                continue
            for item in values:
                rel = str(item or "").replace("\\", "/").strip()
                if not rel:
                    continue
                found_any = True
                if not (Path(mod_root) / rel).exists():
                    return False
    return found_any


def _build_repaired_visual_slot_config(
    dest_root: Path,
    source_config: dict,
    fighter: str,
    source_slot: int,
    target_slot: int,
) -> dict | None:
    repaired: dict[str, object] = {}

    source_new_dir = (
        source_config.get("new-dir-files")
        if isinstance(source_config.get("new-dir-files"), dict)
        else source_config.get("new_dir_files")
        if isinstance(source_config.get("new_dir_files"), dict)
        else {}
    )
    repaired_new_dir = _repair_config_new_dir_files(
        dest_root,
        source_new_dir,
        fighter,
        source_slot,
        target_slot,
    )
    if repaired_new_dir:
        key_name = "new-dir-files" if "new-dir-files" in source_config else "new_dir_files"
        repaired[key_name] = repaired_new_dir

    for source_key, repaired_key in (
        ("share-to-vanilla", "share-to-vanilla"),
        ("share_to_vanilla", "share_to_vanilla"),
        ("share-to-added", "share-to-added"),
        ("share_to_added", "share_to_added"),
    ):
        section = source_config.get(source_key)
        if not isinstance(section, dict):
            continue
        repaired_section = _repair_config_alias_map(
            dest_root,
            section,
            fighter,
            source_slot,
            target_slot,
        )
        if repaired_section:
            repaired[repaired_key] = repaired_section

    return repaired or None


def _repair_config_new_dir_files(
    dest_root: Path,
    section: dict,
    fighter: str,
    source_slot: int,
    target_slot: int,
) -> dict[str, list[str]]:
    repaired: dict[str, list[str]] = {}
    for key, values in section.items():
        key_text = str(key or "").replace("\\", "/")
        if not _config_path_targets_slot(key_text, fighter, source_slot):
            continue
        new_key = _retarget_visual_config_path(key_text, fighter, source_slot, target_slot)
        repaired_values = _repair_config_value_list(
            dest_root,
            values,
            fighter,
            source_slot,
            target_slot,
        )
        if repaired_values:
            repaired[new_key] = repaired_values
    return repaired


def _repair_config_alias_map(
    dest_root: Path,
    section: dict,
    fighter: str,
    source_slot: int,
    target_slot: int,
) -> dict[str, list[str]]:
    repaired: dict[str, list[str]] = {}
    for key, values in section.items():
        key_text = _retarget_visual_config_path(str(key or "").replace("\\", "/"), fighter, source_slot, target_slot)
        repaired_values = _repair_config_value_list(
            dest_root,
            values,
            fighter,
            source_slot,
            target_slot,
        )
        if repaired_values:
            repaired[key_text] = repaired_values
    return repaired


def _repair_config_value_list(
    dest_root: Path,
    values: object,
    fighter: str,
    source_slot: int,
    target_slot: int,
) -> list[str]:
    repaired: list[str] = []
    seen: set[str] = set()
    for item in values if isinstance(values, list) else []:
        path_text = _retarget_visual_config_path(str(item or "").replace("\\", "/"), fighter, source_slot, target_slot)
        if not path_text or path_text in seen:
            continue
        if _ensure_config_path_available(dest_root, path_text, fighter, source_slot, target_slot):
            repaired.append(path_text)
            seen.add(path_text)
    return repaired


def _config_path_targets_slot(path: str, fighter: str, slot: int) -> bool:
    fighter_name = str(fighter or "").lower()
    slot_token = f"c{int(slot):02d}"
    normalized = str(path or "").replace("\\", "/").lower()
    matches = iter_slot_matches(normalized)
    if matches:
        return any(match_fighter == fighter_name and int(match_slot) == int(slot) for match_fighter, match_slot in matches)
    return fighter_name in normalized and slot_token in normalized


def _retarget_visual_config_path(path: str, fighter: str, source_slot: int, target_slot: int) -> str:
    rel = str(path or "").replace("\\", "/")
    lower = rel.lower()
    fighter_name = str(fighter or "").lower()
    if not rel:
        return rel
    if lower.startswith(f"fighter/{fighter_name}/") or lower.startswith(f"camera/fighter/{fighter_name}/"):
        return _replace_path_segment_token(rel, f"c{int(source_slot):02d}", f"c{int(target_slot):02d}")
    if lower.startswith("sound/bank/fighter_voice/") or lower.startswith("sound/bank/fighter/"):
        return _retarget_voice_relative_path(rel, source_slot, target_slot)
    if lower.startswith("ui/replace/chara/") or lower.startswith("ui/replace_patch/chara/"):
        return re.sub(
            rf"(?i)_{int(source_slot):02d}(?=\.bntx$)",
            f"_{int(target_slot):02d}",
            rel,
        )
    if lower.startswith(f"effect/fighter/{fighter_name}/"):
        return _retarget_effect_relative_path(rel, source_slot, target_slot)
    return rel


def _ensure_config_path_available(
    dest_root: Path,
    relative_path: str,
    fighter: str,
    source_slot: int,
    target_slot: int,
) -> bool:
    target = Path(dest_root) / relative_path
    if target.exists():
        return True

    normalized = relative_path.replace("\\", "/").lower()
    fighter_name = str(fighter or "").lower()
    if not normalized.startswith(f"effect/fighter/{fighter_name}/"):
        return False

    source_variant = _retarget_effect_relative_path(relative_path, target_slot, source_slot)
    source_name = Path(source_variant).name
    target_name = Path(relative_path).name
    fallback_candidates = [
        Path(dest_root) / source_variant,
        Path(dest_root) / f"fighter/{fighter_name}/{target_name}",
        Path(dest_root) / f"fighter/{fighter_name}/{source_name}",
        Path(dest_root) / f"effect/fighter/{fighter_name}/{source_name}",
    ]
    if "/trail_c" in normalized:
        fallback_candidates.extend([
            Path(dest_root) / f"fighter/{fighter_name}/trail/{target_name}",
            Path(dest_root) / f"effect/fighter/{fighter_name}/trail/{target_name}",
        ])

    for candidate in fallback_candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate, target)
        return True
    return False


def _build_minimal_slot_effect_config(
    dest_root: Path,
    fighter: str | None = None,
    target_slot: int | None = None,
) -> dict | None:
    analysis = analyze_mod_directory(dest_root, [dest_root.name])
    resolved_fighter = str(fighter or analysis.primary_fighter or "").lower().strip() or None
    resolved_slot = int(target_slot) if target_slot is not None else (
        int(analysis.primary_slot) if analysis.primary_slot is not None else None
    )
    if resolved_fighter is None or resolved_slot is None:
        return None

    effect_paths: list[str] = []
    for file_path in sorted(dest_root.rglob("*")):
        if not file_path.is_file():
            continue
        rel = str(file_path.relative_to(dest_root)).replace("\\", "/")
        if _is_effect_file_for_fighter_slot(rel, resolved_fighter, resolved_slot) or (
            _is_generic_effect_file_for_fighter(rel, resolved_fighter)
        ):
            effect_paths.append(rel)
    if not effect_paths:
        return None
    return {
        "new-dir-files": {
            f"fighter/{resolved_fighter}/c{resolved_slot:02d}": effect_paths,
        }
    }


def _is_generic_effect_file_for_fighter(relative_path: str, fighter: str) -> bool:
    rel = relative_path.replace("\\", "/").lower()
    fighter_name = str(fighter or "").lower()
    prefix = f"effect/fighter/{fighter_name}/"
    if not rel.startswith(prefix):
        return False
    if _is_effect_file_for_fighter_slot(rel, fighter_name):
        return False
    return True


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
    summary: ImportSummary | InstalledModsRepairSummary,
) -> bool:
    mod_root = mods_path / mod_name
    if not mod_root.exists() or not mod_root.is_dir():
        return False

    backup_root = mods_path.parent / _SUPPORT_BACKUP_DIR_NAME / mod_name
    slot_descriptions = _describe_slot_targets_from_paths(mod_root, relative_paths, fallback_name=mod_name)
    slot_text = _format_slot_description_list(slot_descriptions)
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
        return False

    summary.support_mod_adjustments += 1
    summary.support_files_pruned += removed
    warning = (
        f"Pruned {removed} exact support file(s) from '{mod_name}'"
        f"{f' affecting {slot_text}' if slot_text else ''} so a more specific imported override can win cleanly. "
        f"Backups were saved under '{_SUPPORT_BACKUP_DIR_NAME}/{mod_name}'."
    )
    summary.warnings.append(warning)

    if not _has_effective_mod_content(mod_root):
        _disable_support_only_mod(mods_path, mod_name, summary, slot_descriptions)
    return True


def _disable_support_only_mod(
    mods_path: Path,
    mod_name: str,
    summary: ImportSummary | InstalledModsRepairSummary,
    slot_descriptions: list[str] | None = None,
) -> None:
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
    slot_text = _format_slot_description_list(list(slot_descriptions or []))
    summary.warnings.append(
        f"Disabled support mod '{mod_name}'"
        f"{f' ({slot_text})' if slot_text else ''} after all effective conflicting files were pruned. "
        f"It was moved to 'disabled_mods/{dest.name}'."
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
            if rel in _NON_EFFECTIVE_SUPPORT_LEFTOVERS:
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
