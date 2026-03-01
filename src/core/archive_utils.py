"""Archive listing/extraction helpers used by content import flows."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import zipfile


ARCHIVE_EXTENSIONS = {".zip", ".7z", ".rar"}
_COMMON_7Z_PATHS = (
    Path(r"C:\Program Files\7-Zip\7z.exe"),
    Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
)


@dataclass(frozen=True)
class ArchiveMember:
    path: str
    is_dir: bool = False


def is_archive_path(path: Path) -> bool:
    return Path(path).suffix.lower() in ARCHIVE_EXTENSIONS


def find_7z_executable() -> Path | None:
    found = shutil.which("7z") or shutil.which("7za") or shutil.which("7zr")
    if found:
        return Path(found)
    for candidate in _COMMON_7Z_PATHS:
        if candidate.exists():
            return candidate
    return None


def list_archive_members(archive_path: Path) -> list[ArchiveMember]:
    archive_path = Path(archive_path)
    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    if archive_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive_path) as handle:
            return [
                ArchiveMember(info.filename.replace("\\", "/"), info.is_dir())
                for info in handle.infolist()
            ]

    exe = find_7z_executable()
    if exe is None:
        raise FileNotFoundError(
            "7-Zip is required to inspect .7z/.rar archives, but 7z.exe was not found."
        )

    proc = subprocess.run(
        [str(exe), "l", "-ba", str(archive_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or "Unknown archive error."
        raise RuntimeError(f"Failed to list archive '{archive_path.name}': {message}")

    members: list[ArchiveMember] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        path = (line[53:].strip() if len(line) > 53 else line.strip()).replace("\\", "/")
        if not path:
            continue
        attrs = line[20:25] if len(line) >= 25 else ""
        members.append(ArchiveMember(path=path, is_dir="D" in attrs))
    return members


def extract_archive(archive_path: Path, output_dir: Path) -> None:
    archive_path = Path(archive_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if archive_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive_path) as handle:
            handle.extractall(output_dir)
        return

    exe = find_7z_executable()
    if exe is None:
        raise FileNotFoundError(
            "7-Zip is required to extract .7z/.rar archives, but 7z.exe was not found."
        )

    proc = subprocess.run(
        [str(exe), "x", "-y", str(archive_path), f"-o{output_dir}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or "Unknown archive error."
        raise RuntimeError(f"Failed to extract archive '{archive_path.name}': {message}")
