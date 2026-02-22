"""Online compatibility checker — generate and compare gameplay fingerprints.

Tournament Organiser (TO) Workflow:
1. TO clicks "Generate Compatibility Code" in the Online Guide page.
2. The code is a compact base64 string representing a SHA-256 fingerprint of
   ALL gameplay-affecting files (params, movesets, stage collision, plugins).
3. TO posts the code in their Discord / tournament page.
4. Each participant pastes the code and clicks "Check Compatibility".
5. The tool compares their local gameplay fingerprint against the TO's code
   and reports: COMPATIBLE, INCOMPATIBLE (with details), or WARNING.

Desync Classification — EXHAUSTIVE list of file categories:
──────────────────────────────────────────────────────────────────────
SAFE (client-side only, NEVER causes desync):
  1. Custom skins / costumes — model + texture swaps in fighter/*/model/
  2. Custom textures — .nutexb, .bntx files anywhere
  3. Custom audio / music — .nus3audio, sound/bgm/*, stream/*
  4. Custom sound effects — sound/bank/* (non-narration audio only)
  5. Custom announcer / narration — sound/bank/narration/*
  6. UI / CSS changes — ui/ directory (portraits, stock icons, menus, CSS)
  7. Visual effects — effect/ directory (hit sparks, trails, particles)
  8. Camera mods — camera/ directory
  9. Victory screen visuals — model/rendering changes only
 10. Stage texture / model swaps — visual-only changes to existing stages
 11. .xmsbt / .msbt text files — UI text / display names
 12. config.json — ARCropolis file replacement metadata (not gameplay)
 13. info.toml — mod metadata descriptor

UNSAFE (causes desync, MUST match between all players):
  1. Fighter parameters — .prc files inside fighter/* paths
     (hitbox data, frame data, weight, speed, knockback, damage, physics)
  2. Fighter motion lists — .motion_list_hash files (move definitions)
  3. System parameters — .prc files in param/ root (gravity, input lag, etc.)
  4. Stage collision / layout — .stprm, .stdat (geometry, blastzones, platforms)
  5. Stage parameters — .prc inside stage/* (respawn positions, camera bounds)
  6. Gameplay-modifying plugins — .nro files that hook game logic
     (e.g. libhdr.nro, libtraining_modpack.nro, libhdr_hooks.nro)
  7. ACMD scripts / compiled moveset logic — lua* or script* in fighter/
  8. ExeFS patches — subsdk*, main.npdm (framework-level hooks)

CONTEXT-DEPENDENT (warn):
  1. ARCropolis version — doesn't desync by itself, but major version
     mismatches may load files differently → warn if different
  2. Animation files (.nuanmb) — purely cosmetic anims are safe, but if
     they change hitbox active frames they can desync. We err on the side
     of caution and HASH them when inside fighter/ directories outside of
     model/ subdirs.
  3. Stage mods — collision data desyncs, but visual-only stage mods don't.
     We hash .stprm/.stdat/.prc inside stage/ but skip .nutexb/.numdlb.
──────────────────────────────────────────────────────────────────────
"""

import base64
import hashlib
import json
import os
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

from src.utils.logger import logger


# ─── File extension / path classification ────────────────────────────

# Extensions that are ALWAYS visual-only (safe) regardless of location
_SAFE_EXTENSIONS = frozenset({
    # Textures
    ".nutexb", ".bntx", ".png", ".jpg", ".jpeg", ".tga", ".dds",
    # Models (visual mesh / materials)
    ".numdlb", ".numshb", ".numatb", ".nusrcmdlb", ".nuhlpb",
    # Audio
    ".nus3audio", ".nus3bank", ".wav", ".ogg", ".mp3", ".flac",
    ".bfsar", ".bfstm", ".bfwav", ".lopus", ".opus", ".idsp", ".bwav",
    # UI assets
    ".bntx", ".arc",
    # Text / metadata
    ".xmsbt", ".msbt",
    # Mod metadata
    ".toml", ".md", ".txt", ".json",
})

# Extensions that are ALWAYS gameplay-affecting
_UNSAFE_EXTENSIONS = frozenset({
    ".prc",            # Parameter files (hitbox, frame data, physics, etc.)
    ".stprm",          # Stage parameters (blastzones, respawn positions)
    ".stdat",          # Stage collision data (platforms, terrain)
    ".motion_list_hash",  # Fighter motion list (move definitions)
    ".nro",            # Skyline plugins
})

# Directories whose contents are ALWAYS safe (client-side rendering)
_SAFE_DIRS = frozenset({
    "model",           # Character model/skin swaps
    "effect",          # Visual effects (hit sparks, trails)
    "camera",          # Camera angles
    "sound",           # All audio
    "stream",          # Audio streams
})

# File names that are always safe (metadata, not gameplay)
_SAFE_FILENAMES = frozenset({
    "config.json",     # ARCropolis redirect metadata
    "info.toml",       # Mod info descriptor
})

# Known gameplay-modifying plugins (MUST match between players)
KNOWN_GAMEPLAY_PLUGINS = frozenset({
    "libhdr.nro",
    "libhdr_hooks.nro",
    "libtraining_modpack.nro",
    "libnro_hook.nro",
    "libhewdraw_remix.nro",
    "libacmd_hook.nro",
    "libfighter_hook.nro",
    "libparam_hook.nro",
    "libworkspace_hook.nro",
})

# Known safe plugins (mod loader infrastructure, not gameplay)
KNOWN_SAFE_PLUGINS = frozenset({
    "libarcropolis.nro",
    "libarc_managed.nro",
    "libsmash_minecraft_skins.nro",
    "libone_slot_victory_theme.nro",
    "libarc_randomizer.nro",
    "libskyline_web.nro",
})

# ExeFS files that indicate framework-level hooks (gameplay-affecting)
_EXEFS_GAMEPLAY_FILES = frozenset({
    "subsdk9", "subsdk0", "main.npdm",
})


# ─── Data structures ─────────────────────────────────────────────────

@dataclass
class CompatFingerprint:
    """A gameplay fingerprint representing all gameplay-affecting state."""
    version: int = 2                           # Schema version
    app_version: str = ""                      # App version that generated this
    timestamp: str = ""                        # ISO timestamp
    emulator: str = ""                         # Emulator name (informational)
    # Gameplay file hashes: relative_path → sha256 hex
    gameplay_hashes: dict[str, str] = field(default_factory=dict)
    # Plugin hashes: plugin_filename → sha256 hex
    plugin_hashes: dict[str, str] = field(default_factory=dict)
    # ExeFS hashes: filename → sha256 hex
    exefs_hashes: dict[str, str] = field(default_factory=dict)
    # Mod names for display (not used for comparison)
    gameplay_mod_names: list[str] = field(default_factory=list)
    # Combined digest for quick comparison
    digest: str = ""

    def compute_digest(self) -> str:
        """Compute a single SHA-256 digest over all gameplay hashes."""
        h = hashlib.sha256()
        # Sort for determinism
        for key in sorted(self.gameplay_hashes.keys()):
            h.update(key.encode("utf-8"))
            h.update(self.gameplay_hashes[key].encode("utf-8"))
        for key in sorted(self.plugin_hashes.keys()):
            h.update(key.encode("utf-8"))
            h.update(self.plugin_hashes[key].encode("utf-8"))
        for key in sorted(self.exefs_hashes.keys()):
            h.update(key.encode("utf-8"))
            h.update(self.exefs_hashes[key].encode("utf-8"))
        self.digest = h.hexdigest()[:32]
        return self.digest


@dataclass
class CompatResult:
    """Result of comparing two fingerprints."""
    compatible: bool = True
    # Files only in the reference (TO) but not local
    missing_gameplay: list[str] = field(default_factory=list)
    # Files only locally but not in reference
    extra_gameplay: list[str] = field(default_factory=list)
    # Files present in both but with different hashes
    mismatched_gameplay: list[str] = field(default_factory=list)
    # Plugin differences
    missing_plugins: list[str] = field(default_factory=list)
    extra_plugins: list[str] = field(default_factory=list)
    mismatched_plugins: list[str] = field(default_factory=list)
    # ExeFS differences
    mismatched_exefs: list[str] = field(default_factory=list)
    # Warnings (non-blocking)
    warnings: list[str] = field(default_factory=list)
    # Human-readable summary
    summary: str = ""

    @property
    def issue_count(self) -> int:
        return (len(self.missing_gameplay) + len(self.extra_gameplay) +
                len(self.mismatched_gameplay) + len(self.missing_plugins) +
                len(self.extra_plugins) + len(self.mismatched_plugins) +
                len(self.mismatched_exefs))


# ─── File classification ─────────────────────────────────────────────

def _is_gameplay_file(relative_path: str) -> bool:
    """Determine if a file within a mod is gameplay-affecting.

    Uses EXHAUSTIVE classification: a file is gameplay-affecting if it is NOT
    in any known safe category. This conservative approach means unknown file
    types default to "gameplay" to avoid missed desyncs.
    """
    rel_lower = relative_path.lower().replace("\\", "/")
    parts = rel_lower.split("/")
    filename = parts[-1] if parts else ""
    ext = os.path.splitext(filename)[1]

    # 1. Known safe filenames — always safe
    if filename in _SAFE_FILENAMES:
        return False

    # 2. Known safe extensions — always safe regardless of path
    if ext in _SAFE_EXTENSIONS:
        return False

    # 3. Known unsafe extensions — always gameplay-affecting
    if ext in _UNSAFE_EXTENSIONS:
        # Exception: PRC files in ui/ are CSS/UI, not gameplay
        if ext == ".prc" and _is_in_ui_path(rel_lower):
            return False
        return True

    # 4. Check path-based rules
    # Files inside fighter/*/model/ are skins — safe
    if _is_in_fighter_model_dir(parts):
        return False

    # Files in safe directories are safe
    for safe_dir in _SAFE_DIRS:
        if safe_dir in parts:
            return False

    # Files in ui/ directory tree are safe
    if _is_in_ui_path(rel_lower):
        return False

    # 5. Fighter directory files outside model/ — could be gameplay
    # (animations, scripts, params)
    if "fighter" in parts:
        # Animations inside fighter but outside model are risky
        # (could change hitbox timings)
        return True

    # 6. Stage directory files — only collision/params are gameplay
    if "stage" in parts:
        # We already caught .stprm/.stdat/.prc above
        # Other stage files (textures, models) are safe
        return False

    # 7. Unknown file in unknown location — conservative: flag it
    return True


def _is_in_ui_path(rel_lower: str) -> bool:
    """Check if a relative path is inside a UI directory."""
    return (rel_lower.startswith("ui/") or
            "/ui/" in rel_lower or
            "ui_chara" in rel_lower or
            "ui_stage" in rel_lower)


def _is_in_fighter_model_dir(parts: list[str]) -> bool:
    """Check if path parts indicate a fighter/*/model/ location."""
    try:
        fighter_idx = parts.index("fighter")
        # fighter/<name>/model/...
        if len(parts) > fighter_idx + 2 and parts[fighter_idx + 2] == "model":
            return True
    except ValueError:
        pass
    return False


def _is_plugin_gameplay_affecting(plugin_filename: str) -> bool:
    """Determine if a plugin is known to affect gameplay."""
    fname = plugin_filename.lower().replace(".disabled", "")
    if fname in KNOWN_SAFE_PLUGINS:
        return False
    if fname in KNOWN_GAMEPLAY_PLUGINS:
        return True
    # Unknown plugins — conservative: treat as gameplay-affecting
    # unless they have clearly safe prefixes
    safe_prefixes = ("libarc_", "libui_", "libskin_", "libvisual_", "libcss_")
    if any(fname.startswith(p) for p in safe_prefixes):
        return False
    return True


# ─── Hash computation ─────────────────────────────────────────────────

def _hash_file(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
    except (OSError, PermissionError):
        return "error"
    return h.hexdigest()


# ─── Fingerprint generation ──────────────────────────────────────────

def generate_fingerprint(
    mods_path: Path,
    plugins_path: Optional[Path] = None,
    exefs_path: Optional[Path] = None,
    emulator_name: str = "",
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> CompatFingerprint:
    """Generate a gameplay fingerprint from the user's mod setup.

    Scans all ENABLED mods and hashes only gameplay-affecting files.
    Visual-only mods (skins, audio, UI) are completely ignored.

    Args:
        mods_path: Path to ultimate/mods/ directory
        plugins_path: Path to skyline/plugins/ directory
        exefs_path: Path to exefs/ directory (optional)
        emulator_name: Name of current emulator (informational)
        progress_callback: Optional (message, fraction) callback
    """
    from src import __version__
    from datetime import datetime

    fp = CompatFingerprint(
        app_version=__version__,
        timestamp=datetime.now().isoformat(timespec="seconds"),
        emulator=emulator_name,
    )

    # Phase 1: Scan mods for gameplay files
    if progress_callback:
        progress_callback("Scanning mods for gameplay files...", 0.0)

    gameplay_mods = set()

    if mods_path and mods_path.exists():
        mod_folders = []
        try:
            mod_folders = [f for f in sorted(mods_path.iterdir())
                          if f.is_dir() and not f.name.startswith(".")
                          and not f.name.startswith("_")]
        except OSError:
            pass

        total_mods = len(mod_folders) or 1
        for idx, mod_folder in enumerate(mod_folders):
            if progress_callback:
                progress_callback(f"Scanning: {mod_folder.name}", 0.1 + 0.5 * idx / total_mods)

            try:
                for fpath in mod_folder.rglob("*"):
                    if not fpath.is_file():
                        continue
                    rel = str(fpath.relative_to(mod_folder)).replace("\\", "/")

                    if _is_gameplay_file(rel):
                        file_hash = _hash_file(fpath)
                        # Use mod-relative path as key
                        # (same mod structure = same key)
                        fp.gameplay_hashes[rel] = file_hash
                        gameplay_mods.add(mod_folder.name)
            except (PermissionError, OSError):
                continue

    fp.gameplay_mod_names = sorted(gameplay_mods)

    # Phase 2: Scan plugins
    if progress_callback:
        progress_callback("Scanning plugins...", 0.65)

    if plugins_path and plugins_path.exists():
        try:
            for fpath in sorted(plugins_path.iterdir()):
                if not fpath.is_file():
                    continue
                if not fpath.name.endswith(".nro"):
                    continue
                if _is_plugin_gameplay_affecting(fpath.name):
                    fp.plugin_hashes[fpath.name] = _hash_file(fpath)
        except (PermissionError, OSError):
            pass

    # Phase 3: Scan ExeFS
    if progress_callback:
        progress_callback("Scanning ExeFS...", 0.80)

    if exefs_path and exefs_path.exists():
        try:
            for fpath in sorted(exefs_path.iterdir()):
                if not fpath.is_file():
                    continue
                # Only hash gameplay-relevant ExeFS files
                fname_lower = fpath.name.lower()
                if any(fname_lower.startswith(ef) for ef in _EXEFS_GAMEPLAY_FILES):
                    fp.exefs_hashes[fpath.name] = _hash_file(fpath)
        except (PermissionError, OSError):
            pass

    # Compute combined digest
    fp.compute_digest()

    if progress_callback:
        progress_callback("Fingerprint complete!", 1.0)

    logger.info("CompatChecker",
        f"Generated fingerprint: {len(fp.gameplay_hashes)} gameplay files, "
        f"{len(fp.plugin_hashes)} plugins, {len(fp.exefs_hashes)} exefs, "
        f"digest={fp.digest}")

    return fp


# ─── Encode / Decode ──────────────────────────────────────────────────

def encode_fingerprint(fp: CompatFingerprint) -> str:
    """Encode a fingerprint into a compact, shareable string code.

    Format: SSBU-COMPAT-v2:<base64(zlib(json))>
    """
    data = {
        "v": fp.version,
        "av": fp.app_version,
        "ts": fp.timestamp,
        "em": fp.emulator,
        "gh": fp.gameplay_hashes,
        "ph": fp.plugin_hashes,
        "eh": fp.exefs_hashes,
        "gm": fp.gameplay_mod_names,
        "d": fp.digest,
    }
    json_bytes = json.dumps(data, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(json_bytes, level=9)
    b64 = base64.urlsafe_b64encode(compressed).decode("ascii")
    return f"SSBU-COMPAT-v2:{b64}"


def decode_fingerprint(code: str) -> Optional[CompatFingerprint]:
    """Decode a compatibility code back into a fingerprint.

    Returns None if the code is invalid.
    """
    code = code.strip()
    prefix = "SSBU-COMPAT-v2:"
    if not code.startswith(prefix):
        # Try older format or raw base64
        if code.startswith("SSBU-COMPAT-"):
            logger.warn("CompatChecker", "Unsupported compat code version")
            return None
        return None

    b64_part = code[len(prefix):]
    try:
        compressed = base64.urlsafe_b64decode(b64_part)
        json_bytes = zlib.decompress(compressed)
        data = json.loads(json_bytes)
    except Exception as e:
        logger.error("CompatChecker", f"Failed to decode compat code: {e}")
        return None

    fp = CompatFingerprint(
        version=data.get("v", 1),
        app_version=data.get("av", ""),
        timestamp=data.get("ts", ""),
        emulator=data.get("em", ""),
        gameplay_hashes=data.get("gh", {}),
        plugin_hashes=data.get("ph", {}),
        exefs_hashes=data.get("eh", {}),
        gameplay_mod_names=data.get("gm", []),
        digest=data.get("d", ""),
    )
    return fp


# ─── Comparison ───────────────────────────────────────────────────────

def compare_fingerprints(
    local: CompatFingerprint,
    reference: CompatFingerprint,
) -> CompatResult:
    """Compare a local fingerprint against a reference (TO's code).

    Logic:
    - If both have zero gameplay files/plugins → compatible (vanilla)
    - Files only in reference but not local → the user is MISSING a required
      gameplay mod → INCOMPATIBLE
    - Files only locally but not in reference → the user has an EXTRA gameplay
      mod the TO doesn't have → INCOMPATIBLE
    - Files in both but with different hashes → version MISMATCH → INCOMPATIBLE
    - ALL gameplay hashes match → COMPATIBLE

    Note: visual-only mods (skins, audio, UI) are NOT in the fingerprint,
    so they never cause a mismatch — exactly as desired.
    """
    result = CompatResult()

    # Quick check: identical digest means fully compatible
    if local.digest and reference.digest and local.digest == reference.digest:
        result.compatible = True
        result.summary = "Fully compatible! Your gameplay setup matches exactly."
        return result

    # ── Compare gameplay files ──
    ref_files = set(reference.gameplay_hashes.keys())
    local_files = set(local.gameplay_hashes.keys())

    # Files the reference has but we don't → we're MISSING gameplay mods
    for f in sorted(ref_files - local_files):
        result.missing_gameplay.append(f)

    # Files we have but reference doesn't → we have EXTRA gameplay mods
    for f in sorted(local_files - ref_files):
        result.extra_gameplay.append(f)

    # Files in both → check for hash mismatch
    for f in sorted(ref_files & local_files):
        if reference.gameplay_hashes[f] != local.gameplay_hashes[f]:
            result.mismatched_gameplay.append(f)

    # ── Compare plugins ──
    ref_plugins = set(reference.plugin_hashes.keys())
    local_plugins = set(local.plugin_hashes.keys())

    for p in sorted(ref_plugins - local_plugins):
        result.missing_plugins.append(p)
    for p in sorted(local_plugins - ref_plugins):
        result.extra_plugins.append(p)
    for p in sorted(ref_plugins & local_plugins):
        if reference.plugin_hashes[p] != local.plugin_hashes[p]:
            result.mismatched_plugins.append(p)

    # ── Compare ExeFS ──
    ref_exefs = set(reference.exefs_hashes.keys())
    local_exefs = set(local.exefs_hashes.keys())
    for f in sorted((ref_exefs | local_exefs)):
        ref_h = reference.exefs_hashes.get(f)
        local_h = local.exefs_hashes.get(f)
        if ref_h and local_h and ref_h != local_h:
            result.mismatched_exefs.append(f)
        elif ref_h and not local_h:
            result.mismatched_exefs.append(f)
        elif local_h and not ref_h:
            result.mismatched_exefs.append(f)

    # ── Warnings ──
    if reference.emulator and local.emulator:
        if reference.emulator != local.emulator:
            result.warnings.append(
                f"Emulator mismatch: you use {local.emulator}, "
                f"host uses {reference.emulator}. Make sure you're on the same "
                f"emulator to join the same LDN network."
            )

    # ── Determine overall compatibility ──
    result.compatible = result.issue_count == 0

    # ── Build summary ──
    if result.compatible:
        result.summary = "Fully compatible! Your gameplay setup matches exactly."
        if result.warnings:
            result.summary += f"\n\n{len(result.warnings)} warning(s):"
            for w in result.warnings:
                result.summary += f"\n  - {w}"
    else:
        parts = []
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
            f"INCOMPATIBLE — {result.issue_count} issue(s) detected:\n"
            + "\n".join(f"  - {p}" for p in parts)
        )
        if result.warnings:
            result.summary += f"\n\n{len(result.warnings)} warning(s):"
            for w in result.warnings:
                result.summary += f"\n  - {w}"

    logger.info("CompatChecker",
        f"Comparison result: compatible={result.compatible}, "
        f"issues={result.issue_count}, warnings={len(result.warnings)}")

    return result
