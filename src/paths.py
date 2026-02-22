"""Emulator SDMC path detection and derived path resolution."""
import os
from pathlib import Path
from typing import Optional, Tuple

SSBU_TITLE_ID = "01006A800016E000"

# Known emulators and their data paths
EMULATOR_PATHS = {
    "Eden": [
        "{APPDATA}/eden/sdmc",
        "{LOCALAPPDATA}/eden/sdmc",
    ],
    "Ryujinx": [
        "{APPDATA}/Ryujinx/sdmc",
        "{LOCALAPPDATA}/Ryujinx/sdmc",
    ],
    "Yuzu": [
        "{APPDATA}/yuzu/sdmc",
        "{LOCALAPPDATA}/yuzu/sdmc",
    ],
    "Suyu": [
        "{APPDATA}/suyu/sdmc",
        "{LOCALAPPDATA}/suyu/sdmc",
    ],
    "Sudachi": [
        "{APPDATA}/sudachi/sdmc",
        "{LOCALAPPDATA}/sudachi/sdmc",
    ],
    "Citron": [
        "{APPDATA}/Citron/sdmc",
        "{LOCALAPPDATA}/Citron/sdmc",
    ],
}


def _expand_path(template: str) -> Optional[Path]:
    """Expand environment variables in a path template."""
    result = template
    for var in ("APPDATA", "LOCALAPPDATA", "USERPROFILE"):
        val = os.environ.get(var, "")
        result = result.replace("{" + var + "}", val)
    path = Path(result)
    if path.exists() and path.is_dir():
        return path
    return None


def auto_detect_all_emulators() -> list[tuple[str, Path]]:
    """Detect all installed emulators with SSBU data. Returns [(name, path), ...]."""
    found = []
    for emu_name, templates in EMULATOR_PATHS.items():
        for template in templates:
            path = _expand_path(template)
            if path:
                found.append((emu_name, path))
                break  # Only first match per emulator
    return found


def auto_detect_sdmc(emulator: str = "") -> Optional[Path]:
    """Auto-detect an emulator's SDMC path. If emulator is empty, detect any."""
    if emulator:
        templates = EMULATOR_PATHS.get(emulator, [])
        for template in templates:
            path = _expand_path(template)
            if path:
                return path
        return None

    # Try all emulators
    for emu_name, templates in EMULATOR_PATHS.items():
        for template in templates:
            path = _expand_path(template)
            if path:
                return path
    return None


# Keep backwards compatibility
def auto_detect_eden_sdmc() -> Optional[Path]:
    return auto_detect_sdmc()


def derive_mods_path(sdmc: Path) -> Path:
    return sdmc / "ultimate" / "mods"


def derive_plugins_path(sdmc: Path) -> Path:
    return sdmc / "atmosphere" / "contents" / SSBU_TITLE_ID / "romfs" / "skyline" / "plugins"


def validate_sdmc_path(sdmc: Path) -> Tuple[bool, str]:
    if not sdmc.exists():
        return False, "Path does not exist"
    if not sdmc.is_dir():
        return False, "Path is not a directory"

    mods_path = derive_mods_path(sdmc)
    plugins_path = derive_plugins_path(sdmc)

    issues = []
    if not mods_path.exists():
        issues.append("Mods directory not found (ultimate/mods/)")
    if not plugins_path.exists():
        issues.append("Plugins directory not found")

    if issues:
        return False, "Path exists but: " + "; ".join(issues)

    return True, "Valid SSBU setup detected"
