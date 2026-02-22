"""NUS3AUDIO parser and LOPUS-to-OGG converter for audio preview.

NUS3AUDIO is Nintendo's audio container format used in SSBU.
Inside it, tracks are typically stored in LOPUS format (Nintendo's
Opus variant with custom framing). This module extracts the audio
data and converts LOPUS to standard OGG Opus for playback.
"""
import struct
import tempfile
import os
from pathlib import Path
from typing import Optional


# OGG CRC32 lookup table (polynomial 0x04C11DB7)
_OGG_CRC_TABLE: Optional[list[int]] = None


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
    while remaining >= 255:
        segments.append(255)
        remaining -= 255
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


def _lopus_to_ogg(lopus_data: bytes) -> bytes:
    """Convert Nintendo LOPUS data to standard OGG Opus."""
    if len(lopus_data) < 16:
        raise ValueError("LOPUS data too short")

    magic = struct.unpack_from('<I', lopus_data, 0)[0]

    # Parse header based on version
    if magic == 0x80000004:
        header_size = struct.unpack_from('<I', lopus_data, 4)[0]
        sample_rate = struct.unpack_from('<I', lopus_data, 0x0C)[0]
        channel_count = struct.unpack_from('<I', lopus_data, 0x10)[0]
        frame_size = struct.unpack_from('<I', lopus_data, 0x14)[0]
        total_samples = struct.unpack_from('<I', lopus_data, 0x18)[0]
        pre_skip = struct.unpack_from('<H', lopus_data, 0x1C)[0]
    elif magic == 0x80000003:
        header_size = struct.unpack_from('<I', lopus_data, 4)[0]
        sample_rate = struct.unpack_from('<I', lopus_data, 0x0C)[0]
        channel_count = struct.unpack_from('<I', lopus_data, 0x10)[0]
        frame_size = struct.unpack_from('<I', lopus_data, 0x14)[0]
        total_samples = struct.unpack_from('<I', lopus_data, 0x18)[0]
        pre_skip = struct.unpack_from('<H', lopus_data, 0x1C)[0]
    elif magic == 0x80000002:
        header_size = struct.unpack_from('<I', lopus_data, 4)[0]
        channel_count = lopus_data[0x09] if len(lopus_data) > 0x09 else 2
        frame_size = struct.unpack_from('<H', lopus_data, 0x0A)[0] if len(lopus_data) > 0x0B else 640
        sample_rate = struct.unpack_from('<I', lopus_data, 0x0C)[0]
        total_samples = struct.unpack_from('<I', lopus_data, 0x10)[0]
        pre_skip = struct.unpack_from('<H', lopus_data, 0x1A)[0] if len(lopus_data) > 0x1B else 312
    elif magic == 0x80000001:
        header_size = struct.unpack_from('<I', lopus_data, 4)[0]
        channel_count = lopus_data[0x09] if len(lopus_data) > 0x09 else 2
        frame_size = struct.unpack_from('<H', lopus_data, 0x0A)[0] if len(lopus_data) > 0x0B else 640
        sample_rate = struct.unpack_from('<I', lopus_data, 0x0C)[0]
        total_samples = struct.unpack_from('<I', lopus_data, 0x10)[0]
        pre_skip = struct.unpack_from('<H', lopus_data, 0x1A)[0] if len(lopus_data) > 0x1B else 312
    else:
        # Unknown version — try a generic parse
        header_size = struct.unpack_from('<I', lopus_data, 4)[0] if len(lopus_data) >= 8 else 0x28
        sample_rate = 48000
        channel_count = 2
        frame_size = 640
        total_samples = 0
        pre_skip = 312

    # Sanitize
    if channel_count == 0 or channel_count > 8:
        channel_count = 2
    if sample_rate == 0:
        sample_rate = 48000
    if frame_size == 0:
        frame_size = 640
    if pre_skip == 0:
        pre_skip = 312
    if header_size == 0 or header_size > len(lopus_data):
        header_size = 0x28

    # Extract Opus frames from data section
    opus_frames = []
    pos = header_size
    while pos + 4 <= len(lopus_data):
        actual_size = struct.unpack_from('<I', lopus_data, pos)[0]
        if actual_size == 0 or actual_size > frame_size:
            break
        if pos + 4 + actual_size > len(lopus_data):
            break

        frame_data = lopus_data[pos + 4:pos + 4 + actual_size]
        opus_frames.append(frame_data)
        pos += frame_size  # advance by fixed frame slot size

    if not opus_frames:
        raise ValueError("No Opus frames extracted from LOPUS data")

    # Build OGG Opus file
    serial = 0x53534255  # "SSBU"
    pages = []

    # Page 0: OpusHead (BOS = beginning of stream)
    head_data = _make_opus_head(channel_count, pre_skip, sample_rate)
    head_segs = _segment_table_for_packet(len(head_data))
    pages.append(_make_ogg_page(head_data, serial, 0, 0, 0x02, head_segs))

    # Page 1: OpusTags
    tags_data = _make_opus_tags()
    tags_segs = _segment_table_for_packet(len(tags_data))
    pages.append(_make_ogg_page(tags_data, serial, 1, 0, 0x00, tags_segs))

    # Data pages — pack multiple frames per page
    samples_per_frame = 960  # 20ms at 48kHz (standard Opus)
    granule = pre_skip
    page_seq = 2
    i = 0

    while i < len(opus_frames):
        page_data_parts = []
        page_segments = []
        segs_used = 0

        while i < len(opus_frames) and segs_used < 240:
            frame = opus_frames[i]
            frame_segs = _segment_table_for_packet(len(frame))
            if segs_used + len(frame_segs) > 255:
                break
            page_data_parts.append(frame)
            page_segments.extend(frame_segs)
            segs_used += len(frame_segs)
            granule += samples_per_frame
            i += 1

        flags = 0x04 if i >= len(opus_frames) else 0x00  # EOS on last
        page_data = b''.join(page_data_parts)
        pages.append(_make_ogg_page(page_data, serial, page_seq, granule, flags, page_segments))
        page_seq += 1

    return b''.join(pages)


def _find_sections(data: bytes) -> dict[str, tuple[int, int]]:
    """Find all sections in a NUS3AUDIO file. Returns {name: (data_offset, data_size)}."""
    sections = {}
    pos = 8  # Skip "NUS3" + total size
    while pos + 8 <= len(data):
        # Section name (4 or 8 bytes, but we read 4 and check)
        name = data[pos:pos + 4]
        try:
            name_str = name.decode('ascii').strip()
        except UnicodeDecodeError:
            break
        size = struct.unpack_from('<I', data, pos + 4)[0]
        sections[name_str] = (pos + 8, size)
        pos += 8 + size
        # Align to 4 bytes
        if pos % 4:
            pos += 4 - (pos % 4)
    return sections


# Cache directory for converted audio
_CACHE_DIR: Optional[Path] = None


def _get_cache_dir() -> Path:
    global _CACHE_DIR
    if _CACHE_DIR is None:
        _CACHE_DIR = Path(tempfile.gettempdir()) / "ssbu-mod-manager-audio"
        _CACHE_DIR.mkdir(exist_ok=True)
    return _CACHE_DIR


def extract_and_convert(nus3audio_path: Path) -> tuple[bool, str, Optional[Path]]:
    """
    Extract audio from a NUS3AUDIO file and convert to a playable format.

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
    cache_key = f"{nus3audio_path.stem}_{file_size}"
    cached = cache_dir / f"{cache_key}.ogg"
    if cached.exists():
        return True, f"Playing: {nus3audio_path.name}", cached

    try:
        with open(nus3audio_path, 'rb') as f:
            data = f.read()
    except Exception as e:
        return False, f"Failed to read file: {e}", None

    # Verify NUS3 magic
    if len(data) < 8 or data[:4] != b'NUS3':
        return False, "Not a valid NUS3AUDIO file", None

    # Find PACK section (contains the actual audio data)
    # Simple approach: search for section markers
    sections = _find_sections(data)

    pack_offset = None
    pack_size = None

    if 'PACK' in sections:
        pack_offset, pack_size = sections['PACK']
    else:
        # Fallback: search for PACK marker
        idx = data.find(b'PACK')
        if idx >= 0 and idx + 8 <= len(data):
            pack_size = struct.unpack_from('<I', data, idx + 4)[0]
            pack_offset = idx + 8

    if pack_offset is None:
        return False, "No PACK section found in NUS3AUDIO", None

    audio_data = data[pack_offset:pack_offset + pack_size]

    if len(audio_data) < 16:
        return False, "Audio data too short", None

    # Detect format of the audio data
    # Standard WAV
    if audio_data[:4] == b'RIFF':
        out = cache_dir / f"{cache_key}.wav"
        out.write_bytes(audio_data)
        return True, f"Playing: {nus3audio_path.name}", out

    # Standard OGG
    if audio_data[:4] == b'OggS':
        out = cache_dir / f"{cache_key}.ogg"
        out.write_bytes(audio_data)
        return True, f"Playing: {nus3audio_path.name}", out

    # LOPUS (Nintendo Opus) — magic starts with 0x80000001..0x80000004
    lopus_magic = struct.unpack_from('<I', audio_data, 0)[0]
    if lopus_magic & 0x80000000:
        try:
            ogg_data = _lopus_to_ogg(audio_data)
            out = cache_dir / f"{cache_key}.ogg"
            out.write_bytes(ogg_data)
            return True, f"Playing: {nus3audio_path.name}", out
        except Exception as e:
            return False, f"LOPUS conversion failed: {e}", None

    # IDSP (Nintendo ADPCM) — not easily convertible in Python
    if audio_data[:4] == b'IDSP':
        return False, "IDSP audio format not supported for preview. Use vgmstream to convert.", None

    # BWAV
    if audio_data[:4] == b'BWAV':
        return False, "BWAV audio format not supported for preview.", None

    return False, f"Unknown audio format (magic: 0x{lopus_magic:08X})", None


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
