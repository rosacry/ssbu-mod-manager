import json
from pathlib import Path
import shutil
import zipfile

from src.core.content_importer import (
    _build_multi_slot_pack_options,
    apply_mod_camera_pack_scope,
    apply_mod_effect_pack_scope,
    apply_mod_voice_pack_scope,
    import_mod_package,
    import_plugin_package,
    inspect_mod_effect_pack,
    inspect_mod_voice_pack,
    repair_installed_mods,
)
from src.core.skin_slot_utils import analyze_mod_directory, analyze_relative_paths, choose_primary_skin_slot
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


def test_import_mod_package_defaults_to_base_slot_for_multi_slot_pack(tmp_path: Path):
    source = tmp_path / "downloads" / "Sonic Forms"
    (source / "fighter" / "sonic" / "model" / "body" / "c02").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c02" / "model.bin").write_bytes(b"c02")
    (source / "fighter" / "sonic" / "model" / "body" / "c03").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c03" / "model.bin").write_bytes(b"c03")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_02.bntx").write_bytes(b"ui2")
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_03.bntx").write_bytes(b"ui3")

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    summary = import_mod_package(source, mods_path)

    assert summary.items_imported == 1
    assert (mods_path / "Sonic Forms [sonic c02]" / "fighter" / "sonic" / "model" / "body" / "c02" / "model.bin").exists()
    assert not (mods_path / "Sonic Forms [sonic c02]" / "fighter" / "sonic" / "model" / "body" / "c03").exists()
    assert any("Selected base skin sonic c02" in warning for warning in summary.warnings)


def test_import_mod_package_can_split_multi_slot_pack_with_selector(tmp_path: Path):
    source = tmp_path / "downloads" / "Nazo Pack"
    (source / "fighter" / "sonic" / "model" / "body" / "c02").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c02" / "model.bin").write_bytes(b"c02")
    (source / "fighter" / "sonic" / "model" / "body" / "c03").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c03" / "model.bin").write_bytes(b"c03")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_02.bntx").write_bytes(b"ui2")
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_03.bntx").write_bytes(b"ui3")

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    seen_options = []

    def resolver(info):
        seen_options.extend(option.option_id for option in info.options)
        return ["sonic:c02", "sonic:c03"]

    summary = import_mod_package(source, mods_path, multi_slot_pack_resolver=resolver)

    assert summary.items_imported == 2
    assert seen_options == ["sonic:c02", "sonic:c03"]
    assert (mods_path / "Nazo Pack [sonic c02]" / "fighter" / "sonic" / "model" / "body" / "c02" / "model.bin").exists()
    assert (mods_path / "Nazo Pack [sonic c03]" / "fighter" / "sonic" / "model" / "body" / "c03" / "model.bin").exists()
    assert any("Selected 2 skin(s)" in warning for warning in summary.warnings)


def test_import_mod_package_uses_msg_name_labels_for_multi_slot_picker(tmp_path: Path):
    source = tmp_path / "downloads" / "Nazo Pack"
    (source / "fighter" / "sonic" / "model" / "body" / "c02").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c02" / "model.bin").write_bytes(b"c02")
    (source / "fighter" / "sonic" / "model" / "body" / "c03").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c03" / "model.bin").write_bytes(b"c03")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_02.bntx").write_bytes(b"ui2")
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_03.bntx").write_bytes(b"ui3")
    (source / "ui" / "message").mkdir(parents=True)
    (source / "ui" / "message" / "msg_name.xmsbt").write_text(
        """<?xml version="1.0" encoding="utf-16"?>
<xmsbt>
  <entry label="nam_chr1_02_sonic">
    <text>Nazo</text>
  </entry>
  <entry label="nam_chr1_03_sonic">
    <text>Hyper Perfect Nazo</text>
  </entry>
</xmsbt>
""",
        encoding="utf-16",
    )

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    seen_labels = []

    def resolver(info):
        seen_labels.extend(option.label for option in info.options)
        return [option.option_id for option in info.options]

    summary = import_mod_package(source, mods_path, multi_slot_pack_resolver=resolver)

    assert summary.items_imported == 2
    assert seen_labels == [
        "Nazo (sonic c02)",
        "Hyper Perfect Nazo (sonic c03)",
    ]


def test_import_mod_package_falls_back_to_ui_chara_db_labels_for_multi_slot_picker(tmp_path: Path):
    source = tmp_path / "downloads" / "Sonic Forms"
    (source / "fighter" / "sonic" / "model" / "body" / "c02").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c02" / "model.bin").write_bytes(b"c02")
    (source / "fighter" / "sonic" / "model" / "body" / "c03").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c03" / "model.bin").write_bytes(b"c03")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_02.bntx").write_bytes(b"ui2")
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_03.bntx").write_bytes(b"ui3")
    (source / "ui" / "param" / "database").mkdir(parents=True)
    (source / "ui" / "param" / "database" / "ui_chara_db.prcxml").write_text(
        """<struct>
  <hash40 hash="characall_label_c02">vc_narration_characall_dark_sonic</hash40>
  <hash40 hash="characall_label_c03">vc_narration_characall_super_sonic</hash40>
</struct>
""",
        encoding="utf-8",
    )

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    seen_labels = []

    def resolver(info):
        seen_labels.extend(option.label for option in info.options)
        return [option.option_id for option in info.options]

    summary = import_mod_package(source, mods_path, multi_slot_pack_resolver=resolver)

    assert summary.items_imported == 2
    assert seen_labels == [
        "Dark Sonic (sonic c02)",
        "Super Sonic (sonic c03)",
    ]


def test_import_mod_package_hides_css_only_pseudo_fighters_when_metadata_labels_real_slots(tmp_path: Path):
    source = tmp_path / "downloads" / "Nazo Pack"
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_03.bntx").write_bytes(b"ui3")
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_04.bntx").write_bytes(b"ui4")
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_nazo_00.bntx").write_bytes(b"css0")
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_nazo_01.bntx").write_bytes(b"css1")
    (source / "ui" / "message").mkdir(parents=True)
    (source / "ui" / "message" / "msg_name.xmsbt").write_text(
        """<?xml version="1.0" encoding="utf-16"?>
<xmsbt>
  <entry label="nam_chr1_03_sonic">
    <text>Nazo</text>
  </entry>
  <entry label="nam_chr1_04_sonic">
    <text>Wrath of Nazo</text>
  </entry>
</xmsbt>
""",
        encoding="utf-16",
    )

    analysis = analyze_mod_directory(source, [source.name])
    options = _build_multi_slot_pack_options(source, analysis)

    assert [option.option_id for option in options] == ["sonic:c03", "sonic:c04"]


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


def test_import_mod_package_conflict_info_uses_friendly_slot_labels(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    existing = mods_path / "Existing Sonic"
    (existing / "fighter" / "sonic" / "model" / "body" / "c03").mkdir(parents=True)
    (existing / "fighter" / "sonic" / "model" / "body" / "c03" / "existing.bin").write_bytes(b"old")
    (existing / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (existing / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_03.bntx").write_bytes(b"old-ui")
    (existing / "ui" / "message").mkdir(parents=True)
    (existing / "ui" / "message" / "msg_name.xmsbt").write_text(
        """<?xml version="1.0" encoding="utf-16"?>
<xmsbt>
  <entry label="nam_chr1_03_sonic">
    <text>Dark Super Sonic</text>
  </entry>
</xmsbt>
""",
        encoding="utf-16",
    )

    source = tmp_path / "downloads" / "Nazo Sonic"
    (source / "fighter" / "sonic" / "model" / "body" / "c03").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c03" / "new.bin").write_bytes(b"new")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_03.bntx").write_bytes(b"new-ui")
    (source / "ui" / "message").mkdir(parents=True)
    (source / "ui" / "message" / "msg_name.xmsbt").write_text(
        """<?xml version="1.0" encoding="utf-16"?>
<xmsbt>
  <entry label="nam_chr1_03_sonic">
    <text>Nazo</text>
  </entry>
</xmsbt>
""",
        encoding="utf-16",
    )

    seen = {}

    def resolver(conflict):
        seen["requested"] = conflict.requested_label
        seen["existing"] = conflict.conflicting_mod_descriptions["Existing Sonic"]
        seen["open"] = conflict.open_slot_descriptions[0]
        return "skip"

    try:
        import_mod_package(source, mods_path, slot_conflict_resolver=resolver)
    except ValueError:
        pass

    assert seen["requested"] == "Nazo (sonic c03)"
    assert seen["existing"] == "Dark Super Sonic (sonic c03)"
    assert seen["open"] == "Open default slot (c00)"


def test_import_mod_package_move_incoming_warning_uses_friendly_slot_labels(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    existing = mods_path / "Existing Sonic"
    (existing / "fighter" / "sonic" / "model" / "body" / "c03").mkdir(parents=True)
    (existing / "fighter" / "sonic" / "model" / "body" / "c03" / "existing.bin").write_bytes(b"old")
    (existing / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (existing / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_03.bntx").write_bytes(b"old-ui")

    source = tmp_path / "downloads" / "Nazo Sonic"
    (source / "fighter" / "sonic" / "model" / "body" / "c03").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c03" / "new.bin").write_bytes(b"new")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_03.bntx").write_bytes(b"new-ui")
    (source / "ui" / "message").mkdir(parents=True)
    (source / "ui" / "message" / "msg_name.xmsbt").write_text(
        """<?xml version="1.0" encoding="utf-16"?>
<xmsbt>
  <entry label="nam_chr1_03_sonic">
    <text>Nazo</text>
  </entry>
</xmsbt>
""",
        encoding="utf-16",
    )

    summary = import_mod_package(source, mods_path, slot_conflict_resolver=lambda _conflict: "move_incoming")

    assert summary.slot_reassignments == 1
    assert any(
        "Nazo (sonic c02)" in warning and "instead of Nazo (sonic c03)" in warning
        for warning in summary.warnings
    )


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


def test_import_mod_package_prunes_exact_support_files_from_existing_support_mod(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    existing = mods_path / "Sonic Voice Pack"
    (existing / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (existing / "sound" / "bank" / "fighter_voice" / "vc_sonic_c00.nus3audio").write_bytes(b"old-vc00")
    (existing / "sound" / "bank" / "fighter_voice" / "vc_sonic_c01.nus3audio").write_bytes(b"old-vc01")
    (existing / "sound" / "bank" / "fighter").mkdir(parents=True)
    (existing / "sound" / "bank" / "fighter" / "se_sonic_c00.nus3audio").write_bytes(b"old-se00")
    (existing / "sound" / "bank" / "fighter" / "se_sonic_c01.nus3audio").write_bytes(b"old-se01")
    (existing / "ui" / "message").mkdir(parents=True)
    (existing / "ui" / "message" / "msg_name.xmsbt").write_text(
        """<?xml version="1.0" encoding="utf-16"?>
<xmsbt>
  <entry label="nam_chr1_00_sonic">
    <text>Modern Sonic</text>
  </entry>
  <entry label="nam_chr1_01_sonic">
    <text>Dark Sonic</text>
  </entry>
</xmsbt>
""",
        encoding="utf-16",
    )

    source = tmp_path / "downloads" / "Sonic Skin"
    (source / "fighter" / "sonic" / "model" / "body" / "c00").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c00" / "model.bin").write_bytes(b"skin")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_00.bntx").write_bytes(b"ui")
    (source / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (source / "sound" / "bank" / "fighter_voice" / "vc_sonic_c00.nus3audio").write_bytes(b"new-vc00")
    (source / "sound" / "bank" / "fighter").mkdir(parents=True)
    (source / "sound" / "bank" / "fighter" / "se_sonic_c00.nus3audio").write_bytes(b"new-se00")

    summary = import_mod_package(source, mods_path)

    assert summary.items_imported == 1
    assert summary.support_mod_adjustments == 1
    assert summary.support_files_pruned == 2
    assert not (mods_path / "Sonic Voice Pack" / "sound" / "bank" / "fighter_voice" / "vc_sonic_c00.nus3audio").exists()
    assert not (mods_path / "Sonic Voice Pack" / "sound" / "bank" / "fighter" / "se_sonic_c00.nus3audio").exists()
    assert (mods_path / "Sonic Voice Pack" / "sound" / "bank" / "fighter_voice" / "vc_sonic_c01.nus3audio").exists()
    assert (mods_path.parent / "_import_backups" / "Sonic Voice Pack" / "sound" / "bank" / "fighter_voice" / "vc_sonic_c00.nus3audio").exists()
    assert (mods_path / "Sonic Skin" / "sound" / "bank" / "fighter_voice" / "vc_sonic_c00.nus3audio").exists()
    assert any(
        "Modern Sonic (sonic c00)" in warning and "_import_backups/Sonic Voice Pack" in warning
        for warning in summary.warnings
    )


def test_import_mod_package_prunes_support_files_after_reslotting(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    existing_skin = mods_path / "Existing Sonic Skin"
    (existing_skin / "fighter" / "sonic" / "model" / "body" / "c06").mkdir(parents=True)
    (existing_skin / "fighter" / "sonic" / "model" / "body" / "c06" / "existing.bin").write_bytes(b"skin")
    (existing_skin / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (existing_skin / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_06.bntx").write_bytes(b"ui")

    support = mods_path / "Broad Sonic Voice Pack"
    (support / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (support / "sound" / "bank" / "fighter_voice" / "vc_sonic_c05.nus3audio").write_bytes(b"vc05")
    (support / "sound" / "bank" / "fighter_voice" / "vc_sonic_c06.nus3audio").write_bytes(b"vc06")
    (support / "sound" / "bank" / "fighter").mkdir(parents=True)
    (support / "sound" / "bank" / "fighter" / "se_sonic_c05.nus3audio").write_bytes(b"se05")
    (support / "sound" / "bank" / "fighter" / "se_sonic_c06.nus3audio").write_bytes(b"se06")

    source = tmp_path / "downloads" / "Incoming Sonic Skin"
    (source / "fighter" / "sonic" / "model" / "body" / "c06").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c06" / "new.bin").write_bytes(b"new")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_06.bntx").write_bytes(b"new-ui")
    (source / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (source / "sound" / "bank" / "fighter_voice" / "vc_sonic_c06.nus3audio").write_bytes(b"new-vc")
    (source / "sound" / "bank" / "fighter").mkdir(parents=True)
    (source / "sound" / "bank" / "fighter" / "se_sonic_c06.nus3audio").write_bytes(b"new-se")

    summary = import_mod_package(source, mods_path)

    assert summary.items_imported == 1
    assert summary.slot_reassignments == 1
    assert summary.support_mod_adjustments == 1
    assert summary.support_files_pruned == 2
    assert (mods_path / "Incoming Sonic Skin" / "fighter" / "sonic" / "model" / "body" / "c05" / "new.bin").exists()
    assert (mods_path / "Incoming Sonic Skin" / "sound" / "bank" / "fighter_voice" / "vc_sonic_c05.nus3audio").exists()
    assert not (mods_path / "Broad Sonic Voice Pack" / "sound" / "bank" / "fighter_voice" / "vc_sonic_c05.nus3audio").exists()
    assert (mods_path / "Broad Sonic Voice Pack" / "sound" / "bank" / "fighter_voice" / "vc_sonic_c06.nus3audio").exists()


def test_import_mod_package_renames_reslotted_target_when_name_has_slot_hint(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    existing = mods_path / "Existing Sonic"
    (existing / "fighter" / "sonic" / "model" / "body" / "c06").mkdir(parents=True)
    (existing / "fighter" / "sonic" / "model" / "body" / "c06" / "existing.bin").write_bytes(b"skin")
    (existing / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (existing / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_06.bntx").write_bytes(b"ui")

    source = tmp_path / "downloads" / "Riders Sonic C06 (by Watapascul)"
    (source / "fighter" / "sonic" / "model" / "body" / "c06").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c06" / "new.bin").write_bytes(b"new")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_06.bntx").write_bytes(b"new-ui")

    summary = import_mod_package(source, mods_path)

    assert summary.items_imported == 1
    assert summary.slot_reassignments == 1
    assert (mods_path / "Riders Sonic C05 (by Watapascul)" / "fighter" / "sonic" / "model" / "body" / "c05" / "new.bin").exists()
    assert not (mods_path / "Riders Sonic C06 (by Watapascul)").exists()


def test_import_mod_package_does_not_prune_support_files_from_visual_mod(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    existing = mods_path / "Visual Sonic Pack"
    (existing / "fighter" / "sonic" / "model" / "body" / "c00").mkdir(parents=True)
    (existing / "fighter" / "sonic" / "model" / "body" / "c00" / "model.bin").write_bytes(b"skin")
    (existing / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (existing / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_00.bntx").write_bytes(b"ui")
    (existing / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (existing / "sound" / "bank" / "fighter_voice" / "vc_sonic_c00.nus3audio").write_bytes(b"vc")

    source = tmp_path / "downloads" / "Voice Override"
    (source / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (source / "sound" / "bank" / "fighter_voice" / "vc_sonic_c00.nus3audio").write_bytes(b"new-vc")

    summary = import_mod_package(source, mods_path)

    assert summary.items_imported == 1
    assert summary.support_mod_adjustments == 0
    assert any("still shares 1 exact support file" in warning for warning in summary.warnings)
    assert (mods_path / "Visual Sonic Pack" / "sound" / "bank" / "fighter_voice" / "vc_sonic_c00.nus3audio").exists()


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


def test_inspect_mod_voice_pack_prefers_visual_slot_when_available(tmp_path: Path):
    mod_path = tmp_path / "mods" / "Sonic Skin"
    (mod_path / "fighter" / "sonic" / "model" / "body" / "c05").mkdir(parents=True)
    (mod_path / "fighter" / "sonic" / "model" / "body" / "c05" / "model.bin").write_bytes(b"skin")
    (mod_path / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (mod_path / "sound" / "bank" / "fighter_voice" / "vc_sonic_c05.nus3audio").write_bytes(b"voice")

    info = inspect_mod_voice_pack(mod_path)

    assert info is not None
    assert info.fighter == "sonic"
    assert info.source_slots == [5]
    assert info.visual_slots == [5]
    assert info.recommended_source_slot == 5


def test_inspect_mod_voice_pack_includes_msg_name_slot_labels(tmp_path: Path):
    mod_path = tmp_path / "mods" / "Nazo Voice"
    (mod_path / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (mod_path / "sound" / "bank" / "fighter_voice" / "vc_sonic_c03.nus3audio").write_bytes(b"voice")
    (mod_path / "ui" / "message").mkdir(parents=True)
    (mod_path / "ui" / "message" / "msg_name.xmsbt").write_text(
        """<?xml version="1.0" encoding="utf-16"?>
<xmsbt>
  <entry label="nam_chr1_03_sonic">
    <text>Nazo</text>
  </entry>
</xmsbt>
""",
        encoding="utf-16",
    )

    info = inspect_mod_voice_pack(mod_path)

    assert info is not None
    assert info.slot_labels == {3: "Nazo"}


def test_inspect_mod_voice_pack_falls_back_to_ui_chara_db_slot_labels(tmp_path: Path):
    mod_path = tmp_path / "mods" / "Dark Sonic Voice"
    (mod_path / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (mod_path / "sound" / "bank" / "fighter_voice" / "vc_sonic_c02.nus3audio").write_bytes(b"voice")
    (mod_path / "ui" / "param" / "database").mkdir(parents=True)
    (mod_path / "ui" / "param" / "database" / "ui_chara_db.prcxml").write_text(
        """<struct>
  <hash40 hash="characall_label_c02">vc_narration_characall_dark_sonic</hash40>
</struct>
""",
        encoding="utf-8",
    )

    info = inspect_mod_voice_pack(mod_path)

    assert info is not None
    assert info.slot_labels == {2: "Dark Sonic"}


def test_apply_mod_voice_pack_scope_can_retarget_to_single_slot(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_path = mods_path / "Sonic Skin"
    (mod_path / "fighter" / "sonic" / "model" / "body" / "c05").mkdir(parents=True)
    (mod_path / "fighter" / "sonic" / "model" / "body" / "c05" / "model.bin").write_bytes(b"skin")
    (mod_path / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (mod_path / "sound" / "bank" / "fighter_voice" / "vc_sonic_c05.nus3audio").write_bytes(b"voice")
    (mod_path / "sound" / "bank" / "fighter").mkdir(parents=True)
    (mod_path / "sound" / "bank" / "fighter" / "se_sonic_c05.nus3audio").write_bytes(b"sfx")

    broad = mods_path / "Broad Voice"
    (broad / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (broad / "sound" / "bank" / "fighter_voice" / "vc_sonic_c02.nus3audio").write_bytes(b"old-vc")
    (broad / "sound" / "bank" / "fighter").mkdir(parents=True)
    (broad / "sound" / "bank" / "fighter" / "se_sonic_c02.nus3audio").write_bytes(b"old-se")

    summary = apply_mod_voice_pack_scope(mod_path, mods_path, mode="single_slot", source_slot=5, target_slot=2)

    assert summary.files_written == 2
    assert summary.target_slots == [2]
    assert summary.support_mod_adjustments == 1
    assert not (broad / "sound" / "bank" / "fighter_voice" / "vc_sonic_c02.nus3audio").exists()
    assert (mod_path / "sound" / "bank" / "fighter_voice" / "vc_sonic_c02.nus3audio").exists()
    assert not (mod_path / "sound" / "bank" / "fighter_voice" / "vc_sonic_c05.nus3audio").exists()


def test_apply_mod_voice_pack_scope_can_expand_character_wide(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_path = mods_path / "Sonic Skin"
    (mod_path / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (mod_path / "sound" / "bank" / "fighter_voice" / "vc_sonic_c05.nus3audio").write_bytes(b"voice")

    summary = apply_mod_voice_pack_scope(mod_path, mods_path, mode="character_wide", source_slot=5)

    assert summary.files_written == 8
    assert summary.target_slots == list(range(8))
    for slot in range(8):
        assert (mod_path / "sound" / "bank" / "fighter_voice" / f"vc_sonic_c{slot:02d}.nus3audio").exists()


def test_import_mod_package_disables_fully_pruned_support_mod_with_friendly_reporting(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    existing = mods_path / "Nazo Voice Pack"
    (existing / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (existing / "sound" / "bank" / "fighter_voice" / "vc_sonic_c03.nus3audio").write_bytes(b"old-vc")
    (existing / "sound" / "bank" / "fighter").mkdir(parents=True)
    (existing / "sound" / "bank" / "fighter" / "se_sonic_c03.nus3audio").write_bytes(b"old-se")
    (existing / "ui" / "message").mkdir(parents=True)
    (existing / "ui" / "message" / "msg_name.xmsbt").write_text(
        """<?xml version="1.0" encoding="utf-16"?>
<xmsbt>
  <entry label="nam_chr1_03_sonic">
    <text>Nazo</text>
  </entry>
</xmsbt>
""",
        encoding="utf-16",
    )

    source = tmp_path / "downloads" / "Nazo Skin"
    (source / "fighter" / "sonic" / "model" / "body" / "c03").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c03" / "model.bin").write_bytes(b"skin")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_03.bntx").write_bytes(b"ui")
    (source / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (source / "sound" / "bank" / "fighter_voice" / "vc_sonic_c03.nus3audio").write_bytes(b"new-vc")
    (source / "sound" / "bank" / "fighter").mkdir(parents=True)
    (source / "sound" / "bank" / "fighter" / "se_sonic_c03.nus3audio").write_bytes(b"new-se")

    summary = import_mod_package(source, mods_path)

    assert summary.support_mod_adjustments == 1
    assert summary.support_files_pruned == 2
    assert not existing.exists()
    assert (mods_path.parent / "disabled_mods" / "Nazo Voice Pack").exists()
    assert any(
        "Disabled support mod 'Nazo Voice Pack' (Nazo (sonic c03))" in warning
        and "disabled_mods/Nazo Voice Pack" in warning
        for warning in summary.warnings
    )


def test_inspect_mod_effect_pack_detects_slot_scoped_effects(tmp_path: Path):
    mod_path = tmp_path / "mods" / "Sonic Effects"
    (mod_path / "effect" / "fighter" / "sonic").mkdir(parents=True)
    (mod_path / "effect" / "fighter" / "sonic" / "ef_sonic_c07.eff").write_bytes(b"effect")

    info = inspect_mod_effect_pack(mod_path)

    assert info is not None
    assert info.support_kind == "effect"
    assert info.fighter == "sonic"
    assert info.source_slots == [7]


def test_apply_mod_effect_pack_scope_can_retarget_to_single_slot(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_path = mods_path / "Sonic Effects"
    (mod_path / "effect" / "fighter" / "sonic").mkdir(parents=True)
    (mod_path / "effect" / "fighter" / "sonic" / "ef_sonic_c05.eff").write_bytes(b"effect")

    broad = mods_path / "Broad Effects"
    (broad / "effect" / "fighter" / "sonic").mkdir(parents=True)
    (broad / "effect" / "fighter" / "sonic" / "ef_sonic_c02.eff").write_bytes(b"old-effect")

    summary = apply_mod_effect_pack_scope(mod_path, mods_path, mode="single_slot", source_slot=5, target_slot=2)

    assert summary.support_kind == "effect"
    assert summary.files_written == 1
    assert summary.target_slots == [2]
    assert summary.support_mod_adjustments == 1
    assert not (broad / "effect" / "fighter" / "sonic" / "ef_sonic_c02.eff").exists()
    assert (mod_path / "effect" / "fighter" / "sonic" / "ef_sonic_c02.eff").exists()
    assert not (mod_path / "effect" / "fighter" / "sonic" / "ef_sonic_c05.eff").exists()


def test_apply_mod_camera_pack_scope_can_expand_character_wide(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_path = mods_path / "Sonic Camera"
    (mod_path / "camera" / "fighter" / "sonic" / "c05").mkdir(parents=True)
    (mod_path / "camera" / "fighter" / "sonic" / "c05" / "j02win1.nuanmb").write_bytes(b"camera")

    summary = apply_mod_camera_pack_scope(mod_path, mods_path, mode="character_wide", source_slot=5)

    assert summary.support_kind == "camera"
    assert summary.files_written == 8
    assert summary.target_slots == list(range(8))
    for slot in range(8):
        assert (mod_path / "camera" / "fighter" / "sonic" / f"c{slot:02d}" / "j02win1.nuanmb").exists()


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


def test_import_mod_package_normalizes_legacy_config_txt_to_config_json(tmp_path: Path):
    source = tmp_path / "downloads" / "Mario White"
    (source / "fighter" / "mario" / "model" / "body" / "c07").mkdir(parents=True)
    (source / "fighter" / "mario" / "model" / "body" / "c07" / "model.bin").write_bytes(b"skin")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_mario_07.bntx").write_bytes(b"ui")
    (source / "effect" / "fighter" / "mario").mkdir(parents=True)
    (source / "effect" / "fighter" / "mario" / "ef_mario_c07.eff").write_bytes(b"effect")
    (source / "config.txt").write_text(
        json.dumps(
            {
                "new-dir-files": {
                    "fighter/mario/c07": [
                        "effect/fighter/mario/ef_mario_c07.eff",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    import_mod_package(source, mods_path)

    config_path = mods_path / "Mario White" / "config.json"
    assert config_path.exists()
    assert not (mods_path / "Mario White" / "config.txt").exists()
    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "new-dir-files": {
            "fighter/mario/c07": [
                "effect/fighter/mario/ef_mario_c07.eff",
                "fighter/mario/model/body/c07/model.bin",
            ]
        }
    }


def test_import_mod_package_repairs_reslotted_visual_effect_manifest_from_source_config(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    for slot in (0, 2, 3, 4, 5, 6, 7):
        existing = mods_path / f"Occupied Edge c{slot:02d}"
        (existing / "fighter" / "edge" / "model" / "body" / f"c{slot:02d}").mkdir(parents=True)
        (existing / "fighter" / "edge" / "model" / "body" / f"c{slot:02d}" / "model.bin").write_bytes(b"occupied")
        (existing / "ui" / "replace_patch" / "chara" / "chara_0").mkdir(parents=True)
        (existing / "ui" / "replace_patch" / "chara" / "chara_0" / f"chara_0_edge_{slot:02d}.bntx").write_bytes(b"ui")

    source = tmp_path / "downloads" / "Sugeru Geto"
    (source / "fighter" / "edge" / "model" / "body" / "c03").mkdir(parents=True)
    (source / "fighter" / "edge" / "model" / "body" / "c03" / "model.bin").write_bytes(b"skin")
    (source / "ui" / "replace_patch" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace_patch" / "chara" / "chara_0" / "chara_0_edge_03.bntx").write_bytes(b"ui")
    (source / "Fighter" / "edge" / "trail").mkdir(parents=True)
    (source / "Fighter" / "edge" / "ef_edge_c01.eff").write_bytes(b"effect")
    (source / "Fighter" / "edge" / "trail" / "tex_edge_sword01.nutexb").write_bytes(b"trail")
    (source / "config.json").write_text(
        json.dumps(
            {
                "new-dir-files": {
                    "fighter/edge/c03": [
                        "effect/fighter/edge/ef_edge_c01.eff",
                        "effect/fighter/edge/trail_c01/tex_edge_sword01.nutexb",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    summary = import_mod_package(source, mods_path, slot_conflict_resolver=lambda _conflict: "move_incoming")

    assert summary.slot_reassignments == 1
    dest = mods_path / "Sugeru Geto"
    assert (dest / "fighter" / "edge" / "model" / "body" / "c01" / "model.bin").exists()
    assert (dest / "effect" / "fighter" / "edge" / "ef_edge_c01.eff").exists()
    assert (dest / "effect" / "fighter" / "edge" / "trail_c01" / "tex_edge_sword01.nutexb").exists()
    assert json.loads((dest / "config.json").read_text(encoding="utf-8")) == {
        "new-dir-files": {
            "fighter/edge/c01": [
                "effect/fighter/edge/ef_edge_c01.eff",
                "effect/fighter/edge/trail_c01/tex_edge_sword01.nutexb",
                "fighter/edge/model/body/c01/model.bin",
            ]
        }
    }


def test_import_mod_package_synthesizes_config_for_generic_fighter_effect_files(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    existing = mods_path / "Occupied Cloud"
    (existing / "fighter" / "cloud" / "model" / "body" / "c00").mkdir(parents=True)
    (existing / "fighter" / "cloud" / "model" / "body" / "c00" / "model.bin").write_bytes(b"occupied")
    (existing / "ui" / "replace" / "chara" / "chara_1").mkdir(parents=True)
    (existing / "ui" / "replace" / "chara" / "chara_1" / "chara_1_cloud_00.bntx").write_bytes(b"ui")

    source = tmp_path / "downloads" / "Super Sonic Over Cloud"
    (source / "fighter" / "cloud" / "model" / "body" / "c00").mkdir(parents=True)
    for filename, payload in {
        "model.nuhlpb": b"h",
        "model.numatb": b"mat",
        "model.numdlb": b"d",
        "model.numshb": b"s",
        "model.numshexb": b"x",
        "model.nusktb": b"k",
    }.items():
        (source / "fighter" / "cloud" / "model" / "body" / "c00" / filename).write_bytes(payload)
    (source / "ui" / "replace" / "chara" / "chara_1").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_1" / "chara_1_cloud_00.bntx").write_bytes(b"ui")
    (source / "fighter" / "cloud" / "model" / "fusionsword" / "c00").mkdir(parents=True)
    (source / "fighter" / "cloud" / "model" / "fusionsword" / "c00" / "def_cloud_004_col.nutexb").write_bytes(b"sword")
    (source / "effect" / "fighter" / "cloud" / "trail").mkdir(parents=True)
    (source / "effect" / "fighter" / "cloud" / "ef_cloud.eff").write_bytes(b"effect")
    (source / "effect" / "fighter" / "cloud" / "trail" / "tex_cloud_sword1.nutexb").write_bytes(b"trail")

    summary = import_mod_package(source, mods_path)

    assert summary.slot_reassignments == 1
    payload = json.loads((mods_path / "Super Sonic Over Cloud" / "config.json").read_text(encoding="utf-8"))
    assert payload == {
        "new-dir-files": {
            "fighter/cloud/c02": [
                "fighter/cloud/model/fusionsword/c02/def_cloud_004_col.nutexb",
                "effect/fighter/cloud/ef_cloud.eff",
                "effect/fighter/cloud/trail/tex_cloud_sword1.nutexb",
            ]
        }
    }


def test_import_mod_package_synthesizes_config_for_slot_specific_fighter_files_without_source_manifest(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    source = tmp_path / "downloads" / "Cloud Pack"
    (source / "fighter" / "cloud" / "model" / "body" / "c00").mkdir(parents=True)
    (source / "fighter" / "cloud" / "model" / "body" / "c00" / "egle001_body_col.nutexb").write_bytes(b"tex")
    for filename, payload in {
        "model.nuhlpb": b"h",
        "model.numatb": b"mat",
        "model.numdlb": b"d",
        "model.numshb": b"s",
        "model.numshexb": b"x",
        "model.nusktb": b"k",
    }.items():
        (source / "fighter" / "cloud" / "model" / "body" / "c00" / filename).write_bytes(payload)
    (source / "fighter" / "cloud" / "model" / "fusionsword" / "c00").mkdir(parents=True)
    (source / "fighter" / "cloud" / "model" / "fusionsword" / "c00" / "def_cloud_004_col.nutexb").write_bytes(b"sword")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_cloud_00.bntx").write_bytes(b"ui")

    import_mod_package(source, mods_path)

    payload = json.loads((mods_path / "Cloud Pack" / "config.json").read_text(encoding="utf-8"))
    assert payload == {
        "new-dir-files": {
            "fighter/cloud/c00": [
                "fighter/cloud/model/body/c00/egle001_body_col.nutexb",
                "fighter/cloud/model/fusionsword/c00/def_cloud_004_col.nutexb",
            ]
        }
    }


def test_import_mod_package_repairs_same_slot_visual_config_with_missing_entries(tmp_path: Path):
    source = tmp_path / "downloads" / "Skadi Byleth"
    (source / "fighter" / "master" / "model" / "body" / "c03").mkdir(parents=True)
    (source / "fighter" / "master" / "model" / "body" / "c03" / "alp_master_female_002_emi.nutexb").write_bytes(b"a")
    (source / "fighter" / "master" / "model" / "body" / "c03" / "def_master_female_001_emi.nutexb").write_bytes(b"b")
    (source / "fighter" / "master" / "model" / "body" / "c03" / "def_master_female_002_emi.nutexb").write_bytes(b"c")
    (source / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (source / "ui" / "replace" / "chara" / "chara_0" / "chara_0_master_03.bntx").write_bytes(b"ui")
    (source / "config.json").write_text(
        json.dumps(
            {
                "new_dir_files": {
                    "fighter/master/c01": [
                        "fighter/master/model/body/c01/alp_master_female_002_emi.nutexb",
                    ],
                    "fighter/master/c03": [
                        "fighter/master/model/body/c03/alp_master_female_002_emi.nutexb",
                        "fighter/master/model/body/c03/def_master_female_001_emi.nutexb",
                        "fighter/master/model/body/c03/def_master_female_002_emi.nutexb",
                    ],
                    "fighter/master/c05": [
                        "fighter/master/model/body/c05/def_master_female_001_emi.nutexb",
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    import_mod_package(source, mods_path)

    assert not (mods_path / "Skadi Byleth" / "config.json").exists()


def test_import_mod_package_sanitizes_non_visual_config_references_to_missing_files(tmp_path: Path):
    source = tmp_path / "downloads" / "Eternal Heart"
    (source / "stage" / "trail_castle" / "normal" / "model" / "ring_set").mkdir(parents=True)
    (source / "stage" / "trail_castle" / "normal" / "model" / "ring_set" / "white_col.nutexb").write_bytes(b"tex")
    (source / "config.json").write_text(
        json.dumps(
            {
                "new-dir-files": {
                    "stage/trail_castle/normal/model/ring_set": [
                        "stage/trail_castle/normal/model/ring_set/white_col.nutexb",
                        "stage/trail_castle/normal/model/ring_set/missing.nutexb",
                    ],
                    "stage/trail_castle/normal/model/empty_set": [],
                }
            }
        ),
        encoding="utf-8",
    )

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    import_mod_package(source, mods_path)

    payload = json.loads((mods_path / "Eternal Heart" / "config.json").read_text(encoding="utf-8"))
    assert payload == {
        "new-dir-files": {
            "stage/trail_castle/normal/model/ring_set": [
                "stage/trail_castle/normal/model/ring_set/white_col.nutexb",
            ],
            "stage/trail_castle/normal/model/empty_set": [],
        }
    }


def test_repair_installed_mods_normalizes_configs_and_synthesizes_missing_effect_manifest(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"

    mario = mods_path / "Mario White"
    (mario / "fighter" / "mario" / "model" / "body" / "c07").mkdir(parents=True)
    (mario / "fighter" / "mario" / "model" / "body" / "c07" / "model.bin").write_bytes(b"skin")
    (mario / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (mario / "ui" / "replace" / "chara" / "chara_0" / "chara_0_mario_07.bntx").write_bytes(b"ui")
    (mario / "effect" / "fighter" / "mario").mkdir(parents=True)
    (mario / "effect" / "fighter" / "mario" / "ef_mario_c07.eff").write_bytes(b"effect")
    (mario / "config.txt").write_text(
        json.dumps({"new-dir-files": {"fighter/mario/c07": ["effect/fighter/mario/ef_mario_c07.eff"]}}),
        encoding="utf-8",
    )

    cloud = mods_path / "Super Sonic Over Cloud"
    (cloud / "fighter" / "cloud" / "model" / "body" / "c06").mkdir(parents=True)
    for filename, payload in {
        "model.nuhlpb": b"h",
        "model.numatb": b"mat",
        "model.numdlb": b"d",
        "model.numshb": b"s",
        "model.numshexb": b"x",
        "model.nusktb": b"k",
    }.items():
        (cloud / "fighter" / "cloud" / "model" / "body" / "c06" / filename).write_bytes(payload)
    (cloud / "fighter" / "cloud" / "model" / "fusionsword" / "c06").mkdir(parents=True)
    (cloud / "fighter" / "cloud" / "model" / "fusionsword" / "c06" / "def_cloud_004_col.nutexb").write_bytes(b"sword")
    (cloud / "ui" / "replace" / "chara" / "chara_1").mkdir(parents=True)
    (cloud / "ui" / "replace" / "chara" / "chara_1" / "chara_1_cloud_06.bntx").write_bytes(b"ui")
    (cloud / "effect" / "fighter" / "cloud" / "trail").mkdir(parents=True)
    (cloud / "effect" / "fighter" / "cloud" / "ef_cloud.eff").write_bytes(b"effect")
    (cloud / "effect" / "fighter" / "cloud" / "trail" / "tex_cloud_sword1.nutexb").write_bytes(b"trail")

    summary = repair_installed_mods(mods_path)

    assert summary.mods_scanned == 2
    assert summary.configs_normalized == 1
    assert summary.configs_created == 1
    assert (mario / "config.json").exists()
    assert not (mario / "config.txt").exists()
    assert json.loads((cloud / "config.json").read_text(encoding="utf-8")) == {
        "new-dir-files": {
            "fighter/cloud/c06": [
                "fighter/cloud/model/fusionsword/c06/def_cloud_004_col.nutexb",
                "effect/fighter/cloud/ef_cloud.eff",
                "effect/fighter/cloud/trail/tex_cloud_sword1.nutexb",
            ]
        }
    }


def test_repair_installed_mods_merges_existing_slot_manifest_with_missing_fighter_files(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    cloud = mods_path / "Super Sonic Over Cloud"
    (cloud / "fighter" / "cloud" / "model" / "body" / "c06").mkdir(parents=True)
    for filename, payload in {
        "model.nuhlpb": b"h",
        "model.numatb": b"mat",
        "model.numdlb": b"d",
        "model.numshb": b"s",
        "model.numshexb": b"x",
        "model.nusktb": b"k",
    }.items():
        (cloud / "fighter" / "cloud" / "model" / "body" / "c06" / filename).write_bytes(payload)
    (cloud / "fighter" / "cloud" / "model" / "fusionsword" / "c06").mkdir(parents=True)
    (cloud / "fighter" / "cloud" / "model" / "fusionsword" / "c06" / "def_cloud_004_col.nutexb").write_bytes(b"sword")
    (cloud / "effect" / "fighter" / "cloud").mkdir(parents=True)
    (cloud / "effect" / "fighter" / "cloud" / "ef_cloud.eff").write_bytes(b"effect")
    (cloud / "config.json").write_text(
        json.dumps(
            {
                "new-dir-files": {
                    "fighter/cloud/c06": [
                        "effect/fighter/cloud/ef_cloud.eff",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    summary = repair_installed_mods(mods_path)

    assert summary.configs_updated == 1
    assert json.loads((cloud / "config.json").read_text(encoding="utf-8")) == {
        "new-dir-files": {
            "fighter/cloud/c06": [
                "effect/fighter/cloud/ef_cloud.eff",
                "fighter/cloud/model/fusionsword/c06/def_cloud_004_col.nutexb",
            ]
        }
    }


def test_repair_installed_mods_removes_unnecessary_visual_only_base_slot_config(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_root = mods_path / "Marth Fancy"
    (mod_root / "fighter" / "marth" / "model" / "body" / "c00").mkdir(parents=True)
    (mod_root / "fighter" / "marth" / "model" / "body" / "c00" / "def_marth_001_col.nutexb").write_bytes(b"tex")
    (mod_root / "fighter" / "marth" / "model" / "body" / "c00" / "model.numshb").write_bytes(b"mesh")
    (mod_root / "config.json").write_text(
        json.dumps(
            {
                "new-dir-files": {
                    "fighter/marth/c00": [
                        "fighter/marth/model/body/c00/def_marth_001_col.nutexb",
                        "fighter/marth/model/body/c00/model.numshb",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    summary = repair_installed_mods(mods_path)

    assert summary.configs_updated == 1
    assert not (mod_root / "config.json").exists()


def test_repair_installed_mods_prunes_support_overlap_when_visual_mod_should_win(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    visual = mods_path / "Sonic Skin"
    (visual / "fighter" / "sonic" / "model" / "body" / "c03").mkdir(parents=True)
    (visual / "fighter" / "sonic" / "model" / "body" / "c03" / "model.bin").write_bytes(b"skin")
    (visual / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (visual / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_03.bntx").write_bytes(b"ui")
    (visual / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (visual / "sound" / "bank" / "fighter_voice" / "vc_sonic_c03.nus3audio").write_bytes(b"new-voice")

    support = mods_path / "Broad Sonic Voice"
    (support / "sound" / "bank" / "fighter_voice").mkdir(parents=True)
    (support / "sound" / "bank" / "fighter_voice" / "vc_sonic_c03.nus3audio").write_bytes(b"old-voice")
    (support / "sound" / "bank" / "fighter_voice" / "vc_sonic_c04.nus3audio").write_bytes(b"other-voice")

    summary = repair_installed_mods(mods_path)

    assert summary.support_mod_adjustments == 1
    assert summary.support_files_pruned == 1
    assert not (support / "sound" / "bank" / "fighter_voice" / "vc_sonic_c03.nus3audio").exists()
    assert (support / "sound" / "bank" / "fighter_voice" / "vc_sonic_c04.nus3audio").exists()
    assert (mods_path.parent / "_import_backups" / "Broad Sonic Voice" / "sound" / "bank" / "fighter_voice" / "vc_sonic_c03.nus3audio").exists()


def test_repair_installed_mods_dedupes_identical_exact_overlaps(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    alpha = mods_path / "Alpha UI"
    beta = mods_path / "Beta UI"
    for root in (alpha, beta):
        (root / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
        (root / "ui" / "replace" / "chara" / "chara_0" / "shared_texture.bntx").write_bytes(b"same")

    summary = repair_installed_mods(mods_path)

    assert summary.identical_files_pruned == 1
    assert summary.resolved_exact_overlaps == 1
    assert (alpha / "ui" / "replace" / "chara" / "chara_0" / "shared_texture.bntx").exists()
    assert not (beta / "ui" / "replace" / "chara" / "chara_0" / "shared_texture.bntx").exists()
    assert (
        mods_path.parent
        / "_import_backups"
        / "_installed_repair"
        / "Beta UI"
        / "ui"
        / "replace"
        / "chara"
        / "chara_0"
        / "shared_texture.bntx"
    ).exists()


def test_repair_installed_mods_reports_remaining_differing_exact_overlap(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    alpha = mods_path / "Alpha UI"
    beta = mods_path / "Beta UI"
    for root, payload in ((alpha, b"a"), (beta, b"b")):
        (root / "ui" / "param" / "database").mkdir(parents=True)
        (root / "ui" / "param" / "database" / "ui_chara_db.prcx").write_bytes(payload)

    summary = repair_installed_mods(mods_path)

    assert summary.remaining_exact_overlaps == 1
    assert any("ui/param/database/ui_chara_db.prcx" in warning for warning in summary.warnings)


def test_repair_installed_mods_ignores_merge_safe_text_overlap_paths(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    alpha = mods_path / "Alpha UI"
    beta = mods_path / "Beta UI"
    for root, payload in ((alpha, "one"), (beta, "two")):
        (root / "ui" / "message").mkdir(parents=True)
        (root / "ui" / "message" / "msg_name.xmsbt").write_text(payload, encoding="utf-8")

    summary = repair_installed_mods(mods_path)

    assert summary.remaining_exact_overlaps == 0


def test_repair_installed_mods_fills_missing_required_ui_portrait_sizes(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_root = mods_path / "Nazo Sonic C02"
    (mod_root / "fighter" / "sonic" / "model" / "body" / "c02").mkdir(parents=True)
    (mod_root / "fighter" / "sonic" / "model" / "body" / "c02" / "model.bin").write_bytes(b"skin")
    for size in (0, 1, 2, 4):
        target = mod_root / "ui" / "replace" / "chara" / f"chara_{size}" / f"chara_{size}_sonic_02.bntx"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"portrait-{size}".encode("utf-8"))

    summary = repair_installed_mods(mods_path)

    repaired = mod_root / "ui" / "replace" / "chara" / "chara_3" / "chara_3_sonic_02.bntx"
    assert summary.ui_portrait_repairs == 1
    assert repaired.exists()
    assert repaired.read_bytes() == b"portrait-4"


def test_repair_installed_mods_invalidates_arcropolis_mod_cache_on_change(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_root = mods_path / "Nazo Sonic C02"
    (mod_root / "fighter" / "sonic" / "model" / "body" / "c02").mkdir(parents=True)
    (mod_root / "fighter" / "sonic" / "model" / "body" / "c02" / "model.bin").write_bytes(b"skin")
    portrait = mod_root / "ui" / "replace" / "chara" / "chara_4" / "chara_4_sonic_02.bntx"
    portrait.parent.mkdir(parents=True, exist_ok=True)
    portrait.write_bytes(b"portrait-4")

    arcropolis_root = mods_path.parent / "arcropolis"
    mod_cache = arcropolis_root / "config" / "workspace" / "preset" / "mod_cache"
    mod_cache.parent.mkdir(parents=True, exist_ok=True)
    mod_cache.write_text("cached", encoding="utf-8")
    conflicts = arcropolis_root / "conflicts.json"
    conflicts.write_text("{}", encoding="utf-8")

    summary = repair_installed_mods(mods_path)

    assert summary.ui_portrait_repairs == 4
    assert not mod_cache.exists()
    assert not conflicts.exists()


def test_repair_installed_mods_does_not_synthesize_advanced_ui_portrait_sizes(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_root = mods_path / "Nazo Sonic C02"
    (mod_root / "fighter" / "sonic" / "model" / "body" / "c02").mkdir(parents=True)
    (mod_root / "fighter" / "sonic" / "model" / "body" / "c02" / "model.bin").write_bytes(b"skin")
    for size in (0, 1, 2, 4, 6):
        target = mod_root / "ui" / "replace" / "chara" / f"chara_{size}" / f"chara_{size}_sonic_02.bntx"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"portrait-{size}".encode("utf-8"))

    summary = repair_installed_mods(mods_path)

    assert summary.ui_portrait_repairs == 1
    assert not (mod_root / "ui" / "replace" / "chara" / "chara_5" / "chara_5_sonic_02.bntx").exists()
    assert not (mod_root / "ui" / "replace" / "chara" / "chara_7" / "chara_7_sonic_02.bntx").exists()


def test_repair_installed_mods_removes_suspect_generated_stock_icon_clone(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_root = mods_path / "Modern Sonic"
    (mod_root / "fighter" / "sonic" / "model" / "body" / "c00").mkdir(parents=True)
    (mod_root / "fighter" / "sonic" / "model" / "body" / "c00" / "model.bin").write_bytes(b"skin")
    chara4 = mod_root / "ui" / "replace" / "chara" / "chara_4" / "chara_4_sonic_00.bntx"
    chara4.parent.mkdir(parents=True, exist_ok=True)
    chara4.write_bytes(b"portrait-4")
    chara5 = mod_root / "ui" / "replace" / "chara" / "chara_5" / "chara_5_sonic_00.bntx"
    chara5.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(chara4, chara5)

    summary = repair_installed_mods(mods_path)

    assert summary.mods_changed == 1
    assert not chara5.exists()
    backup = (
        mods_path.parent
        / "_import_backups"
        / "_installed_repair"
        / "_ui_stock_icon_cleanup"
        / "Modern Sonic"
        / "ui"
        / "replace"
        / "chara"
        / "chara_5"
        / "chara_5_sonic_00.bntx"
    )
    assert backup.exists()


def test_repair_installed_mods_disables_suspicious_partial_fighter_bundle(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_root = mods_path / "Cloud Shadow"
    (mod_root / "fighter" / "cloud" / "model" / "body" / "c03").mkdir(parents=True)
    (mod_root / "fighter" / "cloud" / "model" / "body" / "c03" / "model.numatb").write_bytes(b"mat")
    (mod_root / "fighter" / "cloud" / "model" / "body" / "c03" / "def_cloud_001_col.nutexb").write_bytes(b"tex")
    (mod_root / "fighter" / "cloud" / "model" / "fusionsword" / "c03").mkdir(parents=True)
    (mod_root / "fighter" / "cloud" / "model" / "fusionsword" / "c03" / "def_cloud_004_col.nutexb").write_bytes(b"sword")
    (mod_root / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (mod_root / "ui" / "replace" / "chara" / "chara_0" / "chara_0_cloud_03.bntx").write_bytes(b"ui")

    summary = repair_installed_mods(mods_path)

    disabled = mods_path.parent / "disabled_mods" / "Cloud Shadow"
    assert summary.mods_changed == 1
    assert not mod_root.exists()
    assert disabled.exists()
    assert any("Disabled suspicious fighter mod 'Cloud Shadow'" in warning for warning in summary.warnings)


def test_repair_installed_mods_disables_cloud_bundle_missing_weapon_support(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_root = mods_path / "crossworlds_miku"
    body = mod_root / "fighter" / "cloud" / "model" / "body" / "c01"
    body.mkdir(parents=True)
    for filename, payload in {
        "model.nuhlpb": b"h",
        "model.numatb": b"LTAM def_cloud_001_col",
        "model.numdlb": b"LDOM bastar_sword_R_VIS_O_OBJShape",
        "model.numshb": b"s",
        "model.numshexb": b"x",
        "model.nusktb": b"k",
    }.items():
        (body / filename).write_bytes(payload)
    (body / "def_cloud_001_col.nutexb").write_bytes(b"tex")
    (mod_root / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (mod_root / "ui" / "replace" / "chara" / "chara_0" / "chara_0_cloud_01.bntx").write_bytes(b"ui")

    summary = repair_installed_mods(mods_path)

    disabled = mods_path.parent / "disabled_mods" / "crossworlds_miku"
    assert summary.mods_changed == 1
    assert not mod_root.exists()
    assert disabled.exists()
    assert any("is missing required weapon model support files" in warning for warning in summary.warnings)


def test_repair_installed_mods_keeps_cloud_bundle_with_matching_weapon_support(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_root = mods_path / "Super Sonic Over Cloud"
    body = mod_root / "fighter" / "cloud" / "model" / "body" / "c06"
    body.mkdir(parents=True)
    for filename, payload in {
        "model.nuhlpb": b"h",
        "model.numatb": b"LTAM def_cloud_004_col",
        "model.numdlb": b"LDOM bastar_sword_R_VIS_O_OBJShape",
        "model.numshb": b"s",
        "model.numshexb": b"x",
        "model.nusktb": b"k",
    }.items():
        (body / filename).write_bytes(payload)
    (body / "def_cloud_004_col.nutexb").write_bytes(b"sword-tex")
    sword_dir = mod_root / "fighter" / "cloud" / "model" / "fusionsword" / "c06"
    sword_dir.mkdir(parents=True)
    (sword_dir / "def_cloud_004_col.nutexb").write_bytes(b"sword")
    (mod_root / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (mod_root / "ui" / "replace" / "chara" / "chara_0" / "chara_0_cloud_06.bntx").write_bytes(b"ui")

    summary = repair_installed_mods(mods_path)

    assert mod_root.exists()
    assert not (mods_path.parent / "disabled_mods" / "Super Sonic Over Cloud").exists()
    assert not any("Super Sonic Over Cloud" in warning for warning in summary.warnings)


def test_repair_installed_mods_disables_cloud_bundle_without_fusionsword_support_even_if_markers_absent(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_root = mods_path / "mihawk over cloud"
    body = mod_root / "fighter" / "cloud" / "model" / "body" / "c00"
    body.mkdir(parents=True)
    for filename, payload in {
        "model.nuhlpb": b"h",
        "model.numatb": b"LTAM def_cloud_001_col",
        "model.numdlb": b"LDOM 5_body_1.0_0_0",
        "model.numshb": b"s",
        "model.numshexb": b"x",
        "model.nusktb": b"k",
    }.items():
        (body / filename).write_bytes(payload)
    (body / "def_cloud_001_col.nutexb").write_bytes(b"tex")
    (mod_root / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (mod_root / "ui" / "replace" / "chara" / "chara_0" / "chara_0_cloud_00.bntx").write_bytes(b"ui")

    summary = repair_installed_mods(mods_path)

    disabled = mods_path.parent / "disabled_mods" / "mihawk over cloud"
    assert summary.mods_changed == 1
    assert not mod_root.exists()
    assert disabled.exists()
    assert any("cloud c00 is missing required weapon model support files" in warning for warning in summary.warnings)


def test_repair_installed_mods_keeps_partial_but_multi_core_model_bundle(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_root = mods_path / "Modern Sonic"
    body = mod_root / "fighter" / "sonic" / "model" / "body" / "c00"
    body.mkdir(parents=True)
    for filename, payload in {
        "model.numatb": b"mat",
        "model.numdlb": b"d",
        "model.numshb": b"s",
        "model.numshexb": b"x",
    }.items():
        (body / filename).write_bytes(payload)
    (body / "def_sonic_001_col.nutexb").write_bytes(b"tex")
    (mod_root / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (mod_root / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_00.bntx").write_bytes(b"ui")

    summary = repair_installed_mods(mods_path)

    assert mod_root.exists()
    assert not (mods_path.parent / "disabled_mods" / "Modern Sonic").exists()
    assert not any("Modern Sonic" in warning for warning in summary.warnings)


def test_repair_installed_mods_keeps_single_core_body_only_bundle(tmp_path: Path):
    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    mod_root = mods_path / "Skadi Byleth"
    body = mod_root / "fighter" / "master" / "model" / "body" / "c03"
    body.mkdir(parents=True)
    (body / "model.numatb").write_bytes(b"mat")
    (body / "def_master_001_col.nutexb").write_bytes(b"tex")
    (mod_root / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (mod_root / "ui" / "replace" / "chara" / "chara_0" / "chara_0_master_03.bntx").write_bytes(b"ui")

    summary = repair_installed_mods(mods_path)

    assert mod_root.exists()
    assert not (mods_path.parent / "disabled_mods" / "Skadi Byleth").exists()
    assert not any("Skadi Byleth" in warning for warning in summary.warnings)


def test_import_mod_package_postflight_fills_missing_required_ui_portrait_sizes(tmp_path: Path):
    source = tmp_path / "downloads" / "Nazo Sonic C02"
    (source / "fighter" / "sonic" / "model" / "body" / "c02").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c02" / "model.bin").write_bytes(b"skin")
    for size in (0, 1, 2, 4):
        target = source / "ui" / "replace" / "chara" / f"chara_{size}" / f"chara_{size}_sonic_02.bntx"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"portrait-{size}".encode("utf-8"))

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    summary = import_mod_package(source, mods_path)

    repaired = mods_path / "Nazo Sonic C02" / "ui" / "replace" / "chara" / "chara_3" / "chara_3_sonic_02.bntx"
    assert summary.ui_portrait_repairs == 1
    assert repaired.exists()
    assert repaired.read_bytes() == b"portrait-4"


def test_import_mod_package_invalidates_arcropolis_mod_cache(tmp_path: Path):
    source = tmp_path / "downloads" / "Nazo Sonic C02"
    (source / "fighter" / "sonic" / "model" / "body" / "c02").mkdir(parents=True)
    (source / "fighter" / "sonic" / "model" / "body" / "c02" / "model.bin").write_bytes(b"skin")
    portrait = source / "ui" / "replace" / "chara" / "chara_4" / "chara_4_sonic_02.bntx"
    portrait.parent.mkdir(parents=True, exist_ok=True)
    portrait.write_bytes(b"portrait-4")

    mods_path = tmp_path / "sdmc" / "ultimate" / "mods"
    arcropolis_root = mods_path.parent / "arcropolis"
    mod_cache = arcropolis_root / "config" / "workspace" / "preset" / "mod_cache"
    mod_cache.parent.mkdir(parents=True, exist_ok=True)
    mod_cache.write_text("cached", encoding="utf-8")

    summary = import_mod_package(source, mods_path)

    assert summary.items_imported == 1
    assert not mod_cache.exists()


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
