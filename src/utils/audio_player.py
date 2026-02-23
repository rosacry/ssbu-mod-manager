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
            self.stop()
            pygame.mixer.music.load(str(file_path))
            pygame.mixer.music.set_volume(self._volume)
            pygame.mixer.music.play()
            self._current_file = file_path
            self._playing = True
            self._paused = False
            return True, f"Playing: {file_path.name}"
        except Exception as e:
            from src.utils.logger import logger as _logger
            _logger.error("AudioPlayer", f"Playback failed for {file_path}: {e}")
            return False, f"Playback failed: {e}"

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

    def cleanup(self):
        """Clean up audio resources."""
        self.stop()
        if _pygame_initialized and _pygame_available:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
        # Clean up cached files
        try:
            from src.utils.nus3audio import cleanup_cache
            cleanup_cache()
        except Exception:
            pass


# Singleton
audio_player = AudioPlayer()
