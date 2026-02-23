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
    # Check common install locations on Windows
    for candidate in [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\ffmpeg\bin\ffmpeg.exe"),
        os.path.expandvars(r"%ProgramFiles%\ffmpeg\bin\ffmpeg.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\ffmpeg\bin\ffmpeg.exe"),
    ]:
        if os.path.isfile(candidate):
            _ffmpeg_path = candidate
            return candidate
    return None


def _convert_ogg_opus_to_wav(ogg_path: Path) -> Optional[Path]:
    """Convert an OGG Opus file to WAV using ffmpeg.

    pygame's SDL_mixer uses stb_vorbis for .ogg files, which only
    supports Vorbis — not Opus. ffmpeg can decode Opus to WAV.
    Returns path to WAV file, or None if conversion failed.
    """
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return None
    # Write WAV to the audio cache directory so cleanup_cache()
    # removes it.  Previous versions wrote to the system temp dir
    # which leaked files on crash.
    cache_dir = _get_cache_dir()
    wav_path = cache_dir / (ogg_path.stem + ".wav")
    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-i", str(ogg_path), "-ar", "48000",
             "-ac", "2", "-sample_fmt", "s16", str(wav_path)],
            capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0 and wav_path.exists() and wav_path.stat().st_size > 44:
            return wav_path
        # Log ffmpeg failure details
        try:
            from src.utils.logger import logger
            stderr = result.stderr.decode('utf-8', errors='replace')[:200] if result.stderr else ''
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
    if len(lopus_data) < 30:
        raise ValueError(f"LOPUS data too short ({len(lopus_data)} bytes, need at least 30)")

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

    # Extract Opus frames from data section (try LE first, then BE)
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

    # If LE extraction yielded too few frames or frames look invalid,
    # try BE frame sizes instead.
    if len(opus_frames) < 10 or not _validate_opus_frames(opus_frames):
        be_frames = []
        pos = header_size
        while pos + 4 <= len(lopus_data):
            actual_size = struct.unpack_from('>I', lopus_data, pos)[0]
            if actual_size == 0 or actual_size > frame_size:
                break
            if pos + 4 + actual_size > len(lopus_data):
                break
            be_frames.append(lopus_data[pos + 4:pos + 4 + actual_size])
            pos += frame_size
        if len(be_frames) > len(opus_frames) and _validate_opus_frames(be_frames):
            opus_frames = be_frames

    # If size-prefixed extraction failed, try CBR (fixed-size) frames
    # where each slot is an entire Opus packet with no size prefix.
    if len(opus_frames) < 10 or not _validate_opus_frames(opus_frames):
        cbr_frames = _extract_opus_cbr_frames(
            lopus_data, frame_size, search_start=header_size)
        if len(cbr_frames) >= 10 and _validate_opus_frames(cbr_frames):
            opus_frames = cbr_frames

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
    # Determine samples_per_frame from first frame's TOC byte
    samples_per_frame = 960  # default 20 ms at 48 kHz
    if opus_frames and len(opus_frames[0]) >= 1:
        samples_per_frame = _opus_toc_samples(opus_frames[0][0])
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


# --- IDSP (Nintendo DSP ADPCM) decoder ---
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
        0x20: u32 data_offset (BE) — typically 0x30–0x40
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
    if len(audio_data) < 8:
        raise ValueError("OPUS container too short")

    # Values parsed from the OPUS header (used by fallback strategies)
    parsed_channels: int = 2
    parsed_sample_rate: int = 48000
    parsed_data_offset: int = 4          # default: skip "OPUS" magic only
    parsed_pre_skip: int = 312
    header_parsed: bool = False

    # --- Strategy 0: SSBU OPUS container with big-endian header ---
    if len(audio_data) >= 0x28:
        try:
            container_data_offset = struct.unpack_from('>I', audio_data, 0x20)[0]
            container_data_size = struct.unpack_from('>I', audio_data, 0x24)[0]
            container_channels = struct.unpack_from('>I', audio_data, 0x0C)[0]
            container_sample_rate = struct.unpack_from('>I', audio_data, 0x10)[0]

            if (0x10 <= container_data_offset <= 0x100
                    and 1 <= container_channels <= 8
                    and 8000 <= container_sample_rate <= 192000
                    and container_data_offset + container_data_size <= len(audio_data) + 64):
                # Header looks valid — save for fallback strategies
                parsed_channels = container_channels
                parsed_sample_rate = container_sample_rate
                parsed_data_offset = container_data_offset
                header_parsed = True

                inner = audio_data[container_data_offset:]

                # Check for LOPUS sub-header inside the inner data
                if len(inner) >= 0x28:
                    sub_magic = struct.unpack_from('<I', inner, 0)[0]
                    if sub_magic & 0x80000000:
                        # _lopus_to_ogg has correct version-specific header
                        # parsing for all LOPUS variants (v1-v4).  Try it
                        # FIRST — the manual slot extraction below uses
                        # hard-coded offsets that are wrong for some versions.
                        try:
                            return _lopus_to_ogg(inner)
                        except Exception:
                            pass

                        # Manual fallback: read header fields and try
                        # slot-based extraction with correct offsets.
                        lopus_type = sub_magic & 0xFF
                        if lopus_type in (1, 2, 3, 4):
                            lopus_hdr_size = struct.unpack_from('<I', inner, 4)[0]

                            # Determine slot_size based on LOPUS version:
                            #   v2: u16 at 0x0A
                            #   v3/v4: u32 at 0x14
                            #   v1: u32 at 0x14 or default 640
                            if lopus_type == 2:
                                slot_size = struct.unpack_from('<H', inner, 0x0A)[0]
                            else:
                                slot_size = struct.unpack_from('<I', inner, 0x14)[0]
                            if slot_size == 0 or not (8 <= slot_size <= 0x2000):
                                # Try alt field
                                alt = struct.unpack_from('<I', inner, 0x14)[0]
                                if 8 <= alt <= 0x2000:
                                    slot_size = alt
                                else:
                                    slot_size = 640

                            # Read pre_skip
                            ps = 312
                            if len(inner) > 0x1C:
                                ps = struct.unpack_from('<H', inner, 0x1A)[0]
                                if ps == 0:
                                    ps = struct.unpack_from('<I', inner, 0x1C)[0]
                                if not (0 < ps < 10000):
                                    ps = 312
                            parsed_pre_skip = ps

                            # Use actual header_size as primary frame start
                            start_offsets = []
                            if 8 <= lopus_hdr_size <= 0x100:
                                start_offsets.append(lopus_hdr_size)
                            for o in [0x28, 0x20, 0x30, 0x38, 0x40, 0x18]:
                                if o not in start_offsets:
                                    start_offsets.append(o)

                            # Try LE frame sizes first (most common in mods)
                            for frame_start in start_offsets:
                                frames = _extract_opus_le_slots(
                                    inner, frame_start, slot_size)
                                if len(frames) >= 10 and _validate_opus_frames(frames):
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
                                if len(frames) >= 10 and _validate_opus_frames(frames):
                                    return _build_ogg_opus_from_frames(
                                        frames,
                                        channels=container_channels,
                                        sample_rate=container_sample_rate,
                                        pre_skip=parsed_pre_skip,
                                    )

                            # Try CBR (fixed-size) frames
                            cbr_start = lopus_hdr_size if 8 <= lopus_hdr_size <= 0x100 else 0x28
                            cbr_frames = _extract_opus_cbr_frames(
                                inner, slot_size, search_start=cbr_start)
                            if len(cbr_frames) >= 10 and _validate_opus_frames(cbr_frames):
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
    if len(inner_data) >= 4:
        sub_magic = struct.unpack_from('<I', inner_data, 0)[0]
        if sub_magic & 0x80000000:
            return _lopus_to_ogg(inner_data)

    errors = []

    # Strategy 1: Skip 4 bytes (data_size field), treat rest as frames
    if len(inner_data) >= 8:
        declared_size = struct.unpack_from('<I', inner_data, 0)[0]
        if 0 < declared_size <= len(inner_data) - 4:
            opus_data = inner_data[4:4 + declared_size]
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
    for header_offset in [8, 12, 16, 20, 24, 28, 32, 48, 64, 0x28, 0x30]:
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
    for slot_size in [0x280, 0x500, 0x200, 0x400, 0x100, 0x300, 0x600, 0x800]:
        try:
            return _extract_opus_fixed_slots(
                inner_data, slot_size,
                channels=parsed_channels,
                sample_rate=parsed_sample_rate)
        except Exception:
            pass
        for skip in [4, 8, 12, 16, 0x28, 0x30]:
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
                             search_start: int = 0x18) -> list[bytes]:
    """Extract fixed-size (CBR) Opus frames with no per-frame size prefix.

    LOPUS type 0x80000001 can use constant bitrate where each Opus packet
    is exactly *slot_size* bytes, packed sequentially after the header.
    We scan for offsets (starting from *search_start*) where valid Opus
    TOC bytes appear consistently at *slot_size* intervals, then pick the
    best candidate (highest Opus config = fullband CELT for music).

    Returns a list of raw Opus frame bytes, or an empty list on failure.
    """
    if slot_size < 8 or slot_size > 0x2000:
        return []

    end_search = min(search_start + slot_size, len(data) - slot_size * 3)
    candidates: list[tuple[int, int, int]] = []  # (config, offset, num_frames)

    for test_off in range(search_start, max(search_start, end_search)):
        if test_off + slot_size * 3 > len(data):
            break
        toc = data[test_off]
        cfg = (toc >> 3) & 0x1F
        if cfg < 12:  # skip SILK-only configs; music uses hybrid/CELT
            continue

        # Check TOC config consistency at slot_size intervals
        total = min(50, (len(data) - test_off) // slot_size)
        if total < 3:
            continue
        consistent = sum(
            1 for n in range(total)
            if ((data[test_off + n * slot_size] >> 3) & 0x1F) == cfg
        )
        if consistent >= total * 0.8 and consistent >= 3:
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
    * Frame sizes are in a reasonable range (2–2000 bytes).
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


def _scan_opus_frames(data: bytes, channels: int = 2,
                      sample_rate: int = 48000) -> bytes:
    """Scan for valid Opus frames by detecting TOC bytes and frame boundaries.

    Opus packets start with a TOC byte. We can validate frames by checking:
    1. TOC byte has valid configuration
    2. The declared frame count is reasonable
    3. Frame data can be consistently extracted
    """
    # Try to find where the first Opus frame starts
    # by looking for patterns that suggest frame data
    for start_offset in range(0, min(256, len(data)), 4):
        if start_offset + 8 > len(data):
            break

        # Check if this could be a length-prefixed frame
        frame_size = struct.unpack_from('<I', data, start_offset)[0]
        if 1 <= frame_size <= 2048 and start_offset + 4 + frame_size <= len(data):
            # Validate that the data after the size looks like an Opus TOC byte
            toc = data[start_offset + 4]
            config = (toc >> 3) & 0x1F
            if config <= 31:  # All configs 0-31 are valid
                # Try to extract frames from this offset
                frames = []
                pos = start_offset
                consecutive_valid = 0

                while pos + 4 <= len(data):
                    fs = struct.unpack_from('<I', data, pos)[0]
                    if fs == 0 or fs > 8192:
                        break
                    if pos + 4 + fs > len(data):
                        break
                    frame_data = data[pos + 4:pos + 4 + fs]
                    frames.append(frame_data)
                    consecutive_valid += 1
                    pos += 4 + fs

                if consecutive_valid >= 10:
                    return _build_ogg_opus_from_frames(
                        frames, channels=channels,
                        sample_rate=sample_rate, pre_skip=312)

                # If variable-length didn't work, try as fixed slots
                if frame_size > 0:
                    # Guess slot sizes based on the first frame
                    for padding in [0, 4, 8, 16]:
                        slot = frame_size + 4 + padding
                        if slot < 8 or slot > 0x1000:
                            continue
                        try:
                            return _extract_opus_fixed_slots(
                                data[start_offset:], slot,
                                channels=channels,
                                sample_rate=sample_rate)
                        except Exception:
                            pass

    raise ValueError("No valid Opus frames found via scanning")


def _extract_opus_fixed_slots(data: bytes, slot_size: int,
                              channels: int = 2,
                              sample_rate: int = 48000) -> bytes:
    """Extract Opus frames from data using fixed-size slots.

    Each slot: u32 actual_frame_size + frame_data + padding to slot_size.
    """
    if slot_size < 8 or slot_size > 0x2000:
        raise ValueError(f"Invalid slot size: {slot_size}")

    frames = []
    pos = 0
    while pos + 4 <= len(data):
        actual_size = struct.unpack_from('<I', data, pos)[0]
        if actual_size == 0:
            # Could be padding, try next slot
            pos += slot_size
            continue
        if actual_size > slot_size or actual_size > 0xFFFF:
            break
        if pos + 4 + actual_size > len(data):
            break
        frames.append(data[pos + 4:pos + 4 + actual_size])
        pos += slot_size

    if len(frames) < 10:
        raise ValueError(f"Too few frames ({len(frames)}) with slot size {slot_size}")

    return _build_ogg_opus_from_frames(frames, channels=channels,
                                       sample_rate=sample_rate, pre_skip=312)


def _raw_opus_frames_to_ogg(data: bytes, channels: int = 2,
                            sample_rate: int = 48000) -> bytes:
    """Convert a sequence of length-prefixed raw Opus frames to OGG Opus.

    Each frame: u32 frame_size + frame_data (frame_size bytes).
    """
    frames = []
    pos = 0
    while pos + 4 <= len(data):
        frame_size = struct.unpack_from('<I', data, pos)[0]
        if frame_size == 0 or frame_size > 0xFFFF:
            break
        if pos + 4 + frame_size > len(data):
            break
        frames.append(data[pos + 4:pos + 4 + frame_size])
        # Advance by 4 + frame_size, no fixed slot padding
        pos += 4 + frame_size

    if not frames:
        # Try with fixed-size frame slots (common in LOPUS)
        # Guess frame slot size from first frame
        pos = 0
        if pos + 4 <= len(data):
            first_size = struct.unpack_from('<I', data, pos)[0]
            if 0 < first_size < 0xFFFF and pos + 4 + first_size <= len(data):
                frames.append(data[pos + 4:pos + 4 + first_size])
                # Estimate slot size: try common sizes
                for slot in [first_size + 4, 0x280, 0x500, 0x200, 0x400]:
                    test_frames = [frames[0]]
                    test_pos = slot
                    valid = True
                    count = 0
                    while test_pos + 4 <= len(data) and count < 5:
                        fs = struct.unpack_from('<I', data, test_pos)[0]
                        if fs == 0 or fs > slot or test_pos + 4 + fs > len(data):
                            valid = False
                            break
                        test_frames.append(data[test_pos + 4:test_pos + 4 + fs])
                        test_pos += slot
                        count += 1
                    if valid and count >= 2:
                        # Confirmed slot size, extract all
                        frames = []
                        p = 0
                        while p + 4 <= len(data):
                            fs = struct.unpack_from('<I', data, p)[0]
                            if fs == 0 or fs > slot:
                                break
                            if p + 4 + fs > len(data):
                                break
                            frames.append(data[p + 4:p + 4 + fs])
                            p += slot
                        break

    if not frames:
        raise ValueError("No Opus frames extracted from raw OPUS data")

    return _build_ogg_opus_from_frames(frames, channels=channels,
                                       sample_rate=sample_rate, pre_skip=312)


def _raw_opus_to_ogg_fallback(data: bytes) -> bytes:
    """Last-resort conversion: treat data as LOPUS with default params."""
    # Construct a synthetic LOPUS header and parse with _lopus_to_ogg
    # This creates a fake 0x80000001 header wrapping the data
    header_size = 0x28
    synthetic = struct.pack('<II', 0x80000001, header_size)
    # Pad to header_size
    synthetic += b'\x00' * (header_size - len(synthetic))
    # Set sample_rate at 0x0C, channel_count at 0x10, frame_size at 0x14
    synthetic = synthetic[:0x0C] + struct.pack('<III', 48000, 2, 640) + synthetic[0x1C:]
    synthetic += data

    return _lopus_to_ogg(synthetic)


def _opus_toc_samples(toc_byte: int) -> int:
    """Derive the number of 48 kHz samples per Opus frame from its TOC byte.

    The top 5 bits of the TOC byte encode the configuration which
    determines the frame duration.  We return the sample count for a
    *single* coded frame.  For code 1/2/3 (multiple frames per packet)
    the sample count is per-sub-frame, but in SSBU LOPUS each packet
    is code-0 so this is fine.

    Reference: RFC 6716 §3.1
    """
    config = (toc_byte >> 3) & 0x1F
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
        return 960  # safe default

    return durations[config % 4]


def _build_ogg_opus_from_frames(opus_frames: list[bytes], channels: int = 2,
                                 sample_rate: int = 48000, pre_skip: int = 312) -> bytes:
    """Build an OGG Opus file from a list of raw Opus frame data."""
    serial = 0x53534255  # "SSBU"
    pages = []

    # Page 0: OpusHead (BOS)
    head_data = _make_opus_head(channels, pre_skip, sample_rate)
    head_segs = _segment_table_for_packet(len(head_data))
    pages.append(_make_ogg_page(head_data, serial, 0, 0, 0x02, head_segs))

    # Page 1: OpusTags
    tags_data = _make_opus_tags()
    tags_segs = _segment_table_for_packet(len(tags_data))
    pages.append(_make_ogg_page(tags_data, serial, 1, 0, 0x00, tags_segs))

    # Determine samples_per_frame from the first valid Opus frame's TOC
    samples_per_frame = 960  # default 20 ms at 48 kHz
    if opus_frames and len(opus_frames[0]) >= 1:
        samples_per_frame = _opus_toc_samples(opus_frames[0][0])

    # Data pages
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

        flags = 0x04 if i >= len(opus_frames) else 0x00
        page_data = b''.join(page_data_parts)
        pages.append(_make_ogg_page(page_data, serial, page_seq, granule, flags, page_segments))
        page_seq += 1

    return b''.join(pages)


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
    from src import __version__
    cache_key = f"{nus3audio_path.stem}_{file_size}_v{__version__}"

    # Check for any cached format (prefer WAV over OGG since pygame handles WAV better)
    for ext in ('.wav', '.ogg'):
        cached = cache_dir / f"{cache_key}{ext}"
        if cached.exists():
            # Validate cached file isn't truncated / corrupt
            try:
                sz = cached.stat().st_size
            except OSError:
                sz = 0
            if ext == '.wav' and sz < 1000:
                # Bad / partial WAV — delete and re-convert
                try:
                    cached.unlink()
                except OSError:
                    pass
                continue
            # If cached file is an OGG Opus, it can't be played by pygame.
            # Try to convert to WAV first, or skip the cache entry.
            if ext == '.ogg':
                try:
                    with open(cached, 'rb') as _f:
                        _hdr = _f.read(48)
                    if b'OpusHead' in _hdr:
                        wav_path = _convert_ogg_opus_to_wav(cached)
                        if wav_path and wav_path.exists():
                            return True, f"Playing: {nus3audio_path.name}", wav_path
                        # ffmpeg not available — skip this cached OGG
                        continue
                except OSError:
                    pass
            return True, f"Playing: {nus3audio_path.name}", cached

    try:
        with open(nus3audio_path, 'rb') as f:
            data = f.read()
    except Exception as e:
        return False, f"Failed to read file: {e}", None

    # Verify NUS3 magic
    if len(data) < 8 or data[:4] != b'NUS3':
        return False, "Not a valid NUS3AUDIO file", None

    # ── Priority 1: let ffmpeg decode the whole NUS3AUDIO file ──
    # Modern ffmpeg (5.0+) has native NUS3AUDIO support and produces
    # clean PCM output, bypassing our manual LOPUS→OGG construction
    # which can introduce distortion.
    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        try:
            wav_out = cache_dir / f"{cache_key}.wav"
            result = subprocess.run(
                [ffmpeg, "-y", "-i", str(nus3audio_path),
                 "-ar", "48000", "-ac", "2", "-sample_fmt", "s16",
                 str(wav_out)],
                capture_output=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0 and wav_out.exists():
                sz = wav_out.stat().st_size
                # Validate: WAV header (44 bytes) + at least 0.1s of audio
                # at 48kHz stereo 16-bit  = 44 + 19200 ≈ 19244 bytes
                if sz > 19000:
                    from src.utils.logger import logger
                    logger.info("NUS3AUDIO",
                                f"ffmpeg decoded NUS3AUDIO directly ({sz} bytes)")
                    return True, f"Playing: {nus3audio_path.name}", wav_out
                # Tiny output — ffmpeg couldn't properly decode; clean up
                try:
                    wav_out.unlink()
                except OSError:
                    pass
        except Exception as e:
            from src.utils.logger import logger
            logger.debug("NUS3AUDIO", f"ffmpeg direct decode failed: {e}")

    # ── Priority 2: manual extraction + per-format conversion ──
    sections = _find_sections(data)

    # Extract audio entries using ADOF if available
    audio_entries = _extract_audio_entries(data, sections)

    if not audio_entries:
        return False, "No audio data found in NUS3AUDIO", None

    # Try the first (usually only) audio entry
    audio_data = audio_entries[0]

    if len(audio_data) < 4:
        return False, "Audio data too short", None

    # Try each format, returning the first successful conversion
    result = _try_convert_audio(audio_data, cache_dir, cache_key, nus3audio_path.name)
    if result[0]:
        return result

    # If first entry failed and there are more, try others
    for i, entry in enumerate(audio_entries[1:], 1):
        if len(entry) < 4:
            continue
        result = _try_convert_audio(entry, cache_dir, f"{cache_key}_{i}", nus3audio_path.name)
        if result[0]:
            return result

    fmt_hex = struct.unpack_from('<I', audio_data, 0)[0]
    fmt_ascii = audio_data[:4].decode('ascii', errors='replace')
    return False, f"Could not convert audio (format: 0x{fmt_hex:08X} / '{fmt_ascii}', size: {len(audio_data)} bytes)", None


def _try_convert_audio(audio_data: bytes, cache_dir: Path, cache_key: str,
                        display_name: str) -> tuple[bool, str, Optional[Path]]:
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

    # LOPUS (Nintendo Opus) — magic starts with 0x80000001..0x80000004
    if len(audio_data) >= 4:
        lopus_magic = struct.unpack_from('<I', audio_data, 0)[0]
        if lopus_magic & 0x80000000:
            try:
                ogg_data = _lopus_to_ogg(audio_data)
                ogg_path = cache_dir / f"{cache_key}.ogg"
                ogg_path.write_bytes(ogg_data)
                # pygame/stb_vorbis can't play OGG Opus — convert to WAV via ffmpeg
                wav_path = _convert_ogg_opus_to_wav(ogg_path)
                if wav_path:
                    return True, f"Playing: {display_name}", wav_path
                # ffmpeg not available — OGG Opus is unplayable by pygame
                from src.utils.logger import logger
                logger.warn("NUS3AUDIO",
                            "Opus audio requires ffmpeg for playback. "
                            "Install ffmpeg and add it to PATH.")
                return False, (
                    "This track uses Opus audio which requires ffmpeg for playback.\n"
                    "Install ffmpeg and add it to PATH."
                ), None
            except Exception as e:
                from src.utils.logger import logger
                logger.warn("NUS3AUDIO", f"LOPUS conversion failed: {e}")
                pass  # Fall through to try other formats

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

    # OPUS raw container (magic "OPUS" = 0x4F505553)
    # Found in some NUS3AUDIO files where audio data starts with "OPUS" header
    if audio_data[:4] == b'OPUS':
        try:
            ogg_data = _opus_container_to_ogg(audio_data)
            ogg_path = cache_dir / f"{cache_key}.ogg"
            ogg_path.write_bytes(ogg_data)
            # pygame/stb_vorbis can't play OGG Opus — convert to WAV via ffmpeg
            wav_path = _convert_ogg_opus_to_wav(ogg_path)
            if wav_path:
                return True, f"Playing: {display_name}", wav_path
            # ffmpeg not available — OGG Opus is unplayable by pygame
            from src.utils.logger import logger
            logger.warn("NUS3AUDIO",
                        "Opus audio requires ffmpeg for playback. "
                        "Install ffmpeg and add it to PATH.")
            return False, (
                "This track uses Opus audio which requires ffmpeg for playback.\n"
                "Install ffmpeg and add it to PATH."
            ), None
        except Exception as e:
            from src.utils.logger import logger
            logger.warn("NUS3AUDIO", f"OPUS container conversion failed: {e}")
            # Fall through to ffmpeg raw fallback

    # --- ffmpeg raw fallback ---
    # If all custom parsers failed, write the raw audio data to a temp
    # file and let ffmpeg try to detect the format and decode it.
    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        try:
            raw_path = cache_dir / f"{cache_key}.raw_opus"
            raw_path.write_bytes(audio_data)
            wav_out = cache_dir / f"{cache_key}.wav"
            result = subprocess.run(
                [ffmpeg, "-y", "-i", str(raw_path), "-ar", "48000",
                 "-ac", "2", "-sample_fmt", "s16", str(wav_out)],
                capture_output=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0 and wav_out.exists() and wav_out.stat().st_size > 1000:
                try:
                    raw_path.unlink()
                except OSError:
                    pass
                return True, f"Playing: {display_name}", wav_out
            # Clean up failed attempt
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

    return False, f"Unsupported audio format", None


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
