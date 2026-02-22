"""Mod listing, enable/disable, metadata extraction."""
from pathlib import Path
from typing import Optional
from src.models.mod import Mod, ModStatus, ModMetadata
from src.core.file_scanner import FileScanner
from src.utils.file_utils import safe_rename

# Quick category detection based on top-level directory names
_DIR_CATEGORIES = {
    "fighter": "Character",
    "sound": "Audio",
    "stage": "Stage",
    "ui": "UI",
    "effect": "Effect",
    "camera": "Camera",
    "assist": "Assist Trophy",
    "item": "Item",
    "param": "Params",
}


class ModManager:
    def __init__(self, mods_path: Path, disable_method: str = "rename"):
        self.mods_path = mods_path
        self.disable_method = disable_method
        self.scanner = FileScanner()
        self._mods: list[Mod] = []
        self._cached = False

    def list_mods(self, force_refresh: bool = False) -> list[Mod]:
        """List all mods with lightweight category detection."""
        if self._cached and not force_refresh:
            return self._mods

        self._mods = []
        if not self.mods_path.exists():
            self._cached = True
            return self._mods

        for folder in sorted(self.mods_path.iterdir()):
            if not folder.is_dir():
                continue
            if folder.name.startswith("_"):
                continue

            if folder.name.startswith("."):
                status = ModStatus.DISABLED
            else:
                status = ModStatus.ENABLED

            mod = Mod(
                name=folder.name,
                path=folder,
                status=status,
            )

            # Lightweight category detection
            mod.metadata.categories = self._quick_categorize(folder)

            self._mods.append(mod)

        self._cached = True
        return self._mods

    def _quick_categorize(self, mod_path: Path) -> list[str]:
        """Quickly detect mod categories by checking top-level subdirectories."""
        categories = set()
        try:
            for child in mod_path.iterdir():
                if child.is_dir():
                    name_lower = child.name.lower()
                    if name_lower in _DIR_CATEGORIES:
                        categories.add(_DIR_CATEGORIES[name_lower])
                    if name_lower == "stream":
                        categories.add("Audio")
                elif child.is_file():
                    if child.suffix.lower() in (".nus3audio",):
                        categories.add("Audio")
        except (PermissionError, OSError):
            pass

        return sorted(categories) if categories else ["Other"]

    def invalidate_cache(self):
        self._cached = False

    def refresh(self) -> list[Mod]:
        return self.list_mods(force_refresh=True)

    def get_mod_details(self, mod: Mod) -> Mod:
        """Populate full metadata for a mod (lazy - only when needed)."""
        if mod.metadata.has_config_json or mod.metadata.fighter_kind:
            return mod

        files = self.scanner.scan_mod(mod.path)
        if files:
            mod.files = files
            mod.file_count = len(files)
            mod.total_size = sum(f.file_size for f in files)
            mod.metadata = self.scanner.extract_metadata(mod.path, files)
        else:
            mod.files = []
            mod.file_count = 0
            mod.total_size = 0

        if mod.metadata.fighter_kind:
            mod.metadata.display_name = mod.original_name

        return mod

    def enable_mod(self, mod: Mod) -> None:
        if mod.status == ModStatus.ENABLED:
            return

        if self.disable_method == "rename":
            new_name = mod.name.lstrip(".")
            new_path = safe_rename(mod.path, new_name)
            mod.name = new_name
            mod.path = new_path
            mod.status = ModStatus.ENABLED
        else:
            new_path = self.mods_path / mod.original_name
            mod.path.rename(new_path)
            mod.path = new_path
            mod.name = mod.original_name
            mod.status = ModStatus.ENABLED

        self.invalidate_cache()

    def disable_mod(self, mod: Mod) -> None:
        if mod.status == ModStatus.DISABLED:
            return

        if self.disable_method == "rename":
            new_name = f".{mod.name}"
            new_path = safe_rename(mod.path, new_name)
            mod.name = new_name
            mod.path = new_path
            mod.status = ModStatus.DISABLED
        else:
            disabled_dir = self.mods_path / ".disabled"
            disabled_dir.mkdir(exist_ok=True)
            new_path = disabled_dir / mod.name
            mod.path.rename(new_path)
            mod.path = new_path
            mod.status = ModStatus.DISABLED

        self.invalidate_cache()

    def toggle_mod(self, mod: Mod) -> None:
        if mod.status == ModStatus.ENABLED:
            self.disable_mod(mod)
        else:
            self.enable_mod(mod)

    def detect_mod_type(self, mod: Mod) -> list[str]:
        if not mod.metadata.categories:
            self.get_mod_details(mod)
        return mod.metadata.categories
