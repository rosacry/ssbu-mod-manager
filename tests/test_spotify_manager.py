from pathlib import Path

from src.core.spotify_manager import (
    SpotifyManager,
    SpotifyPlaylist,
    SpotifyTrackMatch,
)
from src.models.music import MusicTrack
from src.models.settings import AppSettings


class _DummyConfigManager:
    def __init__(self):
        self.settings = AppSettings(
            spotify_client_id="client-id",
            spotify_access_token="access-token",
            spotify_refresh_token="refresh-token",
            spotify_token_expires_at=9999999999,
            spotify_user_id="user-1",
            spotify_display_name="User One",
        )

    def save(self, settings=None):
        if settings is not None:
            self.settings = settings


def test_spotify_export_skips_existing_and_duplicate_tracks(tmp_path, monkeypatch):
    manager = SpotifyManager(_DummyConfigManager())
    playlist = SpotifyPlaylist(
        playlist_id="playlist-1",
        name="Favorites",
        owner_id="user-1",
        track_count=2,
    )
    track_a = MusicTrack(
        track_id="track_a",
        file_path=tmp_path / "track_a.nus3audio",
        display_name="Alpha Song",
    )
    track_b = MusicTrack(
        track_id="track_b",
        file_path=tmp_path / "track_b.nus3audio",
        display_name="Beta Song",
    )
    track_c = MusicTrack(
        track_id="track_c",
        file_path=tmp_path / "track_c.nus3audio",
        display_name="Gamma Song",
    )
    track_d = MusicTrack(
        track_id="track_d",
        file_path=tmp_path / "track_d.nus3audio",
        display_name="Alpha Song Alt",
    )

    monkeypatch.setattr(
        manager,
        "get_playlist_track_uris",
        lambda _playlist_id: {"spotify:track:existing"},
    )

    def _match(track):
        if track.track_id == "track_a":
            return SpotifyTrackMatch(
                uri="spotify:track:new-one",
                name="Alpha Song",
                artist_names=("Artist",),
                album_name="Album",
                score=0.97,
                query_used="Alpha Song",
            ), "matched"
        if track.track_id == "track_b":
            return SpotifyTrackMatch(
                uri="spotify:track:existing",
                name="Beta Song",
                artist_names=("Artist",),
                album_name="Album",
                score=0.94,
                query_used="Beta Song",
            ), "matched"
        if track.track_id == "track_c":
            return None, "low_confidence"
        return SpotifyTrackMatch(
            uri="spotify:track:new-one",
            name="Alpha Song",
            artist_names=("Artist",),
            album_name="Album",
            score=0.91,
            query_used="Alpha Song Alt",
        ), "matched"

    added_uris = []
    monkeypatch.setattr(manager, "find_best_match_for_track", _match)
    monkeypatch.setattr(
        manager,
        "_add_tracks_to_playlist",
        lambda _playlist_id, uris: added_uris.extend(uris),
    )

    report = manager.export_tracks_to_playlist(
        playlist,
        [track_a, track_b, track_c, track_d],
    )

    assert added_uris == ["spotify:track:new-one"]
    assert report.attempted == 4
    assert report.matched == 3
    assert report.added == 1
    assert report.duplicate_skips == 2
    assert report.low_confidence == ["Gamma Song"]
