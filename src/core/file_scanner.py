"""Recursive mod file scanning and indexing."""
import os
from pathlib import Path
from typing import Optional
from src.models.mod import ModFile, ModMetadata
from src.core.skin_slot_utils import analyze_relative_paths

_CATEGORY_PATTERNS = {
    "character": ["fighter/", "ui/replace/chara/", "sound/bank/narration/"],
    "music": ["sound/bgm/", "stream/sound/"],
    "stage": ["stage/", "ui/replace/stage/"],
    "ui": ["ui/param/", "ui/message/", "ui/replace_patch/"],
    "effect": ["effect/"],
}

# Folders to skip during conflict scanning
_SKIP_FOLDERS = {"_MergedResources", "_MusicConfig", ".disabled", "__pycache__"}


class FileScanner:
    def scan_mod(self, mod_path: Path) -> list[ModFile]:
        """Scan a single mod folder and return all files."""
        files = []
        try:
            for entry in mod_path.rglob("*"):
                if entry.is_file():
                    rel = str(entry.relative_to(mod_path)).replace("\\", "/")
                    files.append(ModFile(
                        relative_path=rel,
                        absolute_path=entry,
                        file_size=entry.stat().st_size,
                    ))
        except (PermissionError, OSError):
            pass
        return files

    def build_file_index(self, mods_root: Path) -> dict[str, list[tuple[str, Path]]]:
        """
        Build index of all files across enabled mods.
        Returns: {relative_path: [(mod_name, absolute_path), ...]}
        Skips internal/system folders.
        """
        file_index = {}
        try:
            for folder in mods_root.iterdir():
                if not folder.is_dir():
                    continue
                if folder.name.startswith("."):
                    continue
                if folder.name in _SKIP_FOLDERS:
                    continue

                mod_name = folder.name
                for fpath in folder.rglob("*"):
                    if fpath.is_file():
                        # Skip leftover .merged backup files from older versions
                        if fpath.name.endswith(".merged"):
                            continue
                        rel = str(fpath.relative_to(folder)).replace("\\", "/")
                        if rel not in file_index:
                            file_index[rel] = []
                        file_index[rel].append((mod_name, fpath))
        except (PermissionError, OSError):
            pass
        return file_index

    def extract_metadata(self, mod_path: Path, files: list[ModFile]) -> ModMetadata:
        """Extract metadata about a mod from its files."""
        metadata = ModMetadata()
        categories = set()
        rel_paths = [f.relative_path for f in files]
        slot_analysis = analyze_relative_paths(rel_paths, [mod_path.name])

        for f in files:
            rel = f.relative_path.lower()
            ext = Path(rel).suffix

            if rel == "config.json":
                metadata.has_config_json = True
            if ext == ".prc":
                metadata.has_prc = True
                if "ui_chara_db" in rel:
                    metadata.has_css_data = True
            if ext in (".msbt",):
                metadata.has_msbt = True
            if ext in (".xmsbt",):
                metadata.has_xmsbt = True
            if ext in (".nus3audio",) or "sound/bgm/" in rel:
                metadata.has_music = True

            for cat, patterns in _CATEGORY_PATTERNS.items():
                if any(p in rel for p in patterns):
                    categories.add(cat)

        metadata.categories = sorted(categories)
        if slot_analysis.primary_fighter:
            metadata.fighter_kind = slot_analysis.primary_fighter
        if slot_analysis.fighter_slots:
            slot_values = sorted({
                slot
                for slots in slot_analysis.fighter_slots.values()
                for slot in slots
            })
            metadata.costume_slots = slot_values

        return metadata

    def categorize_file(self, relative_path: str) -> list[str]:
        categories = []
        rel_lower = relative_path.lower()
        for cat, patterns in _CATEGORY_PATTERNS.items():
            if any(p in rel_lower for p in patterns):
                categories.append(cat)
        return categories if categories else ["other"]
