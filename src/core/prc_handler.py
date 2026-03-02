"""Wrapper around pyprc for common PRC operations."""
from pathlib import Path
from typing import Any, Optional

try:
    import pyprc
    _pyprc_available = True
except ImportError:
    pyprc = None
    _pyprc_available = False

SIGNED_BYTE_MAX = 127
UNSIGNED_BYTE_RANGE = 256


class PRCHandler:
    def load(self, path: Path) -> Any:
        """Load a PRC file and return the parsed param object."""
        if not _pyprc_available:
            raise ImportError("pyprc is not installed. Install with: pip install pyprc")
        return pyprc.param(str(path))

    def save(self, prc_root: Any, path: Path) -> None:
        """Save a PRC object to file."""
        prc_root.save(str(path))

    def get_db_root(self, prc_root: Any) -> Any:
        """Get the database root (first element) from a PRC file."""
        return list(prc_root)[0][1]

    def clone_entry(self, entry: Any) -> Any:
        """Clone a PRC entry."""
        return entry.clone()

    def safe_set_value(self, ref: Any, field: str, value: int) -> None:
        """Set an integer value on a PRC field, handling signed byte overflow."""
        try:
            ref[field].value = value
        except Exception as e:
            if "out of range" in str(e).lower():
                if value > SIGNED_BYTE_MAX:
                    ref[field].value = value - UNSIGNED_BYTE_RANGE
                elif value < 0:
                    ref[field].value = value + UNSIGNED_BYTE_RANGE

    def set_hash_value(self, ref: Any, field: str, value: str) -> None:
        """Set a hash40 value on a PRC field."""
        if not _pyprc_available:
            raise ImportError("pyprc is not installed")
        if value.startswith("0x"):
            ref[field].value = pyprc.hash(int(value, 16))
        else:
            ref[field].value = pyprc.hash(value)

    def get_field_str(self, ref: Any, field: str) -> str:
        """Get a field value as string."""
        try:
            return str(ref[field].value)
        except (KeyError, AttributeError):
            return ""

    def get_field_int(self, ref: Any, field: str, default: int = 0) -> int:
        """Get a field value as int."""
        try:
            return ref[field].value
        except (KeyError, AttributeError):
            return default
