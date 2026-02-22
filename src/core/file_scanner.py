"""Recursive mod file scanning and indexing."""
import os
from pathlib import Path
from typing import Optional
from src.models.mod import ModFile, ModMetadata

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
                if folder.name.startswith(".") or folder.name.startswith("_"):
                    continue
                if folder.name in _SKIP_FOLDERS:
                    continue

                mod_name = folder.name
                for fpath in folder.rglob("*"):
                    if fpath.is_file():
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

        config_path = mod_path / "config.json"
        if config_path.exists():
            try:
                import json
                import re
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                dir_infos = config.get("new-dir-infos", [])
                for dir_path in dir_infos:
                    match = re.search(r'fighter/([^/]+)/c(\d{2,3})', dir_path)
                    if match:
                        if not metadata.fighter_kind:
                            metadata.fighter_kind = match.group(1)
                        metadata.costume_slots.append(int(match.group(2)))
                metadata.costume_slots = sorted(set(metadata.costume_slots))
            except Exception as e:
                from src.utils.logger import logger
                logger.warn("FileScanner", f"Failed to parse config.json in {mod_path.name}: {e}")

        return metadata

    def categorize_file(self, relative_path: str) -> list[str]:
        categories = []
        rel_lower = relative_path.lower()
        for cat, patterns in _CATEGORY_PATTERNS.items():
            if any(p in rel_lower for p in patterns):
                categories.append(cat)
        return categories if categories else ["other"]
