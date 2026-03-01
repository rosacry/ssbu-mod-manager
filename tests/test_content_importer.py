from pathlib import Path
import zipfile

from src.core.content_importer import import_mod_package, import_plugin_package
from src.core.skin_slot_utils import analyze_relative_paths, choose_primary_skin_slot
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


def test_import_mod_package_can_import_archives_from_directory(tmp_path: Path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    archive_path = downloads / "mario_skin.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Mario Base/fighter/mario/model/body/c00/model.bin", b"abc")
        archive.writestr("Mario Base/ui/replace/chara/chara_0/chara_0_mario_00.bntx", b"ui")

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    summary = import_mod_package(downloads, mods_path)

    assert summary.archives_processed == 1
    assert summary.items_imported == 1
    assert (mods_path / "Mario Base" / "fighter" / "mario" / "model" / "body" / "c00" / "model.bin").exists()


def test_import_mod_package_discovers_deeply_nested_mod_folder(tmp_path: Path):
    source = tmp_path / "downloads" / "Collection"
    deep_mod = source / "Extras" / "Playable Forms" / "Mario Form"
    (deep_mod / "fighter" / "mario" / "model" / "body" / "c00").mkdir(parents=True)
    (deep_mod / "fighter" / "mario" / "model" / "body" / "c00" / "model.bin").write_bytes(b"abc")
    (deep_mod / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (deep_mod / "ui" / "replace" / "chara" / "chara_0" / "chara_0_mario_00.bntx").write_bytes(b"ui")

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    summary = import_mod_package(source, mods_path)

    assert summary.items_imported == 1
    assert (mods_path / "Mario Form" / "fighter" / "mario" / "model" / "body" / "c00" / "model.bin").exists()


def test_import_mod_package_selects_single_base_variant_from_archive(tmp_path: Path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    archive_path = downloads / "mario_pack.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("MarioPack_c00_Default/fighter/mario/model/body/c00/base.bin", b"c00")
        archive.writestr("MarioPack_c00_Default/ui/replace/chara/chara_0/chara_0_mario_00.bntx", b"ui0")
        archive.writestr("MarioPack_c01_Alt/fighter/mario/model/body/c01/alt.bin", b"c01")
        archive.writestr("MarioPack_c01_Alt/ui/replace/chara/chara_0/chara_0_mario_01.bntx", b"ui1")

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    summary = import_mod_package(downloads, mods_path)

    assert summary.items_imported == 1
    assert (mods_path / "MarioPack_c00_Default" / "fighter" / "mario" / "model" / "body" / "c00" / "base.bin").exists()
    assert not (mods_path / "MarioPack_c01_Alt").exists()
    assert any("Selected base variant" in warning for warning in summary.warnings)


def test_import_mod_package_moves_incoming_skin_to_open_slot_by_default(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    existing = mods_path / "Existing Mario"
    (existing / "fighter" / "mario" / "model" / "body" / "c00").mkdir(parents=True)
    (existing / "fighter" / "mario" / "model" / "body" / "c00" / "existing.bin").write_bytes(b"old")
    (existing / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (existing / "ui" / "replace" / "chara" / "chara_0" / "chara_0_mario_00.bntx").write_bytes(b"old-ui")

    source = tmp_path / "downloads" / "New Mario"
    (source / "fighter" / "mario" / "model" / "body" / "c00").mkdir(parents=True)
    (source / "fighter" / "mario" / "model" / "body" / "c00" / "new.bin").write_bytes(b"new")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_mario_00.bntx").write_bytes(b"new-ui")
    (source / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (source / "sound" / "bank" / "fighter_voice" / "vc_mario_c00.nus3audio").write_bytes(b"voice")
    (source / "sound" / "bank" / "fighter").mkdir(parents=True)
    (source / "sound" / "bank" / "fighter" / "se_mario_c00.nus3audio").write_bytes(b"sfx")

    summary = import_mod_package(source, mods_path)

    assert summary.items_imported == 1
    assert summary.slot_reassignments == 1
    assert (mods_path / "Existing Mario" / "fighter" / "mario" / "model" / "body" / "c00" / "existing.bin").exists()
    assert (mods_path / "New Mario" / "fighter" / "mario" / "model" / "body" / "c01" / "new.bin").exists()
    assert (mods_path / "New Mario" / "ui" / "replace" / "chara" / "chara_0" / "chara_0_mario_01.bntx").exists()
    assert (mods_path / "New Mario" / "sound" / "bank" / "fighter_voice" / "vc_mario_c01.nus3audio").exists()
    assert (mods_path / "New Mario" / "sound" / "bank" / "fighter" / "se_mario_c01.nus3audio").exists()


def test_import_mod_package_can_move_existing_mod_to_open_slot(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    existing = mods_path / "Existing Diddy Pack"
    (existing / "fighter" / "diddy" / "model" / "body" / "c01").mkdir(parents=True)
    (existing / "fighter" / "diddy" / "model" / "body" / "c01" / "skin01.bin").write_bytes(b"c01")
    (existing / "fighter" / "diddy" / "model" / "body" / "c03").mkdir(parents=True)
    (existing / "fighter" / "diddy" / "model" / "body" / "c03" / "skin03.bin").write_bytes(b"c03")
    (existing / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (existing / "ui" / "replace" / "chara" / "chara_0" / "chara_0_diddy_01.bntx").write_bytes(b"ui01")
    (existing / "ui" / "replace" / "chara" / "chara_0" / "chara_0_diddy_03.bntx").write_bytes(b"ui03")

    source = tmp_path / "downloads" / "New Diddy"
    (source / "fighter" / "diddy" / "model" / "body" / "c01").mkdir(parents=True)
    (source / "fighter" / "diddy" / "model" / "body" / "c01" / "new.bin").write_bytes(b"new")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_diddy_01.bntx").write_bytes(b"new-ui")

    summary = import_mod_package(source, mods_path, slot_conflict_resolver=lambda _c: "move_existing")

    assert summary.items_imported == 1
    assert (mods_path / "Existing Diddy Pack" / "fighter" / "diddy" / "model" / "body" / "c00" / "skin01.bin").exists()
    assert (mods_path / "Existing Diddy Pack" / "fighter" / "diddy" / "model" / "body" / "c03" / "skin03.bin").exists()
    assert (mods_path / "Existing Diddy Pack" / "ui" / "replace" / "chara" / "chara_0" / "chara_0_diddy_00.bntx").exists()
    assert (mods_path / "Existing Diddy Pack" / "ui" / "replace" / "chara" / "chara_0" / "chara_0_diddy_03.bntx").exists()
    assert (mods_path / "New Diddy" / "fighter" / "diddy" / "model" / "body" / "c01" / "new.bin").exists()


def test_import_mod_package_prunes_false_positive_motion_slots(tmp_path: Path):
    source = tmp_path / "downloads" / "VegetaLike"
    (source / "fighter" / "mario" / "model" / "body" / "c02").mkdir(parents=True)
    (source / "fighter" / "mario" / "model" / "body" / "c02" / "model.bin").write_bytes(b"model")
    (source / "fighter" / "mario" / "motion" / "body" / "c00").mkdir(parents=True)
    (source / "fighter" / "mario" / "motion" / "body" / "c00" / "c02attackhi3.nuanmb").write_bytes(b"motion")

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    summary = import_mod_package(source, mods_path)

    assert summary.items_imported == 1
    assert (mods_path / "VegetaLike" / "fighter" / "mario" / "model" / "body" / "c02" / "model.bin").exists()
    assert not (mods_path / "VegetaLike" / "fighter" / "mario" / "motion" / "body" / "c00").exists()


def test_import_mod_package_allows_voice_pack_to_share_skin_slot(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    voice_mod = mods_path / "Mario Voice Pack"
    (voice_mod / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (voice_mod / "sound" / "bank" / "fighter_voice" / "vc_mario_c00.nus3audio").write_bytes(b"voice")
    (voice_mod / "sound" / "bank" / "fighter").mkdir(parents=True)
    (voice_mod / "sound" / "bank" / "fighter" / "se_mario_c00.nus3audio").write_bytes(b"sfx")

    source = tmp_path / "downloads" / "Mario Skin"
    (source / "fighter" / "mario" / "model" / "body" / "c00").mkdir(parents=True)
    (source / "fighter" / "mario" / "model" / "body" / "c00" / "model.bin").write_bytes(b"skin")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_mario_00.bntx").write_bytes(b"ui")

    summary = import_mod_package(source, mods_path)

    assert summary.items_imported == 1
    assert summary.slot_reassignments == 0
    assert (mods_path / "Mario Skin" / "fighter" / "mario" / "model" / "body" / "c00" / "model.bin").exists()
    assert not (mods_path / "Mario Skin" / "fighter" / "mario" / "model" / "body" / "c01").exists()


def test_import_mod_package_preserves_multi_slot_voice_pack(tmp_path: Path):
    source = tmp_path / "downloads" / "Sonic Voice Pack"
    (source / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (source / "sound" / "bank" / "fighter_voice" / "vc_sonic_c00.nus3audio").write_bytes(b"vc00")
    (source / "sound" / "bank" / "fighter_voice" / "vc_sonic_c01.nus3audio").write_bytes(b"vc01")
    (source / "sound" / "bank" / "fighter").mkdir(parents=True)
    (source / "sound" / "bank" / "fighter" / "se_sonic_c00.nus3audio").write_bytes(b"se00")
    (source / "sound" / "bank" / "fighter" / "se_sonic_c01.nus3audio").write_bytes(b"se01")

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    summary = import_mod_package(source, mods_path)

    assert summary.items_imported == 1
    assert summary.slot_reassignments == 0
    assert (mods_path / "Sonic Voice Pack" / "sound" / "bank" / "fighter_voice" / "vc_sonic_c00.nus3audio").exists()
    assert (mods_path / "Sonic Voice Pack" / "sound" / "bank" / "fighter_voice" / "vc_sonic_c01.nus3audio").exists()
    assert not any("Selected base skin" in warning for warning in summary.warnings)


def test_import_mod_package_can_replace_existing_mod_without_self_conflict(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    existing = mods_path / "Mario Skin"
    (existing / "fighter" / "mario" / "model" / "body" / "c00").mkdir(parents=True)
    (existing / "fighter" / "mario" / "model" / "body" / "c00" / "old.bin").write_bytes(b"old")
    (existing / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (existing / "ui" / "replace" / "chara" / "chara_0" / "chara_0_mario_00.bntx").write_bytes(b"old-ui")

    source = tmp_path / "downloads" / "Mario Skin"
    (source / "fighter" / "mario" / "model" / "body" / "c00").mkdir(parents=True)
    (source / "fighter" / "mario" / "model" / "body" / "c00" / "new.bin").write_bytes(b"new")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_mario_00.bntx").write_bytes(b"new-ui")

    summary = import_mod_package(source, mods_path)

    assert summary.items_imported == 1
    assert summary.slot_reassignments == 0
    assert summary.replaced_paths == 1
    assert (mods_path / "Mario Skin" / "fighter" / "mario" / "model" / "body" / "c00" / "new.bin").exists()
    assert not (mods_path / "Mario Skin" / "fighter" / "mario" / "model" / "body" / "c00" / "old.bin").exists()


def test_choose_primary_skin_slot_prefers_name_hint_when_present() -> None:
    fighter, slot = choose_primary_skin_slot({"donkey": [0, 6]}, ["Sonic the Werehog over DK C06"])
    assert fighter == "donkey"
    assert slot == 6


def test_slot_analysis_prefers_model_slot_over_generic_motion_slot() -> None:
    analysis = analyze_relative_paths(
        [
            "fighter/mario/motion/body/c00/a00wait1.nuanmb",
            "fighter/mario/model/body/c02/model.numshb",
            "ui/replace/chara/chara_0/chara_0_mario_02.bntx",
        ],
        ["Vegeta"],
    )
    assert analysis.primary_fighter == "mario"
    assert analysis.primary_slot == 2


def test_slot_analysis_detects_effect_only_slot_without_marking_visual() -> None:
    analysis = analyze_relative_paths(
        [
            "effect/fighter/sonic/ef_sonic_c07.eff",
            "effect/fighter/sonic/ef_sonic_c07oldold.eff",
        ],
        ["True Hyper Sonic Effects (c07)"],
    )
    assert analysis.primary_fighter == "sonic"
    assert analysis.primary_slot == 7
    assert analysis.fighter_slots == {"sonic": [7]}
    assert analysis.visual_fighter_slots == {}
    assert not analysis.has_visual_skin_slot


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


def test_import_plugin_package_routes_disabled_plugins_to_disabled_folder(tmp_path: Path):
    source = tmp_path / "plugin_pkg"
    source.mkdir(parents=True)
    (source / "liblegacy.nro.disabled").write_bytes(b"legacy-disabled")

    sdmc = tmp_path / "sdmc"
    sdmc.mkdir(parents=True)
    plugins_path = sdmc / "atmosphere" / "contents" / SSBU_TITLE_ID / "romfs" / "skyline" / "plugins"
    summary = import_plugin_package(source, sdmc, plugins_path)

    assert summary.plugin_files >= 1
    assert not (plugins_path / "liblegacy.nro.disabled").exists()
    assert (plugins_path.parent / "disabled_plugins" / "liblegacy.nro").exists()
