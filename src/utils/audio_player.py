"""Audio player utility for music preview. Uses pygame if available."""
from pathlib import Path
from typing import Optional

_pygame_available = False
_pygame_error = ""
_pygame_initialized = False

# Try to import pygame at module level so it's available as a global name
try:
    import pygame as pygame
except ImportError:
    pygame = None  # type: ignore


def _ensure_mixer():
    """Lazily initialize pygame mixer on first use."""
    global _pygame_available, _pygame_error, _pygame_initialized, pygame
    if _pygame_initialized:
        return
    _pygame_initialized = True
    if pygame is None:
        try:
            import pygame as _pg
            pygame = _pg
        except ImportError:
            _pygame_error = "pygame not installed"
            return
    try:
        pygame.mixer.init(frequency=48000, size=-16, channels=2, buffer=4096)
        _pygame_available = True
    except Exception as e:
        _pygame_error = str(e)
        # Try with different settings
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            _pygame_available = True
            _pygame_error = ""
        except Exception:
            pass


class AudioPlayer:
    """Simple audio player with play/pause/stop/volume controls."""

    def __init__(self):
        self._current_file: Optional[Path] = None
        self._playing = False
        self._paused = False
        self._volume = 0.7
        self._seek_offset = 0.0       # track position (seconds) at last seek/play
        self._raw_pos_at_anchor = 0.0  # get_pos() value (seconds) at last seek/play

    @property
    def available(self) -> bool:
        _ensure_mixer()
        return _pygame_available

    @property
    def is_playing(self) -> bool:
        if not _pygame_initialized or not _pygame_available:
            return False
        return pygame.mixer.music.get_busy() or self._paused

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def current_file(self) -> Optional[Path]:
        return self._current_file

    def play(self, file_path: Path) -> tuple[bool, str]:
        """Play an audio file. Returns (success, message)."""
        _ensure_mixer()
        if not _pygame_available:
            msg = "Audio playback requires pygame. Install with: pip install pygame"
            if _pygame_error:
                msg += f"\nInit error: {_pygame_error}"
            return False, msg

        try:
            from src.utils.logger import logger
        except ImportError:
            logger = None

        suffix = file_path.suffix.lower()

        # Handle NUS3AUDIO files by extracting and converting
        if suffix == ".nus3audio":
            return self._play_nus3audio(file_path)

        if suffix not in (".wav", ".ogg", ".mp3", ".flac"):
            return False, f"Unsupported format: {suffix}"

        return self._play_file(file_path)

    def _play_nus3audio(self, file_path: Path) -> tuple[bool, str]:
        """Extract and play a NUS3AUDIO file."""
        try:
            from src.utils.nus3audio import extract_and_convert
            from src.utils.logger import logger
        except ImportError:
            from src.utils.nus3audio import extract_and_convert
            logger = None

        try:
            success, message, temp_path = extract_and_convert(file_path)
            if not success or temp_path is None:
                if logger:
                    logger.warn("AudioPlayer", f"NUS3AUDIO conversion failed: {message}")
                return False, message
            ok, play_msg = self._play_file(temp_path)
            if ok:
                return True, f"Playing: {file_path.name}"
            return False, play_msg
        except Exception as e:
            if logger:
                logger.error("AudioPlayer", f"NUS3AUDIO playback error: {e}")
            return False, f"NUS3AUDIO playback failed: {e}"

    def _play_file(self, file_path: Path) -> tuple[bool, str]:
        """Play a standard audio file."""
        try:
            # Proactively detect OGG Opus files — pygame/stb_vorbis silently
            # produces no audio for Opus (no exception, just silence).
            if file_path.suffix.lower() == ".ogg":
                try:
                    with open(file_path, 'rb') as f:
                        header = f.read(48)
                    if b'OpusHead' in header:
                        wav_result = self._try_ffmpeg_fallback(file_path)
                        if wav_result:
                            return wav_result
                        return False, (
                            "This track uses Opus audio which pygame cannot play.\n"
                            "Install ffmpeg and add it to PATH for playback."
                        )
                except OSError:
                    pass

            self.stop()
            pygame.mixer.music.load(str(file_path))
            pygame.mixer.music.set_volume(self._volume)
            pygame.mixer.music.play()
            self._current_file = file_path
            self._playing = True
            self._paused = False
            self._seek_offset = 0.0
            self._raw_pos_at_anchor = 0.0
            return True, f"Playing: {file_path.name}"
        except Exception as e:
            error_str = str(e)
            # OGG Opus files fail with stb_vorbis — try ffmpeg conversion to WAV
            if "VORBIS" in error_str.upper() and file_path.suffix.lower() == ".ogg":
                wav_result = self._try_ffmpeg_fallback(file_path)
                if wav_result:
                    return wav_result
            from src.utils.logger import logger as _logger
            _logger.error("AudioPlayer", f"Playback failed for {file_path}: {e}")
            if "VORBIS" in error_str.upper():
                return False, (
                    f"Playback failed: {e}\n"
                    "This track uses Opus audio. Install ffmpeg and add it to PATH for playback."
                )
            return False, f"Playback failed: {e}"

    def _try_ffmpeg_fallback(self, ogg_path: Path) -> Optional[tuple[bool, str]]:
        """Attempt to convert an OGG Opus file to WAV via ffmpeg and play that."""
        try:
            from src.utils.nus3audio import _convert_ogg_opus_to_wav
            wav_path = _convert_ogg_opus_to_wav(ogg_path)
            if wav_path and wav_path.exists():
                self.stop()
                pygame.mixer.music.load(str(wav_path))
                pygame.mixer.music.set_volume(self._volume)
                pygame.mixer.music.play()
                self._current_file = wav_path
                self._playing = True
                self._paused = False
                self._seek_offset = 0.0
                self._raw_pos_at_anchor = 0.0
                return True, f"Playing: {ogg_path.name}"
        except Exception:
            pass
        return None

    def stop(self):
        """Stop playback."""
        if not _pygame_initialized or not _pygame_available:
            return
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except Exception:
            pass
        self._playing = False
        self._paused = False
        self._current_file = None
        self._seek_offset = 0.0
        self._raw_pos_at_anchor = 0.0

    def pause(self):
        """Pause playback."""
        if not _pygame_initialized or not _pygame_available or not self._playing:
            return
        try:
            pygame.mixer.music.pause()
            self._paused = True
        except Exception:
            pass

    def unpause(self):
        """Resume paused playback."""
        if not _pygame_initialized or not _pygame_available or not self._paused:
            return
        try:
            pygame.mixer.music.unpause()
            self._paused = False
        except Exception:
            pass

    def toggle_pause(self):
        """Toggle pause/unpause."""
        if self._paused:
            self.unpause()
        elif self._playing:
            self.pause()

    def set_volume(self, volume: float):
        """Set volume (0.0 to 1.0)."""
        self._volume = max(0.0, min(1.0, volume))
        if _pygame_initialized and _pygame_available:
            try:
                pygame.mixer.music.set_volume(self._volume)
            except Exception:
                pass

    @property
    def volume(self) -> float:
        return self._volume

    def get_position(self) -> float:
        """Get current playback position in seconds (seek-aware)."""
        if not _pygame_initialized or not _pygame_available:
            return 0.0
        try:
            raw = pygame.mixer.music.get_pos() / 1000.0
            if raw < 0:
                return 0.0
            return max(0.0, self._seek_offset + (raw - self._raw_pos_at_anchor))
        except Exception:
            return 0.0

    def get_duration(self) -> float:
        """Get duration of current track in seconds (estimated from file)."""
        if not self._current_file or not self._current_file.exists():
            return 0.0
        try:
            import wave
            if self._current_file.suffix.lower() == '.wav':
                with wave.open(str(self._current_file), 'rb') as wf:
                    return wf.getnframes() / wf.getframerate()
        except Exception:
            pass
        # Rough estimate from file size for other formats
        try:
            size = self._current_file.stat().st_size
            # ~192 kbps average for compressed audio
            return size / 24000.0
        except Exception:
            return 0.0

    def seek(self, position: float):
        """Seek to a position in seconds."""
        if not _pygame_initialized or not _pygame_available or not self._playing:
            return
        self._seek_offset = position
        try:
            pygame.mixer.music.set_pos(position)
            # Record raw get_pos() right after seek so get_position()
            # can compute elapsed time relative to this anchor.
            try:
                self._raw_pos_at_anchor = pygame.mixer.music.get_pos() / 1000.0
            except Exception:
                self._raw_pos_at_anchor = 0.0
        except Exception:
            # Some formats may not support set_pos; restart from offset
            try:
                pygame.mixer.music.play(start=position)
                self._raw_pos_at_anchor = 0.0
            except Exception:
                pass

    def cleanup(self):
        """Clean up audio resources."""
        global _pygame_initialized, _pygame_available
        self.stop()
        if _pygame_initialized and _pygame_available:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
        _pygame_initialized = False
        _pygame_available = False
        # Clean up cached files
        try:
            from src.utils.nus3audio import cleanup_cache
            cleanup_cache()
        except Exception:
            pass


# Singleton
audio_player = AudioPlayer()
