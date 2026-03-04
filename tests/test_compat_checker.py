import base64
import json
import zlib
from pathlib import Path

from src.core.compat_checker import (
    COMPAT_CODE_PREFIX_V2,
    GAMEPLAY_KEY_VARIANT_SEPARATOR,
    CompatFingerprint,
    compare_fingerprints,
    decode_fingerprint,
    encode_fingerprint,
    generate_fingerprint,
)


def _make_v2_code(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return COMPAT_CODE_PREFIX_V2 + base64.urlsafe_b64encode(zlib.compress(raw)).decode("ascii")


def test_encode_decode_v3_round_trip_preserves_environment() -> None:
    fp = CompatFingerprint(
        emulator="Eden",
        emulator_version="0.0.4-rc3",
        game_version="13.0.1",
        strict_audio_sync=True,
        strict_environment_match=True,
        gameplay_hashes={"fighter/mario/param/a.prc": "hash_a"},
        plugin_hashes={"libhdr.nro": "hash_p"},
    )
    fp.compute_digest()
    code = encode_fingerprint(fp)
    decoded = decode_fingerprint(code)

    assert decoded is not None
    assert decoded.version == 3
    assert decoded.emulator == "Eden"
    assert decoded.emulator_version == "0.0.4-rc3"
    assert decoded.game_version == "13.0.1"
    assert decoded.strict_audio_sync is True
    assert decoded.strict_environment_match is True
    assert decoded.gameplay_hashes == fp.gameplay_hashes
    assert decoded.plugin_hashes == fp.plugin_hashes
    assert decoded.digest == fp.digest


def test_decode_v2_code_is_supported() -> None:
    v2_payload = {
        "v": 2,
        "em": "Eden",
        "gh": {"fighter/mario/param/a.prc": "h1"},
        "ph": {"libhdr.nro": "h2"},
        "d": "abcd1234",
    }
    code = _make_v2_code(v2_payload)
    decoded = decode_fingerprint(code)

    assert decoded is not None
    assert decoded.version == 2
    assert decoded.emulator == "Eden"
    assert decoded.strict_audio_sync is False
    assert decoded.strict_environment_match is False
    assert decoded.gameplay_hashes == {"fighter/mario/param/a.prc": "h1"}
    assert decoded.plugin_hashes == {"libhdr.nro": "h2"}
    assert decoded.digest == "abcd1234"


def test_generate_fingerprint_keeps_duplicate_relative_paths(tmp_path: Path) -> None:
    mods_path = tmp_path / "mods"
    mod_a = mods_path / "ModA" / "fighter" / "mario" / "param"
    mod_b = mods_path / "ModB" / "fighter" / "mario" / "param"
    mod_a.mkdir(parents=True)
    mod_b.mkdir(parents=True)
    (mod_a / "fighter_param.prc").write_bytes(b"one")
    (mod_b / "fighter_param.prc").write_bytes(b"two")

    fp = generate_fingerprint(mods_path=mods_path)
    keys = sorted(fp.gameplay_hashes.keys())

    assert len(keys) == 2
    assert keys[0].endswith(f"{GAMEPLAY_KEY_VARIANT_SEPARATOR}1")
    assert keys[1].endswith(f"{GAMEPLAY_KEY_VARIANT_SEPARATOR}2")
    assert fp.gameplay_mod_names == ["ModA", "ModB"]


def test_generate_fingerprint_carries_environment_versions(tmp_path: Path) -> None:
    mods_path = tmp_path / "mods"
    mods_path.mkdir(parents=True)

    fp = generate_fingerprint(
        mods_path=mods_path,
        emulator_name="Eden",
        emulator_version="v0.0.4-rc3",
        game_version="13.0.1",
    )

    assert fp.emulator == "Eden"
    assert fp.emulator_version == "v0.0.4-rc3"
    assert fp.game_version == "13.0.1"
    assert fp.strict_environment_match is False


def test_generate_fingerprint_sets_strict_environment_policy(tmp_path: Path) -> None:
    mods_path = tmp_path / "mods"
    mods_path.mkdir(parents=True)

    fp = generate_fingerprint(
        mods_path=mods_path,
        strict_environment_match=True,
    )

    assert fp.strict_environment_match is True


def test_generate_fingerprint_standard_policy_ignores_vanilla_bgm_replacements(tmp_path: Path) -> None:
    mods_path = tmp_path / "mods"
    bgm_dir = mods_path / "AudioOnly" / "sound" / "bgm"
    bgm_dir.mkdir(parents=True)
    (bgm_dir / "bgm_z90_menu.nus3audio").write_bytes(b"audio")

    standard_fp = generate_fingerprint(mods_path=mods_path, strict_audio_sync=False)
    strict_fp = generate_fingerprint(mods_path=mods_path, strict_audio_sync=True)

    assert standard_fp.strict_audio_sync is False
    assert strict_fp.strict_audio_sync is True
    assert standard_fp.gameplay_hashes == {}
    assert len(strict_fp.gameplay_hashes) == 1


def test_generate_fingerprint_always_includes_added_bgm_tracks(tmp_path: Path) -> None:
    mods_path = tmp_path / "mods"
    bgm_dir = mods_path / "TracklistExpansion" / "sound" / "bgm"
    bgm_dir.mkdir(parents=True)
    (bgm_dir / "bgm_custom_song.nus3audio").write_bytes(b"audio")

    standard_fp = generate_fingerprint(mods_path=mods_path, strict_audio_sync=False)
    strict_fp = generate_fingerprint(mods_path=mods_path, strict_audio_sync=True)

    assert len(standard_fp.gameplay_hashes) == 1
    assert len(strict_fp.gameplay_hashes) == 1


def test_compare_fingerprints_blocks_environment_mismatch() -> None:
    local = CompatFingerprint(
        emulator="Eden",
        emulator_version="0.0.4-rc3",
        game_version="13.0.1",
        gameplay_hashes={"fighter/mario/param/a.prc": "same"},
    )
    reference = CompatFingerprint(
        emulator="Ryujinx",
        emulator_version="1.2.3",
        game_version="13.0.0",
        gameplay_hashes={"fighter/mario/param/a.prc": "same"},
    )
    local.compute_digest()
    reference.compute_digest()

    result = compare_fingerprints(local, reference)

    assert not result.compatible
    assert len(result.environment_issues) == 3
    assert result.issue_count >= 3


def test_compare_fingerprints_blocks_strict_audio_policy_mismatch() -> None:
    local = CompatFingerprint(
        gameplay_hashes={"fighter/mario/param/a.prc": "same"},
        strict_audio_sync=False,
    )
    reference = CompatFingerprint(
        gameplay_hashes={"fighter/mario/param/a.prc": "same"},
        strict_audio_sync=True,
    )
    local.compute_digest()
    reference.compute_digest()

    result = compare_fingerprints(local, reference)

    assert not result.compatible
    assert any("strict audio sync" in issue.lower() for issue in result.environment_issues)


def test_compare_fingerprints_blocks_strict_environment_policy_mismatch() -> None:
    local = CompatFingerprint(
        gameplay_hashes={"fighter/mario/param/a.prc": "same"},
        strict_environment_match=False,
    )
    reference = CompatFingerprint(
        gameplay_hashes={"fighter/mario/param/a.prc": "same"},
        strict_environment_match=True,
    )
    local.compute_digest()
    reference.compute_digest()

    result = compare_fingerprints(local, reference)

    assert not result.compatible
    assert any("strict environment" in issue.lower() for issue in result.environment_issues)


def test_compare_fingerprints_strict_environment_requires_local_metadata() -> None:
    local = CompatFingerprint(
        emulator="Eden",
        emulator_version="",
        game_version="",
        strict_environment_match=True,
        gameplay_hashes={"fighter/mario/param/a.prc": "same"},
    )
    reference = CompatFingerprint(
        emulator="Eden",
        emulator_version="v0.0.4-rc3",
        game_version="13.0.1",
        strict_environment_match=True,
        gameplay_hashes={"fighter/mario/param/a.prc": "same"},
    )
    local.compute_digest()
    reference.compute_digest()

    result = compare_fingerprints(local, reference)

    assert not result.compatible
    assert any("metadata is missing" in issue.lower() for issue in result.environment_issues)
