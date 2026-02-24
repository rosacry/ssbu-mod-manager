"""Regression tests for CBR LOPUS trailer handling."""

import unittest

from src.utils.nus3audio import _extract_opus_cbr_frames


def _make_slot(slot_size: int, payload: bytes, declared_len: int) -> bytes:
    slot = bytearray(slot_size)
    slot[: len(payload)] = payload
    slot[-8:-4] = int(declared_len).to_bytes(4, "big", signed=False)
    slot[-4:] = b"\x00\x00\x00\x00"
    return bytes(slot)


class CBRTrailerTrimTests(unittest.TestCase):
    def test_trailer_trim_applied_when_pattern_is_consistent(self):
        slot_size = 64
        payload_len = 56  # slot_size - 8 trailer
        frame_count = 24

        expected_payloads = []
        blob_parts = []
        for i in range(frame_count):
            payload = bytes([0xFC]) + bytes(((i + j) & 0xFF) for j in range(payload_len - 1))
            expected_payloads.append(payload)
            blob_parts.append(_make_slot(slot_size, payload, declared_len=payload_len))

        data = b"".join(blob_parts)
        frames = _extract_opus_cbr_frames(data, slot_size=slot_size, search_start=0)

        self.assertEqual(len(frames), frame_count)
        self.assertTrue(all(len(fr) == payload_len for fr in frames))
        self.assertEqual(frames, expected_payloads)

    def test_no_trim_without_majority_trailer_pattern(self):
        slot_size = 64
        payload_len = 56
        frame_count = 20

        blob_parts = []
        for i in range(frame_count):
            payload = bytes([0xFC]) + bytes(((i * 3 + j) & 0xFF) for j in range(payload_len - 1))
            declared = payload_len if i < 6 else 0  # below trim majority threshold
            blob_parts.append(_make_slot(slot_size, payload, declared_len=declared))

        data = b"".join(blob_parts)
        frames = _extract_opus_cbr_frames(data, slot_size=slot_size, search_start=0)

        self.assertEqual(len(frames), frame_count)
        self.assertTrue(all(len(fr) == slot_size for fr in frames))


if __name__ == "__main__":
    unittest.main()
