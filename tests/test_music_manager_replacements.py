import json
from pathlib import Path

import src.core.music_manager as music_manager_module
from src.core.music_manager import MusicManager, infer_bgm_filename
from src.models.music import MusicTrack


def _write_track(path: Path, payload: bytes) -> MusicTrack:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return MusicTrack(
        track_id=path.stem,
        file_path=path,
        display_name=path.stem,
        source_mod=path.parent.parent.name if path.parent.parent.name else "Pack",
    )


def test_infer_bgm_filename_prefers_stream_set_id() -> None:
    assert infer_bgm_filename("ui_bgm_unused", "set_a01_smb_chijyou") == "bgm_a01_smb_chijyou.nus3audio"
    assert infer_bgm_filename("ui_bgm_menu_select", "") == "bgm_menu_select.nus3audio"


def test_save_assignments_writes_safe_replacements_and_prunes_stale_files(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.setattr(music_manager_module, "CONFIG_DIR", config_dir)

    mods_root = tmp_path / "mods"
    track_a = _write_track(mods_root / "PackA" / "sound" / "bgm" / "bgm_alpha.nus3audio", b"alpha")
    track_b = _write_track(mods_root / "PackB" / "sound" / "bgm" / "bgm_beta.nus3audio", b"beta")

    manager = MusicManager()
    manager.tracks = [track_a, track_b]
    manager.set_stage_slot_replacement("ui_stage_id_battlefield", "bgm_target_one.nus3audio", track_a)

    first_result = manager.save_assignments(mods_root)
    stream_dir = mods_root / "_MusicConfig" / "stream;" / "sound" / "bgm"
    first_dest = stream_dir / "bgm_target_one.nus3audio"

    assert first_result["replacement_files"] == 1
    assert first_dest.exists()
    assert first_dest.read_bytes() == b"alpha"

    metadata_path = mods_root / "_MusicConfig" / "wifi_safe_replacements.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["replacements"][0]["replacement_track_id"] == "bgm_alpha"

    manager.clear_all_replacements()
    manager.set_stage_slot_replacement("ui_stage_id_battlefield", "bgm_target_two.nus3audio", track_b)
    second_result = manager.save_assignments(mods_root)
    second_dest = stream_dir / "bgm_target_two.nus3audio"

    assert second_result["replacement_files"] == 1
    assert not first_dest.exists()
    assert second_dest.exists()
    assert second_dest.read_bytes() == b"beta"

