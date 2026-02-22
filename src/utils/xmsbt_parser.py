"""Parser for XMSBT files (XML-based MSBT overlay format used by ARCropolis).

Also handles conversion of binary MSBT files to XMSBT overlay format
for emulators that don't support binary MSBT replacement.
"""
import re
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape as xml_escape
from src.utils.logger import logger


def extract_entries_from_msbt(msbt_path: Path) -> dict[str, str]:
    """Extract all text entries from a binary MSBT file.

    Returns a dict of {label: text} compatible with XMSBT format.
    Only includes entries that contain printable text.
    """
    entries = {}
    try:
        from LMS.Message.MSBT import MSBT
        from LMS.Stream.Reader import Reader

        with open(msbt_path, 'rb') as f:
            data = f.read()

        msbt = MSBT()
        reader = Reader(data)
        msbt.read(reader)

        # labels is a dict: {int_index: str_label_name}
        for idx, label_name in msbt.LBL1.labels.items():
            if not isinstance(label_name, str):
                continue
            if idx >= len(msbt.TXT2.messages):
                continue
            msg = msbt.TXT2.messages[idx]
            text = ''.join(c for c in str(msg) if c.isprintable())
            if text:
                entries[label_name] = text

        logger.info("XMSBT", f"Extracted {len(entries)} entries from {msbt_path.name}")
    except ImportError:
        logger.warn("XMSBT", "pylibms (LMS) not installed - cannot parse binary MSBT files")
    except Exception as e:
        logger.warn("XMSBT", f"Failed to parse MSBT {msbt_path.name}: {e}")
    return entries


def filter_custom_entries(entries: dict[str, str]) -> dict[str, str]:
    """Filter entries to keep only custom (mod-added) ones.

    Custom entries typically have alphanumeric label suffixes (e.g.
    bgm_title_25AR) while vanilla entries use purely numeric suffixes
    (e.g. bgm_title_0001).  A generic catch-all also handles labels
    whose numeric suffix exceeds 1605 (the vanilla BGM ceiling in SSBU
    v13.0.1).
    """
    custom = {}
    for label, text in entries.items():
        parts = label.rsplit('_', 1)
        if len(parts) < 2:
            continue
        suffix = parts[-1]
        # Keep entries with any alphabetic character in the suffix
        if re.search(r'[A-Za-z]', suffix):
            custom[label] = text
            continue
        # Keep entries with very high numeric IDs (likely custom)
        try:
            if int(suffix) > 1605:
                custom[label] = text
        except ValueError:
            custom[label] = text
    return custom

def parse_xmsbt(file_path: Path) -> dict[str, str]:
    """Parse an XMSBT file and return a dict of label -> text."""
    entries = {}
    try:
        # Try UTF-16 first (most common for XMSBT)
        try:
            with open(file_path, 'r', encoding='utf-16') as f:
                content = f.read()
        except (UnicodeError, UnicodeDecodeError):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

        # Parse <entry label="..."><text>...</text></entry> blocks
        pattern = r'<entry\s+label="([^"]+)">\s*<text>(.*?)</text>\s*</entry>'
        for match in re.finditer(pattern, content, re.DOTALL):
            label = match.group(1)
            text = match.group(2).strip()
            entries[label] = text
    except Exception as e:
        logger.warn("XMSBT", f"Failed to parse {file_path.name}: {e}")
    return entries

def write_xmsbt(file_path: Path, entries: dict[str, str]) -> None:
    """Write entries to an XMSBT file.

    Text values are written as-is (not XML-escaped) to preserve any
    inline formatting tags the game may use. Only label attributes
    are escaped to keep the XML structure valid.
    """
    lines = ['<?xml version="1.0" encoding="utf-16"?>', '<xmsbt>']
    for label, text in sorted(entries.items()):
        safe_label = xml_escape(label, {'"': '&quot;'})
        # Do NOT escape text content - XMSBT text values can contain
        # game-specific inline tags and entities that must be preserved
        lines.append(f'  <entry label="{safe_label}">')
        lines.append(f'    <text>{text}</text>')
        lines.append('  </entry>')
    lines.append('</xmsbt>')

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-16') as f:
            f.write('\n'.join(lines))
    except OSError as e:
        logger.error("XMSBT", f"Failed to write {file_path}: {e}")
        raise

def merge_xmsbt_files(file_paths: list[Path]) -> tuple[dict[str, str], set[str]]:
    """
    Merge multiple XMSBT files. Returns (merged_entries, overlapping_labels).
    overlapping_labels contains labels that appear in multiple files with different values.
    """
    merged = {}
    seen_labels = {}  # label -> (first_value, first_file)
    overlapping = set()

    for fpath in file_paths:
        entries = parse_xmsbt(fpath)
        for label, text in entries.items():
            if label in seen_labels:
                if seen_labels[label][0] != text:
                    overlapping.add(label)
            else:
                seen_labels[label] = (text, str(fpath))
            merged[label] = text  # Last file wins for overlapping

    return merged, overlapping

def diff_xmsbt(file_a: Path, file_b: Path) -> dict:
    """Compare two XMSBT files and return differences."""
    entries_a = parse_xmsbt(file_a)
    entries_b = parse_xmsbt(file_b)

    all_labels = set(entries_a.keys()) | set(entries_b.keys())

    only_in_a = {l: entries_a[l] for l in all_labels if l in entries_a and l not in entries_b}
    only_in_b = {l: entries_b[l] for l in all_labels if l in entries_b and l not in entries_a}
    different = {l: (entries_a[l], entries_b[l]) for l in all_labels
                 if l in entries_a and l in entries_b and entries_a[l] != entries_b[l]}

    return {
        "only_in_a": only_in_a,
        "only_in_b": only_in_b,
        "different": different,
        "common_count": len(all_labels) - len(only_in_a) - len(only_in_b) - len(different)
    }
