from src.core.desync_classifier import (
    DesyncRiskLevel,
    classify_mod_file,
    classify_plugin_filename,
    is_gameplay_affecting_mod_file,
    is_gameplay_affecting_plugin,
    is_plugin_optional,
)


def test_classify_mod_file_core_rules() -> None:
    assert classify_mod_file("fighter/mario/model/body/c00/body.nutexb")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert classify_mod_file("fighter/mario/param/fighter_param.prc")[0] == DesyncRiskLevel.DESYNC_VULNERABLE
    assert classify_mod_file("stage/battlefield/param/stage_param.prc")[0] == DesyncRiskLevel.CONDITIONALLY_SHARED


def test_classify_mod_file_audio_strict_mode() -> None:
    relaxed = classify_mod_file("sound/bgm/my_song.nus3audio", strict_audio_sync=False)[0]
    strict = classify_mod_file("sound/bgm/my_song.nus3audio", strict_audio_sync=True)[0]
    assert relaxed == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert strict == DesyncRiskLevel.CONDITIONALLY_SHARED


def test_classify_mod_file_preview_and_effect_assets_are_safe_client_only() -> None:
    assert classify_mod_file("preview.webp")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY
    assert classify_mod_file("fighter/edge/ef_edge_c01.eff")[0] == DesyncRiskLevel.SAFE_CLIENT_ONLY


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
