from pathlib import Path

from src.utils.audio_player import AudioPlayer
from src.utils import nus3audio


def test_resolve_cached_preview_prefers_opus_stream_when_requested(tmp_path: Path) -> None:
    ogg_path = tmp_path / "song.ogg"
    ogg_path.write_bytes(b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * 16)

    ok, _message, preview_path = nus3audio._resolve_cached_preview(
        tmp_path,
        "song",
        "song.nus3audio",
        prefer_stream=True,
    )

    assert ok is True
    assert preview_path == ogg_path


def test_resolve_cached_preview_converts_opus_stream_for_wav_playback(
    tmp_path: Path, monkeypatch
) -> None:
    ogg_path = tmp_path / "song.ogg"
    wav_path = tmp_path / "song.wav"
    ogg_path.write_bytes(b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * 16)

    calls: list[Path] = []

    def fake_convert(path: Path) -> Path:
        calls.append(path)
        wav_path.write_bytes(b"RIFF" + b"\x00" * 2000)
        return wav_path

    monkeypatch.setattr(nus3audio, "_convert_ogg_opus_to_wav", fake_convert)

    ok, _message, preview_path = nus3audio._resolve_cached_preview(
        tmp_path,
        "song",
        "song.nus3audio",
        prefer_stream=False,
    )

    assert ok is True
    assert preview_path == wav_path
    assert calls == [ogg_path]


def test_play_nus3audio_prefers_ffplay_when_available(
    tmp_path: Path, monkeypatch
) -> None:
    player = AudioPlayer()
    player._ffplay = "ffplay"
    nus3_path = tmp_path / "song.nus3audio"
    preview_path = tmp_path / "song.ogg"
    nus3_path.write_bytes(b"NUS3")
    preview_path.write_bytes(b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * 16)

    extract_calls: list[tuple[Path, bool]] = []
    ffplay_calls: list[tuple[Path, float]] = []

    def fake_extract(path: Path, prefer_stream: bool = False):
        extract_calls.append((path, prefer_stream))
        return True, "Playing", preview_path

    def fake_ffplay(path: Path, start: float = 0.0):
        ffplay_calls.append((path, start))
        return True, "Playing preview"

    monkeypatch.setattr(nus3audio, "extract_and_convert", fake_extract)
    monkeypatch.setattr(player, "_play_file_ffplay", fake_ffplay)

    ok, message = player._play_nus3audio(nus3_path)

    assert ok is True
    assert message == f"Playing: {nus3_path.name}"
    assert extract_calls == [(nus3_path, True)]
    assert ffplay_calls == [(preview_path, 0.0)]


def test_play_nus3audio_uses_standard_backend_without_ffplay(
    tmp_path: Path, monkeypatch
) -> None:
    player = AudioPlayer()
    player._ffplay = None
    nus3_path = tmp_path / "song.nus3audio"
    preview_path = tmp_path / "song.wav"
    nus3_path.write_bytes(b"NUS3")
    preview_path.write_bytes(b"RIFF" + b"\x00" * 2000)

    extract_calls: list[tuple[Path, bool]] = []
    play_calls: list[Path] = []

    def fake_extract(path: Path, prefer_stream: bool = False):
        extract_calls.append((path, prefer_stream))
        return True, "Playing", preview_path

    def fake_play(path: Path):
        play_calls.append(path)
        return True, "Playing preview"

    monkeypatch.setattr(nus3audio, "extract_and_convert", fake_extract)
    monkeypatch.setattr(player, "_play_file", fake_play)

    ok, message = player._play_nus3audio(nus3_path)

    assert ok is True
    assert message == f"Playing: {nus3_path.name}"
    assert extract_calls == [(nus3_path, False)]
    assert play_calls == [preview_path]
