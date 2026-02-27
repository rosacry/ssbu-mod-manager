"""Import helpers for mods and plugins."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil

from src.paths import SSBU_TITLE_ID

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


@dataclass
class ImportSummary:
    """Aggregated import stats shown in UI after an import."""

    items_imported: int = 0
    files_copied: int = 0
    replaced_paths: int = 0
    flattened_mods: int = 0
    plugin_files: int = 0
    warnings: list[str] = field(default_factory=list)


def import_mod_package(source_dir: Path, mods_path: Path) -> ImportSummary:
    """Import one or more mod folders from a chosen directory."""
    source_dir = Path(source_dir)
    mods_path = Path(mods_path)
    if not source_dir.exists() or not source_dir.is_dir():
        raise ValueError("Selected mod import path is not a valid folder.")

    sources = _collect_mod_sources(source_dir)
    if not sources:
        raise ValueError(
            "No importable mod folders were found. "
            "Select a folder that contains SSBU mod content."
        )

    mods_path.mkdir(parents=True, exist_ok=True)
    summary = ImportSummary()
    for src, target_name in sources:
        dest = mods_path / target_name
        if _same_path(src, dest):
            summary.warnings.append(f"Skipped '{target_name}' (already in mods folder).")
            continue

        _copy_dir_replace(src, dest, summary)
        summary.items_imported += 1
        summary.files_copied += _count_files(dest)

        if _flatten_nested_mod(dest):
            summary.flattened_mods += 1

    if summary.items_imported == 0:
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
