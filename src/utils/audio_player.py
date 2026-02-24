"""Audio player utility for music preview. Uses pygame if available."""
from pathlib import Path
from typing import Optional
import os
import shutil
import subprocess
import time

_pygame_available = False
_pygame_error = ""
_pygame_initialized = False
_pygame_backend = ""
_ffplay_path: Optional[str] = None
_ffplay_checked = False

# Keep pygame import lazy so startup never touches SDL/audio until playback.
pygame = None  # type: ignore


def _find_ffplay() -> Optional[str]:
    """Find ffplay executable (used as alternate playback backend)."""
    global _ffplay_path, _ffplay_checked
    if _ffplay_checked:
        return _ffplay_path
    _ffplay_checked = True
    path = shutil.which("ffplay")
    if path:
        _ffplay_path = path
    return _ffplay_path


def _ensure_mixer():
    """Lazily initialize pygame mixer on first use."""
    global _pygame_available, _pygame_error, _pygame_initialized, _pygame_backend, pygame
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
    init_errors = []

    # Try stricter/larger-buffer configurations first to avoid global crackle
    # or distortion on some Windows audio stacks.
    attempts = [
        (None, 48000, 8192, 0),
        ("directsound", 48000, 8192, 0),
        ("wasapi", 48000, 8192, 0),
        ("winmm", 44100, 8192, 0),
        (None, 44100, 4096, 0),
    ]

    for driver, freq, buffer, allowed in attempts:
        try:
            if pygame.mixer.get_init():
                pygame.mixer.quit()
        except Exception:
            pass

        try:
            if driver:
                os.environ["SDL_AUDIODRIVER"] = driver
            else:
                os.environ.pop("SDL_AUDIODRIVER", None)

            pygame.mixer.init(
                frequency=freq,
                size=-16,
                channels=2,
                buffer=buffer,
                allowedchanges=allowed,
            )
            init_tuple = pygame.mixer.get_init()
            _pygame_available = True
            _pygame_error = ""
            _pygame_backend = f"driver={driver or 'default'} init={init_tuple} buffer={buffer}"
            try:
                from src.utils.logger import logger
                logger.info("AudioPlayer", f"Pygame mixer initialized ({_pygame_backend})")
            except Exception:
                pass
            return
        except Exception as e:
            init_errors.append(f"{driver or 'default'}@{freq}/{buffer}: {e}")

    _pygame_error = "; ".join(init_errors)[:500]
    try:
        from src.utils.logger import logger
        logger.error("AudioPlayer", f"Failed to initialize mixer: {_pygame_error}")
    except Exception:
        pass


class AudioPlayer:
    """Simple audio player with play/pause/stop/volume controls."""

    def __init__(self):
        self._ffplay = _find_ffplay()
        self._ffplay_proc: Optional[subprocess.Popen] = None
        self._ffplay_offset = 0.0
        self._ffplay_anchor = 0.0
        self._ffplay_duration = 0.0
        self._ffplay_paused = False
        self._backend = "ffplay" if self._ffplay else "pygame"
        self._current_file: Optional[Path] = None
        self._playing = False
        self._paused = False
        self._volume = 0.7
        self._seek_offset = 0.0       # track position (seconds) at last seek/play
        self._raw_pos_at_anchor = 0.0  # get_pos() value (seconds) at last seek/play

    @property
    def available(self) -> bool:
        if self._ffplay:
            return True
        _ensure_mixer()
        return _pygame_available

    @property
    def is_playing(self) -> bool:
        if self._backend == "ffplay":
            if self._ffplay_paused:
                return True
            if self._ffplay_proc and self._ffplay_proc.poll() is None:
                return True
            if self._playing:
                self._playing = False
            return False
        if not _pygame_initialized or not _pygame_available:
            return False
        return pygame.mixer.music.get_busy() or self._paused

    @property
    def is_paused(self) -> bool:
        if self._backend == "ffplay":
            return self._ffplay_paused
        return self._paused

    @property
    def current_file(self) -> Optional[Path]:
        return self._current_file

    def _estimate_duration(self, file_path: Path) -> float:
        """Best-effort duration estimation in seconds."""
        if not file_path.exists():
            return 0.0
        try:
            import wave
            if file_path.suffix.lower() == ".wav":
                with wave.open(str(file_path), "rb") as wf:
                    rate = wf.getframerate()
                    if rate > 0:
                        return wf.getnframes() / float(rate)
        except Exception:
            pass
        try:
            size = file_path.stat().st_size
            return size / 24000.0
        except Exception:
            return 0.0

    def _terminate_ffplay(self):
        """Terminate ffplay process if active."""
        proc = self._ffplay_proc
        if not proc:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=0.8)
                except Exception:
                    proc.kill()
                    try:
                        proc.wait(timeout=0.5)
                    except Exception:
                        pass
        except Exception:
            pass
        self._ffplay_proc = None

    def _play_file_ffplay(self, file_path: Path, start: float = 0.0) -> tuple[bool, str]:
        """Play via ffplay backend."""
        if not self._ffplay:
            return False, "ffplay not available"
        self._terminate_ffplay()
        try:
            vol = max(0, min(100, int(round(self._volume * 100.0))))
            cmd = [
                self._ffplay,
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "error",
                "-volume",
                str(vol),
            ]
            if start > 0.0:
                cmd.extend(["-ss", f"{start:.3f}"])
            cmd.append(str(file_path))
            self._ffplay_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self._backend = "ffplay"
            self._current_file = file_path
            self._playing = True
            self._paused = False
            self._ffplay_paused = False
            self._ffplay_offset = max(0.0, start)
            self._ffplay_anchor = time.monotonic()
            self._ffplay_duration = self._estimate_duration(file_path)
            try:
                from src.utils.logger import logger
                logger.info("AudioPlayer", f"Using ffplay backend (vol={vol}, start={start:.2f}s)")
            except Exception:
                pass
            return True, f"Playing: {file_path.name}"
        except Exception as e:
            self._ffplay_proc = None
            return False, f"ffplay backend failed: {e}"

    def play(self, file_path: Path) -> tuple[bool, str]:
        """Play an audio file. Returns (success, message)."""
        if not self._ffplay:
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
        if self._ffplay:
            return self._play_file_ffplay(file_path, start=0.0)
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
            self._backend = "pygame"
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
                return self._play_file(wav_path)
        except Exception:
            pass
        return None

    def stop(self):
        """Stop playback."""
        if self._backend == "ffplay":
            self._terminate_ffplay()
            self._playing = False
            self._paused = False
            self._ffplay_paused = False
            self._current_file = None
            self._ffplay_offset = 0.0
            self._ffplay_anchor = 0.0
            self._ffplay_duration = 0.0
            return
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
        if self._backend == "ffplay":
            if not self._playing or self._ffplay_paused:
                return
            self._ffplay_offset = self.get_position()
            self._terminate_ffplay()
            self._ffplay_paused = True
            self._paused = True
            return
        if not _pygame_initialized or not _pygame_available or not self._playing:
            return
        try:
            pygame.mixer.music.pause()
            self._paused = True
        except Exception:
            pass

    def unpause(self):
        """Resume paused playback."""
        if self._backend == "ffplay":
            if not self._ffplay_paused or not self._current_file:
                return
            ok, _msg = self._play_file_ffplay(self._current_file, start=self._ffplay_offset)
            if ok:
                self._ffplay_paused = False
                self._paused = False
            return
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
        new_volume = max(0.0, min(1.0, volume))
        old_step = int(round(self._volume * 100.0))
        new_step = int(round(new_volume * 100.0))
        self._volume = new_volume
        if new_step == old_step:
            return
        if self._backend == "ffplay" and self._playing and self._current_file and not self._ffplay_paused:
            # ffplay has no runtime volume IPC, so restart at current position.
            pos = self.get_position()
            self._play_file_ffplay(self._current_file, start=pos)
            return
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
        if self._backend == "ffplay":
            if not self._playing:
                return 0.0
            if self._ffplay_paused:
                return max(0.0, self._ffplay_offset)
            if self._ffplay_proc and self._ffplay_proc.poll() is None:
                pos = self._ffplay_offset + (time.monotonic() - self._ffplay_anchor)
                if self._ffplay_duration > 0.0:
                    return max(0.0, min(self._ffplay_duration, pos))
                return max(0.0, pos)
            self._playing = False
            if self._ffplay_duration > 0.0:
                self._ffplay_offset = self._ffplay_duration
            return max(0.0, self._ffplay_offset)
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
        if self._backend == "ffplay":
            if self._ffplay_duration > 0.0:
                return self._ffplay_duration
            if self._current_file:
                self._ffplay_duration = self._estimate_duration(self._current_file)
                return self._ffplay_duration
            return 0.0
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
        if self._backend == "ffplay":
            if not self._current_file:
                return
            pos = max(0.0, position)
            if self._ffplay_duration > 0.0:
                pos = min(pos, self._ffplay_duration)
            if self._ffplay_paused:
                self._ffplay_offset = pos
                return
            if self._playing:
                if abs(self.get_position() - pos) < 0.05:
                    return
                self._play_file_ffplay(self._current_file, start=pos)
            return
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
