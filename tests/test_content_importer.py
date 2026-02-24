from pathlib import Path

from src.core.content_importer import import_mod_package, import_plugin_package
from src.paths import SSBU_TITLE_ID


def test_import_mod_package_unwraps_nested_wrapper(tmp_path: Path):
    source = tmp_path / "downloads" / "CoolMod_v1"
    inner_mod = source / "CoolMod" / "fighter" / "mario"
    inner_mod.mkdir(parents=True)
    (inner_mod / "model.bin").write_bytes(b"abc")

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    summary = import_mod_package(source, mods_path)

    assert summary.items_imported == 1
    assert (mods_path / "CoolMod" / "fighter" / "mario" / "model.bin").exists()


def test_import_plugin_package_from_atmosphere_tree(tmp_path: Path):
    source = tmp_path / "plugin_pkg"
    plugin_src = source / "atmosphere" / "contents" / SSBU_TITLE_ID / "romfs" / "skyline" / "plugins"
    plugin_src.mkdir(parents=True)
    (plugin_src / "libexample.nro").write_bytes(b"plugin")

    exefs_src = source / "atmosphere" / "contents" / SSBU_TITLE_ID / "exefs"
    exefs_src.mkdir(parents=True)
    (exefs_src / "main.npdm").write_bytes(b"npdm")

    sdmc = tmp_path / "sdmc"
    sdmc.mkdir(parents=True)
    plugins_path = sdmc / "atmosphere" / "contents" / SSBU_TITLE_ID / "romfs" / "skyline" / "plugins"
    summary = import_plugin_package(source, sdmc, plugins_path)

    assert summary.files_copied >= 2
    assert summary.plugin_files >= 1
    assert (plugins_path / "libexample.nro").exists()
    assert (sdmc / "atmosphere" / "contents" / SSBU_TITLE_ID / "exefs" / "main.npdm").exists()


def test_import_plugin_package_handles_loose_romfs_exefs_and_nro(tmp_path: Path):
    source = tmp_path / "loose_plugin"
    (source / "romfs" / "ui" / "msg").mkdir(parents=True)
    (source / "romfs" / "ui" / "msg" / "file.msbt").write_bytes(b"romfs")
    (source / "exefs").mkdir(parents=True)
    (source / "exefs" / "subsdk9").write_bytes(b"exefs")
    (source / "libloose.nro").write_bytes(b"plugin")

    sdmc = tmp_path / "sdmc"
    sdmc.mkdir(parents=True)
    plugins_path = sdmc / "atmosphere" / "contents" / SSBU_TITLE_ID / "romfs" / "skyline" / "plugins"
    summary = import_plugin_package(source, sdmc, plugins_path)

    assert summary.files_copied >= 3
    assert (plugins_path / "libloose.nro").exists()
    assert (sdmc / "atmosphere" / "contents" / SSBU_TITLE_ID / "romfs" / "ui" / "msg" / "file.msbt").exists()
    assert (sdmc / "atmosphere" / "contents" / SSBU_TITLE_ID / "exefs" / "subsdk9").exists()
