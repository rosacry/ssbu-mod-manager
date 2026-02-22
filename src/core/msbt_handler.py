"""Wrapper around pylibms (LMS) for MSBT operations."""
from pathlib import Path
from typing import Any, Optional
from LMS.Message.MSBT import MSBT
from LMS.Stream.Reader import Reader
from LMS.Stream.Writer import Writer
import io


class MSBTHandler:
    def load(self, path: Path) -> MSBT:
        """Load an MSBT file."""
        with open(path, 'rb') as f:
            data = f.read()
        msbt = MSBT()
        reader = Reader(data)
        msbt.read(reader)
        return msbt

    def save(self, msbt: MSBT, path: Path) -> None:
        """Save an MSBT file."""
        buffer = io.BytesIO()
        writer = Writer(buffer)
        msbt.write(writer)
        with open(path, 'wb') as f:
            f.write(buffer.getvalue())

    def get_entry(self, msbt: MSBT, label: str) -> Optional[str]:
        """Get a text entry by label. Returns None if not found."""
        try:
            index = msbt.LBL1.get_index_by_label(label)
            if index is not None and index < len(msbt.TXT2.messages):
                return msbt.TXT2.messages[index]
        except (KeyError, IndexError, Exception):
            pass
        return None

    def set_entry(self, msbt: MSBT, label: str, text: str) -> None:
        """Set an MSBT entry, creating it if it doesn't exist."""
        try:
            index = msbt.LBL1.get_index_by_label(label)
            if index is not None and index < len(msbt.TXT2.messages):
                msbt.TXT2.messages[index] = text
                return
        except (KeyError, Exception):
            pass
        # Label doesn't exist, add it
        try:
            msbt.add_data(label)
            # The new entry is at the end of messages
            msbt.TXT2.messages[-1] = text
        except Exception as e:
            from src.utils.logger import logger
            logger.warn("MSBT", f"Failed to add entry '{label}': {e}")
