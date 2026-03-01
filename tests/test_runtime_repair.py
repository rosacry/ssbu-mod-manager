from pathlib import Path

from src.core.runtime_repair import (
    derive_yuzu_root_from_mods_path,
    repair_yuzu_runtime_for_smash,
)
from src.paths import SSBU_TITLE_ID


def test_repair_yuzu_runtime_for_smash_resets_profile_and_caches(tmp_path: Path):
    yuzu_root = tmp_path / "yuzu"
    mods_path = yuzu_root / "sdmc" / "ultimate" / "mods"
    mods_path.mkdir(parents=True)

    qt_config = yuzu_root / "config" / "qt-config.ini"
    qt_config.parent.mkdir(parents=True)
    qt_config.write_text("[Renderer]\nenable_compute_pipelines=false\n", encoding="utf-8")

    title_profile = yuzu_root / "config" / "custom" / f"{SSBU_TITLE_ID}.ini"
    title_profile.parent.mkdir(parents=True)
    title_profile.write_text("[Renderer]\nanti_aliasing=2\n", encoding="utf-8")

    shader_dir = yuzu_root / "shader" / SSBU_TITLE_ID.lower()
    shader_dir.mkdir(parents=True)
    (shader_dir / "vulkan.bin").write_bytes(b"shader")
    (shader_dir / "vulkan_pipelines.bin").write_bytes(b"pipes")

    pipeline_dir = yuzu_root / "pipeline" / SSBU_TITLE_ID.lower()
    pipeline_dir.mkdir(parents=True)
    (pipeline_dir / "cache.bin").write_bytes(b"pipeline")

    arcropolis_root = yuzu_root / "sdmc" / "ultimate" / "arcropolis"
    arcropolis_root.mkdir(parents=True)
    (arcropolis_root / "conflicts.json").write_text("{}", encoding="utf-8")
    (arcropolis_root / "mod_cache").write_text("cache", encoding="utf-8")

    plugins_root = (
        yuzu_root
        / "sdmc"
        / "atmosphere"
        / "contents"
        / SSBU_TITLE_ID
        / "romfs"
        / "skyline"
        / "plugins"
    )
    plugins_root.mkdir(parents=True)
    (plugins_root / ".DS_Store").write_text("junk", encoding="utf-8")

    summary = repair_yuzu_runtime_for_smash(mods_path)

    assert summary.emulator_name == "Yuzu"
    assert summary.title_profile_backed_up is True
    assert summary.title_profile_written is True
    assert summary.shader_files_cleared == 2
    assert summary.pipeline_files_cleared == 1
    assert summary.arcropolis_cache_files_cleared == 3
    assert summary.backup_root is not None
    assert (summary.backup_root / "config" / "custom" / f"{SSBU_TITLE_ID}.ini").exists()
    assert (summary.backup_root / "shader" / SSBU_TITLE_ID.lower() / "vulkan.bin").exists()
    assert (summary.backup_root / "pipeline" / SSBU_TITLE_ID.lower() / "cache.bin").exists()
    assert not (arcropolis_root / "conflicts.json").exists()
    assert not (arcropolis_root / "mod_cache").exists()
    assert not (plugins_root / ".DS_Store").exists()

    profile_text = title_profile.read_text(encoding="utf-8")
    assert "enable_compute_pipelines=true" in profile_text
    assert "use_asynchronous_shaders=true" in profile_text
    assert "async_presentation=true" in profile_text


def test_derive_yuzu_root_from_mods_path_returns_none_without_qt_config(tmp_path: Path):
    mods_path = tmp_path / "random" / "sdmc" / "ultimate" / "mods"
    mods_path.mkdir(parents=True)

    assert derive_yuzu_root_from_mods_path(mods_path) is None
