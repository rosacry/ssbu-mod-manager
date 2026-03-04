from src.core.desync_classifier import (
    DesyncRiskLevel,
    classify_mod_file,
    classify_mod_path,
    classify_plugin_filename,
    is_gameplay_affecting_mod_file,
    is_gameplay_affecting_plugin,
    is_plugin_optional,
)


def test_classify_mod_file_core_rules() -> None:
    assert classify_mod_file("fighter/mario/model/body/c00/body.nutexb")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert classify_mod_file("fighter/mario/param/fighter_param.prc")[0] == DesyncRiskLevel.DESYNC_VULNERABLE
    assert classify_mod_file("stage/battlefield/param/stage_param.prc")[0] == DesyncRiskLevel.CONDITIONALLY_SHARED


def test_classify_mod_file_costume_support_assets_are_wifi_safe() -> None:
    assert classify_mod_file("fighter/mario/motion/body/c04/a00wait1.nuanmb")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert classify_mod_file("fighter/mario/motion/body/c04/swing.prc")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert classify_mod_file("fighter/mario/motion/pump/c04/motion_list.bin")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert classify_mod_file("fighter/mario/motion/pump/c04/update.prc")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert classify_mod_file("fighter/captain/model/body/c03/update.prc")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY


def test_classify_mod_file_visual_stage_assets_are_wifi_safe() -> None:
    assert classify_mod_file("stage/trail_castle/normal/render/stage.shpcanim")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert classify_mod_file("stage/trail_castle/normal/motion/camera/camera00.nuanmb")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert classify_mod_file("stage/trail_castle/normal/param/trail_castle_visual.stdat")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY


def test_classify_mod_file_ui_param_variants_are_safe_client_only() -> None:
    assert classify_mod_file("ui/param/database/ui_chara_db.prcx")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert classify_mod_file("ui/param/database/ui_chara_db.prcxml")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY


def test_classify_mod_file_vanilla_bgm_replacement_respects_strict_audio_policy() -> None:
    relaxed = classify_mod_file("sound/bgm/bgm_z90_menu.nus3audio", strict_audio_sync=False)[0]
    strict = classify_mod_file("sound/bgm/bgm_z90_menu.nus3audio", strict_audio_sync=True)[0]
    assert relaxed == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert strict == DesyncRiskLevel.CONDITIONALLY_SHARED


def test_classify_mod_file_added_bgm_track_is_not_wifi_safe() -> None:
    relaxed = classify_mod_file("sound/bgm/bgm_custom_song.nus3audio", strict_audio_sync=False)[0]
    strict = classify_mod_file("sound/bgm/bgm_custom_song.nus3audio", strict_audio_sync=True)[0]
    assert relaxed == DesyncRiskLevel.CONDITIONALLY_SHARED
    assert strict == DesyncRiskLevel.CONDITIONALLY_SHARED
    assert is_gameplay_affecting_mod_file("sound/bgm/bgm_custom_song.nus3audio")


def test_classify_mod_file_music_db_edits_are_not_wifi_safe() -> None:
    assert classify_mod_file("ui/param/database/ui_bgm_db.prc")[0] == DesyncRiskLevel.CONDITIONALLY_SHARED
    assert classify_mod_file("ui/param/database/ui_stage_db.prcxml")[0] == DesyncRiskLevel.CONDITIONALLY_SHARED


def test_classify_mod_file_preview_and_effect_assets_are_safe_client_only() -> None:
    assert classify_mod_file("preview.webp")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert classify_mod_file("fighter/edge/ef_edge_c01.eff")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY


def test_classify_mod_path_vanilla_bgm_replacement_mod_is_wifi_safe(tmp_path) -> None:
    mod_path = tmp_path / "ReplacementOnly"
    bgm_dir = mod_path / "sound" / "bgm"
    bgm_dir.mkdir(parents=True)
    (bgm_dir / "bgm_z90_menu.nus3audio").write_bytes(b"menu")

    report = classify_mod_path(mod_path)

    assert report.level == DesyncRiskLevel.SAFE_CLIENT_ONLY


def test_classify_mod_path_added_track_mod_is_not_wifi_safe(tmp_path) -> None:
    mod_path = tmp_path / "TracklistExpansion"
    bgm_dir = mod_path / "sound" / "bgm"
    bgm_dir.mkdir(parents=True)
    (bgm_dir / "bgm_custom_song.nus3audio").write_bytes(b"custom")
    db_dir = mod_path / "ui" / "param" / "database"
    db_dir.mkdir(parents=True)
    (db_dir / "ui_bgm_db.prc").write_bytes(b"db")

    report = classify_mod_path(mod_path)

    assert report.level == DesyncRiskLevel.CONDITIONALLY_SHARED
    assert any(reason.code in {"bgm_track_extension", "music_db_edit"} for reason in report.reasons)


def test_unknown_mod_file_is_review_and_gameplay_affecting() -> None:
    level = classify_mod_file("mystery/content/custom_blob.bin")[0]
    assert level == DesyncRiskLevel.UNKNOWN_NEEDS_REVIEW
    assert is_gameplay_affecting_mod_file("mystery/content/custom_blob.bin")


def test_classify_plugin_filename_rules() -> None:
    optional = classify_plugin_filename("libless_lag.nro")
    gameplay = classify_plugin_filename("libhdr.nro")
    safe = classify_plugin_filename("libarcropolis.nro")
    unknown = classify_plugin_filename("libtotally_unknown_feature.nro")

    assert optional.level == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert optional.code == "optional_plugin"
    assert optional.evidence_url
    assert is_plugin_optional("libless_lag.nro")

    assert gameplay.level == DesyncRiskLevel.DESYNC_VULNERABLE
    assert gameplay.evidence_url
    assert is_gameplay_affecting_plugin("libhdr.nro")

    assert safe.level == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert safe.evidence_url
    assert not is_gameplay_affecting_plugin("libarcropolis.nro")

    assert unknown.level == DesyncRiskLevel.UNKNOWN_NEEDS_REVIEW
    assert unknown.evidence_url
    assert is_gameplay_affecting_plugin("libtotally_unknown_feature.nro")
