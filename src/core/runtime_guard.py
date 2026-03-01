"""Detect running emulators and block live mod/plugin file operations."""

from __future__ import annotations

import csv
import errno
import io
import os
import subprocess
from dataclasses import dataclass


EMULATOR_PROCESS_NAMES: dict[str, tuple[str, ...]] = {
    "Eden": ("eden.exe",),
    "Ryujinx": ("ryujinx.exe",),
    "Yuzu": ("yuzu.exe",),
    "Suyu": ("suyu.exe",),
    "Sudachi": ("sudachi.exe",),
    "Citron": ("citron.exe",),
}

LOCKED_WINERRORS = {5, 32, 33}
LOCKED_ERRNOS = {errno.EACCES, errno.EPERM, errno.EBUSY}


@dataclass(frozen=True)
class RuntimeBlockInfo:
    target_label: str
    action: str
    running_emulators: tuple[str, ...] = ()
    files_in_use: bool = False

    @property
    def title(self) -> str:
        return f"Cannot {self.action.title()} {self.target_label.title()}"

    @property
    def message(self) -> str:
        base = (
            f"Cannot {self.action} this {self.target_label} while the game is currently running."
        )
        if self.running_emulators:
            names = ", ".join(self.running_emulators)
            base = (
                f"Cannot {self.action} this {self.target_label} while the game is currently "
                f"running in {names}."
            )
        followup = " Close the game or emulator completely, then try again."
        if self.files_in_use and not self.running_emulators:
            followup = " Close the game, emulator, or any tool using these files, then try again."
        return base + followup


class ContentOperationBlockedError(RuntimeError):
    """Raised when a live content change should not proceed."""

    def __init__(self, info: RuntimeBlockInfo):
        super().__init__(info.message)
        self.info = info


def _list_running_process_names() -> set[str]:
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return set()
        reader = csv.reader(io.StringIO(result.stdout))
        return {
            row[0].strip().lower()
            for row in reader
            if row and row[0].strip()
        }

    result = subprocess.run(
        ["ps", "-A", "-o", "comm="],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
    )
    if result.returncode != 0:
        return set()
    return {
        line.strip().lower()
        for line in result.stdout.splitlines()
        if line.strip()
    }


def list_running_emulators() -> list[str]:
    running_processes = _list_running_process_names()
    found: list[str] = []
    for emulator_name, process_names in EMULATOR_PROCESS_NAMES.items():
        if any(name.lower() in running_processes for name in process_names):
            found.append(emulator_name)
    return found


def ensure_runtime_content_change_allowed(target_label: str, action: str) -> None:
    running_emulators = tuple(list_running_emulators())
    if running_emulators:
        raise ContentOperationBlockedError(
            RuntimeBlockInfo(
                target_label=target_label,
                action=action,
                running_emulators=running_emulators,
            )
        )


def should_treat_as_files_in_use(error: OSError) -> bool:
    if isinstance(error, FileExistsError):
        return False
    if isinstance(error, PermissionError):
        return True
    if getattr(error, "winerror", None) in LOCKED_WINERRORS:
        return True
    return getattr(error, "errno", None) in LOCKED_ERRNOS


def raise_if_files_in_use(error: OSError, target_label: str, action: str) -> None:
    if not should_treat_as_files_in_use(error):
        return
    raise ContentOperationBlockedError(
        RuntimeBlockInfo(
            target_label=target_label,
            action=action,
            running_emulators=tuple(list_running_emulators()),
            files_in_use=True,
        )
    ) from error
