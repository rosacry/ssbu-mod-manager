"""Online compatibility checker for gameplay-affecting SSBU setup data."""

from __future__ import annotations

import base64
import hashlib
import json
import zlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from src.core.desync_classifier import (
    is_gameplay_affecting_mod_file,
    is_gameplay_affecting_plugin,
    is_plugin_optional,
)
from src.utils.logger import logger

COMPAT_CODE_PREFIX_V2 = "SSBU-COMPAT-v2:"
COMPAT_CODE_PREFIX_V3 = "SSBU-COMPAT-v3:"
GAMEPLAY_KEY_VARIANT_SEPARATOR = "::"

FILE_HASH_CHUNK_SIZE = 65_536
DIGEST_HEX_LENGTH = 32

# ExeFS files that indicate framework-level hooks.
EXEFS_GAMEPLAY_FILES = frozenset({"subsdk9", "subsdk0", "main.npdm"})


@dataclass
class CompatFingerprint:
    """Gameplay compatibility fingerprint."""

    version: int = 3
    app_version: str = ""
    timestamp: str = ""
    emulator: str = ""
    emulator_version: str = ""
    game_version: str = ""
    strict_audio_sync: bool = False
    strict_environment_match: bool = False
    gameplay_hashes: dict[str, str] = field(default_factory=dict)
    plugin_hashes: dict[str, str] = field(default_factory=dict)
    optional_plugins: list[str] = field(default_factory=list)
    exefs_hashes: dict[str, str] = field(default_factory=dict)
    gameplay_mod_names: list[str] = field(default_factory=list)
    digest: str = ""

    def compute_digest(self) -> str:
        """Compute deterministic digest over gameplay-relevant data."""
        h = hashlib.sha256()
        for key in sorted(self.gameplay_hashes.keys()):
            h.update(key.encode("utf-8"))
            h.update(self.gameplay_hashes[key].encode("utf-8"))
        for key in sorted(self.plugin_hashes.keys()):
            h.update(key.encode("utf-8"))
            h.update(self.plugin_hashes[key].encode("utf-8"))
        for key in sorted(self.exefs_hashes.keys()):
            h.update(key.encode("utf-8"))
            h.update(self.exefs_hashes[key].encode("utf-8"))
        # Include environment metadata in digest so "quick equal" stays valid.
        h.update(self.emulator.encode("utf-8"))
        h.update(self.emulator_version.encode("utf-8"))
        h.update(self.game_version.encode("utf-8"))
        h.update(b"1" if self.strict_audio_sync else b"0")
        h.update(b"1" if self.strict_environment_match else b"0")
        self.digest = h.hexdigest()[:DIGEST_HEX_LENGTH]
        return self.digest


@dataclass
class CompatResult:
    """Result of comparing local setup against reference setup."""

    compatible: bool = True
    missing_gameplay: list[str] = field(default_factory=list)
    extra_gameplay: list[str] = field(default_factory=list)
    mismatched_gameplay: list[str] = field(default_factory=list)
    missing_plugins: list[str] = field(default_factory=list)
    extra_plugins: list[str] = field(default_factory=list)
    mismatched_plugins: list[str] = field(default_factory=list)
    optional_only_local: list[str] = field(default_factory=list)
    optional_only_remote: list[str] = field(default_factory=list)
    mismatched_exefs: list[str] = field(default_factory=list)
    environment_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def issue_count(self) -> int:
        return (
            len(self.environment_issues)
            + len(self.missing_gameplay)
            + len(self.extra_gameplay)
            + len(self.mismatched_gameplay)
            + len(self.missing_plugins)
            + len(self.extra_plugins)
            + len(self.mismatched_plugins)
            + len(self.mismatched_exefs)
        )


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(FILE_HASH_CHUNK_SIZE), b""):
                h.update(chunk)
    except (OSError, PermissionError):
        return "error"
    return h.hexdigest()


def _display_gameplay_key(key: str) -> str:
    """Strip v3 duplicate-key suffix for user-facing display."""
    if GAMEPLAY_KEY_VARIANT_SEPARATOR in key:
        base, _sep, tail = key.rpartition(GAMEPLAY_KEY_VARIANT_SEPARATOR)
        if tail.isdigit():
            return f"{base} (variant {tail})"
    return key


def _add_unique(target: list[str], value: str) -> None:
    if value not in target:
        target.append(value)


def _add_grouped_gameplay_hashes(
    grouped_hashes: dict[str, list[str]],
    target: dict[str, str],
) -> None:
    """Expand grouped gameplay hashes with collision-safe deterministic keys.

    v2 used one key per relative path, which overwrote duplicates.
    v3 keeps deterministic variants for duplicate relative-path providers.
    """
    for rel in sorted(grouped_hashes.keys()):
        hashes = sorted(grouped_hashes[rel])
        if len(hashes) == 1:
            target[rel] = hashes[0]
            continue
        for idx, h in enumerate(hashes, start=1):
            target[f"{rel}{GAMEPLAY_KEY_VARIANT_SEPARATOR}{idx}"] = h


def _compare_environment(
    local: CompatFingerprint,
    reference: CompatFingerprint,
    result: CompatResult,
) -> None:
    if reference.strict_environment_match:
        missing_host_fields: list[str] = []
        if not reference.emulator:
            missing_host_fields.append("emulator")
        if not reference.emulator_version:
            missing_host_fields.append("emulator version")
        if not reference.game_version:
            missing_host_fields.append("game version")
        if missing_host_fields:
            result.warnings.append(
                "Host enabled strict environment mode but code is missing: "
                + ", ".join(missing_host_fields)
                + "."
            )

    if reference.strict_environment_match != local.strict_environment_match:
        result.environment_issues.append(
            "Compatibility policy mismatch: strict environment setting differs between host and local scan."
        )

    if reference.strict_audio_sync != local.strict_audio_sync:
        result.environment_issues.append(
            "Compatibility policy mismatch: strict audio sync setting differs between host and local scan."
        )

    if reference.emulator and local.emulator:
        if reference.emulator != local.emulator:
            result.environment_issues.append(
                f"Emulator mismatch: you use {local.emulator}, host uses {reference.emulator}."
            )
    elif reference.emulator and not local.emulator:
        if reference.strict_environment_match:
            result.environment_issues.append(
                f"Host emulator is {reference.emulator}, but your emulator metadata is missing."
            )
        else:
            result.warnings.append(
                f"Host emulator is {reference.emulator}, but your emulator is unknown."
            )
    elif local.emulator and not reference.emulator:
        result.warnings.append(
            f"Your emulator is {local.emulator}, but host emulator metadata is missing."
        )

    if reference.emulator_version and local.emulator_version:
        if reference.emulator_version != local.emulator_version:
            result.environment_issues.append(
                "Emulator build/version mismatch between host and local setup."
            )
    elif reference.emulator_version and not local.emulator_version:
        if reference.strict_environment_match:
            result.environment_issues.append(
                "Host provided emulator version, but local emulator version metadata is missing."
            )
        else:
            result.warnings.append(
                "Host provided emulator version, but local version is unknown."
            )

    if reference.game_version and local.game_version:
        if reference.game_version != local.game_version:
            result.environment_issues.append(
                f"Game update mismatch: you use {local.game_version}, host uses {reference.game_version}."
            )
    elif reference.game_version and not local.game_version:
        if reference.strict_environment_match:
            result.environment_issues.append(
                "Host provided game version, but local game version metadata is missing."
            )
        else:
            result.warnings.append(
                "Host provided game version, but local game version is unknown."
            )


def generate_fingerprint(
    mods_path: Path,
    plugins_path: Optional[Path] = None,
    exefs_path: Optional[Path] = None,
    emulator_name: str = "",
    emulator_version: str = "",
    game_version: str = "",
    strict_audio_sync: bool = False,
    strict_environment_match: bool = False,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> CompatFingerprint:
    """Generate a gameplay fingerprint from current local setup."""
    from datetime import datetime

    from src import __version__

    fp = CompatFingerprint(
        app_version=__version__,
        timestamp=datetime.now().isoformat(timespec="seconds"),
        emulator=emulator_name,
        emulator_version=emulator_version,
        game_version=game_version,
        strict_audio_sync=bool(strict_audio_sync),
        strict_environment_match=bool(strict_environment_match),
    )

    if progress_callback:
        progress_callback("Scanning mods for gameplay files...", 0.0)

    gameplay_mods = set()
    grouped_hashes: dict[str, list[str]] = defaultdict(list)

    if mods_path and mods_path.exists():
        try:
            mod_folders = [
                f
                for f in sorted(mods_path.iterdir())
                if f.is_dir() and not f.name.startswith(".") and not f.name.startswith("_")
            ]
        except OSError:
            mod_folders = []

        total_mods = len(mod_folders) or 1
        for idx, mod_folder in enumerate(mod_folders):
            if progress_callback:
                progress_callback(f"Scanning: {mod_folder.name}", 0.1 + 0.5 * idx / total_mods)

            try:
                for fpath in mod_folder.rglob("*"):
                    if not fpath.is_file():
                        continue
                    rel = str(fpath.relative_to(mod_folder)).replace("\\", "/")
                    if is_gameplay_affecting_mod_file(rel, strict_audio_sync=strict_audio_sync):
                        grouped_hashes[rel].append(_hash_file(fpath))
                        gameplay_mods.add(mod_folder.name)
            except (PermissionError, OSError):
                continue

    _add_grouped_gameplay_hashes(grouped_hashes, fp.gameplay_hashes)
    fp.gameplay_mod_names = sorted(gameplay_mods)

    if progress_callback:
        progress_callback("Scanning plugins...", 0.65)

    if plugins_path and plugins_path.exists():
        try:
            for fpath in sorted(plugins_path.iterdir()):
                if not fpath.is_file() or not fpath.name.endswith(".nro"):
                    continue
                if is_plugin_optional(fpath.name):
                    fp.optional_plugins.append(fpath.name)
                elif is_gameplay_affecting_plugin(fpath.name):
                    fp.plugin_hashes[fpath.name] = _hash_file(fpath)
        except (PermissionError, OSError):
            pass

    fp.optional_plugins = sorted(set(fp.optional_plugins))

    if progress_callback:
        progress_callback("Scanning ExeFS...", 0.80)

    if exefs_path and exefs_path.exists():
        try:
            for fpath in sorted(exefs_path.iterdir()):
                if not fpath.is_file():
                    continue
                fname_lower = fpath.name.lower()
                if any(fname_lower.startswith(marker) for marker in EXEFS_GAMEPLAY_FILES):
                    fp.exefs_hashes[fpath.name] = _hash_file(fpath)
        except (PermissionError, OSError):
            pass

    fp.compute_digest()

    if progress_callback:
        progress_callback("Fingerprint complete!", 1.0)

    logger.info(
        "CompatChecker",
        f"Generated fingerprint: {len(fp.gameplay_hashes)} gameplay files, "
        f"{len(fp.plugin_hashes)} plugins, {len(fp.exefs_hashes)} exefs, "
        f"strict_audio_sync={fp.strict_audio_sync}, "
        f"strict_environment_match={fp.strict_environment_match}, digest={fp.digest}",
    )

    return fp


def encode_fingerprint(fp: CompatFingerprint) -> str:
    """Encode a fingerprint into compact shareable string."""
    data = {
        "v": fp.version,
        "av": fp.app_version,
        "ts": fp.timestamp,
        "em": fp.emulator,
        "ev": fp.emulator_version,
        "gv": fp.game_version,
        "sa": bool(fp.strict_audio_sync),
        "se": bool(fp.strict_environment_match),
        "gh": fp.gameplay_hashes,
        "ph": fp.plugin_hashes,
        "op": fp.optional_plugins,
        "eh": fp.exefs_hashes,
        "gm": fp.gameplay_mod_names,
        "d": fp.digest,
    }
    payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(payload, level=9)
    b64 = base64.urlsafe_b64encode(compressed).decode("ascii")
    return f"{COMPAT_CODE_PREFIX_V3}{b64}"


def decode_fingerprint(code: str) -> Optional[CompatFingerprint]:
    """Decode v2/v3 compatibility code."""
    code = code.strip()
    prefix = ""
    if code.startswith(COMPAT_CODE_PREFIX_V3):
        prefix = COMPAT_CODE_PREFIX_V3
    elif code.startswith(COMPAT_CODE_PREFIX_V2):
        prefix = COMPAT_CODE_PREFIX_V2
    else:
        if code.startswith("SSBU-COMPAT-"):
            logger.warn("CompatChecker", "Unsupported compat code version")
        return None

    b64_part = code[len(prefix):]
    try:
        compressed = base64.urlsafe_b64decode(b64_part)
        json_bytes = zlib.decompress(compressed)
        data = json.loads(json_bytes)
    except Exception as exc:
        logger.error("CompatChecker", f"Failed to decode compat code: {exc}")
        return None

    fp = CompatFingerprint(
        version=int(data.get("v", 2)),
        app_version=data.get("av", ""),
        timestamp=data.get("ts", ""),
        emulator=data.get("em", ""),
        emulator_version=data.get("ev", ""),
        game_version=data.get("gv", ""),
        strict_audio_sync=bool(data.get("sa", False)),
        strict_environment_match=bool(data.get("se", False)),
        gameplay_hashes=data.get("gh", {}) or {},
        plugin_hashes=data.get("ph", {}) or {},
        optional_plugins=data.get("op", []) or [],
        exefs_hashes=data.get("eh", {}) or {},
        gameplay_mod_names=data.get("gm", []) or [],
        digest=data.get("d", ""),
    )
    if not fp.digest:
        fp.compute_digest()
    return fp


def compare_fingerprints(local: CompatFingerprint, reference: CompatFingerprint) -> CompatResult:
    """Compare local setup against host/reference compatibility fingerprint."""
    result = CompatResult()
    _compare_environment(local, reference, result)

    # Fast path only if digest matches and environment is clean.
    if (
        local.digest
        and reference.digest
        and local.digest == reference.digest
        and not result.environment_issues
    ):
        result.compatible = True
        result.summary = "Fully compatible! Your gameplay setup matches exactly."
        if result.warnings:
            result.summary += f"\n\n{len(result.warnings)} warning(s):"
            for warning in result.warnings:
                result.summary += f"\n  - {warning}"
        return result

    ref_files = set(reference.gameplay_hashes.keys())
    local_files = set(local.gameplay_hashes.keys())

    for f in sorted(ref_files - local_files):
        _add_unique(result.missing_gameplay, _display_gameplay_key(f))
    for f in sorted(local_files - ref_files):
        _add_unique(result.extra_gameplay, _display_gameplay_key(f))
    for f in sorted(ref_files & local_files):
        if reference.gameplay_hashes[f] != local.gameplay_hashes[f]:
            _add_unique(result.mismatched_gameplay, _display_gameplay_key(f))

    ref_plugins = set(reference.plugin_hashes.keys())
    local_plugins = set(local.plugin_hashes.keys())
    for p in sorted(ref_plugins - local_plugins):
        result.missing_plugins.append(p)
    for p in sorted(local_plugins - ref_plugins):
        result.extra_plugins.append(p)
    for p in sorted(ref_plugins & local_plugins):
        if reference.plugin_hashes[p] != local.plugin_hashes[p]:
            result.mismatched_plugins.append(p)

    local_opt = set(local.optional_plugins)
    ref_opt = set(reference.optional_plugins)
    result.optional_only_local = sorted(local_opt - ref_opt)
    result.optional_only_remote = sorted(ref_opt - local_opt)

    ref_exefs = set(reference.exefs_hashes.keys())
    local_exefs = set(local.exefs_hashes.keys())
    for fname in sorted(ref_exefs | local_exefs):
        ref_h = reference.exefs_hashes.get(fname)
        local_h = local.exefs_hashes.get(fname)
        if ref_h != local_h:
            result.mismatched_exefs.append(fname)

    result.compatible = result.issue_count == 0

    optional_parts: list[str] = []
    if result.optional_only_local:
        optional_parts.append(
            f"You have {len(result.optional_only_local)} optional plugin(s) the host doesn't: "
            f"{', '.join(result.optional_only_local)}. These won't cause desyncs."
        )
    if result.optional_only_remote:
        optional_parts.append(
            f"The host has {len(result.optional_only_remote)} optional plugin(s) you don't: "
            f"{', '.join(result.optional_only_remote)}. These won't cause desyncs."
        )

    if result.compatible:
        result.summary = "Fully compatible! Your gameplay setup matches exactly."
    else:
        parts: list[str] = []
        if result.environment_issues:
            parts.append(f"{len(result.environment_issues)} environment mismatch(es)")
        if result.missing_gameplay:
            parts.append(f"{len(result.missing_gameplay)} missing gameplay file(s)")
        if result.extra_gameplay:
            parts.append(f"{len(result.extra_gameplay)} extra gameplay file(s)")
        if result.mismatched_gameplay:
            parts.append(f"{len(result.mismatched_gameplay)} mismatched gameplay file(s)")
        if result.missing_plugins:
            parts.append(f"{len(result.missing_plugins)} missing plugin(s)")
        if result.extra_plugins:
            parts.append(f"{len(result.extra_plugins)} extra plugin(s)")
        if result.mismatched_plugins:
            parts.append(f"{len(result.mismatched_plugins)} mismatched plugin(s)")
        if result.mismatched_exefs:
            parts.append(f"{len(result.mismatched_exefs)} mismatched ExeFS file(s)")
        result.summary = (
            f"INCOMPATIBLE - {result.issue_count} issue(s) detected:\n"
            + "\n".join(f"  - {part}" for part in parts)
        )

    if optional_parts:
        result.summary += "\n\nSetup differences (non-blocking):"
        for part in optional_parts:
            result.summary += f"\n  i  {part}"

    if result.warnings:
        result.summary += f"\n\n{len(result.warnings)} warning(s):"
        for warning in result.warnings:
            result.summary += f"\n  - {warning}"

    logger.info(
        "CompatChecker",
        f"Comparison result: compatible={result.compatible}, "
        f"issues={result.issue_count}, warnings={len(result.warnings)}",
    )
    return result
