from pathlib import Path

from src import __version__


REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"
BUILD_SCRIPT_PATH = REPO_ROOT / "build.py"


def test_readme_mentions_current_release_version() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    assert f"Current release version: **{__version__}**." in readme


def test_build_script_uses_runtime_version_for_zip_name() -> None:
    build_script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "RELEASE_ZIP_FILENAME" in build_script
    assert "{__version__}" in build_script
