"""NUS3AUDIO parser and LOPUS-to-OGG converter for audio preview.

NUS3AUDIO is Nintendo's audio container format used in SSBU.
Inside it, tracks are typically stored in LOPUS format (Nintendo's
Opus variant with custom framing). This module extracts the audio
data and converts LOPUS to standard OGG Opus for playback.
"""
import struct
import subprocess
import shutil
import tempfile
import os
from pathlib import Path
from typing import Optional


# Cache whether ffmpeg is available (checked once)
_ffmpeg_path: Optional[str] = None
_ffmpeg_checked = False

RIFF_MAGIC = b"RIFF"
WAV_HEADER_SIZE = 44
WAV_MIN_HEADER_SIZE = WAV_HEADER_SIZE
WAV_SAMPLE_RATE_HZ = "48000"
WAV_SAMPLE_FORMAT = "s16"
FFMPEG_TIMEOUT_SECONDS = 30
LOG_STDERR_PREVIEW_CHARS = 800
PCM_ANALYSIS_MIN_BYTES = 4000
PCM_WINDOW_BYTES_VALIDATE = 96000
PCM_WINDOW_BYTES_SCORE = 120000
PCM_WINDOW_BYTES_NOISE = 160000
INT16_SAMPLE_WIDTH_BYTES = 2
U32_BYTE_WIDTH = 4
INT16_ARRAY_TYPECODE = "h"
MIN_SAMPLES_VALIDATE = 100
MIN_SAMPLES_SCORE = 200
ANALYSIS_SAMPLE_COUNT_VALIDATE = 2000
ANALYSIS_SAMPLE_COUNT_SCORE = 12000
ANALYSIS_MAX_STEREO_SAMPLES = 6000
NON_ZERO_MIN_SAMPLES = 10
CLIPPING_ABS_THRESHOLD = 32000
CLIPPING_MAX_RATIO_VALIDATE = 0.8
INT16_ABS_MAX = 32768.0
SCORE_INVALID = -1.0
SCORE_INVALID_CHANNELS = 0
CHANNEL_COUNT_OFFSET = 22
CHANNEL_COUNT_FALLBACK = 2
STEREO_CHANNEL_COUNT = 2
SCORE_NON_ZERO_CAP = 1.2
SCORE_NON_ZERO_SCALE = 1.5
SCORE_RMS_CAP = 2.0
SCORE_RMS_SCALE = 7.0
SCORE_PEAK_CAP = 1.2
SCORE_PEAK_SCALE = 1.8
SCORE_CLIP_CAP = 1.0
SCORE_CLIP_SCALE = 6.0
SCORE_CLIP_PENALTY_THRESHOLD = 0.2
SCORE_CLIP_PENALTY = 1.5
SCORE_ZCR_HIGH_THRESHOLD = 0.42
SCORE_ZCR_LOW_THRESHOLD = 0.001
SCORE_ZCR_PENALTY = 1.0
SCORE_STEREO_BONUS = 0.25
STEREO_CORR_MIN_SAMPLES = 8
STEREO_CORR_EPSILON = 1e-9
BITS_PER_BYTE = 8.0
KILOBITS_DIVISOR = 1000.0
IMPOSSIBLE_BITRATE_THRESHOLD = 1600.0
VERY_HIGH_BITRATE_THRESHOLD = 1200.0
HIGH_BITRATE_THRESHOLD = 900.0
MEDIUM_HIGH_BITRATE_THRESHOLD = 700.0
MODERATELY_HIGH_BITRATE_THRESHOLD = 512.0
LOW_BITRATE_THRESHOLD_MIN = 8.0
LOW_BITRATE_THRESHOLD_LOW = 16.0
LOW_BITRATE_THRESHOLD_MID = 24.0
EXPECTED_BITRATE_MIN = 32.0
EXPECTED_BITRATE_MAX = 320.0
BITRATE_BONUS = 0.25
BITRATE_PENALTY_IMPOSSIBLE = 3.0
BITRATE_PENALTY_VERY_HIGH = 2.4
BITRATE_PENALTY_HIGH = 1.8
BITRATE_PENALTY_MEDIUM_HIGH = 1.1
BITRATE_PENALTY_MODERATE_HIGH = 0.6
BITRATE_PENALTY_TOO_LOW = 2.0
BITRATE_PENALTY_LOW = 1.2
BITRATE_PENALTY_MID = 0.6
MIN_DURATION_BYTES_PER_SECOND_CAP = 96000.0
DURATION_PENALTY_SEVERE_RATIO = 0.35
DURATION_PENALTY_MILD_RATIO = 0.6
DURATION_PENALTY_SEVERE = 2.0
DURATION_PENALTY_MILD = 1.0
CANDIDATE_MISSING_SCORE = -999.0
CANDIDATE_MONO_FORCED_PENALTY = 0.75
NOISE_OVERRIDE_TRIGGER_ZCR = 0.28
NOISE_OVERRIDE_TRIGGER_CORR = 0.62
NOISE_OVERRIDE_DURATION_TOLERANCE_S = 0.4
NOISE_OVERRIDE_BITRATE_TOLERANCE_MIN = 6.0
NOISE_OVERRIDE_BITRATE_TOLERANCE_RATIO = 0.08
NOISE_OVERRIDE_ZCR_TARGET = 0.12
NOISE_OVERRIDE_ZCR_MARGIN = 0.14
NOISE_OVERRIDE_MIN_CORR_BASE = 0.65
NOISE_OVERRIDE_CORR_MARGIN = 0.15
NOISE_OVERRIDE_RAW_MARGIN = 0.8
FFMPEG_OVERWRITE_FLAG = "-y"
FFMPEG_INPUT_FLAG = "-i"
FFMPEG_AUDIO_RATE_FLAG = "-ar"
FFMPEG_SAMPLE_FORMAT_FLAG = "-sample_fmt"
OPUS_SEGMENT_SIZE_MAX = 255
OPUS_SEGMENTS_PER_PAGE_TARGET = 240
OPUS_SERIAL_SSBU = 0x53534255
OPUS_PAGE_BOS_FLAG = 0x02
OPUS_PAGE_EOS_FLAG = 0x04
OPUS_PAGE_NO_FLAGS = 0x00
OPUS_TOC_CONFIG_SHIFT = 3
OPUS_TOC_CONFIG_MASK = 0x1F
OPUS_DURATION_VARIANTS = 4
OPUS_DEFAULT_SAMPLES_PER_FRAME = 960
OPUS_MIN_VALID_FRAME_COUNT = 10
OPUS_MAX_VALID_FRAME_SAMPLES = 50
OPUS_MIN_MUSIC_CONFIG = 12
OPUS_MAX_CONFIG_VALUE = 31
OPUS_FRAME_SIZE_SCAN_MAX = 2048
OPUS_FRAME_SIZE_HARD_MAX = 8192
OPUS_FRAME_SIZE_U16_MAX = 0xFFFF
LOPUS_MIN_INPUT_SIZE = 30
LOPUS_DEFAULT_SAMPLE_RATE = 48000
LOPUS_DEFAULT_PRE_SKIP = 312
LOPUS_DEFAULT_HEADER_SIZE = 0x28
LOPUS_MAGIC_V1 = 0x80000001
LOPUS_MAGIC_V2 = 0x80000002
LOPUS_MAGIC_V3 = 0x80000003
LOPUS_MAGIC_V4 = 0x80000004
LOPUS_MIN_SLOT_SIZE = 8
LOPUS_MAX_SLOT_SIZE = 0x2000
LOPUS_MIN_CHANNELS = 1
LOPUS_MAX_CHANNELS = 8
LOPUS_MIN_PRE_SKIP = 1
LOPUS_MAX_PRE_SKIP = 10000
LOPUS_MAX_SAMPLE_RATE = 200000
LOPUS_HEADER_SIZE_OFFSET = 0x04
LOPUS_SAMPLE_RATE_OFFSET = 0x0C
LOPUS_CHANNEL_COUNT_OFFSET = 0x10
LOPUS_FRAME_SIZE_OFFSET = 0x14
LOPUS_PRE_SKIP_OFFSETS = (0x1C, 0x1A, 0x14)
LOPUS_FALLBACK_FRAME_SIZES = (640, 1280, 512, 1024, 0x500, 0x300, 0x800)
LOPUS_START_OFFSET_BASES = (0x20, 0x24, 0x28, 0x2C, 0x30, 0x38, 0x40)
LOPUS_HEADER_START_FALLBACKS = (0x28, 0x20, 0x30, 0x38, 0x40, 0x18)
OPUS_CONTAINER_HEADER_MIN_SIZE = 0x28
OPUS_CONTAINER_DATA_OFFSET_OFFSET = 0x20
OPUS_CONTAINER_DATA_SIZE_OFFSET = 0x24
OPUS_CONTAINER_CHANNELS_OFFSET = 0x0C
OPUS_CONTAINER_SAMPLE_RATE_OFFSET = 0x10
OPUS_CONTAINER_MIN_DATA_OFFSET = 0x10
OPUS_CONTAINER_MAX_DATA_OFFSET = 0x100
OPUS_CONTAINER_SAMPLE_RATE_MIN = 8000
OPUS_CONTAINER_SAMPLE_RATE_MAX = 192000
OPUS_CONTAINER_SIZE_SLACK_BYTES = 64
OPUS_PAYLOAD_OFFSETS = (4, 0x20, 0x30, 0x40)
OPUS_HEADER_SCAN_OFFSETS = (8, 12, 16, 20, 24, 28, 32, 48, 64, 0x28, 0x30)
OPUS_FIXED_SLOT_SIZES = (0x280, 0x500, 0x200, 0x400, 0x100, 0x300, 0x600, 0x800)
OPUS_FIXED_SLOT_SKIP_OFFSETS = (4, 8, 12, 16, 0x28, 0x30)
OPUS_RAW_SLOT_FALLBACKS = (0x280, 0x500, 0x200, 0x400)
OPUS_RAW_SCAN_ALIGN_STEP = 4
OPUS_RAW_SCAN_MAX_OFFSET = 256
OPUS_RAW_PADDING_OFFSETS = (0, 4, 8, 16)
OPUS_RAW_SLOT_MAX = 0x1000
OPUS_CBR_SEARCH_START_DEFAULT = 0x18
OPUS_CBR_TOC_CONSISTENCY_MIN_RATIO = 0.8
FFMPEG_DIRECT_NOISE_ZCR_THRESHOLD = 0.38
FFMPEG_DIRECT_NOISE_CORR_THRESHOLD = 0.45
FFMPEG_RAW_MIN_WAV_BYTES = 1000
OPUS_PAGE_SEQUENCE_START = 2
OPUS_INNER_DATA_OFFSET_FALLBACK = 4
OPUS_LIKELY_HEADER_SIZE_MIN = 0x40
OPUS_LIKELY_HEADER_SIZE_MAX = 0x100
OPUS_LOPUS_MAGIC_MASK = 0x80000000
LOPUS_SUPPORTED_TYPES = (1, 2, 3, 4)
LOPUS_TYPE_V2 = 2
LOPUS_TYPE_V2_SLOT_OFFSET = 0x0A
LOPUS_HEADER_FIELD_OFFSET = 4
LOPUS_PRESKIP_U16_OFFSET = 0x1A
LOPUS_PRESKIP_U32_OFFSET = 0x1C
WINDOWS_FFMPEG_CANDIDATES = (
    r"%LOCALAPPDATA%\Programs\ffmpeg\bin\ffmpeg.exe",
    r"%ProgramFiles%\ffmpeg\bin\ffmpeg.exe",
    r"%ProgramFiles(x86)%\ffmpeg\bin\ffmpeg.exe",
)


def _find_ffmpeg() -> Optional[str]:
    """Find ffmpeg executable. Returns path or None."""
    global _ffmpeg_path, _ffmpeg_checked
    if _ffmpeg_checked:
        return _ffmpeg_path
    _ffmpeg_checked = True
    path = shutil.which("ffmpeg")
    if path:
        _ffmpeg_path = path
        return path
    for candidate_pattern in WINDOWS_FFMPEG_CANDIDATES:
        candidate = os.path.expandvars(candidate_pattern)
        if os.path.isfile(candidate):
            _ffmpeg_path = candidate
            return candidate
    return None


def _run_ffmpeg_to_wav(input_path: Path, output_path: Path):
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return None
    return subprocess.run(
        [
            ffmpeg,
            FFMPEG_OVERWRITE_FLAG,
            FFMPEG_INPUT_FLAG,
            str(input_path),
            FFMPEG_AUDIO_RATE_FLAG,
            WAV_SAMPLE_RATE_HZ,
            FFMPEG_SAMPLE_FORMAT_FLAG,
            WAV_SAMPLE_FORMAT,
            str(output_path),
        ],
        capture_output=True,
        timeout=FFMPEG_TIMEOUT_SECONDS,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _convert_ogg_opus_to_wav(ogg_path: Path) -> Optional[Path]:
    """Convert an OGG Opus file to WAV using ffmpeg.

    pygame's SDL_mixer uses stb_vorbis for .ogg files, which only
    supports Vorbis, not Opus. ffmpeg can decode Opus to WAV.
    Returns path to WAV file, or None if conversion failed.
    """
    if not _find_ffmpeg():
        return None
    # Write WAV to the audio cache directory so cleanup_cache()
    # removes it.  Previous versions wrote to the system temp dir
    # which leaked files on crash.
    cache_dir = _get_cache_dir()
    wav_path = cache_dir / (ogg_path.stem + ".wav")
    try:
        result = _run_ffmpeg_to_wav(ogg_path, wav_path)
        if result is None:
            return None
        if (
            result.returncode == 0
            and wav_path.exists()
            and wav_path.stat().st_size > WAV_MIN_HEADER_SIZE
        ):
            return wav_path
        try:
            from src.utils.logger import logger

            stderr = (
                result.stderr.decode("utf-8", errors="replace")[
                    :LOG_STDERR_PREVIEW_CHARS
                ]
                if result.stderr
                else ""
            )
            logger.warn("NUS3AUDIO", f"ffmpeg conversion failed (rc={result.returncode}): {stderr}")
        except Exception:
            pass
    except Exception as e:
        try:
            from src.utils.logger import logger
            logger.warn("NUS3AUDIO", f"ffmpeg conversion error: {e}")
        except Exception:
            pass
    return None


# OGG CRC32 lookup table (polynomial 0x04C11DB7)
_OGG_CRC_TABLE: Optional[list[int]] = None


def _validate_wav_quality(wav_path: Path) -> bool:
    """Basic quality check for a WAV file produced by ffmpeg.

    Reads a sample of PCM data and checks that:
    1. Not all silence (zeros)
    2. Not pure noise (nearly all samples at extreme values)
    3. Has reasonable amplitude distribution

    Returns True if the WAV looks like valid audio.
    """
    try:
        with open(wav_path, 'rb') as f:
            header = f.read(WAV_HEADER_SIZE)
            if len(header) < WAV_MIN_HEADER_SIZE or header[:4] != RIFF_MAGIC:
                return False
            pcm = f.read(PCM_WINDOW_BYTES_VALIDATE)
        if len(pcm) < PCM_ANALYSIS_MIN_BYTES:
            return False

        import array

        samples = array.array(INT16_ARRAY_TYPECODE)
        samples.frombytes(pcm[:len(pcm) - len(pcm) % INT16_SAMPLE_WIDTH_BYTES])
        if len(samples) < MIN_SAMPLES_VALIDATE:
            return False

        sample_window = samples[:ANALYSIS_SAMPLE_COUNT_VALIDATE]
        non_zero = sum(1 for s in sample_window if s != 0)
        if non_zero < NON_ZERO_MIN_SAMPLES:
            return False

        clipping = sum(1 for s in sample_window if abs(s) > CLIPPING_ABS_THRESHOLD)
        if clipping > len(sample_window) * CLIPPING_MAX_RATIO_VALIDATE:
            return False

        return True
    except Exception:
        return False


def _score_wav_quality(wav_path: Path) -> tuple[float, int]:
    """Return a rough quality score for a decoded WAV candidate.

    Higher score generally means less clipped/noisy output.
    Returns (score, channel_count).
    """
    try:
        with open(wav_path, 'rb') as f:
            header = f.read(WAV_HEADER_SIZE)
            if len(header) < WAV_MIN_HEADER_SIZE or header[:4] != RIFF_MAGIC:
                return SCORE_INVALID, SCORE_INVALID_CHANNELS
            channels = int(struct.unpack_from('<H', header, CHANNEL_COUNT_OFFSET)[0])
            pcm = f.read(PCM_WINDOW_BYTES_SCORE)
        if len(pcm) < PCM_ANALYSIS_MIN_BYTES:
            return SCORE_INVALID, channels

        import array

        samples = array.array(INT16_ARRAY_TYPECODE)
        samples.frombytes(pcm[:len(pcm) - len(pcm) % INT16_SAMPLE_WIDTH_BYTES])
        if len(samples) < MIN_SAMPLES_SCORE:
            return SCORE_INVALID, channels

        view = samples[:min(len(samples), ANALYSIS_SAMPLE_COUNT_SCORE)]
        n = len(view)
        if n < MIN_SAMPLES_SCORE:
            return SCORE_INVALID, channels

        non_zero = sum(1 for s in view if s != 0)
        clipping = sum(1 for s in view if abs(s) >= CLIPPING_ABS_THRESHOLD)
        peak = max(abs(s) for s in view)
        rms = (sum(s * s for s in view) / n) ** 0.5
        zero_crossings = 0
        for i in range(1, n):
            a = view[i - 1]
            b = view[i]
            if (a < 0 <= b) or (a > 0 >= b):
                zero_crossings += 1

        non_zero_ratio = non_zero / n
        clipping_ratio = clipping / n
        peak_norm = peak / INT16_ABS_MAX
        rms_norm = rms / INT16_ABS_MAX
        zcr = zero_crossings / max(1, n - 1)

        score = 0.0
        score += min(SCORE_NON_ZERO_CAP, non_zero_ratio * SCORE_NON_ZERO_SCALE)
        score += min(SCORE_RMS_CAP, rms_norm * SCORE_RMS_SCALE)
        score += min(SCORE_PEAK_CAP, peak_norm * SCORE_PEAK_SCALE)
        score += max(SCORE_INVALID_CHANNELS, SCORE_CLIP_CAP - clipping_ratio * SCORE_CLIP_SCALE)
        if clipping_ratio > SCORE_CLIP_PENALTY_THRESHOLD:
            score -= SCORE_CLIP_PENALTY
        if zcr > SCORE_ZCR_HIGH_THRESHOLD:
            score -= SCORE_ZCR_PENALTY
        if zcr < SCORE_ZCR_LOW_THRESHOLD:
            score -= SCORE_ZCR_PENALTY
        if channels == STEREO_CHANNEL_COUNT:
            score += SCORE_STEREO_BONUS
        return score, channels
    except Exception:
        return SCORE_INVALID, SCORE_INVALID_CHANNELS


def _wav_duration_seconds(wav_path: Path) -> float:
    """Best-effort duration for a WAV file in seconds."""
    try:
        import wave
        with wave.open(str(wav_path), 'rb') as wf:
            rate = wf.getframerate()
            if rate <= 0:
                return 0.0
            return wf.getnframes() / float(rate)
    except Exception:
        return 0.0


def _wav_noise_signature(wav_path: Path) -> tuple[float, float]:
    """Return quick noise-signature metrics as (zcr, stereo_corr)."""
    try:
        with open(wav_path, 'rb') as f:
            header = f.read(WAV_HEADER_SIZE)
            if len(header) < WAV_MIN_HEADER_SIZE or header[:4] != RIFF_MAGIC:
                return 0.0, 1.0
            channels = (
                int(struct.unpack_from("<H", header, CHANNEL_COUNT_OFFSET)[0])
                if len(header) >= CHANNEL_COUNT_OFFSET + INT16_SAMPLE_WIDTH_BYTES
                else CHANNEL_COUNT_FALLBACK
            )
            pcm = f.read(PCM_WINDOW_BYTES_NOISE)
        if len(pcm) < PCM_ANALYSIS_MIN_BYTES:
            return 0.0, 1.0

        import array

        samples = array.array(INT16_ARRAY_TYPECODE)
        samples.frombytes(pcm[:len(pcm) - len(pcm) % INT16_SAMPLE_WIDTH_BYTES])
        if len(samples) < MIN_SAMPLES_SCORE:
            return 0.0, 1.0

        view = samples[:min(len(samples), ANALYSIS_SAMPLE_COUNT_SCORE)]
        n = len(view)
        if n < MIN_SAMPLES_SCORE:
            return 0.0, 1.0

        zero_crossings = 0
        for i in range(1, n):
            a = view[i - 1]
            b = view[i]
            if (a < 0 <= b) or (a > 0 >= b):
                zero_crossings += 1
        zcr = zero_crossings / max(1, n - 1)

        if channels != STEREO_CHANNEL_COUNT:
            return zcr, 0.0

        left = view[0::2]
        right = view[1::2]
        m = min(len(left), len(right), ANALYSIS_MAX_STEREO_SAMPLES)
        if m < STEREO_CORR_MIN_SAMPLES:
            return zcr, 1.0
        left = left[:m]
        right = right[:m]
        mean_l = sum(left) / m
        mean_r = sum(right) / m
        var_l = sum((x - mean_l) ** 2 for x in left) / m
        var_r = sum((x - mean_r) ** 2 for x in right) / m
        cov = sum((left[i] - mean_l) * (right[i] - mean_r) for i in range(m)) / m
        corr = cov / ((var_l * var_r) ** 0.5 + STEREO_CORR_EPSILON)
        return zcr, corr
    except Exception:
        return 0.0, 1.0


def _score_opus_candidate(base_score: float, duration_s: float,
                          encoded_size_bytes: int) -> tuple[float, float]:
    """Adjust raw PCM quality score using encoded-size plausibility.

    Wrong offsets can decode to very short/noisy audio that still gets a
    deceptively high PCM score. We penalize implausible implied bitrates.

    Returns (adjusted_score, implied_bitrate_kbps).
    """
    if duration_s <= 0.0 or encoded_size_bytes <= 0:
        return base_score - BITRATE_PENALTY_IMPOSSIBLE, 0.0

    bitrate_kbps = (encoded_size_bytes * BITS_PER_BYTE) / (duration_s * KILOBITS_DIVISOR)
    score = base_score

    if bitrate_kbps > IMPOSSIBLE_BITRATE_THRESHOLD:
        score -= BITRATE_PENALTY_IMPOSSIBLE
    elif bitrate_kbps > VERY_HIGH_BITRATE_THRESHOLD:
        score -= BITRATE_PENALTY_VERY_HIGH
    elif bitrate_kbps > HIGH_BITRATE_THRESHOLD:
        score -= BITRATE_PENALTY_HIGH
    elif bitrate_kbps > MEDIUM_HIGH_BITRATE_THRESHOLD:
        score -= BITRATE_PENALTY_MEDIUM_HIGH
    elif bitrate_kbps > MODERATELY_HIGH_BITRATE_THRESHOLD:
        score -= BITRATE_PENALTY_MODERATE_HIGH

    if bitrate_kbps < LOW_BITRATE_THRESHOLD_MIN:
        score -= BITRATE_PENALTY_TOO_LOW
    elif bitrate_kbps < LOW_BITRATE_THRESHOLD_LOW:
        score -= BITRATE_PENALTY_LOW
    elif bitrate_kbps < LOW_BITRATE_THRESHOLD_MID:
        score -= BITRATE_PENALTY_MID
    elif EXPECTED_BITRATE_MIN <= bitrate_kbps <= EXPECTED_BITRATE_MAX:
        score += BITRATE_BONUS

    min_expected_duration = encoded_size_bytes / MIN_DURATION_BYTES_PER_SECOND_CAP
    if duration_s < min_expected_duration * DURATION_PENALTY_SEVERE_RATIO:
        score -= DURATION_PENALTY_SEVERE
    elif duration_s < min_expected_duration * DURATION_PENALTY_MILD_RATIO:
        score -= DURATION_PENALTY_MILD

    return score, bitrate_kbps


def _select_best_candidate_index(candidates: list[dict]) -> int:
    """Select the best decode candidate with conservative channel handling."""
    if not candidates:
        return -1

    stereo_available = any(
        int(c.get("out_channels", 0) or 0) >= 2 for c in candidates
    )

    def _adjusted_score(c: dict) -> float:
        score = float(c.get("score", CANDIDATE_MISSING_SCORE))
        forced_channels = c.get("forced_channels")
        out_channels = int(c.get("out_channels", 0) or 0)
        if stereo_available and forced_channels == 1 and out_channels == 1:
            score -= CANDIDATE_MONO_FORCED_PENALTY
        return score

    best_idx = 0
    best_rank = None
    for i, c in enumerate(candidates):
        out_channels = int(c.get("out_channels", 0) or 0)
        corr_rank = float(c.get("corr", 0.0)) if out_channels >= 2 else -1.0
        rank = (
            _adjusted_score(c),
            float(c.get("raw", CANDIDATE_MISSING_SCORE)),
            float(c.get("duration", 0.0)),
            -float(c.get("zcr", 1.0)),
            corr_rank,
        )
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best_idx = i

    return best_idx


def _pick_low_noise_override(candidates: list[dict], best_idx: int) -> int:
    """Optionally replace best candidate when it has a clear noise signature.

    This is intentionally narrow and only fires when:
    - best candidate looks hissy/noisy (high zcr, weak stereo correlation), and
    - another candidate has nearly identical timing/bitrate but much cleaner
      signature and not dramatically worse raw score.
    """
    if best_idx < 0 or best_idx >= len(candidates):
        return best_idx

    best = candidates[best_idx]
    # Trigger override checks whenever the selected decode has clearly
    # elevated high-frequency/noise signature, even if correlation is
    # not extremely low.
    if not (
        best["zcr"] >= NOISE_OVERRIDE_TRIGGER_ZCR
        and best["corr"] <= NOISE_OVERRIDE_TRIGGER_CORR
    ):
        return best_idx

    best_out_channels = int(best.get("out_channels", 0) or 0)
    if best_out_channels < 2:
        return best_idx

    best_dur = best["duration"]
    best_br = best["bitrate"]
    best_raw = best["raw"]

    alt_idx = best_idx
    alt_rank = None
    for i, c in enumerate(candidates):
        if i == best_idx:
            continue
        c_out_channels = int(c.get("out_channels", 0) or 0)
        if c_out_channels != best_out_channels:
            continue
        if abs(c["duration"] - best_dur) > NOISE_OVERRIDE_DURATION_TOLERANCE_S:
            continue
        if abs(c["bitrate"] - best_br) > max(
            NOISE_OVERRIDE_BITRATE_TOLERANCE_MIN,
            best_br * NOISE_OVERRIDE_BITRATE_TOLERANCE_RATIO,
        ):
            continue
        if c["zcr"] > min(NOISE_OVERRIDE_ZCR_TARGET, best["zcr"] - NOISE_OVERRIDE_ZCR_MARGIN):
            continue
        # Require clearly better stereo coherence, but avoid demanding
        # near-perfect correlation for tracks that are naturally wide.
        min_corr = max(NOISE_OVERRIDE_MIN_CORR_BASE, best["corr"] + NOISE_OVERRIDE_CORR_MARGIN)
        if c["corr"] < min_corr:
            continue
        if c["raw"] < (best_raw - NOISE_OVERRIDE_RAW_MARGIN):
            continue
        rank = (
            c["score"],
            c["raw"],
            -c["zcr"],
            c["corr"],
        )
        if alt_rank is None or rank > alt_rank:
            alt_rank = rank
            alt_idx = i

    return alt_idx


def _build_crc_table():
    global _OGG_CRC_TABLE
    _OGG_CRC_TABLE = []
    for i in range(256):
        crc = i << 24
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
        _OGG_CRC_TABLE.append(crc)


def _ogg_crc32(data: bytes) -> int:
    """OGG uses its own CRC32 variant (not the standard zlib one)."""
    global _OGG_CRC_TABLE
    if _OGG_CRC_TABLE is None:
        _build_crc_table()
    crc = 0
    for byte in data:
        crc = ((crc << 8) ^ _OGG_CRC_TABLE[((crc >> 24) ^ byte) & 0xFF]) & 0xFFFFFFFF
    return crc


def _make_ogg_page(data: bytes, serial: int, page_seq: int,
                   granule: int, flags: int, segment_sizes: list[int]) -> bytes:
    """Build a single OGG page with proper CRC."""
    n_segments = len(segment_sizes)
    # Header without CRC (CRC field = 0)
    header = struct.pack(
        '<4sBBqIIIB',
        b'OggS',       # capture pattern
        0,              # stream structure version
        flags,          # header type flags
        granule,        # granule position (signed 64-bit)
        serial,         # bitstream serial number
        page_seq,       # page sequence number
        0,              # CRC checksum placeholder
        n_segments,     # number of page segments
    )
    header += bytes(segment_sizes)

    # Calculate CRC over header + data
    full = header + data
    crc = _ogg_crc32(full)

    # Patch CRC into header (offset 22)
    header = header[:22] + struct.pack('<I', crc) + header[26:]
    return header + data


def _segment_table_for_packet(packet_size: int) -> list[int]:
    """Build OGG segment table entries for a single packet."""
    segments = []
    remaining = packet_size
    while remaining >= OPUS_SEGMENT_SIZE_MAX:
        segments.append(OPUS_SEGMENT_SIZE_MAX)
        remaining -= OPUS_SEGMENT_SIZE_MAX
    segments.append(remaining)
    return segments


def _make_opus_head(channels: int, pre_skip: int, sample_rate: int) -> bytes:
    """Create the OpusHead identification header."""
    return struct.pack(
        '<8sBBHIhB',
        b'OpusHead',
        1,              # version
        channels,
        pre_skip,
        sample_rate,
        0,              # output gain
        0,              # channel mapping family (0 = mono/stereo)
    )


def _make_opus_tags() -> bytes:
    """Create the OpusTags (comment) header."""
    vendor = b'SSBUModManager'
    return struct.pack('<8sI', b'OpusTags', len(vendor)) + vendor + struct.pack('<I', 0)


def _extract_frames_with_slot(data: bytes, start: int, slot_size: int,
                              endian: str = '<') -> list[bytes]:
    """Extract Opus frames from *data* using fixed-size slots.

    Each slot is *slot_size* bytes.  The first 4 bytes of each slot hold
    the actual Opus frame length (in *endian* byte order), followed by the
    frame data and zero-padding.

    Args:
        data: Raw LOPUS data (with header).
        start: Byte offset where frame slots begin (typically header_size).
        slot_size: Total bytes per slot (including the 4-byte size prefix).
        endian: '<' for little-endian, '>' for big-endian frame sizes.

    Returns:
        List of raw Opus frame bytes (may be empty).
    """
    fmt = f'{endian}I'
    frames: list[bytes] = []
    pos = start
    while pos + U32_BYTE_WIDTH <= len(data):
        actual_size = struct.unpack_from(fmt, data, pos)[0]
        if actual_size == 0 or actual_size >= slot_size:
            break
        if pos + U32_BYTE_WIDTH + actual_size > len(data):
            break
        frames.append(data[pos + U32_BYTE_WIDTH:pos + U32_BYTE_WIDTH + actual_size])
        pos += slot_size
    return frames


def _auto_detect_slot_frames(data: bytes, start: int) -> Optional[list[bytes]]:
    """Auto-detect slot size by scanning the data for valid Opus frame patterns.

    Reads the first frame size at *start*, then scans ahead to find where
    the next valid frame size occurs.  The distance between them is the
    slot size.

    Returns:
        List of validated Opus frames, or None if detection fails.
    """
    if start + LOPUS_MIN_SLOT_SIZE > len(data):
        return None

    # Try both endiannesses for the first frame size
    for endian in ('<', '>'):
        fmt = f'{endian}I'
        first_size = struct.unpack_from(fmt, data, start)[0]
        if (
            first_size == 0
            or first_size > LOPUS_MAX_SLOT_SIZE
            or start + U32_BYTE_WIDTH + first_size > len(data)
        ):
            continue

        # The first frame data starts at start+4.  Check its TOC byte.
        first_toc = data[start + U32_BYTE_WIDTH]
        first_cfg = (first_toc >> OPUS_TOC_CONFIG_SHIFT) & OPUS_TOC_CONFIG_MASK

        # Scan from start + first_size + 4 onwards to find the next
        # frame size prefix that points to data with the same TOC config.
        for probe in range(
            start + first_size + U32_BYTE_WIDTH,
            min(start + LOPUS_MAX_SLOT_SIZE, len(data) - LOPUS_MIN_SLOT_SIZE),
        ):
            next_size = struct.unpack_from(fmt, data, probe)[0]
            if (
                next_size == 0
                or next_size > LOPUS_MAX_SLOT_SIZE
                or probe + U32_BYTE_WIDTH + next_size > len(data)
            ):
                continue
            next_toc = data[probe + U32_BYTE_WIDTH]
            next_cfg = (next_toc >> OPUS_TOC_CONFIG_SHIFT) & OPUS_TOC_CONFIG_MASK
            if next_cfg != first_cfg:
                continue

            # Potential slot size
            slot_size = probe - start
            if slot_size < LOPUS_MIN_SLOT_SIZE or slot_size > LOPUS_MAX_SLOT_SIZE:
                continue

            # Validate: extract frames with this slot size and check
            frames = _extract_frames_with_slot(data, start, slot_size, endian)
            if len(frames) >= OPUS_MIN_VALID_FRAME_COUNT and _validate_opus_frames(frames):
                return frames

    return None


def _lopus_to_ogg(lopus_data: bytes, force_channels: Optional[int] = None) -> bytes:
    """Convert Nintendo LOPUS data to standard OGG Opus.

    Args:
        lopus_data: Raw LOPUS data bytes.
        force_channels: If set, override the channel count from the header.
            Useful for retrying when the header's channel field is wrong.
    """
    if len(lopus_data) < LOPUS_MIN_INPUT_SIZE:
        raise ValueError(
            f"LOPUS data too short ({len(lopus_data)} bytes, need at least {LOPUS_MIN_INPUT_SIZE})"
        )

    magic = struct.unpack_from('<I', lopus_data, 0)[0]

        # header_size is always at offset 0x04 for all versions.
    header_size = (
        struct.unpack_from("<I", lopus_data, LOPUS_HEADER_SIZE_OFFSET)[0]
        if len(lopus_data) >= LOPUS_MIN_SLOT_SIZE
        else LOPUS_DEFAULT_HEADER_SIZE
    )
    # sample_rate is always at 0x0C for all known versions.
    sample_rate = (
        struct.unpack_from("<I", lopus_data, LOPUS_SAMPLE_RATE_OFFSET)[0]
        if len(lopus_data) > LOPUS_SAMPLE_RATE_OFFSET + 3
        else LOPUS_DEFAULT_SAMPLE_RATE
    )

    # channel_count and frame_size (slot size) differ between versions.
    # Collect candidates for each field and try them all.
    channel_candidates: list[int] = []
    frame_size_candidates: list[int] = []
    pre_skip = LOPUS_DEFAULT_PRE_SKIP

    if magic in (LOPUS_MAGIC_V4, LOPUS_MAGIC_V3):
        # v3/v4: well-documented layout
        channel_candidates.append(
            struct.unpack_from("<I", lopus_data, LOPUS_CHANNEL_COUNT_OFFSET)[0]
        )
        frame_size_candidates.append(
            struct.unpack_from("<I", lopus_data, LOPUS_FRAME_SIZE_OFFSET)[0]
        )
        if len(lopus_data) > 0x1D:
            pre_skip = struct.unpack_from("<H", lopus_data, LOPUS_PRE_SKIP_OFFSETS[0])[0]
    elif magic in (LOPUS_MAGIC_V2, LOPUS_MAGIC_V1):
        # v1/v2: header layout varies between tools.
        # Strategy: try BOTH known layouts and pick the one that works.
        # Layout A (some references): channel_count=u8@0x09, frame_size=u16@0x0A
        if len(lopus_data) > 0x0B:
            ch_a = lopus_data[0x09]
            fs_a = struct.unpack_from('<H', lopus_data, 0x0A)[0]
            if ch_a > 0:
                channel_candidates.append(ch_a)
            if fs_a > 0:
                frame_size_candidates.append(fs_a)
        # Layout B (same as v3/v4): channel_count=u32@0x10, frame_size=u32@0x14
        if len(lopus_data) > 0x17:
            ch_b = struct.unpack_from('<I', lopus_data, 0x10)[0]
            fs_b = struct.unpack_from('<I', lopus_data, 0x14)[0]
            if LOPUS_MIN_CHANNELS <= ch_b <= LOPUS_MAX_CHANNELS:
                channel_candidates.append(ch_b)
            if LOPUS_MIN_SLOT_SIZE <= fs_b <= LOPUS_MAX_SLOT_SIZE:
                frame_size_candidates.append(fs_b)
        # pre_skip: try multiple offsets
        for ps_off in LOPUS_PRE_SKIP_OFFSETS:
            if len(lopus_data) > ps_off + 1:
                ps = struct.unpack_from('<H', lopus_data, ps_off)[0]
                if LOPUS_MIN_PRE_SKIP < ps < LOPUS_MAX_PRE_SKIP:
                    pre_skip = ps
                    break
    else:
        # Unknown version  try v3/v4 layout first
        if len(lopus_data) > 0x17:
            ch = struct.unpack_from('<I', lopus_data, 0x10)[0]
            fs = struct.unpack_from('<I', lopus_data, 0x14)[0]
            if LOPUS_MIN_CHANNELS <= ch <= LOPUS_MAX_CHANNELS:
                channel_candidates.append(ch)
            if LOPUS_MIN_SLOT_SIZE <= fs <= LOPUS_MAX_SLOT_SIZE:
                frame_size_candidates.append(fs)

    # Add common defaults as fallbacks
    if not channel_candidates:
        channel_candidates = [STEREO_CHANNEL_COUNT]
    if not frame_size_candidates:
        frame_size_candidates = [LOPUS_FALLBACK_FRAME_SIZES[0]]

    # Add common frame sizes as extra fallbacks
    for fs in LOPUS_FALLBACK_FRAME_SIZES:
        if fs not in frame_size_candidates:
            frame_size_candidates.append(fs)

    # De-duplicate channel candidates and ensure valid values
    channel_candidates = [
        c
        for c in dict.fromkeys(channel_candidates)
        if LOPUS_MIN_CHANNELS <= c <= LOPUS_MAX_CHANNELS
    ]
    if not channel_candidates:
        channel_candidates = [STEREO_CHANNEL_COUNT]
    # De-duplicate frame sizes, ensure valid range
    frame_size_candidates = [
        f
        for f in dict.fromkeys(frame_size_candidates)
        if LOPUS_MIN_SLOT_SIZE <= f <= LOPUS_MAX_SLOT_SIZE
    ]

    # Sanitize
    if sample_rate == 0 or sample_rate > LOPUS_MAX_SAMPLE_RATE:
        sample_rate = LOPUS_DEFAULT_SAMPLE_RATE
    if pre_skip == 0:
        pre_skip = LOPUS_DEFAULT_PRE_SKIP
    if header_size == 0 or header_size > len(lopus_data):
        header_size = LOPUS_DEFAULT_HEADER_SIZE

        # Some OPUS/LOPUS variants keep valid frame slots at offsets beyond
    # header_size.  Scan a small set of candidate starts and prefer
    # size-prefixed extraction over CBR if both validate.
    start_offsets: list[int] = []
    for off in [
        header_size,
        header_size + U32_BYTE_WIDTH,
        header_size + U32_BYTE_WIDTH * 2,
        header_size + U32_BYTE_WIDTH * 3,
        header_size + U32_BYTE_WIDTH * 4,
        *LOPUS_START_OFFSET_BASES,
    ]:
        if 0 <= off <= len(lopus_data) - LOPUS_MIN_SLOT_SIZE and off not in start_offsets:
            start_offsets.append(off)
    if not start_offsets:
        start_offsets = [header_size]

    best_frames: list[bytes] = []
    best_channel_count = channel_candidates[0]
    best_kind_rank = -1  # 3=size-prefixed, 2=CBR, 1=auto-detect

    def _consider(frames: list[bytes], kind_rank: int) -> None:
        nonlocal best_frames, best_kind_rank
        if len(frames) < OPUS_MIN_VALID_FRAME_COUNT or not _validate_opus_frames(frames):
            return
        if kind_rank > best_kind_rank:
            best_frames = frames
            best_kind_rank = kind_rank
            return
        if kind_rank == best_kind_rank and len(frames) > len(best_frames):
            best_frames = frames

    for frame_size in frame_size_candidates:
        for slot_size in [frame_size, frame_size + 4]:
            if slot_size < LOPUS_MIN_SLOT_SIZE or slot_size > LOPUS_MAX_SLOT_SIZE:
                continue
            for frame_start in start_offsets:
                _consider(
                    _extract_frames_with_slot(
                        lopus_data, frame_start, slot_size, '<'),
                    3,
                )
                _consider(
                    _extract_frames_with_slot(
                        lopus_data, frame_start, slot_size, '>'),
                    3,
                )

    # CBR fallback when no robust size-prefixed extraction was found.
    for frame_size in frame_size_candidates:
        for frame_start in start_offsets:
            _consider(
                _extract_opus_cbr_frames(
                    lopus_data, frame_size, search_start=frame_start),
                2,
            )

    # Last resort: auto-detect slot size by scanning from each candidate start.
    for frame_start in start_offsets:
        detected = _auto_detect_slot_frames(lopus_data, frame_start)
        if detected:
            _consider(detected, 1)

    if not best_frames:
        raise ValueError("No Opus frames extracted from LOPUS data")

    channel_count = force_channels if force_channels is not None else best_channel_count

    # Build OGG Opus file
    serial = OPUS_SERIAL_SSBU
    pages = []

    # Page 0: OpusHead (BOS = beginning of stream)
    head_data = _make_opus_head(channel_count, pre_skip, sample_rate)
    head_segs = _segment_table_for_packet(len(head_data))
    pages.append(
        _make_ogg_page(
            head_data, serial, 0, 0, OPUS_PAGE_BOS_FLAG, head_segs
        )
    )

    # Page 1: OpusTags
    tags_data = _make_opus_tags()
    tags_segs = _segment_table_for_packet(len(tags_data))
    pages.append(
        _make_ogg_page(
            tags_data, serial, 1, 0, OPUS_PAGE_NO_FLAGS, tags_segs
        )
    )

    # Data pages  pack multiple frames per page
    # Determine samples_per_frame from first frame's TOC byte
    samples_per_frame = OPUS_DEFAULT_SAMPLES_PER_FRAME
    if best_frames and len(best_frames[0]) >= 1:
        samples_per_frame = _opus_toc_samples(best_frames[0][0])
    granule = pre_skip
    page_seq = OPUS_PAGE_SEQUENCE_START
    i = 0

    while i < len(best_frames):
        page_data_parts = []
        page_segments = []
        segs_used = 0

        while i < len(best_frames) and segs_used < OPUS_SEGMENTS_PER_PAGE_TARGET:
            frame = best_frames[i]
            frame_segs = _segment_table_for_packet(len(frame))
            if segs_used + len(frame_segs) > OPUS_SEGMENT_SIZE_MAX:
                break
            page_data_parts.append(frame)
            page_segments.extend(frame_segs)
            segs_used += len(frame_segs)
            granule += samples_per_frame
            i += 1

        flags = OPUS_PAGE_EOS_FLAG if i >= len(best_frames) else OPUS_PAGE_NO_FLAGS
        page_data = b''.join(page_data_parts)
        pages.append(_make_ogg_page(page_data, serial, page_seq, granule, flags, page_segments))
        page_seq += 1

    return b''.join(pages)


def _find_sections(data: bytes) -> dict[str, tuple[int, int]]:
    """Find all sections in a NUS3AUDIO file. Returns {name: (data_offset, data_size)}.

    NUS3AUDIO has an 8-byte header ("NUS3" + u32 file_size), then sections.
    The first section is typically "AUDIINDX" with an 8-byte magic (unlike the
    other sections which use 4-byte magics).  All subsequent sections use
    4-byte magic + 4-byte size.
    """
    sections = {}
    pos = 8  # Skip "NUS3" + total size

    # Handle AUDIINDX section (8-byte magic, 4-byte size)
    if pos + 12 <= len(data) and data[pos:pos + 8] == b'AUDIINDX':
        size = struct.unpack_from('<I', data, pos + 8)[0]
        # Sanity check: size must not exceed remaining data
        if size > len(data) - pos - 12:
            size = len(data) - pos - 12
        sections['AUDIINDX'] = (pos + 12, size)
        pos += 12 + size
        # Align to 4 bytes
        if pos % 4:
            pos += 4 - (pos % 4)

    # Parse remaining sections (4-byte magic + 4-byte size)
    while pos + 8 <= len(data):
        name = data[pos:pos + 4]
        try:
            name_str = name.decode('ascii').strip()
        except UnicodeDecodeError:
            break
        # Reject names containing non-printable ASCII (control chars, nulls)
        if not name_str or not all(c.isalnum() or c in '_-' for c in name_str):
            break
        size = struct.unpack_from('<I', data, pos + 4)[0]
        # Sanity check: size must not exceed remaining data
        if size > len(data) - pos - 8:
            break
        sections[name_str] = (pos + 8, size)
        pos += 8 + size
        # NUS3AUDIO sections are NOT always 4-byte aligned (e.g. TNNM
        # with an odd-length track name).  Only align if the next bytes
        # don't already look like a valid section header.
        if pos % 4:
            peek = data[pos:pos + 4] if pos + 4 <= len(data) else b''
            try:
                peek_str = peek.decode('ascii').strip()
            except UnicodeDecodeError:
                peek_str = ''
            if not (peek_str and all(c.isalnum() or c in '_-' for c in peek_str)):
                pos += 4 - (pos % 4)

    # Fallback: if PACK wasn't found by sequential parsing (alignment
    # or padding issues), scan the remaining data for the PACK magic.
    if 'PACK' not in sections:
        scan_start = pos
        while scan_start + 8 <= len(data):
            idx = data.find(b'PACK', scan_start, len(data))
            if idx == -1:
                break
            pack_size = struct.unpack_from('<I', data, idx + 4)[0]
            if 0 < pack_size <= len(data) - idx - 8:
                sections['PACK'] = (idx + 8, pack_size)
                break
            scan_start = idx + 1

    return sections


def _extract_audio_entries(data: bytes, sections: dict) -> list[bytes]:
    """Extract individual audio entries from NUS3AUDIO using ADOF offsets."""
    from src.utils.logger import logger
    entries = []

    logger.debug("NUS3AUDIO", f"Sections found: {list(sections.keys())}")

    # Get audio entry offsets from ADOF section
    if 'ADOF' in sections and 'PACK' in sections:
        adof_off, adof_size = sections['ADOF']
        pack_off, pack_size = sections['PACK']

        # ADOF contains pairs of (offset, size) for each audio entry
        num_entries = adof_size // 8
        for i in range(num_entries):
            entry_offset = struct.unpack_from('<I', data, adof_off + i * 8)[0]
            entry_size = struct.unpack_from('<I', data, adof_off + i * 8 + 4)[0]
            if entry_size > 0 and pack_off + entry_offset + entry_size <= len(data):
                entries.append(data[pack_off + entry_offset:pack_off + entry_offset + entry_size])

    # Fallback: treat entire PACK as single entry
    if not entries and 'PACK' in sections:
        pack_off, pack_size = sections['PACK']
        if pack_size > 0:
            entries.append(data[pack_off:pack_off + pack_size])

    return entries


_DSP_COEF = [
    (0, 0), (2048, 0), (0, 2048), (1024, 1024),
    (4096, -2048), (3584, -1536), (3072, -1024), (2560, -512),
    (4096, -2048), (3584, -1536), (3072, -1024), (4608, -2560),
    (4200, -2248), (4800, -2300), (5120, -3072), (4384, -2112),
]


def _decode_dsp_adpcm(adpcm_data: bytes, sample_count: int, coefs: list,
                       initial_hist1: int = 0, initial_hist2: int = 0) -> bytes:
    """Decode Nintendo DSP ADPCM to 16-bit PCM."""
    samples = []
    hist1 = initial_hist1
    hist2 = initial_hist2
    pos = 0
    decoded = 0

    while decoded < sample_count and pos < len(adpcm_data):
        # Each frame is 8 bytes: 1 header + 7 data bytes = 14 samples
        if pos >= len(adpcm_data):
            break
        header = adpcm_data[pos]
        scale = 1 << (header & 0x0F)
        coef_idx = (header >> 4) & 0x0F
        if coef_idx >= len(coefs):
            coef_idx = 0
        coef1, coef2 = coefs[coef_idx]
        pos += 1

        for byte_i in range(7):
            if pos >= len(adpcm_data):
                break
            byte = adpcm_data[pos]
            pos += 1

            for nibble in range(2):
                if decoded >= sample_count:
                    break
                if nibble == 0:
                    nib = (byte >> 4) & 0x0F
                else:
                    nib = byte & 0x0F

                # Sign extend
                if nib >= 8:
                    nib -= 16

                sample = (nib * scale + (coef1 * hist1 + coef2 * hist2 + 1024)) >> 11
                sample = max(-32768, min(32767, sample))
                samples.append(sample)
                hist2 = hist1
                hist1 = sample
                decoded += 1

    # Convert to bytes (16-bit little-endian PCM)
    import array
    pcm = array.array('h', samples)
    return pcm.tobytes()


def _idsp_to_wav(audio_data: bytes) -> bytes:
    """Convert IDSP (Nintendo DSP ADPCM) to WAV."""
    if len(audio_data) < 0x60:
        raise ValueError("IDSP data too short")

    # IDSP header parsing
    # Offset 0x00: "IDSP" magic
    # Offset 0x04: version/channel count varies
    channel_count = struct.unpack_from('>I', audio_data, 0x08)[0]
    sample_rate = struct.unpack_from('>I', audio_data, 0x0C)[0]
    sample_count = struct.unpack_from('>I', audio_data, 0x10)[0]

    if channel_count == 0:
        channel_count = 1
    if channel_count > 2:
        channel_count = 2
    if sample_rate == 0 or sample_rate > 200000:
        sample_rate = 48000
    if sample_count == 0 or sample_count > 100000000:
        raise ValueError("Invalid sample count in IDSP")

    # Try to find header size and coefficient locations
    # IDSP v2/v3 structure varies; try common layouts
    header_size = struct.unpack_from('>I', audio_data, 0x04)[0]
    if header_size < 0x40 or header_size > len(audio_data):
        header_size = 0x60  # Common default

    # Read DSP coefficients (16 pairs per channel, big-endian int16)
    channels_pcm = []
    for ch in range(min(channel_count, 2)):
        coefs = []
        coef_offset = 0x14 + ch * 0x3C  # Approximate offset for coefficients
        if coef_offset + 32 > len(audio_data):
            coefs = list(_DSP_COEF)  # Use defaults
        else:
            for j in range(16):
                if coef_offset + j * 2 + 2 <= len(audio_data):
                    c = struct.unpack_from('>h', audio_data, coef_offset + j * 2)[0]
                    coefs.append(c)
                else:
                    coefs.append(0)
            # Reform into pairs
            coefs = [(coefs[i], coefs[i + 1]) for i in range(0, min(len(coefs), 32), 2)]

        # Calculate data position
        data_start = header_size + ch * ((sample_count + 13) // 14 * 8)
        if data_start >= len(audio_data):
            data_start = header_size
        adpcm = audio_data[data_start:]
        pcm = _decode_dsp_adpcm(adpcm, sample_count, coefs)
        channels_pcm.append(pcm)

    # Interleave channels if stereo
    if len(channels_pcm) == 2:
        import array
        left = array.array('h')
        left.frombytes(channels_pcm[0])
        right = array.array('h')
        right.frombytes(channels_pcm[1])
        min_len = min(len(left), len(right))
        interleaved = array.array('h')
        for i in range(min_len):
            interleaved.append(left[i])
            interleaved.append(right[i])
        pcm_data = interleaved.tobytes()
    else:
        pcm_data = channels_pcm[0]

    return _make_wav(pcm_data, channel_count, sample_rate, 16)


def _bwav_to_wav(audio_data: bytes) -> bytes:
    """Convert BWAV to WAV. BWAV can contain DSP ADPCM or PCM16."""
    if len(audio_data) < 0x40:
        raise ValueError("BWAV data too short")

    # BWAV header
    # 0x00: "BWAV"
    # 0x04: BOM (0xFEFF = LE)
    # 0x06: version
    # 0x08: CRC or flags
    # 0x0C: sample count or offset info varies

    bom = struct.unpack_from('<H', audio_data, 0x04)[0]
    is_le = (bom == 0xFEFF)

    fmt = '<' if is_le else '>'

    channel_count = struct.unpack_from(f'{fmt}H', audio_data, 0x0E)[0]
    if channel_count == 0 or channel_count > 8:
        channel_count = 1

    # Read channel info entries
    channels_pcm = []
    sample_rate = 48000
    sample_count = 0

    for ch in range(min(channel_count, 2)):
        ch_info_offset = 0x10 + ch * 0x4C  # Approximate channel info offset
        if ch_info_offset + 0x4C > len(audio_data):
            break

        codec = struct.unpack_from(f'{fmt}H', audio_data, ch_info_offset)[0]
        ch_sample_rate = struct.unpack_from(f'{fmt}I', audio_data, ch_info_offset + 0x04)[0]
        ch_sample_count = struct.unpack_from(f'{fmt}I', audio_data, ch_info_offset + 0x08)[0]
        data_offset = struct.unpack_from(f'{fmt}I', audio_data, ch_info_offset + 0x10)[0]

        if ch_sample_rate > 0 and ch_sample_rate < 200000:
            sample_rate = ch_sample_rate
        if ch_sample_count > sample_count:
            sample_count = ch_sample_count

        if codec == 0x0000:  # PCM16
            end = min(data_offset + sample_count * 2, len(audio_data))
            channels_pcm.append(audio_data[data_offset:end])
        elif codec == 0x0200:  # DSP ADPCM
            # Coefficients are embedded in the channel info
            coefs = []
            coef_start = ch_info_offset + 0x14
            for j in range(16):
                if coef_start + j * 2 + 2 <= len(audio_data):
                    c = struct.unpack_from(f'{fmt}h', audio_data, coef_start + j * 2)[0]
                    coefs.append(c)
                else:
                    coefs.append(0)
            coefs = [(coefs[i], coefs[i + 1]) for i in range(0, min(len(coefs), 32), 2)]
            adpcm = audio_data[data_offset:]
            pcm = _decode_dsp_adpcm(adpcm, ch_sample_count, coefs)
            channels_pcm.append(pcm)
        else:
            # Unknown codec, skip
            continue

    if not channels_pcm:
        raise ValueError("No decodable channels in BWAV")

    # Interleave if stereo
    if len(channels_pcm) >= 2:
        import array
        left = array.array('h')
        left.frombytes(channels_pcm[0])
        right = array.array('h')
        right.frombytes(channels_pcm[1])
        min_len = min(len(left), len(right))
        interleaved = array.array('h')
        for i in range(min_len):
            interleaved.append(left[i])
            interleaved.append(right[i])
        pcm_data = interleaved.tobytes()
        actual_channels = 2
    else:
        pcm_data = channels_pcm[0]
        actual_channels = 1

    return _make_wav(pcm_data, actual_channels, sample_rate, 16)


def _make_wav(pcm_data: bytes, channels: int, sample_rate: int, bits: int) -> bytes:
    """Create a WAV file from raw PCM data."""
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    data_size = len(pcm_data)
    file_size = 36 + data_size

    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', file_size, b'WAVE',
        b'fmt ', 16,
        1,  # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b'data', data_size,
    )
    return header + pcm_data


def _opus_container_to_ogg(audio_data: bytes) -> bytes:
    """Convert a raw OPUS container (magic 'OPUS') to standard OGG Opus.

    The OPUS container format found in NUS3AUDIO files has several variants:

    **SSBU OPUS container** (most common in custom SSBU tracks):
      Big-endian header (0x40 bytes):
        0x00: "OPUS" magic
        0x08: u32 total_samples (BE)
        0x0C: u32 channels (BE)
        0x10: u32 sample_rate (BE)
        0x20: u32 data_offset (BE) - typically 0x30-0x40
        0x24: u32 data_size (BE)
      At data_offset: LOPUS sub-header (LE) with frame data using
        either big-endian or little-endian u32 frame sizes in fixed
        slots.

    Other variants:
      1. OPUS magic + LOPUS sub-header (0x80000001..0x80000004)
      2. OPUS magic + raw length-prefixed opus frames
      3. OPUS magic + custom header + opus frame data with fixed slots

    We try the SSBU format first (BE *and* LE frame sizes), then fall
    back to generic strategies using header values when available.
    """
    if len(audio_data) < LOPUS_MIN_SLOT_SIZE:
        raise ValueError("OPUS container too short")

    # Values parsed from the OPUS header (used by fallback strategies)
    parsed_channels: int = STEREO_CHANNEL_COUNT
    parsed_sample_rate: int = LOPUS_DEFAULT_SAMPLE_RATE
    parsed_data_offset: int = OPUS_INNER_DATA_OFFSET_FALLBACK
    parsed_pre_skip: int = LOPUS_DEFAULT_PRE_SKIP

    if len(audio_data) >= OPUS_CONTAINER_HEADER_MIN_SIZE:
        try:
            container_data_offset = struct.unpack_from(
                ">I", audio_data, OPUS_CONTAINER_DATA_OFFSET_OFFSET
            )[0]
            container_data_size = struct.unpack_from(
                ">I", audio_data, OPUS_CONTAINER_DATA_SIZE_OFFSET
            )[0]
            container_channels = struct.unpack_from(
                ">I", audio_data, OPUS_CONTAINER_CHANNELS_OFFSET
            )[0]
            container_sample_rate = struct.unpack_from(
                ">I", audio_data, OPUS_CONTAINER_SAMPLE_RATE_OFFSET
            )[0]

            if (
                OPUS_CONTAINER_MIN_DATA_OFFSET <= container_data_offset <= OPUS_CONTAINER_MAX_DATA_OFFSET
                and LOPUS_MIN_CHANNELS <= container_channels <= LOPUS_MAX_CHANNELS
                and OPUS_CONTAINER_SAMPLE_RATE_MIN <= container_sample_rate <= OPUS_CONTAINER_SAMPLE_RATE_MAX
                and container_data_offset + container_data_size
                <= len(audio_data) + OPUS_CONTAINER_SIZE_SLACK_BYTES
            ):
                # Header looks valid  save for fallback strategies
                parsed_channels = container_channels
                parsed_sample_rate = container_sample_rate
                parsed_data_offset = container_data_offset
                inner = audio_data[container_data_offset:]

                # Check for LOPUS sub-header inside the inner data
                if len(inner) >= OPUS_CONTAINER_HEADER_MIN_SIZE:
                    sub_magic = struct.unpack_from('<I', inner, 0)[0]
                    if sub_magic & OPUS_LOPUS_MAGIC_MASK:
                        # _lopus_to_ogg has correct version-specific header
                        # parsing for all LOPUS variants (v1-v4).  Try it
                        # FIRST  the manual slot extraction below uses
                        # hard-coded offsets that are wrong for some versions.
                        try:
                            return _lopus_to_ogg(inner)
                        except Exception:
                            pass

                        # Manual fallback: read header fields and try
                        # slot-based extraction with correct offsets.
                        lopus_type = sub_magic & 0xFF
                        if lopus_type in LOPUS_SUPPORTED_TYPES:
                            lopus_hdr_size = struct.unpack_from("<I", inner, LOPUS_HEADER_FIELD_OFFSET)[0]

                            # Determine slot_size based on LOPUS version:
                            #   v2: u16 at 0x0A
                            #   v3/v4: u32 at 0x14
                            #   v1: u32 at 0x14 or default 640
                            if lopus_type == LOPUS_TYPE_V2:
                                slot_size = struct.unpack_from("<H", inner, LOPUS_TYPE_V2_SLOT_OFFSET)[0]
                            else:
                                slot_size = struct.unpack_from("<I", inner, LOPUS_FRAME_SIZE_OFFSET)[0]
                            if slot_size == 0 or not (
                                LOPUS_MIN_SLOT_SIZE <= slot_size <= LOPUS_MAX_SLOT_SIZE
                            ):
                                # Try alt field
                                alt = struct.unpack_from("<I", inner, LOPUS_FRAME_SIZE_OFFSET)[0]
                                if LOPUS_MIN_SLOT_SIZE <= alt <= LOPUS_MAX_SLOT_SIZE:
                                    slot_size = alt
                                else:
                                    slot_size = LOPUS_FALLBACK_FRAME_SIZES[0]

                            # Read pre_skip
                            ps = LOPUS_DEFAULT_PRE_SKIP
                            if len(inner) > LOPUS_PRESKIP_U32_OFFSET:
                                ps = struct.unpack_from("<H", inner, LOPUS_PRESKIP_U16_OFFSET)[0]
                                if ps == 0:
                                    ps = struct.unpack_from("<I", inner, LOPUS_PRESKIP_U32_OFFSET)[0]
                                if not (LOPUS_MIN_PRE_SKIP < ps < LOPUS_MAX_PRE_SKIP):
                                    ps = LOPUS_DEFAULT_PRE_SKIP
                            parsed_pre_skip = ps

                            # Use actual header_size as primary frame start
                            start_offsets = []
                            if (
                                OPUS_LIKELY_HEADER_SIZE_MIN
                                <= lopus_hdr_size
                                <= OPUS_LIKELY_HEADER_SIZE_MAX
                            ):
                                start_offsets.append(lopus_hdr_size)
                            for o in LOPUS_HEADER_START_FALLBACKS:
                                if o not in start_offsets:
                                    start_offsets.append(o)

                            # Try LE frame sizes first (most common in mods)
                            for frame_start in start_offsets:
                                frames = _extract_opus_le_slots(
                                    inner, frame_start, slot_size)
                                if len(frames) >= OPUS_MIN_VALID_FRAME_COUNT and _validate_opus_frames(frames):
                                    return _build_ogg_opus_from_frames(
                                        frames,
                                        channels=container_channels,
                                        sample_rate=container_sample_rate,
                                        pre_skip=parsed_pre_skip,
                                    )

                            # Try BE frame sizes (original SSBU format)
                            for frame_start in start_offsets:
                                frames = _extract_opus_be_slots(
                                    inner, frame_start, slot_size)
                                if len(frames) >= OPUS_MIN_VALID_FRAME_COUNT and _validate_opus_frames(frames):
                                    return _build_ogg_opus_from_frames(
                                        frames,
                                        channels=container_channels,
                                        sample_rate=container_sample_rate,
                                        pre_skip=parsed_pre_skip,
                                    )

                            # Try CBR (fixed-size) frames
                            cbr_start = (
                                lopus_hdr_size
                                if (
                                    OPUS_LIKELY_HEADER_SIZE_MIN
                                    <= lopus_hdr_size
                                    <= OPUS_LIKELY_HEADER_SIZE_MAX
                                )
                                else LOPUS_DEFAULT_HEADER_SIZE
                            )
                            cbr_frames = _extract_opus_cbr_frames(
                                inner, slot_size, search_start=cbr_start)
                            if len(cbr_frames) >= OPUS_MIN_VALID_FRAME_COUNT and _validate_opus_frames(cbr_frames):
                                return _build_ogg_opus_from_frames(
                                    cbr_frames,
                                    channels=container_channels,
                                    sample_rate=container_sample_rate,
                                    pre_skip=parsed_pre_skip,
                                )
        except Exception:
            pass  # Fall through to other strategies

    # Determine the data that follows the OPUS header.
    # If we parsed a valid header, skip to data_offset; otherwise just
    # skip the 4-byte "OPUS" magic.
    inner_data = audio_data[parsed_data_offset:]

    # Check if the remaining data has a LOPUS sub-header
    if len(inner_data) >= U32_BYTE_WIDTH:
        sub_magic = struct.unpack_from('<I', inner_data, 0)[0]
        if sub_magic & OPUS_LOPUS_MAGIC_MASK:
            return _lopus_to_ogg(inner_data)

    errors = []

    # Strategy 1: Skip 4 bytes (data_size field), treat rest as frames
    if len(inner_data) >= LOPUS_MIN_SLOT_SIZE:
        declared_size = struct.unpack_from('<I', inner_data, 0)[0]
        if 0 < declared_size <= len(inner_data) - U32_BYTE_WIDTH:
            opus_data = inner_data[
                U32_BYTE_WIDTH:U32_BYTE_WIDTH + declared_size
            ]
            try:
                return _raw_opus_frames_to_ogg(
                    opus_data, channels=parsed_channels,
                    sample_rate=parsed_sample_rate)
            except Exception as e:
                errors.append(f"Strategy 1 (skip size): {e}")

    # Strategy 2: Try entire inner data as raw frames
    try:
        return _raw_opus_frames_to_ogg(
            inner_data, channels=parsed_channels,
            sample_rate=parsed_sample_rate)
    except Exception as e:
        errors.append(f"Strategy 2 (raw frames): {e}")

    # Strategy 3: Scan for Opus frames by looking for valid TOC bytes
    try:
        return _scan_opus_frames(
            inner_data, channels=parsed_channels,
            sample_rate=parsed_sample_rate)
    except Exception as e:
        errors.append(f"Strategy 3 (TOC scan): {e}")

    # Strategy 4: Try different header sizes before frame data
    for header_offset in OPUS_HEADER_SCAN_OFFSETS:
        if header_offset >= len(inner_data):
            continue
        try:
            return _raw_opus_frames_to_ogg(
                inner_data[header_offset:],
                channels=parsed_channels,
                sample_rate=parsed_sample_rate)
        except Exception:
            pass

    # Strategy 5: Try with various fixed slot sizes directly
    for slot_size in OPUS_FIXED_SLOT_SIZES:
        try:
            return _extract_opus_fixed_slots(
                inner_data, slot_size,
                channels=parsed_channels,
                sample_rate=parsed_sample_rate)
        except Exception:
            pass
        for skip in OPUS_FIXED_SLOT_SKIP_OFFSETS:
            if skip >= len(inner_data):
                continue
            try:
                return _extract_opus_fixed_slots(
                    inner_data[skip:], slot_size,
                    channels=parsed_channels,
                    sample_rate=parsed_sample_rate)
            except Exception:
                pass

    # Strategy 6: Last resort - synthetic LOPUS header
    try:
        return _raw_opus_to_ogg_fallback(inner_data)
    except Exception as e:
        errors.append(f"Strategy 6 (synthetic LOPUS): {e}")

    raise ValueError(f"All OPUS conversion strategies failed: {'; '.join(errors[:3])}")


def _extract_opus_cbr_frames(data: bytes, slot_size: int,
                             search_start: int = OPUS_CBR_SEARCH_START_DEFAULT) -> list[bytes]:
    """Extract fixed-size (CBR) Opus frames with no per-frame size prefix.

    LOPUS type 0x80000001 can use constant bitrate where each Opus packet
    is exactly *slot_size* bytes, packed sequentially after the header.
    We scan for offsets (starting from *search_start*) where valid Opus
    TOC bytes appear consistently at *slot_size* intervals, then pick the
    best candidate (highest Opus config = fullband CELT for music).

    Returns a list of raw Opus frame bytes, or an empty list on failure.
    """
    if slot_size < LOPUS_MIN_SLOT_SIZE or slot_size > LOPUS_MAX_SLOT_SIZE:
        return []

    end_search = min(search_start + slot_size, len(data) - slot_size * 3)
    candidates: list[tuple[int, int, int]] = []  # (config, offset, num_frames)

    for test_off in range(search_start, max(search_start, end_search)):
        if test_off + slot_size * 3 > len(data):
            break
        toc = data[test_off]
        cfg = (toc >> OPUS_TOC_CONFIG_SHIFT) & OPUS_TOC_CONFIG_MASK
        if cfg < OPUS_MIN_MUSIC_CONFIG:
            continue

        # Check TOC config consistency at slot_size intervals
        total = min(OPUS_MAX_VALID_FRAME_SAMPLES, (len(data) - test_off) // slot_size)
        if total < 3:
            continue
        consistent = sum(
            1 for n in range(total)
            if ((data[test_off + n * slot_size] >> OPUS_TOC_CONFIG_SHIFT) & OPUS_TOC_CONFIG_MASK) == cfg
        )
        if consistent >= total * OPUS_CBR_TOC_CONSISTENCY_MIN_RATIO and consistent >= 3:
            num_frames = (len(data) - test_off) // slot_size
            candidates.append((cfg, test_off, num_frames))

    if not candidates:
        return []

    # Pick the candidate with the highest config value.
    # Music files use fullband CELT (configs 28-31) which sorts highest.
    candidates.sort(key=lambda c: c[0], reverse=True)
    best_cfg, best_off, _ = candidates[0]

    frames: list[bytes] = []
    pos = best_off
    while pos + slot_size <= len(data):
        frames.append(data[pos:pos + slot_size])
        pos += slot_size
    if not frames:
        return frames

    # Many SSBU custom CBR LOPUS tracks append an 8-byte trailer to each
    # slot where the first 4 bytes are a BE payload length (commonly slot-8).
    # Passing trailer bytes into Opus decoding causes global crunchy distortion.
    # Detect this pattern conservatively and trim per-frame payloads.
    trailer_lengths: list[int] = []
    probe_n = min(80, len(frames))
    for fr in frames[:probe_n]:
        if len(fr) < 12:
            continue
        declared = struct.unpack_from('>I', fr, len(fr) - 8)[0]
        if 1 <= declared <= slot_size - 8:
            trailer_lengths.append(declared)

    if trailer_lengths:
        from collections import Counter
        mode_len, mode_count = Counter(trailer_lengths).most_common(1)[0]
        # Require a strong majority before trimming to avoid false positives.
        if mode_count >= max(8, int(probe_n * 0.7)):
            trimmed: list[bytes] = []
            for fr in frames:
                declared = struct.unpack_from('>I', fr, len(fr) - 8)[0] if len(fr) >= 12 else 0
                pkt_len = declared if 1 <= declared <= slot_size - 8 else mode_len
                trimmed.append(fr[:pkt_len])
            if _validate_opus_frames(trimmed):
                return trimmed

    return frames


def _extract_opus_be_slots(data: bytes, start_offset: int,
                           slot_size: int) -> list[bytes]:
    """Extract Opus frames using big-endian u32 sizes in fixed-size slots.

    The SSBU OPUS container stores frame lengths as big-endian u32
    at the start of each fixed-size slot, followed by the Opus packet data
    and zero-padding to fill the slot.

    Args:
        data: Inner LOPUS data (starting from the LOPUS header).
        start_offset: Byte offset within *data* where frame slots begin.
        slot_size: Fixed number of bytes per slot (header field at 0x0A).

    Returns:
        List of raw Opus frame bytes.
    """
    frames: list[bytes] = []
    pos = start_offset
    while pos + 4 <= len(data):
        frame_size = struct.unpack_from('>I', data, pos)[0]
        if frame_size == 0 or frame_size > slot_size:
            break
        if pos + 4 + frame_size > len(data):
            break
        frames.append(data[pos + 4:pos + 4 + frame_size])
        pos += slot_size
    return frames


def _extract_opus_le_slots(data: bytes, start_offset: int,
                           slot_size: int) -> list[bytes]:
    """Extract Opus frames using **little-endian** u32 sizes in fixed slots.

    Many mod-created NUS3AUDIO tracks store frame sizes in LE even
    inside an OPUS container whose outer header is BE.
    """
    frames: list[bytes] = []
    pos = start_offset
    while pos + 4 <= len(data):
        frame_size = struct.unpack_from('<I', data, pos)[0]
        if frame_size == 0 or frame_size > slot_size:
            break
        if pos + 4 + frame_size > len(data):
            break
        frames.append(data[pos + 4:pos + 4 + frame_size])
        pos += slot_size
    return frames


def _validate_opus_frames(frames: list[bytes], min_consistent: int = 5) -> bool:
    """Quick sanity-check that extracted data looks like real Opus frames.

    Checks:
    * The majority of frames start with a byte whose top-5-bit config
      field is consistent (same Opus mode throughout the track).
    * Frame sizes are in a reasonable range (2-2000 bytes).
    * At least 70% of sampled frames share the dominant config.
    """
    if not frames:
        return False

    # Collect TOC config values (top 5 bits) from the first N frames
    sample_count = min(len(frames), 30)
    configs: dict[int, int] = {}
    for f in frames[:sample_count]:
        if len(f) < 2:
            return False
        cfg = (f[0] >> 3) & 0x1F
        configs[cfg] = configs.get(cfg, 0) + 1

    if not configs:
        return False

    # The most common config must appear in at least 70% of sampled
    # frames AND at least min_consistent frames.  The 70% threshold
    # prevents false positives from misaligned data that can have
    # random config distributions.
    most_common_count = max(configs.values())
    threshold = max(min_consistent, sample_count * 7 // 10)
    return most_common_count >= threshold


def _scan_opus_frames(
    data: bytes,
    channels: int = STEREO_CHANNEL_COUNT,
    sample_rate: int = LOPUS_DEFAULT_SAMPLE_RATE,
) -> bytes:
    """Scan for valid Opus frames by detecting TOC bytes and frame boundaries.

    Opus packets start with a TOC byte. We can validate frames by checking:
    1. TOC byte has valid configuration
    2. The declared frame count is reasonable
    3. Frame data can be consistently extracted
    """
    # Try to find where the first Opus frame starts
    # by looking for patterns that suggest frame data
    for start_offset in range(
        0,
        min(OPUS_RAW_SCAN_MAX_OFFSET, len(data)),
        OPUS_RAW_SCAN_ALIGN_STEP,
    ):
        if start_offset + LOPUS_MIN_SLOT_SIZE > len(data):
            break

        # Check if this could be a length-prefixed frame
        frame_size = struct.unpack_from('<I', data, start_offset)[0]
        if (
            LOPUS_MIN_CHANNELS <= frame_size <= OPUS_FRAME_SIZE_SCAN_MAX
            and start_offset + U32_BYTE_WIDTH + frame_size <= len(data)
        ):
            # Validate that the data after the size looks like an Opus TOC byte
            toc = data[start_offset + U32_BYTE_WIDTH]
            config = (toc >> OPUS_TOC_CONFIG_SHIFT) & OPUS_TOC_CONFIG_MASK
            if config <= OPUS_MAX_CONFIG_VALUE:
                # Try to extract frames from this offset
                frames = []
                pos = start_offset
                consecutive_valid = 0

                while pos + U32_BYTE_WIDTH <= len(data):
                    fs = struct.unpack_from('<I', data, pos)[0]
                    if fs == 0 or fs > OPUS_FRAME_SIZE_HARD_MAX:
                        break
                    if pos + U32_BYTE_WIDTH + fs > len(data):
                        break
                    frame_data = data[pos + U32_BYTE_WIDTH:pos + U32_BYTE_WIDTH + fs]
                    frames.append(frame_data)
                    consecutive_valid += 1
                    pos += U32_BYTE_WIDTH + fs

                if consecutive_valid >= OPUS_MIN_VALID_FRAME_COUNT:
                    return _build_ogg_opus_from_frames(
                        frames, channels=channels,
                        sample_rate=sample_rate, pre_skip=LOPUS_DEFAULT_PRE_SKIP,
                    )

                # If variable-length didn't work, try as fixed slots
                if frame_size > 0:
                    # Guess slot sizes based on the first frame
                    for padding in OPUS_RAW_PADDING_OFFSETS:
                        slot = frame_size + U32_BYTE_WIDTH + padding
                        if slot < LOPUS_MIN_SLOT_SIZE or slot > OPUS_RAW_SLOT_MAX:
                            continue
                        try:
                            return _extract_opus_fixed_slots(
                                data[start_offset:], slot,
                                channels=channels,
                                sample_rate=sample_rate)
                        except Exception:
                            pass

    raise ValueError("No valid Opus frames found via scanning")


def _extract_opus_fixed_slots(
    data: bytes,
    slot_size: int,
    channels: int = STEREO_CHANNEL_COUNT,
    sample_rate: int = LOPUS_DEFAULT_SAMPLE_RATE,
) -> bytes:
    """Extract Opus frames from data using fixed-size slots.

    Each slot: u32 actual_frame_size + frame_data + padding to slot_size.
    """
    if slot_size < LOPUS_MIN_SLOT_SIZE or slot_size > LOPUS_MAX_SLOT_SIZE:
        raise ValueError(f"Invalid slot size: {slot_size}")

    frames = []
    pos = 0
    while pos + U32_BYTE_WIDTH <= len(data):
        actual_size = struct.unpack_from('<I', data, pos)[0]
        if actual_size == 0:
            # Could be padding, try next slot
            pos += slot_size
            continue
        if actual_size > slot_size or actual_size > OPUS_FRAME_SIZE_U16_MAX:
            break
        if pos + U32_BYTE_WIDTH + actual_size > len(data):
            break
        frames.append(data[pos + U32_BYTE_WIDTH:pos + U32_BYTE_WIDTH + actual_size])
        pos += slot_size

    if len(frames) < OPUS_MIN_VALID_FRAME_COUNT:
        raise ValueError(f"Too few frames ({len(frames)}) with slot size {slot_size}")

    return _build_ogg_opus_from_frames(frames, channels=channels,
                                       sample_rate=sample_rate, pre_skip=LOPUS_DEFAULT_PRE_SKIP)


def _raw_opus_frames_to_ogg(
    data: bytes,
    channels: int = STEREO_CHANNEL_COUNT,
    sample_rate: int = LOPUS_DEFAULT_SAMPLE_RATE,
) -> bytes:
    """Convert a sequence of length-prefixed raw Opus frames to OGG Opus.

    Each frame: u32 frame_size + frame_data (frame_size bytes).
    """
    frames = []
    pos = 0
    while pos + U32_BYTE_WIDTH <= len(data):
        frame_size = struct.unpack_from('<I', data, pos)[0]
        if frame_size == 0 or frame_size > OPUS_FRAME_SIZE_U16_MAX:
            break
        if pos + U32_BYTE_WIDTH + frame_size > len(data):
            break
        frames.append(data[pos + U32_BYTE_WIDTH:pos + U32_BYTE_WIDTH + frame_size])
        pos += U32_BYTE_WIDTH + frame_size

    if not frames:
        # Try with fixed-size frame slots (common in LOPUS)
        # Guess frame slot size from first frame
        pos = 0
        if pos + U32_BYTE_WIDTH <= len(data):
            first_size = struct.unpack_from('<I', data, pos)[0]
            if 0 < first_size < OPUS_FRAME_SIZE_U16_MAX and pos + U32_BYTE_WIDTH + first_size <= len(data):
                frames.append(data[pos + U32_BYTE_WIDTH:pos + U32_BYTE_WIDTH + first_size])
                # Estimate slot size: try common sizes
                for slot in (first_size + U32_BYTE_WIDTH, *OPUS_RAW_SLOT_FALLBACKS):
                    test_frames = [frames[0]]
                    test_pos = slot
                    valid = True
                    count = 0
                    while test_pos + U32_BYTE_WIDTH <= len(data) and count < 5:
                        fs = struct.unpack_from('<I', data, test_pos)[0]
                        if fs == 0 or fs > slot or test_pos + U32_BYTE_WIDTH + fs > len(data):
                            valid = False
                            break
                        test_frames.append(data[test_pos + U32_BYTE_WIDTH:test_pos + U32_BYTE_WIDTH + fs])
                        test_pos += slot
                        count += 1
                    if valid and count >= 2:
                        # Confirmed slot size, extract all
                        frames = []
                        p = 0
                        while p + U32_BYTE_WIDTH <= len(data):
                            fs = struct.unpack_from('<I', data, p)[0]
                            if fs == 0 or fs > slot:
                                break
                            if p + U32_BYTE_WIDTH + fs > len(data):
                                break
                            frames.append(data[p + U32_BYTE_WIDTH:p + U32_BYTE_WIDTH + fs])
                            p += slot
                        break

    if not frames:
        raise ValueError("No Opus frames extracted from raw OPUS data")

    return _build_ogg_opus_from_frames(frames, channels=channels,
                                       sample_rate=sample_rate, pre_skip=LOPUS_DEFAULT_PRE_SKIP)


def _raw_opus_to_ogg_fallback(data: bytes) -> bytes:
    """Last-resort conversion: treat data as LOPUS with default params."""
    # Construct a synthetic LOPUS header and parse with _lopus_to_ogg
    # This creates a fake 0x80000001 header wrapping the data
    header_size = LOPUS_DEFAULT_HEADER_SIZE
    synthetic = struct.pack("<II", LOPUS_MAGIC_V1, header_size)
    # Pad to header_size
    synthetic += b'\x00' * (header_size - len(synthetic))
    # Set sample_rate at 0x0C, channel_count at 0x10, frame_size at 0x14
    synthetic = (
        synthetic[:LOPUS_SAMPLE_RATE_OFFSET]
        + struct.pack(
            "<III",
            LOPUS_DEFAULT_SAMPLE_RATE,
            STEREO_CHANNEL_COUNT,
            LOPUS_FALLBACK_FRAME_SIZES[0],
        )
        + synthetic[LOPUS_PRE_SKIP_OFFSETS[0]:]
    )
    synthetic += data

    return _lopus_to_ogg(synthetic)


def _opus_toc_samples(toc_byte: int) -> int:
    """Derive the number of 48 kHz samples per Opus frame from its TOC byte.

    The top 5 bits of the TOC byte encode the configuration which
    determines the frame duration.  We return the sample count for a
    *single* coded frame.  For code 1/2/3 (multiple frames per packet)
    the sample count is per-sub-frame, but in SSBU LOPUS each packet
    is code-0 so this is fine.

    Reference: RFC 6716 Section 3.1
    """
    config = (toc_byte >> OPUS_TOC_CONFIG_SHIFT) & OPUS_TOC_CONFIG_MASK
    # Frame durations at 48 kHz for each config range
    if config <= 3:       # SILK NB   10/20/40/60 ms
        durations = [480, 960, 1920, 2880]
    elif config <= 7:     # SILK MB   10/20/40/60 ms
        durations = [480, 960, 1920, 2880]
    elif config <= 11:    # SILK WB   10/20/40/60 ms
        durations = [480, 960, 1920, 2880]
    elif config <= 15:    # Hybrid SWB 10/20 ms
        durations = [480, 960, 480, 960]
    elif config <= 19:    # Hybrid FB  10/20 ms
        durations = [480, 960, 480, 960]
    elif config <= 23:    # CELT NB   2.5/5/10/20 ms
        durations = [120, 240, 480, 960]
    elif config <= 27:    # CELT WB   2.5/5/10/20 ms
        durations = [120, 240, 480, 960]
    elif config <= 31:    # CELT FB   2.5/5/10/20 ms
        durations = [120, 240, 480, 960]
    else:
        return OPUS_DEFAULT_SAMPLES_PER_FRAME

    return durations[config % OPUS_DURATION_VARIANTS]


def _build_ogg_opus_from_frames(
    opus_frames: list[bytes],
    channels: int = STEREO_CHANNEL_COUNT,
    sample_rate: int = LOPUS_DEFAULT_SAMPLE_RATE,
    pre_skip: int = LOPUS_DEFAULT_PRE_SKIP,
) -> bytes:
    """Build an OGG Opus file from a list of raw Opus frame data."""
    serial = OPUS_SERIAL_SSBU
    pages = []

    # Page 0: OpusHead (BOS)
    head_data = _make_opus_head(channels, pre_skip, sample_rate)
    head_segs = _segment_table_for_packet(len(head_data))
    pages.append(_make_ogg_page(head_data, serial, 0, 0, OPUS_PAGE_BOS_FLAG, head_segs))

    # Page 1: OpusTags
    tags_data = _make_opus_tags()
    tags_segs = _segment_table_for_packet(len(tags_data))
    pages.append(_make_ogg_page(tags_data, serial, 1, 0, OPUS_PAGE_NO_FLAGS, tags_segs))

    # Determine samples_per_frame from the first valid Opus frame's TOC
    samples_per_frame = OPUS_DEFAULT_SAMPLES_PER_FRAME
    if opus_frames and len(opus_frames[0]) >= 1:
        samples_per_frame = _opus_toc_samples(opus_frames[0][0])

    # Data pages
    granule = pre_skip
    page_seq = OPUS_PAGE_SEQUENCE_START
    i = 0

    while i < len(opus_frames):
        page_data_parts = []
        page_segments = []
        segs_used = 0

        while i < len(opus_frames) and segs_used < OPUS_SEGMENTS_PER_PAGE_TARGET:
            frame = opus_frames[i]
            frame_segs = _segment_table_for_packet(len(frame))
            if segs_used + len(frame_segs) > OPUS_SEGMENT_SIZE_MAX:
                break
            page_data_parts.append(frame)
            page_segments.extend(frame_segs)
            segs_used += len(frame_segs)
            granule += samples_per_frame
            i += 1

        flags = OPUS_PAGE_EOS_FLAG if i >= len(opus_frames) else OPUS_PAGE_NO_FLAGS
        page_data = b''.join(page_data_parts)
        pages.append(_make_ogg_page(page_data, serial, page_seq, granule, flags, page_segments))
        page_seq += 1

    return b''.join(pages)


# Cache directory for converted audio
_CACHE_DIR: Optional[Path] = None
_DECODER_CACHE_REV = "r14"


def _get_cache_dir() -> Path:
    global _CACHE_DIR
    if _CACHE_DIR is None:
        _CACHE_DIR = Path(tempfile.gettempdir()) / "ssbu-mod-manager-audio"
        _CACHE_DIR.mkdir(exist_ok=True)
    return _CACHE_DIR


def _is_ogg_opus(file_path: Path) -> bool:
    """Return True when *file_path* is an Ogg container carrying Opus."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(48)
        return b"OpusHead" in header
    except OSError:
        return False


def _copy_audio_variant(source: Optional[Path], destination: Path) -> Optional[Path]:
    """Copy a cached audio artifact to its canonical cache path."""
    if source is None or not source.exists():
        return None
    if source == destination:
        return destination
    try:
        shutil.copyfile(source, destination)
        return destination
    except OSError:
        return source


def _cache_selected_opus_artifacts(
    cache_dir: Path, cache_key: str, candidate: dict
) -> tuple[Optional[Path], Optional[Path]]:
    """Store the selected Opus candidate in canonical cache locations."""
    ogg_path = _copy_audio_variant(candidate.get("ogg"), cache_dir / f"{cache_key}.ogg")
    wav_path = _copy_audio_variant(candidate.get("wav"), cache_dir / f"{cache_key}.wav")
    return ogg_path, wav_path


def _resolve_cached_preview(
    cache_dir: Path, cache_key: str, display_name: str, prefer_stream: bool
) -> tuple[bool, str, Optional[Path]]:
    """Return a cached preview path matching the requested fidelity.

    Always prefers WAV over OGG because the Python OGG builder can produce
    pages that ffplay rejects ("Error parsing the packet header") even
    though ffmpeg tolerates them during WAV conversion.
    """
    for ext in (".wav", ".ogg"):
        cached = cache_dir / f"{cache_key}{ext}"
        if not cached.exists():
            continue
        try:
            size = cached.stat().st_size
        except OSError:
            size = 0
        if ext == ".wav" and size < 1000:
            try:
                cached.unlink()
            except OSError:
                pass
            continue
        if ext == ".ogg" and _is_ogg_opus(cached):
            wav_path = _convert_ogg_opus_to_wav(cached)
            if wav_path and wav_path.exists():
                return True, f"Playing: {display_name}", wav_path
            continue
        return True, f"Playing: {display_name}", cached
    return False, "", None


def _try_ffmpeg_direct_to_wav(input_path: Path, wav_out: Path) -> Optional[Path]:
    """Decode via ffmpeg with quality validation (last-resort fallback)."""
    try:
        from src.utils.logger import logger
        result = _run_ffmpeg_to_wav(input_path, wav_out)
        if result is None:
            return None
        if result.returncode != 0:
            # Always clean up partial output on failure
            try:
                wav_out.unlink(missing_ok=True)
            except (OSError, TypeError):
                try:
                    wav_out.unlink()
                except OSError:
                    pass
            stderr_preview = ""
            if result.stderr:
                stderr_preview = result.stderr.decode("utf-8", errors="replace")[:LOG_STDERR_PREVIEW_CHARS]
            logger.debug("NUS3AUDIO", f"ffmpeg direct failed (rc={result.returncode}): {stderr_preview}")
            return None
        if not wav_out.exists():
            return None

        sz = wav_out.stat().st_size
        zcr, corr = _wav_noise_signature(wav_out)
        noisy_signature = (
            zcr > FFMPEG_DIRECT_NOISE_ZCR_THRESHOLD
            and corr < FFMPEG_DIRECT_NOISE_CORR_THRESHOLD
        )
        if sz > PCM_WINDOW_BYTES_VALIDATE and _validate_wav_quality(wav_out) and not noisy_signature:
            dur = _wav_duration_seconds(wav_out)
            logger.info(
                "NUS3AUDIO",
                f"ffmpeg direct accepted ({sz} bytes, dur={dur:.1f}s, "
                f"zcr={zcr:.3f}, corr={corr:.3f})"
            )
            return wav_out

        logger.debug(
            "NUS3AUDIO",
            f"ffmpeg direct rejected ({sz} bytes, zcr={zcr:.3f}, corr={corr:.3f})"
        )
        try:
            wav_out.unlink()
        except OSError:
            pass
    except Exception as e:
        # Clean up partial output on exception too
        try:
            wav_out.unlink(missing_ok=True)
        except (OSError, TypeError):
            try:
                wav_out.unlink()
            except OSError:
                pass
        try:
            from src.utils.logger import logger
            logger.debug("NUS3AUDIO", f"ffmpeg direct failed: {e}")
        except Exception:
            pass
    return None


def _try_ffmpeg_raw_entry(audio_data: bytes, cache_dir: Path,
                          cache_key: str) -> Optional[Path]:
    """Try decoding a raw audio entry via ffmpeg auto-detection.

    Useful for NX OPUS containers that ffmpeg can handle natively even
    though it may not support the outer NUS3AUDIO wrapper.
    """
    if not _find_ffmpeg():
        return None
    raw_path = cache_dir / f"{cache_key}.raw_entry"
    wav_out = cache_dir / f"{cache_key}.wav"
    try:
        from src.utils.logger import logger
        raw_path.write_bytes(audio_data)
        result = _run_ffmpeg_to_wav(raw_path, wav_out)
        # Clean up temp input regardless
        try:
            raw_path.unlink()
        except OSError:
            pass
        if result is None or result.returncode != 0:
            try:
                wav_out.unlink(missing_ok=True)
            except (OSError, TypeError):
                try:
                    wav_out.unlink()
                except OSError:
                    pass
            if result and result.returncode != 0:
                stderr_preview = ""
                if result.stderr:
                    stderr_preview = result.stderr.decode("utf-8", errors="replace")[:LOG_STDERR_PREVIEW_CHARS]
                logger.debug("NUS3AUDIO", f"ffmpeg raw entry failed (rc={result.returncode}): {stderr_preview}")
            return None
        if not wav_out.exists() or wav_out.stat().st_size < FFMPEG_RAW_MIN_WAV_BYTES:
            try:
                wav_out.unlink(missing_ok=True)
            except (OSError, TypeError):
                try:
                    wav_out.unlink()
                except OSError:
                    pass
            return None
        # Quality / noise validation
        if not _validate_wav_quality(wav_out):
            try:
                wav_out.unlink()
            except OSError:
                pass
            return None
        zcr, corr = _wav_noise_signature(wav_out)
        if zcr > FFMPEG_DIRECT_NOISE_ZCR_THRESHOLD and corr < FFMPEG_DIRECT_NOISE_CORR_THRESHOLD:
            try:
                wav_out.unlink()
            except OSError:
                pass
            return None
        dur = _wav_duration_seconds(wav_out)
        logger.info(
            "NUS3AUDIO",
            f"ffmpeg raw entry accepted ({wav_out.stat().st_size} bytes, "
            f"dur={dur:.1f}s, zcr={zcr:.3f}, corr={corr:.3f})"
        )
        return wav_out
    except Exception as e:
        try:
            raw_path.unlink()
        except OSError:
            pass
        try:
            wav_out.unlink(missing_ok=True)
        except (OSError, TypeError):
            try:
                wav_out.unlink()
            except OSError:
                pass
        try:
            from src.utils.logger import logger
            logger.debug("NUS3AUDIO", f"ffmpeg raw entry error: {e}")
        except Exception:
            pass
        return None


def extract_and_convert(
    nus3audio_path: Path, prefer_stream: bool = False
) -> tuple[bool, str, Optional[Path]]:
    """
    Extract audio from a NUS3AUDIO file and convert to a playable format.
    Supports LOPUS, IDSP, BWAV, WAV, and OGG formats inside NUS3AUDIO containers.

    Returns:
        (success, message, temp_file_path)
        If success is True, temp_file_path is a playable .ogg or .wav file.
    """
    # Check cache first
    cache_dir = _get_cache_dir()
    try:
        file_size = os.path.getsize(nus3audio_path)
    except OSError:
        file_size = 0
    cache_key = f"{nus3audio_path.stem}_{file_size}_{_DECODER_CACHE_REV}"

    cached_result = _resolve_cached_preview(
        cache_dir, cache_key, nus3audio_path.name, prefer_stream
    )
    if cached_result[0]:
        return cached_result

    try:
        with open(nus3audio_path, 'rb') as f:
            data = f.read()
    except Exception as e:
        return False, f"Failed to read file: {e}", None

    # Verify NUS3 magic
    if len(data) < 8 or data[:4] != b'NUS3':
        return False, "Not a valid NUS3AUDIO file", None

    # Manual extraction from NUS3AUDIO container.
    sections = _find_sections(data)
    audio_entries = _extract_audio_entries(data, sections)

    if not audio_entries:
        # Last-resort: try ffmpeg on the whole NUS3AUDIO file (requires
        # an ffmpeg build with the NUS3AUDIO demuxer).
        wav_out = cache_dir / f"{cache_key}.wav"
        direct = _try_ffmpeg_direct_to_wav(nus3audio_path, wav_out)
        if direct is not None:
            return True, f"Playing: {nus3audio_path.name}", direct
        return False, "No audio data found in NUS3AUDIO", None

    # Try the first (usually only) audio entry
    audio_data = audio_entries[0]

    if len(audio_data) < 4:
        return False, "Audio data too short", None

    # Try each format, returning the first successful conversion
    result = _try_convert_audio(
        audio_data, cache_dir, cache_key, nus3audio_path.name, prefer_stream=prefer_stream
    )
    if result[0]:
        return result

    # If first entry failed and there are more, try others
    for i, entry in enumerate(audio_entries[1:], 1):
        if len(entry) < 4:
            continue
        result = _try_convert_audio(
            entry,
            cache_dir,
            f"{cache_key}_{i}",
            nus3audio_path.name,
            prefer_stream=prefer_stream,
        )
        if result[0]:
            return result

    fmt_hex = struct.unpack_from('<I', audio_data, 0)[0]
    fmt_ascii = audio_data[:4].decode('ascii', errors='replace')
    return False, f"Could not convert audio (format: 0x{fmt_hex:08X} / '{fmt_ascii}', size: {len(audio_data)} bytes)", None


def _try_convert_audio(
    audio_data: bytes,
    cache_dir: Path,
    cache_key: str,
    display_name: str,
    prefer_stream: bool = False,
) -> tuple[bool, str, Optional[Path]]:
    """Try converting audio data from various Nintendo formats to a playable format."""
    # Standard WAV
    if audio_data[:4] == b'RIFF':
        out = cache_dir / f"{cache_key}.wav"
        out.write_bytes(audio_data)
        return True, f"Playing: {display_name}", out

    # Standard OGG
    if audio_data[:4] == b'OggS':
        out = cache_dir / f"{cache_key}.ogg"
        out.write_bytes(audio_data)
        return True, f"Playing: {display_name}", out

    # For LOPUS / OPUS entries, try ffmpeg on the raw extracted entry
    # first.  ffmpeg may have a native decoder (NX OPUS / nsopusdec)
    # that handles these more reliably than manual OGG construction.
    if len(audio_data) >= 4:
        _raw_magic = struct.unpack_from('<I', audio_data, 0)[0]
        if (_raw_magic & 0x80000000) or audio_data[:4] == b'OPUS':
            _raw_wav = _try_ffmpeg_raw_entry(audio_data, cache_dir, cache_key)
            if _raw_wav is not None:
                return True, f"Playing: {display_name}", _raw_wav

    # LOPUS (Nintendo Opus)
    if len(audio_data) >= 4:
        lopus_magic = struct.unpack_from('<I', audio_data, 0)[0]
        if lopus_magic & 0x80000000:
            from src.utils.logger import logger
            candidates: list[dict] = []
            best_candidate: Optional[dict] = None

            # Prefer auto/stereo. Forced mono is only used as a last resort
            # when no other candidate could be decoded.
            for try_channels in [None, 2]:
                ch_label = str(try_channels) if try_channels is not None else "auto"
                try:
                    ogg_data = _lopus_to_ogg(audio_data, force_channels=try_channels)
                    ogg_path = cache_dir / f"{cache_key}_lopus_{ch_label}.ogg"
                    ogg_path.write_bytes(ogg_data)
                    wav_path = _convert_ogg_opus_to_wav(ogg_path)
                    if wav_path and wav_path.exists():
                        raw_score, out_channels = _score_wav_quality(wav_path)
                        duration_s = _wav_duration_seconds(wav_path)
                        score, bitrate_kbps = _score_opus_candidate(
                            raw_score, duration_s, len(audio_data)
                        )
                        zcr, corr = _wav_noise_signature(wav_path)
                        candidate = {
                            "label": f"{ch_label}/{out_channels}ch",
                            "score": score,
                            "raw": raw_score,
                            "duration": duration_s,
                            "bitrate": bitrate_kbps,
                            "zcr": zcr,
                            "corr": corr,
                            "out_channels": out_channels,
                            "forced_channels": try_channels,
                            "ogg": ogg_path,
                            "wav": wav_path,
                        }
                        candidates.append(candidate)
                except Exception as e:
                    logger.debug("NUS3AUDIO", f"LOPUS try ch={ch_label}: {e}")

            if not candidates:
                ch_label = "1"
                try:
                    ogg_data = _lopus_to_ogg(audio_data, force_channels=1)
                    ogg_path = cache_dir / f"{cache_key}_lopus_{ch_label}.ogg"
                    ogg_path.write_bytes(ogg_data)
                    wav_path = _convert_ogg_opus_to_wav(ogg_path)
                    if wav_path and wav_path.exists():
                        raw_score, out_channels = _score_wav_quality(wav_path)
                        duration_s = _wav_duration_seconds(wav_path)
                        score, bitrate_kbps = _score_opus_candidate(
                            raw_score, duration_s, len(audio_data)
                        )
                        zcr, corr = _wav_noise_signature(wav_path)
                        candidates.append({
                            "label": f"{ch_label}/{out_channels}ch",
                            "score": score,
                            "raw": raw_score,
                            "duration": duration_s,
                            "bitrate": bitrate_kbps,
                            "zcr": zcr,
                            "corr": corr,
                            "out_channels": out_channels,
                            "forced_channels": 1,
                            "ogg": ogg_path,
                            "wav": wav_path,
                        })
                except Exception as e:
                    logger.debug("NUS3AUDIO", f"LOPUS try ch={ch_label}: {e}")

            best_idx = _select_best_candidate_index(candidates)
            if best_idx >= 0 and candidates:
                chosen_idx = _pick_low_noise_override(candidates, best_idx)
                if chosen_idx != best_idx:
                    noisy = candidates[best_idx]
                    clean = candidates[chosen_idx]
                    logger.info(
                        "NUS3AUDIO",
                        f"LOPUS override {noisy['label']} -> {clean['label']} "
                        f"(zcr {noisy['zcr']:.3f}->{clean['zcr']:.3f}, "
                        f"corr {noisy['corr']:.3f}->{clean['corr']:.3f})"
                    )
                best = candidates[chosen_idx]
                best_candidate = best
                best_label = best["label"]
                best_score = best["score"]
                best_duration = best["duration"]
                best_bitrate = best["bitrate"]
            else:
                best_label = ""
                best_score = 0.0
                best_duration = 0.0
                best_bitrate = 0.0

            if best_idx >= 0 and best_candidate:
                if candidates:
                    top = sorted(candidates, key=lambda x: x["score"], reverse=True)[:4]
                    logger.debug(
                        "NUS3AUDIO",
                        "LOPUS candidates: " + "; ".join(
                            f"{c['label']} adj={c['score']:.2f} raw={c['raw']:.2f} "
                            f"dur={c['duration']:.2f}s br={int(round(c['bitrate']))}kbps "
                            f"zcr={c['zcr']:.3f} corr={c['corr']:.3f}"
                            for c in top
                        )
                    )
                best_ogg, best_wav = _cache_selected_opus_artifacts(
                    cache_dir, cache_key, best_candidate
                )
                if best_wav and _validate_wav_quality(best_wav):
                    logger.info(
                        "NUS3AUDIO",
                        f"LOPUS best decode {best_label} score={best_score:.2f} "
                        f"duration={best_duration:.2f}s bitrate={best_bitrate:.1f}kbps"
                    )
                else:
                    logger.warn(
                        "NUS3AUDIO",
                        f"LOPUS decode below quality threshold ({best_label}, "
                        f"score={best_score:.2f}, duration={best_duration:.2f}s, "
                        f"bitrate={best_bitrate:.1f}kbps)"
                    )
                chosen_output = best_wav if best_wav and best_wav.exists() else best_ogg
                if chosen_output is not None and chosen_output.exists():
                    return True, f"Playing: {display_name}", chosen_output

            if not _find_ffmpeg():
                logger.warn(
                    "NUS3AUDIO",
                    "Opus audio requires ffmpeg for playback. Install ffmpeg and add it to PATH."
                )
                return False, (
                    "This track uses Opus audio which requires ffmpeg for playback.\n"
                    "Install ffmpeg and add it to PATH."
                ), None

            logger.warn("NUS3AUDIO", "All LOPUS conversion attempts failed")

    # IDSP (Nintendo DSP ADPCM)
    if audio_data[:4] == b'IDSP':
        try:
            wav_data = _idsp_to_wav(audio_data)
            out = cache_dir / f"{cache_key}.wav"
            out.write_bytes(wav_data)
            return True, f"Playing: {display_name}", out
        except Exception as e:
            return False, f"IDSP conversion failed: {e}", None

    # BWAV
    if audio_data[:4] == b'BWAV':
        try:
            wav_data = _bwav_to_wav(audio_data)
            out = cache_dir / f"{cache_key}.wav"
            out.write_bytes(wav_data)
            return True, f"Playing: {display_name}", out
        except Exception as e:
            return False, f"BWAV conversion failed: {e}", None

    # OPUS raw container
    if audio_data[:4] == b'OPUS':
        from src.utils.logger import logger
        candidates: list[dict] = []
        best_candidate: Optional[dict] = None

        def _capture_best(ogg_data: bytes, label: str,
                          forced_channels: Optional[int] = None) -> None:
            ogg_path = cache_dir / f"{cache_key}_{label}.ogg"
            ogg_path.write_bytes(ogg_data)
            wav_path = _convert_ogg_opus_to_wav(ogg_path)
            if wav_path and wav_path.exists():
                raw_score, out_channels = _score_wav_quality(wav_path)
                duration_s = _wav_duration_seconds(wav_path)
                score, bitrate_kbps = _score_opus_candidate(
                    raw_score, duration_s, len(audio_data)
                )
                zcr, corr = _wav_noise_signature(wav_path)
                candidate = {
                    "label": f"{label}/{out_channels}ch",
                    "score": score,
                    "raw": raw_score,
                    "duration": duration_s,
                    "bitrate": bitrate_kbps,
                    "zcr": zcr,
                    "corr": corr,
                    "out_channels": out_channels,
                    "forced_channels": forced_channels,
                    "ogg": ogg_path,
                    "wav": wav_path,
                }
                candidates.append(candidate)

        # Main OPUS container path.
        try:
            _capture_best(_opus_container_to_ogg(audio_data), "opus_container")
        except Exception as e:
            logger.debug("NUS3AUDIO", f"OPUS container conversion: {e}")

        # Fallback: try interpreting payload offsets as LOPUS. Keep mono as
        # a strict last resort only.
        for try_ch in [None, 2]:
            ch_label = str(try_ch) if try_ch is not None else "auto"
            for payload_off in OPUS_PAYLOAD_OFFSETS:
                if len(audio_data) <= payload_off + LOPUS_MIN_SLOT_SIZE:
                    continue
                try:
                    ogg_data = _lopus_to_ogg(audio_data[payload_off:], force_channels=try_ch)
                    _capture_best(
                        ogg_data,
                        f"opus_lopus_{ch_label}_off{payload_off}",
                        forced_channels=try_ch,
                    )
                except Exception:
                    pass

        if not candidates:
            ch_label = "1"
            for payload_off in OPUS_PAYLOAD_OFFSETS:
                if len(audio_data) <= payload_off + LOPUS_MIN_SLOT_SIZE:
                    continue
                try:
                    ogg_data = _lopus_to_ogg(audio_data[payload_off:], force_channels=1)
                    _capture_best(
                        ogg_data,
                        f"opus_lopus_{ch_label}_off{payload_off}",
                        forced_channels=1,
                    )
                except Exception:
                    pass

        best_idx = _select_best_candidate_index(candidates)
        if best_idx >= 0 and candidates:
            chosen_idx = _pick_low_noise_override(candidates, best_idx)
            if chosen_idx != best_idx:
                noisy = candidates[best_idx]
                clean = candidates[chosen_idx]
                logger.info(
                    "NUS3AUDIO",
                    f"OPUS override {noisy['label']} -> {clean['label']} "
                    f"(zcr {noisy['zcr']:.3f}->{clean['zcr']:.3f}, "
                    f"corr {noisy['corr']:.3f}->{clean['corr']:.3f})"
                )
            best = candidates[chosen_idx]
            best_candidate = best
            best_label = best["label"]
            best_score = best["score"]
            best_duration = best["duration"]
            best_bitrate = best["bitrate"]
        else:
            best_label = ""
            best_score = 0.0
            best_duration = 0.0
            best_bitrate = 0.0

        if best_candidate:
            if candidates:
                top = sorted(candidates, key=lambda x: x["score"], reverse=True)[:6]
                logger.debug(
                    "NUS3AUDIO",
                    "OPUS candidates: " + "; ".join(
                        f"{c['label']} adj={c['score']:.2f} raw={c['raw']:.2f} "
                        f"dur={c['duration']:.2f}s br={int(round(c['bitrate']))}kbps "
                        f"zcr={c['zcr']:.3f} corr={c['corr']:.3f}"
                        for c in top
                    )
                )
            best_ogg, best_wav = _cache_selected_opus_artifacts(
                cache_dir, cache_key, best_candidate
            )
            if best_wav and _validate_wav_quality(best_wav):
                logger.info(
                    "NUS3AUDIO",
                    f"OPUS best decode {best_label} score={best_score:.2f} "
                    f"duration={best_duration:.2f}s bitrate={best_bitrate:.1f}kbps"
                )
            else:
                logger.warn(
                    "NUS3AUDIO",
                    f"OPUS decode below quality threshold ({best_label}, "
                    f"score={best_score:.2f}, duration={best_duration:.2f}s, "
                    f"bitrate={best_bitrate:.1f}kbps)"
                )
            chosen_output = best_wav if best_wav and best_wav.exists() else best_ogg
            if chosen_output is not None and chosen_output.exists():
                return True, f"Playing: {display_name}", chosen_output

        if not _find_ffmpeg():
            return False, (
                "This track uses Opus audio which requires ffmpeg for playback.\n"
                "Install ffmpeg and add it to PATH."
            ), None

        logger.warn("NUS3AUDIO", "All OPUS conversion attempts failed")

    # --- ffmpeg raw fallback ---
    if _find_ffmpeg():
        try:
            raw_path = cache_dir / f"{cache_key}.raw_opus"
            raw_path.write_bytes(audio_data)
            wav_out = cache_dir / f"{cache_key}.wav"
            result = _run_ffmpeg_to_wav(raw_path, wav_out)
            if (
                result is not None
                and result.returncode == 0
                and wav_out.exists()
                and wav_out.stat().st_size > FFMPEG_RAW_MIN_WAV_BYTES
            ):
                try:
                    raw_path.unlink()
                except OSError:
                    pass
                return True, f"Playing: {display_name}", wav_out
            try:
                raw_path.unlink()
            except OSError:
                pass
        except Exception:
            pass

    # MP3
    if audio_data[:3] == b'ID3' or (len(audio_data) >= 2 and audio_data[0] == 0xFF and (audio_data[1] & 0xE0) == 0xE0):
        out = cache_dir / f"{cache_key}.mp3"
        out.write_bytes(audio_data)
        return True, f"Playing: {display_name}", out

    return False, "Unsupported audio format", None

def cleanup_cache():
    """Remove all cached audio files."""
    cache_dir = _get_cache_dir()
    try:
        for f in cache_dir.iterdir():
            try:
                f.unlink()
            except Exception:
                pass
    except Exception:
        pass


