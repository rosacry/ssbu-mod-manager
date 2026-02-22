"""Audio player utility for music preview. Uses pygame if available."""
from pathlib import Path
from typing import Optional

_pygame_available = False
try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
    _pygame_available = True
except (ImportError, Exception):
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
        return _pygame_available

    @property
    def is_playing(self) -> bool:
        if not _pygame_available:
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
        if not _pygame_available:
            return False, "Audio playback requires pygame. Install with: pip install pygame"

        suffix = file_path.suffix.lower()
        if suffix == ".nus3audio":
            return False, "NUS3AUDIO files cannot be played directly. Convert to WAV/OGG first."

        if suffix not in (".wav", ".ogg", ".mp3", ".flac"):
            return False, f"Unsupported format: {suffix}"

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
            return False, f"Playback failed: {e}"

    def stop(self):
        """Stop playback."""
        if not _pygame_available:
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
        if not _pygame_available or not self._playing:
            return
        try:
            pygame.mixer.music.pause()
            self._paused = True
        except Exception:
            pass

    def unpause(self):
        """Resume paused playback."""
        if not _pygame_available or not self._paused:
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
        if _pygame_available:
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
        if _pygame_available:
            try:
                pygame.mixer.quit()
            except Exception:
                pass


# Singleton
audio_player = AudioPlayer()
