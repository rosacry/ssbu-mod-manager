from src.core.conflict_detector import ConflictDetector


def test_detect_conflicts_adds_friendly_slot_labels(tmp_path):
    mods_root = tmp_path / "mods"

    nazo = mods_root / "Nazo Pack"
    (nazo / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (nazo / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_03.bntx").write_bytes(b"nazo")
    (nazo / "ui" / "message").mkdir(parents=True)
    (nazo / "ui" / "message" / "msg_name.xmsbt").write_text(
        """<?xml version="1.0" encoding="utf-16"?>
<xmsbt>
  <entry label="nam_chr1_03_sonic">
    <text>Nazo</text>
  </entry>
</xmsbt>
""",
        encoding="utf-16",
    )

    dark = mods_root / "Dark Pack"
    (dark / "ui" / "replace" / "chara" / "chara_0").mkdir(parents=True)
    (dark / "ui" / "replace" / "chara" / "chara_0" / "chara_0_sonic_03.bntx").write_bytes(b"dark")
    (dark / "ui" / "message").mkdir(parents=True)
    (dark / "ui" / "message" / "msg_name.xmsbt").write_text(
        """<?xml version="1.0" encoding="utf-16"?>
<xmsbt>
  <entry label="nam_chr1_03_sonic">
    <text>Dark Super Sonic</text>
  </entry>
</xmsbt>
""",
        encoding="utf-16",
    )

    conflicts = ConflictDetector().detect_conflicts(mods_root)

    conflict = next(
        c for c in conflicts
        if c.relative_path == "ui/replace/chara/chara_0/chara_0_sonic_03.bntx"
    )
    assert conflict.display_path == "ui/replace/chara/chara_0/chara_0_sonic_03.bntx"
    assert "Affected slots/forms:" in conflict.slot_summary
    assert "Nazo (sonic c03)" in conflict.slot_summary
    assert "Dark Super Sonic (sonic c03)" in conflict.slot_summary
    assert conflict.slot_group_key == "sonic:c03"
    assert "sonic c03" in conflict.slot_group_label
    assert "Nazo" in conflict.slot_group_label
    assert "Dark Super Sonic" in conflict.slot_group_label
    assert conflict.mod_display_labels["Nazo Pack"] == "Nazo (sonic c03)"
    assert conflict.mod_display_labels["Dark Pack"] == "Dark Super Sonic (sonic c03)"
