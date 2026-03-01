from pathlib import Path

import src.core.music_manager as music_manager_module
from src.core.music_manager import MusicManager


def _make_track(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"audio")


def test_music_manager_persists_favorite_tracks(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    monkeypatch.setattr(music_manager_module, "CONFIG_DIR", config_dir)

    mods_root = tmp_path / "mods"
    _make_track(mods_root / "PackA" / "sound" / "bgm" / "bgm_alpha.nus3audio")
    _make_track(mods_root / "PackB" / "sound" / "bgm" / "bgm_beta.nus3audio")

    manager = MusicManager()
    tracks = manager.discover_tracks(
        mods_root,
        parse_binary_msbt=False,
        generate_msbt_overlays=False,
    )

    assert {track.track_id for track in tracks} == {"bgm_alpha", "bgm_beta"}
    assert not any(track.is_favorite for track in tracks)

    assert manager.set_track_favorite("bgm_alpha", True) is True

    reloaded_manager = MusicManager()
    reloaded_tracks = reloaded_manager.discover_tracks(
        mods_root,
        parse_binary_msbt=False,
        generate_msbt_overlays=False,
    )
    by_id = {track.track_id: track for track in reloaded_tracks}

    assert by_id["bgm_alpha"].is_favorite is True
    assert by_id["bgm_beta"].is_favorite is False
    assert reloaded_manager.favorite_track_ids == {"bgm_alpha"}
