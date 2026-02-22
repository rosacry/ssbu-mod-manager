"""Mod listing, enable/disable, metadata extraction."""
import re
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

# Name-based patterns that strongly indicate a primary category
# Order matters: first match wins. More specific patterns come first.
_NAME_PATTERNS = [
    # [UI] prefix or CSS (Character Select Screen) mods are UI, not Character
    (re.compile(r'^\[UI\]|\bcss\b|custom\s*request\s*css', re.IGNORECASE), "UI"),
    (re.compile(r'moveset|fighter|skin|costume|slot|c\d{2}', re.IGNORECASE), "Character"),
    (re.compile(r'\bstage\b|battlefield|omega|fd\b', re.IGNORECASE), "Stage"),
    (re.compile(r'\bmusic\b|soundtrack|bgm|tracklist', re.IGNORECASE), "Music"),
    (re.compile(r'\bui\b|menu|hud|portrait', re.IGNORECASE), "UI"),
    (re.compile(r'\beffect\b|vfx|particle', re.IGNORECASE), "Effect"),
]

# Category priority: lower index = more dominant primary category
_CATEGORY_PRIORITY = [
    "Character", "Stage", "Music", "UI", "Effect",
    "Camera", "Assist Trophy", "Item", "Params", "Audio", "Other",
]


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
        if not self.mods_path.exists() or self.mods_path == Path("."):
            self._cached = True
            return self._mods

        for folder in sorted(self.mods_path.iterdir()):
            if not folder.is_dir():
                continue
            if folder.name.startswith("_"):
                continue

            if folder.name.startswith("."):
                # Skip the .disabled container directory itself
                if folder.name == ".disabled":
                    continue
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

        # Also scan .disabled directory for mods disabled via "move" method
        disabled_dir = self.mods_path / ".disabled"
        if disabled_dir.exists() and disabled_dir.is_dir():
            for folder in sorted(disabled_dir.iterdir()):
                if not folder.is_dir():
                    continue

                mod = Mod(
                    name=folder.name,
                    path=folder,
                    status=ModStatus.DISABLED,
                )
                mod.metadata.categories = self._quick_categorize(folder)
                self._mods.append(mod)

        self._cached = True
        return self._mods

    def _quick_categorize(self, mod_path: Path) -> list[str]:
        """Detect mod categories using directory structure, file types, and name heuristics."""
        categories = set()
        has_fighter_content = False
        has_config_json = False
        try:
            for child in mod_path.iterdir():
                if child.is_dir():
                    name_lower = child.name.lower()
                    if name_lower in _DIR_CATEGORIES:
                        categories.add(_DIR_CATEGORIES[name_lower])
                    if name_lower == "stream":
                        categories.add("Audio")
                    # Check for fighter subdirectories (indicates moveset/character mod)
                    if name_lower == "fighter":
                        has_fighter_content = True
                elif child.is_file():
                    fl = child.name.lower()
                    if child.suffix.lower() in (".nus3audio",):
                        categories.add("Audio")
                    if fl == "config.json":
                        has_config_json = True
        except (PermissionError, OSError):
            pass

        # Name-based heuristic: check mod folder name for strong category hints
        name_hint = None
        for pattern, cat in _NAME_PATTERNS:
            if pattern.search(mod_path.name):
                name_hint = cat
                categories.add(cat)
                break

        if not categories:
            return ["Other"]

        # Determine primary category with smart prioritization
        primary = self._determine_primary_category(
            categories, mod_path.name, has_fighter_content, has_config_json, name_hint)

        # Build sorted list with primary first
        result = [primary]
        for cat in sorted(categories):
            if cat != primary:
                result.append(cat)
        return result

    def _determine_primary_category(self, categories: set, mod_name: str,
                                     has_fighter: bool, has_config: bool,
                                     name_hint: Optional[str] = None) -> str:
        """Determine the primary (most important) category for grouping."""
        # If name strongly hints at a category, use that
        if name_hint and name_hint in categories:
            return name_hint

        # If mod has fighter directory + config.json, it's almost certainly a character mod
        if has_fighter and has_config and "Character" in categories:
            return "Character"

        # If Character is present with Audio/Camera/Effect, Character is primary
        # (movesets are character mods that include audio/camera/effect assets)
        if "Character" in categories and len(categories) > 1:
            return "Character"

        # If only Audio-related categories ("Audio" only), it's a music/sound mod
        if categories == {"Audio"}:
            return "Audio"

        # Use priority order
        for cat in _CATEGORY_PRIORITY:
            if cat in categories:
                return cat

        return sorted(categories)[0]

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
            if new_path.exists():
                raise FileExistsError(f"Cannot enable: '{mod.original_name}' already exists in mods folder")
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
            if new_path.exists():
                raise FileExistsError(f"Cannot disable: '{mod.name}' already exists in disabled folder")
            mod.path.rename(new_path)
            mod.path = new_path
            mod.status = ModStatus.DISABLED

        self.invalidate_cache()

    def toggle_mod(self, mod: Mod) -> None:
        if mod.status == ModStatus.ENABLED:
            self.disable_mod(mod)
        else:
            self.enable_mod(mod)

    def enable_all(self) -> int:
        """Enable all disabled mods. Returns count of mods enabled."""
        count = 0
        # Snapshot list to avoid iteration-during-mutation
        mods_snapshot = list(self.list_mods())
        for mod in mods_snapshot:
            if mod.status == ModStatus.DISABLED:
                try:
                    self.enable_mod(mod)
                    count += 1
                except (FileExistsError, OSError):
                    pass
        self.invalidate_cache()
        return count

    def disable_all(self) -> int:
        """Disable all enabled mods. Returns count of mods disabled."""
        count = 0
        # Snapshot list to avoid iteration-during-mutation
        mods_snapshot = list(self.list_mods())
        for mod in mods_snapshot:
            if mod.status == ModStatus.ENABLED:
                try:
                    self.disable_mod(mod)
                    count += 1
                except (FileExistsError, OSError):
                    pass
        self.invalidate_cache()
        return count

    def detect_mod_type(self, mod: Mod) -> list[str]:
        if not mod.metadata.categories:
            self.get_mod_details(mod)
        return mod.metadata.categories

    # ---------- Subfolder nesting detection & flattening ----------

    # Directories that indicate actual SSBU mod content
    _CONTENT_DIRS = {
        "fighter", "sound", "stage", "ui", "effect", "camera",
        "assist", "item", "param", "stream",
    }

    def _is_content_dir(self, path: Path) -> bool:
        """Check if a directory contains recognized SSBU mod content dirs."""
        try:
            for child in path.iterdir():
                if child.is_dir() and child.name.lower() in self._CONTENT_DIRS:
                    return True
                if child.is_file() and child.name.lower() == "config.json":
                    return True
        except (PermissionError, OSError):
            pass
        return False

    def detect_nested_mods(self) -> list[Mod]:
        """Find mods that have unnecessary subfolder nesting.

        A mod is considered unnecessarily nested when:
        - It contains exactly one subfolder (no other dirs, maybe some files)
        - That subfolder contains the actual SSBU content dirs (fighter/, ui/, etc.)
        """
        nested = []
        for mod in self.list_mods():
            if self._is_unnecessarily_nested(mod.path):
                nested.append(mod)
        return nested

    def _is_unnecessarily_nested(self, mod_path: Path) -> bool:
        """Check if a mod folder has unnecessary nesting."""
        try:
            children = list(mod_path.iterdir())
        except (PermissionError, OSError):
            return False

        # Already has content directly? Not nested.
        if self._is_content_dir(mod_path):
            return False

        # Find subdirectories (exclude hidden/meta dirs)
        subdirs = [c for c in children if c.is_dir() and not c.name.startswith(".")]
        if len(subdirs) != 1:
            return False

        # The single subfolder should contain actual mod content
        sole_subdir = subdirs[0]
        return self._is_content_dir(sole_subdir)

    def flatten_mod(self, mod: Mod) -> bool:
        """Remove one level of unnecessary subfolder nesting from a mod.

        Returns True if flattening was performed.
        """
        if not self._is_unnecessarily_nested(mod.path):
            return False

        import shutil

        subdirs = [c for c in mod.path.iterdir()
                   if c.is_dir() and not c.name.startswith(".")]
        sole_subdir = subdirs[0]

        # Move everything from the sole subfolder up to mod root
        for item in sole_subdir.iterdir():
            dest = mod.path / item.name
            if dest.exists():
                # Conflict - skip to avoid data loss
                continue
            item.rename(dest)

        # Remove the now-empty subfolder
        try:
            if sole_subdir.exists() and not any(sole_subdir.iterdir()):
                sole_subdir.rmdir()
            elif sole_subdir.exists():
                # Some items remain (conflicts) - leave it
                pass
        except OSError:
            pass

        self.invalidate_cache()
        return True

    def flatten_all_nested(self) -> int:
        """Flatten all unnecessarily nested mods. Returns count fixed."""
        nested = self.detect_nested_mods()
        count = 0
        for mod in nested:
            if self.flatten_mod(mod):
                count += 1
        return count
