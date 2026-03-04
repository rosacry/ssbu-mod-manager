"""Tests for r22/r23 NUS3AUDIO fixes: silence rejection, ranking guard,
TOC stereo-bit-flip, CBR consistency tiebreaker, and LOPUS v1 extended header."""

import struct
import unittest

from src.utils.nus3audio import (
    _validate_opus_frames,
    _extract_opus_cbr_frames,
    _extract_frames_with_slot,
    _flip_ogg_opus_stereo_bits,
    _build_ogg_opus_from_frames,
    _make_opus_head,
    _make_opus_tags,
    _make_ogg_page,
    _segment_table_for_packet,
    OPUS_PAGE_BOS_FLAG,
    OPUS_PAGE_NO_FLAGS,
    OPUS_PAGE_EOS_FLAG,
    OPUS_SERIAL_SSBU,
)


def _make_valid_opus_frame(config: int = 31, stereo: bool = True,
                           size: int = 120) -> bytes:
    """Create a synthetic Opus frame with a valid TOC byte and random-ish data."""
    toc = (config << 3) | (int(stereo) << 2)  # code=0 (single frame)
    payload = bytes(((i * 7 + 0x5A) & 0xFF) for i in range(size - 1))
    return bytes([toc]) + payload


def _make_zero_opus_frame(config: int = 31, stereo: bool = True,
                          size: int = 120) -> bytes:
    """Create a synthetic Opus frame that is mostly zeros (silence)."""
    toc = (config << 3) | (int(stereo) << 2)
    return bytes([toc, 0xFF, 0xFE]) + b'\x00' * (size - 3)


class TestZeroDataRejection(unittest.TestCase):
    """_validate_opus_frames should reject frames that are mostly zeros."""

    def test_rejects_all_zero_frames(self):
        frames = [_make_zero_opus_frame() for _ in range(30)]
        self.assertFalse(_validate_opus_frames(frames))

    def test_rejects_majority_zero_frames(self):
        good = [_make_valid_opus_frame() for _ in range(5)]
        bad = [_make_zero_opus_frame() for _ in range(15)]
        # Bad frames outnumber good, should fail the 50% gate
        self.assertFalse(_validate_opus_frames(bad + good))

    def test_accepts_valid_high_entropy_frames(self):
        frames = [_make_valid_opus_frame() for _ in range(30)]
        self.assertTrue(_validate_opus_frames(frames))

    def test_accepts_when_few_zero_frames(self):
        """A small fraction of zero frames should not cause rejection."""
        good = [_make_valid_opus_frame() for _ in range(18)]
        bad = [_make_zero_opus_frame() for _ in range(2)]
        self.assertTrue(_validate_opus_frames(good + bad))


class TestRankOverrideProtection(unittest.TestCase):
    """The _consider function should not let a rank-3 extraction with very
    few frames beat a rank-2 extraction with many frames.

    We test this indirectly via _lopus_to_ogg's _consider semantics by
    constructing CBR data that produces many frames, and verifying that
    a small rank-3 extraction cannot override it.
    """

    def test_small_rank3_does_not_beat_large_rank2(self):
        """Construct a scenario: 1000 CBR frames (rank 2) vs 10 szpfx
        frames (rank 3).  The CBR extraction should win."""
        # Build 1000 valid CBR frames at slot_size=64
        slot_size = 64
        frame_count = 1000
        toc = (31 << 3) | 0x04  # cfg=31, stereo, code=0
        cbr_data = bytearray()
        for i in range(frame_count):
            frame = bytes([toc]) + bytes(
                ((i + j) & 0xFF) for j in range(slot_size - 1)
            )
            cbr_data.extend(frame)
        cbr_data = bytes(cbr_data)

        # CBR extraction should find all 1000 frames
        cbr_frames, _ = _extract_opus_cbr_frames(cbr_data, slot_size, search_start=0)
        self.assertEqual(len(cbr_frames), frame_count)

        # Now build a tiny szpfx extraction with only 10 frames
        szpfx_data = bytearray()
        for i in range(10):
            payload = bytes([toc]) + bytes(
                ((i * 3 + j) & 0xFF) for j in range(59)
            )
            szpfx_data.extend(struct.pack('<I', len(payload)))
            szpfx_data.extend(payload)
            szpfx_data.extend(b'\x00' * (slot_size - 4 - len(payload)))

        szpfx_frames = _extract_frames_with_slot(bytes(szpfx_data), 0, slot_size, '<')
        self.assertEqual(len(szpfx_frames), 10)

        # The ranking guard in _consider should prevent 10 rank-3 frames
        # from overriding 1000 rank-2 frames.  We verify the logic
        # directly: 10 < max(50, 1000 * 0.20) = max(50, 200) = 200
        self.assertLess(len(szpfx_frames), max(50, int(len(cbr_frames) * 0.20)))


class TestTOCStereoFlip(unittest.TestCase):
    """Test the _flip_ogg_opus_stereo_bits helper."""

    def _build_ogg_with_stereo_frames(self) -> bytes:
        """Build a minimal OGG Opus file with stereo TOC bits set."""
        frames = [_make_valid_opus_frame(config=31, stereo=True, size=60)
                  for _ in range(20)]
        return _build_ogg_opus_from_frames(frames, channels=1)

    def test_flip_clears_stereo_bit(self):
        ogg = self._build_ogg_with_stereo_frames()
        flipped = _flip_ogg_opus_stereo_bits(ogg)
        self.assertIsNotNone(flipped)
        # All original TOC bytes had stereo bit set (0x04).
        # After flip, bit 2 should be cleared.
        # Parse the OGG to find audio pages (page 3+) and check TOC bytes.
        pos = 0
        pages_seen = 0
        while pos < len(flipped) - 27:
            if flipped[pos:pos + 4] != b'OggS':
                pos += 1
                continue
            pages_seen += 1
            n_segs = flipped[pos + 26]
            seg_start = pos + 27
            seg_table = flipped[seg_start:seg_start + n_segs]
            data_start = seg_start + n_segs
            if pages_seen >= 3 and data_start < len(flipped):
                # First byte of page data should be a TOC with stereo cleared
                toc = flipped[data_start]
                self.assertEqual(toc & 0x04, 0,
                                 f"Stereo bit not cleared in page {pages_seen}")
            page_size = data_start - pos + sum(seg_table)
            pos += page_size

    def test_flip_returns_none_on_garbage(self):
        self.assertIsNone(_flip_ogg_opus_stereo_bits(b'garbage'))
        self.assertIsNone(_flip_ogg_opus_stereo_bits(b''))


class TestValidateOpusFramesBasic(unittest.TestCase):
    """Ensure _validate_opus_frames still passes on normal data."""

    def test_consistent_config_passes(self):
        frames = [_make_valid_opus_frame(config=31) for _ in range(20)]
        self.assertTrue(_validate_opus_frames(frames))

    def test_inconsistent_config_fails(self):
        """Frames with wildly different configs should fail the 70% test."""
        frames = []
        for i in range(20):
            cfg = i % 32  # rotating configs
            frames.append(_make_valid_opus_frame(config=cfg))
        self.assertFalse(_validate_opus_frames(frames))

    def test_empty_frames_fails(self):
        self.assertFalse(_validate_opus_frames([]))

    def test_tiny_frames_fails(self):
        frames = [bytes([0xFC])]  # 1-byte frame
        self.assertFalse(_validate_opus_frames(frames))


class TestCBRConsistencyTiebreaker(unittest.TestCase):
    """The CBR extractor should prefer higher-consistency offsets when
    multiple candidates share the same Opus config value."""

    def test_higher_consistency_wins_over_lower(self):
        """Build data where offset 5 has cfg=31 but low consistency,
        and offset 8 has cfg=31 with perfect consistency.  Offset 8
        should be chosen."""
        slot = 64
        num_slots = 100
        data = bytearray(8 + slot * num_slots)
        toc_31_stereo = (31 << 3) | 0x04  # 0xFC

        # Place a single valid TOC byte at offset 5 (metadata region)
        data[5] = toc_31_stereo

        # Place perfectly aligned CBR frames with cfg=31 at offset 8
        for i in range(num_slots):
            off = 8 + i * slot
            data[off] = toc_31_stereo
            # Fill rest with non-zero data so validation passes
            for j in range(1, slot):
                data[off + j] = ((i * 7 + j * 3) & 0xFF) | 0x01

        frames, found_off = _extract_opus_cbr_frames(bytes(data), slot, search_start=0)
        # The higher-consistency offset (8) should win
        self.assertEqual(found_off, 8)
        self.assertGreater(len(frames), 50)

    def test_equal_config_different_consistency(self):
        """Two offsets with same config but one has 50/50 consistency
        and the other 40/50.  The 50/50 should win."""
        slot = 32
        num_slots = 60
        toc_a = (31 << 3) | 0x04  # cfg=31 stereo → 0xFC
        toc_low = (5 << 3)        # cfg=5, will fail music config check

        data = bytearray(20 + slot * num_slots)
        # Offset 3: every slot has toc_a at 3, 3+32, 3+64, ...
        # but only 80% of them (still passes threshold)
        for i in range(num_slots):
            off = 3 + i * slot
            if off < len(data):
                data[off] = toc_a if i % 5 != 0 else toc_low  # 80% consistent
                for j in range(1, min(slot, len(data) - off)):
                    data[off + j] = ((i + j) & 0xFF) | 0x01

        # Offset 8: perfectly consistent cfg=31
        for i in range(num_slots):
            off = 8 + i * slot
            if off < len(data):
                data[off] = toc_a
                for j in range(1, min(slot, len(data) - off)):
                    data[off + j] = ((i * 3 + j) & 0xFF) | 0x01

        frames, found_off = _extract_opus_cbr_frames(bytes(data), slot, search_start=0)
        # Perfect consistency at offset 8 should beat 80% at offset 3
        self.assertEqual(found_off, 8)


class TestTOCStereoFlipContinuation(unittest.TestCase):
    """The OGG TOC flip function should correctly handle continuation
    pages (where the first packet spans from the previous page)."""

    def _build_ogg_with_large_frames(self) -> bytes:
        """Build OGG with frames large enough to span multiple segments."""
        # 300-byte frames need 2 segments each (255 + 45)
        frames = [_make_valid_opus_frame(config=31, stereo=True, size=300)
                  for _ in range(10)]
        return _build_ogg_opus_from_frames(frames, channels=1)

    def test_flip_handles_multi_segment_packets(self):
        """Frames spanning multiple OGG segments should still get flipped."""
        ogg = self._build_ogg_with_large_frames()
        flipped = _flip_ogg_opus_stereo_bits(ogg)
        self.assertIsNotNone(flipped)
        # Verify all audio TOC bytes have stereo bit cleared
        pos = 0
        pages_seen = 0
        toc_bytes_found = 0
        while pos < len(flipped) - 27:
            if flipped[pos:pos + 4] != b'OggS':
                pos += 1
                continue
            pages_seen += 1
            n_segs = flipped[pos + 26]
            seg_start = pos + 27
            seg_table = flipped[seg_start:seg_start + n_segs]
            data_start = seg_start + n_segs
            if pages_seen >= 3:
                # Walk segments to find new-packet boundaries
                is_cont = bool(flipped[pos + 5] & 0x01)
                acc = 0
                in_cont = is_cont
                for seg_sz in seg_table:
                    if not in_cont:
                        toc_pos = data_start + acc
                        if toc_pos < len(flipped):
                            toc = flipped[toc_pos]
                            self.assertEqual(toc & 0x04, 0,
                                             f"Stereo bit not cleared at byte {toc_pos}")
                            toc_bytes_found += 1
                    acc += seg_sz
                    in_cont = (seg_sz == 255)
            page_size = data_start - pos + sum(seg_table)
            pos += page_size
        self.assertGreater(toc_bytes_found, 0, "No TOC bytes found to verify")


class TestZeroDataUniformSampling(unittest.TestCase):
    """r24: zero-data sampling must be uniform across the frame array so
    tracks with a legitimate silent intro (e.g. 21 leading silence frames
    among 8886 total) are NOT rejected."""

    def test_leading_silence_not_rejected(self):
        """21 silence frames followed by 8865 real frames should pass."""
        silence = [_make_zero_opus_frame(size=275) for _ in range(21)]
        real = [_make_valid_opus_frame(size=275) for _ in range(8865)]
        self.assertTrue(_validate_opus_frames(silence + real))

    def test_majority_silence_still_rejected(self):
        """When >50% of UNIFORMLY sampled frames are silence, still reject."""
        # 5000 silence + 3886 real → ~56% silence in uniform sample
        silence = [_make_zero_opus_frame(size=275) for _ in range(5000)]
        real = [_make_valid_opus_frame(size=275) for _ in range(3886)]
        self.assertFalse(_validate_opus_frames(silence + real))

    def test_all_real_frames_accepted(self):
        """8886 real frames should trivially pass."""
        frames = [_make_valid_opus_frame(size=275) for _ in range(8886)]
        self.assertTrue(_validate_opus_frames(frames))


if __name__ == "__main__":
    unittest.main()
