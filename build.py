"""Build and package SSBU Mod Manager for release."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import PyInstaller.__main__

from src import __version__

ENTRYPOINT = "main.py"
EXECUTABLE_NAME = "SSBUModManager"
OUTPUT_DIR_NAME = EXECUTABLE_NAME
ICON_RELATIVE_PATH = Path("assets") / "icon.ico"
ASSETS_RELATIVE_PATH = Path("assets")
PARAM_LABELS_RELATIVE_PATH = Path("ParamLabels.csv")
WINDOWS_RELEASE_SUFFIX = "windows"
ZIP_COMPRESSION = zipfile.ZIP_DEFLATED
ZIP_COMPRESSION_LEVEL = 9
PYINSTALLER_COMMON_FLAGS = [
    "--onedir",
    "--windowed",
    "--noconfirm",
    "--clean",
]
HIDDEN_IMPORTS = [
    "pyprc",
    "LMS",
    "LMS.Common",
    "LMS.Message",
    "LMS.Message.MSBT",
    "LMS.Stream",
    "LMS.Stream.Reader",
    "LMS.Stream.Writer",
    "LMS.Project",
    "lupa",
    "customtkinter",
    "src.ui.pages",
    "src.ui.pages.dashboard_page",
    "src.ui.pages.mods_page",
    "src.ui.pages.plugins_page",
    "src.ui.pages.css_page",
    "src.ui.pages.music_page",
    "src.ui.pages.conflicts_page",
    "src.ui.pages.share_page",
    "src.ui.pages.migration_page",
    "src.ui.pages.online_compat_page",
    "src.ui.pages.settings_page",
    "src.ui.pages.developer_page",
    "PIL",
    "PIL._tkinter_finder",
    "pygame",
]
COLLECT_ALL_PACKAGES = [
    "LMS",
    "lupa",
    "customtkinter",
]
COLLECT_SUBMODULE_PACKAGES = [
    "src.ui.pages",
]
PROJECT_ROOT = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist"
ONEDIR_OUTPUT_PATH = DIST_DIR / OUTPUT_DIR_NAME
RELEASE_ZIP_FILENAME = (
    f"{EXECUTABLE_NAME}-{__version__}-{WINDOWS_RELEASE_SUFFIX}.zip"
)
RELEASE_ZIP_PATH = DIST_DIR / RELEASE_ZIP_FILENAME


def _build_pyinstaller_args(icon_path: Path) -> list[str]:
    args: list[str] = [
        ENTRYPOINT,
        f"--name={EXECUTABLE_NAME}",
        f"--add-data={PARAM_LABELS_RELATIVE_PATH};.",
        f"--add-data={ASSETS_RELATIVE_PATH};assets",
    ]
    args.extend(PYINSTALLER_COMMON_FLAGS)
    args.extend(f"--hidden-import={name}" for name in HIDDEN_IMPORTS)
    args.extend(f"--collect-all={name}" for name in COLLECT_ALL_PACKAGES)
    args.extend(
        f"--collect-submodules={name}" for name in COLLECT_SUBMODULE_PACKAGES
    )
    if icon_path.exists():
        args.append(f"--icon={icon_path}")
        print(f"Using icon: {icon_path}")
    else:
        print(f"WARNING: icon not found: {icon_path}")
    return args


def _zip_onedir_output() -> Path:
    if not ONEDIR_OUTPUT_PATH.exists():
        raise FileNotFoundError(f"Build output not found: {ONEDIR_OUTPUT_PATH}")

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if RELEASE_ZIP_PATH.exists():
        RELEASE_ZIP_PATH.unlink()

    with zipfile.ZipFile(
        RELEASE_ZIP_PATH,
        mode="w",
        compression=ZIP_COMPRESSION,
        compresslevel=ZIP_COMPRESSION_LEVEL,
    ) as archive:
        for path in ONEDIR_OUTPUT_PATH.rglob("*"):
            if path.is_file():
                archive_name = path.relative_to(DIST_DIR)
                archive.write(path, arcname=str(archive_name))

    return RELEASE_ZIP_PATH


def main() -> None:
    os.chdir(PROJECT_ROOT)
    icon_path = PROJECT_ROOT / ICON_RELATIVE_PATH
    build_args = _build_pyinstaller_args(icon_path)
    print(f"Building {EXECUTABLE_NAME} {__version__}...")
    PyInstaller.__main__.run(build_args)
    zip_path = _zip_onedir_output()
    print(f"Build complete: {ONEDIR_OUTPUT_PATH / (EXECUTABLE_NAME + '.exe')}")
    print(f"Release artifact: {zip_path}")


if __name__ == "__main__":
    main()
