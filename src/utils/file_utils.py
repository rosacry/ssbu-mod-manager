import os
import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

_KB = 1024
_MB = _KB * 1024
_GB = _MB * 1024


def open_folder(path) -> None:
    """Open a folder in the system file manager. Cross-platform."""
    path_str = str(path)
    if sys.platform == "win32":
        os.startfile(path_str)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path_str])
    else:
        subprocess.Popen(["xdg-open", path_str])

def safe_rename(path: Path, new_name: str) -> Path:
    """Rename a file or directory safely."""
    new_path = path.parent / new_name
    if new_path.exists():
        raise FileExistsError(f"Cannot rename: '{new_name}' already exists")
    path.rename(new_path)
    return new_path

def backup_file(file_path: Path, backup_dir: Optional[Path] = None) -> Path:
    """Create a timestamped backup of a file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Cannot backup: source file '{file_path}' does not exist")
    if backup_dir is None:
        backup_dir = Path.home() / ".ssbu-mod-manager" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
    backup_path = backup_dir / backup_name
    shutil.copy2(file_path, backup_path)
    return backup_path

def get_dir_size(path: Path) -> int:
    """Get total size of a directory in bytes."""
    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
    except (PermissionError, OSError):
        pass
    return total

def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    if size_bytes < _KB:
        return f"{size_bytes} B"
    elif size_bytes < _MB:
        return f"{size_bytes / _KB:.1f} KB"
    elif size_bytes < _GB:
        return f"{size_bytes / _MB:.1f} MB"
    else:
        return f"{size_bytes / _GB:.1f} GB"

def count_files(path: Path) -> int:
    """Count files in a directory recursively."""
    count = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                count += 1
    except (PermissionError, OSError):
        pass
    return count
