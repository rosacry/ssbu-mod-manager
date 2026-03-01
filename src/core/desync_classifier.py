"""Desync risk classification for SSBU mods and Skyline plugins.

This module centralizes rules used by:
- Online compatibility fingerprint generation
- Mods/Plugins page risk badges
- Future strict/tournament policy modes
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class DesyncRiskLevel(str, Enum):
    SAFE_CLIENT_ONLY = "safe_client_only"
    CONDITIONALLY_SHARED = "conditionally_shared"
    DESYNC_VULNERABLE = "desync_vulnerable"
    UNKNOWN_NEEDS_REVIEW = "unknown_needs_review"


@dataclass(frozen=True)
class RiskReason:
    code: str
    message: str
    relative_path: str = ""
    evidence_url: str = ""


@dataclass
class ModDesyncReport:
    level: DesyncRiskLevel
    reasons: list[RiskReason] = field(default_factory=list)
    scanned_files: int = 0
    gameplay_hits: int = 0
    conditional_hits: int = 0
    unknown_hits: int = 0


@dataclass
class PluginDesyncReport:
    level: DesyncRiskLevel
    reason: str
    code: str
    plugin_filename: str = ""
    evidence_url: str = ""


# Known safe visual/content extensions (client-only effects).
SAFE_EXTENSIONS = frozenset({
    ".nutexb", ".bntx", ".png", ".jpg", ".jpeg", ".webp", ".tga", ".dds",
    ".numdlb", ".numshb", ".numatb", ".nusrcmdlb", ".nuhlpb",
    ".eff",
    ".nus3audio", ".nus3bank", ".wav", ".ogg", ".mp3", ".flac",
    ".bfsar", ".bfstm", ".bfwav", ".lopus", ".opus", ".idsp", ".bwav",
    ".xmsbt", ".msbt",
    ".toml", ".md", ".txt", ".json",
})

# Explicit gameplay-affecting extensions.
GAMEPLAY_EXTENSIONS = frozenset({
    ".prc",             # params, fighter/system/stage behavior
    ".stprm",           # stage blastzones/spawns/config
    ".stdat",           # stage collision/layout
    ".motion_list_hash",
})

SAFE_FILENAMES = frozenset({
    "config.json",
    "info.toml",
})

SAFE_DIR_PARTS = frozenset({
    "model",
    "effect",
    "camera",
    "sound",
    "stream",
})

_COSTUME_MOTION_PATH_RE = re.compile(
    r"^fighter/[^/]+/motion/[^/]+/c\d{2,3}/[^/]+$",
    re.IGNORECASE,
)
_COSTUME_MODEL_UPDATE_RE = re.compile(
    r"^fighter/[^/]+/model/[^/]+/c\d{2,3}/update\.prc$",
    re.IGNORECASE,
)
_COSTUME_MOTION_SAFE_FILENAMES = frozenset({
    "flip.prc",
    "ik.prc",
    "motion_list.bin",
    "scharge.prc",
    "swing.prc",
    "update.prc",
})

# Plugins explicitly categorized from project research + existing app behavior.
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
    "libsmashline_hook.nro",
    "libsmashline_plugin.nro",
    "libparam_config.nro",
    "libstage_config.nro",
})

KNOWN_SAFE_PLUGINS = frozenset({
    "libarcropolis.nro",
    "libarc_managed.nro",
    "libskyline_web.nro",
    "libsmash_minecraft_skins.nro",
    "libone_slot_victory_theme.nro",
    "libarc_randomizer.nro",
    "libcss_preserve.nro",
    "libresults_screen.nro",
})

# Optional plugins are local QoL/perf/cosmetic tooling and are non-blocking.
KNOWN_OPTIONAL_PLUGINS = frozenset({
    "libless_lag.nro",
    "libssbu_less_lag.nro",
    "liblag_fix.nro",
    "libperformance.nro",
    "libfps.nro",
    "liblatency_slider_de.nro",
    "libcss_manager.nro",
    "libcss_changer.nro",
    "libui_manager.nro",
    "libskin_changer.nro",
    "libvisual_effects.nro",
    "libinput_display.nro",
    "libinput_viewer.nro",
    "libreplay.nro",
    "librecording.nro",
    "libmusic_manager.nro",
    "libbgm_manager.nro",
    "libone_slot_eff.nro",
    "libtesting.nro",
})

SAFE_PLUGIN_PREFIXES = ("libarc_", "libui_", "libskin_", "libvisual_", "libcss_")

# Source-backed references used for rule auditability.
_EVIDENCE_URLS: dict[str, str] = {
    "safe_metadata": "https://github.com/Raytwo/ARCropolis",
    "safe_extension": "https://yuzu-mirror.github.io/help/feature/game-modding/",
    "ui_prc": "https://yuzu-mirror.github.io/help/feature/game-modding/",
    "ui_param": "https://yuzu-mirror.github.io/help/feature/game-modding/",
    "stage_gameplay_file": "https://github.com/spacemeowx2/switch-lan-play",
    "stage_visual_file": "https://yuzu-mirror.github.io/help/feature/game-modding/",
    "gameplay_param_file": "https://github.com/blu-dev/smashline",
    "fighter_model_only": "https://yuzu-mirror.github.io/help/feature/game-modding/",
    "fighter_cosmetic_support": "https://yuzu-mirror.github.io/help/feature/game-modding/",
    "audio_strict_mode": "https://github.com/jugeeya/UltimateTrainingModpack",
    "safe_directory": "https://yuzu-mirror.github.io/help/feature/game-modding/",
    "ui_content": "https://yuzu-mirror.github.io/help/feature/game-modding/",
    "fighter_logic_content": "https://github.com/blu-dev/smashline",
    "stage_content": "https://github.com/spacemeowx2/switch-lan-play",
    "unknown_file_type": "https://yuzu-mirror.github.io/help/feature/game-modding/",
    "optional_plugin": "https://github.com/jugeeya/UltimateTrainingModpack",
    "framework_plugin": "https://github.com/Raytwo/ARCropolis",
    "gameplay_plugin": "https://github.com/skyline-dev/skyline",
    "heuristic_gameplay_plugin": "https://github.com/skyline-dev/skyline",
    "safe_prefix_plugin": "https://github.com/Raytwo/ARCropolis",
    "unknown_plugin": "https://github.com/skyline-dev/skyline",
}


def evidence_url_for_rule(rule_code: str) -> str:
    """Return a source URL for the given rule code, if available."""
    return _EVIDENCE_URLS.get(rule_code, "")


def _is_in_ui_path(rel_lower: str) -> bool:
    return (
        rel_lower.startswith("ui/")
        or "/ui/" in rel_lower
        or "ui_chara" in rel_lower
        or "ui_stage" in rel_lower
    )


def _is_in_fighter_model_dir(parts: list[str]) -> bool:
    try:
        fighter_idx = parts.index("fighter")
    except ValueError:
        return False
    return len(parts) > fighter_idx + 2 and parts[fighter_idx + 2] == "model"


def _is_ui_param_file(rel_lower: str, ext: str) -> bool:
    if ext not in {".prc", ".prcx", ".prcxml"}:
        return False
    return _is_in_ui_path(rel_lower)


def _is_stage_visual_file(rel_lower: str, filename: str) -> bool:
    if not rel_lower.startswith("stage/"):
        return False
    if "/model/" in rel_lower or "/render/" in rel_lower or "/motion/" in rel_lower:
        return True
    return filename.endswith("visual.stdat")


def _is_fighter_cosmetic_support_file(rel_lower: str, filename: str, ext: str) -> bool:
    if ext == ".nuanmb" and _COSTUME_MOTION_PATH_RE.match(rel_lower) is not None:
        return True
    if filename in _COSTUME_MOTION_SAFE_FILENAMES and _COSTUME_MOTION_PATH_RE.match(rel_lower) is not None:
        return True
    return (
        filename == "update.prc"
        and _COSTUME_MODEL_UPDATE_RE.match(rel_lower) is not None
    )


def classify_mod_file(relative_path: str, strict_audio_sync: bool = False) -> tuple[DesyncRiskLevel, str, str]:
    """Classify a mod file by desync risk using path + extension rules."""
    rel_lower = relative_path.lower().replace("\\", "/")
    parts = rel_lower.split("/")
    filename = parts[-1] if parts else ""
    ext = os.path.splitext(filename)[1]

    if filename in SAFE_FILENAMES:
        return (DesyncRiskLevel.SAFE_CLIENT_ONLY, "safe_metadata", "Metadata file only")

    if _is_ui_param_file(rel_lower, ext):
        return (DesyncRiskLevel.SAFE_CLIENT_ONLY, "ui_param", "UI/CSS parameter file")

    if _is_stage_visual_file(rel_lower, filename):
        return (DesyncRiskLevel.SAFE_CLIENT_ONLY, "stage_visual_file", "Visual-only stage asset")

    if _is_fighter_cosmetic_support_file(rel_lower, filename, ext):
        return (
            DesyncRiskLevel.SAFE_CLIENT_ONLY,
            "fighter_cosmetic_support",
            "Costume-scoped cosmetic support file",
        )

    if ext in SAFE_EXTENSIONS:
        if strict_audio_sync and ext in {".nus3audio", ".nus3bank", ".wav", ".ogg", ".mp3", ".flac"}:
            return (
                DesyncRiskLevel.CONDITIONALLY_SHARED,
                "audio_strict_mode",
                "Audio file flagged under strict audio sync policy",
            )
        return (DesyncRiskLevel.SAFE_CLIENT_ONLY, "safe_extension", "Visual/UI/audio/text asset")

    if ext in GAMEPLAY_EXTENSIONS:
        # PRC under ui/ is CSS/UI data, not gameplay logic.
        if ext == ".prc" and _is_in_ui_path(rel_lower):
            return (DesyncRiskLevel.SAFE_CLIENT_ONLY, "ui_prc", "UI/CSS PRC file")
        if "stage" in parts:
            return (
                DesyncRiskLevel.CONDITIONALLY_SHARED,
                "stage_gameplay_file",
                "Stage gameplay file (requires match when stage is used)",
            )
        return (
            DesyncRiskLevel.DESYNC_VULNERABLE,
            "gameplay_param_file",
            "Gameplay parameter/script file",
        )

    if _is_in_fighter_model_dir(parts):
        return (DesyncRiskLevel.SAFE_CLIENT_ONLY, "fighter_model_only", "Fighter model/skin content")

    # Fast safe-directory rule for obvious client-only content.
    for safe_part in SAFE_DIR_PARTS:
        if safe_part in parts:
            if strict_audio_sync and safe_part in {"sound", "stream"}:
                return (
                    DesyncRiskLevel.CONDITIONALLY_SHARED,
                    "audio_strict_mode",
                    "Audio content flagged under strict audio sync policy",
                )
            return (DesyncRiskLevel.SAFE_CLIENT_ONLY, "safe_directory", "Client-only visual/audio directory")

    if _is_in_ui_path(rel_lower):
        return (DesyncRiskLevel.SAFE_CLIENT_ONLY, "ui_content", "UI/CSS content")

    # Fighter files outside model are treated gameplay-relevant.
    if "fighter" in parts:
        return (
            DesyncRiskLevel.DESYNC_VULNERABLE,
            "fighter_logic_content",
            "Fighter logic/animation/script content outside model directory",
        )

    # Stage content that isn't explicitly gameplay is conditional.
    if "stage" in parts:
        return (
            DesyncRiskLevel.CONDITIONALLY_SHARED,
            "stage_content",
            "Stage content can require matching setup depending on selection",
        )

    # Unknown location/type: conservative warning.
    return (
        DesyncRiskLevel.UNKNOWN_NEEDS_REVIEW,
        "unknown_file_type",
        "Unknown file type/location; manual review recommended",
    )


def is_gameplay_affecting_mod_file(relative_path: str, strict_audio_sync: bool = False) -> bool:
    level, _code, _msg = classify_mod_file(relative_path, strict_audio_sync=strict_audio_sync)
    return level in {
        DesyncRiskLevel.DESYNC_VULNERABLE,
        DesyncRiskLevel.CONDITIONALLY_SHARED,
        DesyncRiskLevel.UNKNOWN_NEEDS_REVIEW,
    }


def classify_mod_path(
    mod_path: Path,
    strict_audio_sync: bool = False,
    max_reason_examples: int = 12,
) -> ModDesyncReport:
    """Scan a mod directory and return a summarized desync risk report."""
    gameplay_reasons: list[RiskReason] = []
    conditional_reasons: list[RiskReason] = []
    unknown_reasons: list[RiskReason] = []
    scanned = 0

    try:
        files_iter = mod_path.rglob("*")
    except (OSError, PermissionError):
        return ModDesyncReport(
            level=DesyncRiskLevel.UNKNOWN_NEEDS_REVIEW,
            reasons=[RiskReason(
                code="scan_failed",
                message="Could not scan mod directory",
                relative_path=str(mod_path),
            )],
        )

    for fpath in files_iter:
        if not fpath.is_file():
            continue
        scanned += 1
        rel = str(fpath.relative_to(mod_path)).replace("\\", "/")
        level, code, msg = classify_mod_file(rel, strict_audio_sync=strict_audio_sync)
        reason = RiskReason(
            code=code,
            message=msg,
            relative_path=rel,
            evidence_url=evidence_url_for_rule(code),
        )
        if level == DesyncRiskLevel.DESYNC_VULNERABLE:
            gameplay_reasons.append(reason)
        elif level == DesyncRiskLevel.CONDITIONALLY_SHARED:
            conditional_reasons.append(reason)
        elif level == DesyncRiskLevel.UNKNOWN_NEEDS_REVIEW:
            unknown_reasons.append(reason)

    if gameplay_reasons:
        return ModDesyncReport(
            level=DesyncRiskLevel.DESYNC_VULNERABLE,
            reasons=gameplay_reasons[:max_reason_examples],
            scanned_files=scanned,
            gameplay_hits=len(gameplay_reasons),
            conditional_hits=len(conditional_reasons),
            unknown_hits=len(unknown_reasons),
        )
    if conditional_reasons:
        return ModDesyncReport(
            level=DesyncRiskLevel.CONDITIONALLY_SHARED,
            reasons=conditional_reasons[:max_reason_examples],
            scanned_files=scanned,
            gameplay_hits=0,
            conditional_hits=len(conditional_reasons),
            unknown_hits=len(unknown_reasons),
        )
    if unknown_reasons:
        return ModDesyncReport(
            level=DesyncRiskLevel.UNKNOWN_NEEDS_REVIEW,
            reasons=unknown_reasons[:max_reason_examples],
            scanned_files=scanned,
            gameplay_hits=0,
            conditional_hits=0,
            unknown_hits=len(unknown_reasons),
        )
    return ModDesyncReport(
        level=DesyncRiskLevel.SAFE_CLIENT_ONLY,
        reasons=[],
        scanned_files=scanned,
    )


def classify_plugin_filename(plugin_filename: str) -> PluginDesyncReport:
    """Classify a Skyline plugin by desync risk."""
    fname = plugin_filename.lower().replace(".disabled", "")

    if fname in KNOWN_OPTIONAL_PLUGINS:
        return PluginDesyncReport(
            level=DesyncRiskLevel.SAFE_CLIENT_ONLY,
            code="optional_plugin",
            reason="Optional client-side plugin (non-blocking)",
            plugin_filename=fname,
            evidence_url=evidence_url_for_rule("optional_plugin"),
        )
    if fname in KNOWN_SAFE_PLUGINS:
        return PluginDesyncReport(
            level=DesyncRiskLevel.SAFE_CLIENT_ONLY,
            code="framework_plugin",
            reason="Framework/utility plugin (not directly gameplay logic)",
            plugin_filename=fname,
            evidence_url=evidence_url_for_rule("framework_plugin"),
        )
    if fname in KNOWN_GAMEPLAY_PLUGINS:
        return PluginDesyncReport(
            level=DesyncRiskLevel.DESYNC_VULNERABLE,
            code="gameplay_plugin",
            reason="Gameplay hook/plugin that should match across players",
            plugin_filename=fname,
            evidence_url=evidence_url_for_rule("gameplay_plugin"),
        )

    # Heuristic fallback for unknown plugins.
    gameplay_markers = ("hook", "acmd", "param", "fighter", "moveset", "hdr", "smashline")
    if any(marker in fname for marker in gameplay_markers):
        return PluginDesyncReport(
            level=DesyncRiskLevel.DESYNC_VULNERABLE,
            code="heuristic_gameplay_plugin",
            reason="Plugin name indicates runtime gameplay hooks",
            plugin_filename=fname,
            evidence_url=evidence_url_for_rule("heuristic_gameplay_plugin"),
        )
    if any(fname.startswith(prefix) for prefix in SAFE_PLUGIN_PREFIXES):
        return PluginDesyncReport(
            level=DesyncRiskLevel.SAFE_CLIENT_ONLY,
            code="safe_prefix_plugin",
            reason="Plugin prefix indicates client/UI utility behavior",
            plugin_filename=fname,
            evidence_url=evidence_url_for_rule("safe_prefix_plugin"),
        )

    return PluginDesyncReport(
        level=DesyncRiskLevel.UNKNOWN_NEEDS_REVIEW,
        code="unknown_plugin",
        reason="Unknown plugin behavior; review before online play",
        plugin_filename=fname,
        evidence_url=evidence_url_for_rule("unknown_plugin"),
    )


def is_plugin_optional(plugin_filename: str) -> bool:
    return classify_plugin_filename(plugin_filename).code == "optional_plugin"


def is_gameplay_affecting_plugin(plugin_filename: str) -> bool:
    level = classify_plugin_filename(plugin_filename).level
    return level in {
        DesyncRiskLevel.DESYNC_VULNERABLE,
        DesyncRiskLevel.UNKNOWN_NEEDS_REVIEW,
    }
