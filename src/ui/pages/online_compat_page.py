"""Online Compatibility page — mod compatibility guide, mod analysis by online
impact, and a Compatibility Code system for tournament/multiplayer verification.

The checker fingerprints gameplay-affecting files (fighter params, stage
collision, gameplay plugins, ExeFS patches).  Visual-only mods are ignored
by default; strict audio mode includes audio/BGM for tournament parity.
"""

import threading
import customtkinter as ctk
from pathlib import Path
from tkinter import messagebox
from src.ui.base_page import BasePage
from src.ui import theme
from src.models.mod import Mod, ModStatus
from src.utils.logger import logger


# â”€â”€â”€ Online compatibility categories â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

COMPAT_CATEGORIES = {
    "required_both": {
        "label": "Required by Both Players",
        "icon": "\u26a0",
        "color": theme.ACCENT,
        "description": "These mods change gameplay mechanics and MUST be identical "
                       "on both players' setups to avoid desyncs.",
    },
    "visual_only": {
        "label": "Client-Side Only (Visual)",
        "icon": "\u2713",
        "color": theme.SUCCESS,
        "description": "These mods only change visuals (skins, textures, UI). "
                       "Only the player using them needs to have them installed.",
    },
    "audio_only": {
        "label": "Client-Side Only (Audio)",
        "icon": "\u2713",
        "color": theme.SUCCESS,
        "description": "These mods only change audio/music. "
                       "Only the player using them needs to have them installed.",
    },
    "stage_mods": {
        "label": "Shared if Stage is Used",
        "icon": "\u25b2",
        "color": theme.WARNING,
        "description": "Custom stages must be installed by both players if that stage is selected. "
                       "Standard stages are fine with one-sided mods.",
    },
    "unknown": {
        "label": "Unknown / Mixed",
        "icon": "-",
        "color": theme.TEXT_DIM,
        "description": "Could not determine online impact. Check mod documentation.",
    },
}

GAMEPLAY_KEYWORDS = [
    "hdr", "hewdraw", "moveset", "fighter", "param", "gameplay",
    "competitive", "balance", "frame", "hitbox", "knockback",
    "damage", "weight", "speed", "physics", "ai", "training",
]

VISUAL_KEYWORDS = [
    "skin", "costume", "texture", "model", "color", "visual",
    "portrait", "render", "csp", "stock", "icon", "ui_chara",
    "effect", "particle", "trail", "recolor",
]

AUDIO_KEYWORDS = [
    "music", "bgm", "sound", "audio", "voice", "narrator",
    "announcer", "sfx", "nus3audio", "victory_theme", "fanfare",
    "soundtrack", "song",
]

STAGE_KEYWORDS = [
    "stage", "battlefield", "final_destination", "smashville",
    "stadium", "arena", "platform", "hazard", "layout",
]

GAMEPLAY_PLUGINS = {
    "libhdr.nro", "libhdr_hooks.nro", "libtraining_modpack.nro",
    "libnro_hook.nro",
}

VISUAL_PLUGINS = {
    "libsmash_minecraft_skins.nro", "libone_slot_victory_theme.nro",
    "libarc_randomizer.nro",
}


def categorize_mod_online(mod: Mod) -> str:
    """Determine a mod's online compatibility category.

    Returns one of: 'required_both', 'visual_only', 'audio_only',
    'stage_mods', 'unknown'
    """
    name_lower = mod.name.lower()
    cats = mod.metadata.categories if mod.metadata else []
    cats_lower = [c.lower() for c in cats]

    # Prefer centralized risk classification when available.
    risk = (mod.metadata.online_risk if mod.metadata else "") or ""
    if risk == "desync_vulnerable":
        return "required_both"
    if risk == "conditionally_shared":
        return "stage_mods"
    if risk == "unknown_needs_review":
        return "unknown"

    for kw in GAMEPLAY_KEYWORDS:
        if kw in name_lower:
            return "required_both"

    if mod.metadata and mod.metadata.has_prc:
        if mod.metadata.fighter_kind:
            return "required_both"

    for kw in AUDIO_KEYWORDS:
        if kw in name_lower:
            return "audio_only"
    if mod.metadata and mod.metadata.has_music:
        return "audio_only"
    if "Audio" in cats:
        return "audio_only"

    for kw in STAGE_KEYWORDS:
        if kw in name_lower:
            return "stage_mods"
    if "Stage" in cats:
        return "stage_mods"

    for kw in VISUAL_KEYWORDS:
        if kw in name_lower:
            return "visual_only"
    if mod.metadata and mod.metadata.has_css_data:
        return "visual_only"
    if any(c in cats for c in ("Character", "UI", "Effect")):
        return "visual_only"

    if mod.metadata:
        if not mod.metadata.has_prc and not mod.metadata.has_msbt and not mod.metadata.has_xmsbt:
            return "visual_only"

    return "unknown"


class OnlineCompatPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._analyzed = False
        self._checker_generating = False
        self._checker_checking = False
        settings = self.app.config_manager.settings
        self._strict_audio_var = ctk.BooleanVar(
            value=bool(getattr(settings, "online_strict_audio_sync", False))
        )
        self._strict_environment_var = ctk.BooleanVar(
            value=bool(getattr(settings, "online_strict_environment_match", False))
        )
        self._build_ui()

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(25, 5))

        ctk.CTkLabel(header, text="Online Guide",
                     font=ctk.CTkFont(size=theme.FONT_PAGE_TITLE, weight="bold"), anchor="w"
                     ).pack(side="left")

        ctk.CTkButton(header, text="\u21bb  Analyze Mods", width=140,
                      fg_color=theme.PRIMARY, hover_color=theme.HOVER_PRIMARY,
                      command=self._analyze_mods, height=34, corner_radius=8
                      ).pack(side="right")

        desc = ctk.CTkLabel(self,
            text="Understand which mods are needed by both players for online multiplayer via emulator LDN networks, "
                 "and which mods are client-side only. Use the Compatibility Checker to verify setups before playing.",
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), text_color=theme.TEXT_MUTED, anchor="w", wraplength=theme.WRAP_LARGE,
            justify="left")
        desc.pack(fill="x", padx=30, pady=(0, 15))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=30)
        self._scroll = scroll

        self._build_checker_section(scroll)

        guide_section = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=10)
        guide_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(guide_section, text="Online Mod Compatibility Guide",
                     font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 10))

        rules = [
            ("\u26a0  Gameplay / Moveset Mods (e.g., HDR)",
             "BOTH players MUST have the exact same gameplay mods installed. "
             "Different gameplay code causes immediate desyncs. Both players also need "
             "compatible versions of required plugins (ARCropolis, Skyline).",
             theme.ACCENT),
            ("\u2713  Custom Skins / Costumes",
             "Only the player using the custom skin needs it installed. The other player "
             "will see the default character skin. No desync occurs because skins are "
             "purely visual and processed client-side only.",
             theme.SUCCESS),
            ("\u2713  Custom Audio / Music",
             "Default policy treats audio/music as client-side local content. "
             "If an event enforces Strict Audio Sync, both players should match audio/BGM files.",
             theme.SUCCESS),
            ("\u25b2  Custom Stages",
             "If a custom stage is selected for play, BOTH players need the same stage mod. "
             "If playing on standard/vanilla stages, no stage mods are needed by either player.",
             theme.WARNING),
            ("\u2713  UI / CSS Mods",
             "Character Select Screen mods, portraits, stock icons, and other UI changes "
             "are client-side only. Only the player using them needs them.",
             theme.SUCCESS),
            ("\u26a0  Plugins (ARCropolis, Skyline)",
             "Both players should use compatible versions of core plugins. ARCropolis "
             "itself doesn't usually cause desyncs, but gameplay-modifying plugins "
             "(like HDR hooks) MUST match on both sides.",
             theme.WARNING),
        ]

        for title, desc_text, color in rules:
            rule_frame = ctk.CTkFrame(guide_section, fg_color=theme.BG_CARD_INNER, corner_radius=6)
            rule_frame.pack(fill="x", padx=15, pady=3)

            ctk.CTkLabel(rule_frame, text=title,
                         font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS, weight="bold"),
                         text_color=color, anchor="w"
                         ).pack(fill="x", padx=12, pady=(8, 2))
            ctk.CTkLabel(rule_frame, text=desc_text,
                         font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.TEXT_HINT,
                         anchor="w", wraplength=theme.WRAP_STANDARD, justify="left"
                         ).pack(fill="x", padx=12, pady=(0, 8))

        emu_note = ctk.CTkFrame(guide_section, fg_color=theme.BG_CARD_DEEP, corner_radius=6)
        emu_note.pack(fill="x", padx=15, pady=(10, 15))
        ctk.CTkLabel(emu_note,
            text="\u2139  Important: Emulator Cross-Compatibility",
            font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS, weight="bold"), text_color=theme.INFO, anchor="w"
        ).pack(fill="x", padx=12, pady=(10, 2))
        ctk.CTkLabel(emu_note,
            text="Different emulators run separate multiplayer networks. Ryujinx LDN rooms, "
                 "Yuzu-family rooms, and other emulator lobbies are not guaranteed to interoperate. "
                 "For reliable online play, both players should use the same emulator and build "
                 "(or a specifically validated compatible fork). "
                 "Use the Migration page to transfer your data between emulators.",
            font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.INFO_EMU, anchor="w",
            wraplength=theme.WRAP_STANDARD, justify="left"
        ).pack(fill="x", padx=12, pady=(0, 10))

        self.analysis_section = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=10)
        self.analysis_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(self.analysis_section, text="Your Mod Analysis",
                     font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(self.analysis_section,
                     text="Click 'Analyze Mods' to categorize your enabled mods by online compatibility.",
                     font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), text_color=theme.TEXT_MUTED, anchor="w"
                     ).pack(fill="x", padx=15, pady=(0, 5))

        self.analysis_content = ctk.CTkFrame(self.analysis_section, fg_color="transparent")
        self.analysis_content.pack(fill="x", padx=15, pady=(5, 15))

        self.share_section = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=10)

    # â”€â”€â”€ Compatibility Checker â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _build_checker_section(self, parent):
        checker = ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=10)
        checker.pack(fill="x", pady=(0, 15))
        self._checker_frame = checker

        header_row = ctk.CTkFrame(checker, fg_color="transparent")
        header_row.pack(fill="x", padx=15, pady=(15, 5))

        ctk.CTkLabel(header_row, text="\u2611  Compatibility Checker",
                     font=ctk.CTkFont(size=theme.FONT_SUBSECTION, weight="bold"), anchor="w"
                     ).pack(side="left")

        ctk.CTkLabel(checker,
            text="Generate a compatibility code to share with tournament hosts or friends. "
                 "By default, only gameplay-affecting files are fingerprinted. Enable Strict Audio Sync "
                 "to include audio/BGM files for tournament rulesets that require exact parity.",
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), text_color=theme.TEXT_MUTED, anchor="w",
            wraplength=theme.WRAP_MEDIUM, justify="left"
        ).pack(fill="x", padx=15, pady=(0, 12))

        # â”€â”€ Tournament workflow explanation â”€â”€
        policy_row = ctk.CTkFrame(checker, fg_color="transparent")
        policy_row.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkCheckBox(
            policy_row,
            text="Strict Audio Sync (tournament policy)",
            variable=self._strict_audio_var,
            command=self._on_strict_audio_toggle,
            font=ctk.CTkFont(size=theme.FONT_BODY),
        ).pack(side="left")

        ctk.CTkCheckBox(
            policy_row,
            text="Strict Environment Match",
            variable=self._strict_environment_var,
            command=self._on_strict_environment_toggle,
            font=ctk.CTkFont(size=theme.FONT_BODY),
        ).pack(side="left", padx=(14, 0))

        ctk.CTkLabel(
            policy_row,
            text="Strict audio includes BGM files; strict environment requires emulator/build/game metadata.",
            font=ctk.CTkFont(size=theme.FONT_BODY),
            text_color=theme.INFO_EMU,
            anchor="w",
        ).pack(side="left", padx=(10, 0))

        workflow = ctk.CTkFrame(checker, fg_color=theme.BG_CARD_DEEP, corner_radius=8)
        workflow.pack(fill="x", padx=15, pady=(0, 12))

        ctk.CTkLabel(workflow,
            text="\u2139  How It Works (Tournament Setup)",
            font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS, weight="bold"), text_color=theme.INFO, anchor="w"
        ).pack(fill="x", padx=12, pady=(10, 4))

        steps = [
            "1.  The host/TO clicks 'Generate My Code' and copies the code.",
            "2.  The host pastes the code in their Discord server or tournament page.",
            "3.  Each participant pastes the host's code into 'Check Against Code' below.",
            "4.  The tool compares gameplay files (and audio if Strict Audio Sync is enabled).",
            "     With Strict Environment Match enabled, emulator/build/game metadata must also match.",
        ]
        for step in steps:
            ctk.CTkLabel(workflow, text=step,
                         font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.INFO_WORKFLOW,
                         anchor="w").pack(fill="x", padx=12, pady=1)
        ctk.CTkFrame(workflow, height=8, fg_color="transparent").pack()

        # â”€â”€ Generate Code â”€â”€
        gen_frame = ctk.CTkFrame(checker, fg_color=theme.BG_CARD_INNER, corner_radius=8)
        gen_frame.pack(fill="x", padx=15, pady=(0, 10))

        gen_header = ctk.CTkFrame(gen_frame, fg_color="transparent")
        gen_header.pack(fill="x", padx=12, pady=(10, 5))

        ctk.CTkLabel(gen_header, text="Generate My Compatibility Code",
                     font=ctk.CTkFont(size=theme.FONT_CARD_HEADING, weight="bold"), anchor="w"
                     ).pack(side="left")

        self._gen_btn = ctk.CTkButton(gen_header, text="\u2192  Generate My Code",
                                      width=180, height=34, corner_radius=8,
                                      fg_color=theme.SUCCESS, hover_color=theme.HOVER_SUCCESS_ALT,
                                      command=self._generate_code)
        self._gen_btn.pack(side="right")

        ctk.CTkLabel(gen_frame,
            text="Scans all your enabled mods and generates a code containing only gameplay file hashes. "
                 "Skins and UI are excluded; audio/BGM is included only if Strict Audio Sync is enabled.",
            font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.TEXT_DIM, anchor="w",
            wraplength=theme.WRAP_STANDARD, justify="left"
        ).pack(fill="x", padx=12, pady=(0, 5))

        self._gen_status = ctk.CTkLabel(gen_frame, text="",
                                        font=ctk.CTkFont(size=theme.FONT_BODY),
                                        text_color=theme.INFO, anchor="w")
        self._gen_status.pack(fill="x", padx=12, pady=(0, 3))

        self._gen_progress = ctk.CTkProgressBar(gen_frame, height=4,
                                                fg_color=theme.PROGRESS_TRACK,
                                                progress_color=theme.SUCCESS)
        self._gen_progress.pack(fill="x", padx=12, pady=(0, 5))
        self._gen_progress.set(0)

        self._gen_code_frame = ctk.CTkFrame(gen_frame, fg_color="transparent")
        self._gen_code_frame.pack(fill="x", padx=12, pady=(0, 10))

        # â”€â”€ Check Against Code â”€â”€
        check_frame = ctk.CTkFrame(checker, fg_color=theme.BG_CARD_INNER, corner_radius=8)
        check_frame.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkLabel(check_frame, text="Check Against a Code",
                     font=ctk.CTkFont(size=theme.FONT_CARD_HEADING, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=12, pady=(10, 5))

        ctk.CTkLabel(check_frame,
            text="Paste the host's / opponent's compatibility code below, then click Check.",
            font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.TEXT_DIM, anchor="w"
        ).pack(fill="x", padx=12, pady=(0, 5))

        input_row = ctk.CTkFrame(check_frame, fg_color="transparent")
        input_row.pack(fill="x", padx=12, pady=(0, 5))

        self._check_entry = ctk.CTkTextbox(input_row, height=60, fg_color=theme.BG_INPUT,
                                           font=ctk.CTkFont(family="Consolas", size=theme.FONT_CAPTION),
                                           border_width=1, border_color=theme.BORDER_INPUT)
        self._check_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_col = ctk.CTkFrame(input_row, fg_color="transparent", width=140)
        btn_col.pack(side="right")
        btn_col.pack_propagate(False)

        self._check_btn = ctk.CTkButton(btn_col, text="\u2713  Check", width=130,
                                        height=34, corner_radius=8,
                                        fg_color=theme.PRIMARY, hover_color=theme.HOVER_PRIMARY,
                                        command=self._check_code)
        self._check_btn.pack(pady=(0, 4))

        self._paste_btn = ctk.CTkButton(btn_col, text="\u2398  Paste", width=130,
                                        height=26, corner_radius=6,
                                        fg_color=theme.BTN_TERTIARY, hover_color=theme.HOVER_TERTIARY,
                                        font=ctk.CTkFont(size=theme.FONT_BODY),
                                        command=self._paste_from_clipboard)
        self._paste_btn.pack()

        self._check_status = ctk.CTkLabel(check_frame, text="",
                                          font=ctk.CTkFont(size=theme.FONT_BODY),
                                          text_color=theme.INFO, anchor="w")
        self._check_status.pack(fill="x", padx=12, pady=(0, 3))

        self._check_progress = ctk.CTkProgressBar(check_frame, height=4,
                                                   fg_color=theme.PROGRESS_TRACK,
                                                   progress_color=theme.PRIMARY)
        self._check_progress.pack(fill="x", padx=12, pady=(0, 5))
        self._check_progress.set(0)

        self._check_results = ctk.CTkFrame(check_frame, fg_color="transparent")
        self._check_results.pack(fill="x", padx=12, pady=(0, 10))

    def _get_paths(self):
        """Resolve mods, plugins, and exefs paths from current settings."""
        settings = self.app.config_manager.settings
        mods_path = settings.mods_path
        plugins_path = settings.plugins_path
        sdmc = settings.eden_sdmc_path
        emulator = settings.emulator or ""

        # Try to derive from SDMC if direct paths not set
        if sdmc:
            from src.paths import derive_mods_path, derive_plugins_path, SSBU_TITLE_ID
            if not mods_path:
                mods_path = derive_mods_path(sdmc)
            if not plugins_path:
                plugins_path = derive_plugins_path(sdmc)
            exefs_path = (sdmc / "atmosphere" / "contents" / SSBU_TITLE_ID / "exefs")
        else:
            exefs_path = None

        emulator_version = str(getattr(settings, "emulator_version", "") or "")
        game_version = str(getattr(settings, "game_version", "") or "")
        return mods_path, plugins_path, exefs_path, emulator, emulator_version, game_version

    def _strict_audio_enabled(self) -> bool:
        return bool(self._strict_audio_var.get())

    def _strict_environment_enabled(self) -> bool:
        return bool(self._strict_environment_var.get())

    def _on_strict_audio_toggle(self):
        self._persist_checker_policy_settings()

    def _on_strict_environment_toggle(self):
        self._persist_checker_policy_settings()

    def _persist_checker_policy_settings(self):
        settings = self.app.config_manager.settings
        settings.online_strict_audio_sync = self._strict_audio_enabled()
        settings.online_strict_environment_match = self._strict_environment_enabled()
        self.app.config_manager.save(settings)

    def _generate_code(self):
        if self._checker_generating:
            return

        (
            mods_path,
            plugins_path,
            exefs_path,
            emulator,
            emulator_version,
            game_version,
        ) = self._get_paths()

        if self._strict_environment_enabled():
            missing_env = []
            if not emulator:
                missing_env.append("emulator")
            if not emulator_version:
                missing_env.append("emulator build")
            if not game_version:
                missing_env.append("game version")
            if missing_env:
                messagebox.showwarning(
                    "Missing Metadata",
                    "Strict Environment Match is enabled, but required metadata is missing:\n\n"
                    + ", ".join(missing_env)
                    + "\n\nSet these values in Settings -> Online Compatibility Metadata.",
                )
                return

        if not mods_path or not mods_path.exists():
            messagebox.showwarning("Warning",
                "Set up your emulator SDMC path in Settings first.")
            return

        self._checker_generating = True
        self._gen_btn.configure(state="disabled", text="Generating...")
        self._gen_status.configure(text="Starting scan...", text_color=theme.INFO)
        self._gen_progress.set(0)

        for w in self._gen_code_frame.winfo_children():
            w.destroy()

        def progress_cb(msg, frac):
            try:
                self.after(0, lambda: self._gen_status.configure(text=msg))
                self.after(0, lambda: self._gen_progress.set(frac))
            except Exception:
                pass

        def run():
            try:
                from src.core.compat_checker import (
                    generate_fingerprint, encode_fingerprint
                )
                fp = generate_fingerprint(
                    mods_path=mods_path,
                    plugins_path=plugins_path,
                    exefs_path=exefs_path,
                    emulator_name=emulator,
                    emulator_version=emulator_version,
                    game_version=game_version,
                    strict_audio_sync=self._strict_audio_enabled(),
                    strict_environment_match=self._strict_environment_enabled(),
                    progress_callback=progress_cb,
                )
                code = encode_fingerprint(fp)

                self.after(0, lambda: self._show_generated_code(fp, code))
            except Exception as e:
                logger.error("CompatChecker", f"Code generation failed: {e}")
                self.after(0, lambda: self._gen_status.configure(
                    text=f"Error: {e}", text_color=theme.ACCENT))
            finally:
                self._checker_generating = False
                self.after(0, lambda: self._gen_btn.configure(
                    state="normal", text="\u2192  Generate My Code"))

        threading.Thread(target=run, daemon=True).start()

    def _show_generated_code(self, fp, code: str):
        from src.core.compat_checker import CompatFingerprint

        opt_text = ""
        if fp.optional_plugins:
            opt_text = f", {len(fp.optional_plugins)} optional"
        self._gen_status.configure(
            text=f"Done! {len(fp.gameplay_hashes)} gameplay files, "
                 f"{len(fp.plugin_hashes)} plugins{opt_text} fingerprinted. "
                 f"Audio policy: {'Strict' if getattr(fp, 'strict_audio_sync', False) else 'Standard'}. "
                 f"Env policy: {'Strict' if getattr(fp, 'strict_environment_match', False) else 'Standard'}. "
                 f"Digest: {fp.digest[:16]}...",
            text_color=theme.SUCCESS)
        self._gen_progress.set(1.0)

        for w in self._gen_code_frame.winfo_children():
            w.destroy()

        code_box = ctk.CTkTextbox(self._gen_code_frame, height=70,
                                  fg_color=theme.BG_INPUT,
                                  font=ctk.CTkFont(family="Consolas", size=theme.FONT_CAPTION),
                                  border_width=1, border_color=theme.SUCCESS)
        code_box.pack(fill="x", pady=(5, 5))
        code_box.insert("1.0", code)

        btn_row = ctk.CTkFrame(self._gen_code_frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 5))

        ctk.CTkButton(btn_row, text="\u2398  Copy Code", width=130,
                      height=30, corner_radius=6,
                      fg_color=theme.SUCCESS, hover_color=theme.HOVER_SUCCESS_ALT,
                      command=lambda: self._copy_text(code, "Compatibility code")
                      ).pack(side="left", padx=(0, 8))

        if fp.gameplay_mod_names:
            mods_text = ", ".join(fp.gameplay_mod_names[:5])
            if len(fp.gameplay_mod_names) > 5:
                mods_text += f" +{len(fp.gameplay_mod_names) - 5} more"
            ctk.CTkLabel(btn_row, text=f"Gameplay mods: {mods_text}",
                         font=ctk.CTkFont(size=theme.FONT_CAPTION), text_color=theme.TEXT_DIM,
                         anchor="w").pack(side="left", fill="x", expand=True)

        env_bits = [f"Emulator: {fp.emulator or 'Unknown'}"]
        if getattr(fp, "emulator_version", ""):
            env_bits.append(f"Build: {fp.emulator_version}")
        if getattr(fp, "game_version", ""):
            env_bits.append(f"Game: {fp.game_version}")
        ctk.CTkLabel(
            self._gen_code_frame,
            text=" \u00b7 ".join(env_bits),
            font=ctk.CTkFont(size=theme.FONT_CAPTION),
            text_color=theme.TEXT_SCAN_HINT,
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        if not getattr(fp, "emulator_version", "") or not getattr(fp, "game_version", ""):
            ctk.CTkLabel(
                self._gen_code_frame,
                text=(
                    "▲  Recommended: set Emulator Build and SSBU Game Version in Settings "
                    "for stronger environment matching."
                ),
                font=ctk.CTkFont(size=theme.FONT_CAPTION),
                text_color=theme.WARNING,
                anchor="w",
                wraplength=theme.WRAP_STANDARD,
                justify="left",
            ).pack(fill="x", pady=(0, 4))

        if not fp.gameplay_hashes and not fp.plugin_hashes:
            note = ctk.CTkLabel(self._gen_code_frame,
                text="\u2713  No gameplay-affecting mods detected under current policy â€” "
                     "you appear to be running vanilla or visual-only content.",
                font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.SUCCESS, anchor="w",
                wraplength=theme.WRAP_STANDARD, justify="left")
            note.pack(fill="x", pady=(0, 5))

    def _paste_from_clipboard(self):
        try:
            text = self.clipboard_get()
            if text:
                self._check_entry.delete("1.0", "end")
                self._check_entry.insert("1.0", text.strip())
        except Exception:
            pass

    def _check_code(self):
        """Check local setup against a pasted compatibility code."""
        if self._checker_checking:
            return

        code = self._check_entry.get("1.0", "end").strip()
        if not code:
            messagebox.showwarning("Warning", "Paste a compatibility code first.")
            return

        from src.core.compat_checker import decode_fingerprint
        ref_fp = decode_fingerprint(code)
        if ref_fp is None:
            messagebox.showerror("Invalid Code",
                "The pasted code is invalid or uses an unsupported format.\n\n"
                "Make sure you copied the entire code starting with "
                "'SSBU-COMPAT-v2:' or 'SSBU-COMPAT-v3:'.")
            return
        strict_audio_sync = bool(getattr(ref_fp, "strict_audio_sync", False))
        strict_environment_match = bool(getattr(ref_fp, "strict_environment_match", False))

        (
            mods_path,
            plugins_path,
            exefs_path,
            emulator,
            emulator_version,
            game_version,
        ) = self._get_paths()

        if not mods_path or not mods_path.exists():
            messagebox.showwarning("Warning",
                "Set up your emulator SDMC path in Settings first.")
            return

        self._checker_checking = True
        self._check_btn.configure(state="disabled", text="Checking...")
        self._check_status.configure(
            text=(
                "Generating local fingerprint "
                f"(host audio policy: {'Strict' if strict_audio_sync else 'Standard'}, "
                f"env policy: {'Strict' if strict_environment_match else 'Standard'})..."
            ),
            text_color=theme.INFO,
        )
        self._check_progress.set(0)

        for w in self._check_results.winfo_children():
            w.destroy()

        def progress_cb(msg, frac):
            try:
                self.after(0, lambda: self._check_status.configure(text=msg))
                self.after(0, lambda: self._check_progress.set(frac))
            except Exception:
                pass

        def run():
            try:
                from src.core.compat_checker import (
                    generate_fingerprint, compare_fingerprints
                )
                local_fp = generate_fingerprint(
                    mods_path=mods_path,
                    plugins_path=plugins_path,
                    exefs_path=exefs_path,
                    emulator_name=emulator,
                    emulator_version=emulator_version,
                    game_version=game_version,
                    strict_audio_sync=strict_audio_sync,
                    strict_environment_match=strict_environment_match,
                    progress_callback=progress_cb,
                )
                result = compare_fingerprints(local_fp, ref_fp)

                self.after(0, lambda: self._show_check_result(result, ref_fp, local_fp))
            except Exception as e:
                logger.error("CompatChecker", f"Check failed: {e}")
                self.after(0, lambda: self._check_status.configure(
                    text=f"Error: {e}", text_color=theme.ACCENT))
            finally:
                self._checker_checking = False
                self.after(0, lambda: self._check_btn.configure(
                    state="normal", text="\u2713  Check"))

        threading.Thread(target=run, daemon=True).start()

    def _show_check_result(self, result, ref_fp, local_fp):
        self._check_progress.set(1.0)

        for w in self._check_results.winfo_children():
            w.destroy()

        if result.compatible:
            self._check_status.configure(
                text="\u2713  COMPATIBLE â€” Your gameplay setup matches!",
                text_color=theme.SUCCESS)

            compat_frame = ctk.CTkFrame(self._check_results, fg_color=theme.BG_SUCCESS_RESULT,
                                        corner_radius=8, border_width=1,
                                        border_color=theme.SUCCESS)
            compat_frame.pack(fill="x", pady=5)

            ctk.CTkLabel(compat_frame,
                text="\u2713  COMPATIBLE",
                font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"),
                text_color=theme.SUCCESS, anchor="w"
            ).pack(fill="x", padx=12, pady=(10, 3))

            ctk.CTkLabel(compat_frame,
                text="Your gameplay-affecting files match the host's setup. "
                     "You're good to play online without desyncs!",
                font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), text_color=theme.SUCCESS_DETAIL, anchor="w",
                wraplength=theme.WRAP_STANDARD, justify="left"
            ).pack(fill="x", padx=12, pady=(0, 5))

            details = []
            details.append(f"Gameplay files compared: {len(ref_fp.gameplay_hashes)}")
            details.append(f"Plugins compared: {len(ref_fp.plugin_hashes)}")
            details.append(f"Host emulator: {ref_fp.emulator or 'Unknown'}")
            if getattr(ref_fp, "emulator_version", ""):
                details.append(f"Host emulator version: {ref_fp.emulator_version}")
            if getattr(ref_fp, "game_version", ""):
                details.append(f"Host game version: {ref_fp.game_version}")
            details.append(
                f"Host strict audio policy: "
                f"{'ON' if getattr(ref_fp, 'strict_audio_sync', False) else 'OFF'}"
            )
            details.append(
                f"Host strict environment policy: "
                f"{'ON' if getattr(ref_fp, 'strict_environment_match', False) else 'OFF'}"
            )
            details.append(f"Code generated: {ref_fp.timestamp or 'Unknown'}")

            for d in details:
                ctk.CTkLabel(compat_frame, text=f"  \u2022  {d}",
                             font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.SUCCESS_RULE,
                             anchor="w").pack(fill="x", padx=12, pady=1)

            ctk.CTkFrame(compat_frame, height=8, fg_color="transparent").pack()

        else:
            self._check_status.configure(
                text=f"\u2716  INCOMPATIBLE â€” {result.issue_count} issue(s) found",
                text_color=theme.ACCENT)

            incompat_frame = ctk.CTkFrame(self._check_results, fg_color=theme.BG_ERROR_RESULT,
                                          corner_radius=8, border_width=1,
                                          border_color=theme.ACCENT)
            incompat_frame.pack(fill="x", pady=5)

            ctk.CTkLabel(incompat_frame,
                text=f"\u2716  INCOMPATIBLE â€” {result.issue_count} issue(s)",
                font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"),
                text_color=theme.ACCENT, anchor="w"
            ).pack(fill="x", padx=12, pady=(10, 3))

            ctk.CTkLabel(incompat_frame,
                text="Your gameplay setup differs from the host's. Playing online "
                     "will likely cause desyncs. See details below:",
                font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), text_color=theme.DANGER_DETAIL, anchor="w",
                wraplength=theme.WRAP_STANDARD, justify="left"
            ).pack(fill="x", padx=12, pady=(0, 8))

            # Environment issues (emulator/game version mismatches)
            if getattr(result, "environment_issues", None):
                self._build_issue_group(incompat_frame,
                    f"\u2716  Environment Mismatch ({len(result.environment_issues)})",
                    "Core environment metadata differs between setups "
                    "(emulator or game version).",
                    result.environment_issues, theme.ACCENT)

            # Missing gameplay files
            if result.missing_gameplay:
                self._build_issue_group(incompat_frame,
                    f"\u2716  Missing Gameplay Files ({len(result.missing_gameplay)})",
                    "The host has these gameplay files but you don't. "
                    "You may be missing a required gameplay mod.",
                    result.missing_gameplay, theme.ACCENT)

            # Extra gameplay files
            if result.extra_gameplay:
                self._build_issue_group(incompat_frame,
                    f"\u26a0  Extra Gameplay Files ({len(result.extra_gameplay)})",
                    "You have these gameplay files but the host doesn't. "
                    "You have a gameplay mod the host doesn't use.",
                    result.extra_gameplay, theme.WARNING)

            # Mismatched gameplay files
            if result.mismatched_gameplay:
                self._build_issue_group(incompat_frame,
                    f"\u2716  Mismatched Gameplay Files ({len(result.mismatched_gameplay)})",
                    "Both you and the host have these files but they differ. "
                    "You may have a different version of the same mod.",
                    result.mismatched_gameplay, theme.ACCENT)

            # Plugin issues
            if result.missing_plugins:
                self._build_issue_group(incompat_frame,
                    f"\u2716  Missing Plugins ({len(result.missing_plugins)})",
                    "The host has these gameplay plugins but you don't.",
                    result.missing_plugins, theme.ACCENT)

            if result.extra_plugins:
                self._build_issue_group(incompat_frame,
                    f"\u26a0  Extra Plugins ({len(result.extra_plugins)})",
                    "You have these gameplay plugins but the host doesn't.",
                    result.extra_plugins, theme.WARNING)

            if result.mismatched_plugins:
                self._build_issue_group(incompat_frame,
                    f"\u2716  Mismatched Plugins ({len(result.mismatched_plugins)})",
                    "Both sides have these plugins but versions differ.",
                    result.mismatched_plugins, theme.ACCENT)

            # ExeFS
            if result.mismatched_exefs:
                self._build_issue_group(incompat_frame,
                    f"\u26a0  ExeFS Differences ({len(result.mismatched_exefs)})",
                    "Framework-level hooks differ between setups.",
                    result.mismatched_exefs, theme.WARNING)

            ctk.CTkFrame(incompat_frame, height=8, fg_color="transparent").pack()

        # Warnings (shown for both compatible and incompatible)
        if result.warnings:
            warn_frame = ctk.CTkFrame(self._check_results, fg_color=theme.BG_WARNING_TINT,
                                      corner_radius=8, border_width=1,
                                      border_color=theme.WARNING)
            warn_frame.pack(fill="x", pady=5)

            ctk.CTkLabel(warn_frame,
                text=f"\u25b2  Warnings ({len(result.warnings)})",
                font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS, weight="bold"),
                text_color=theme.WARNING, anchor="w"
            ).pack(fill="x", padx=12, pady=(10, 5))

            for w in result.warnings:
                ctk.CTkLabel(warn_frame, text=f"  \u2022  {w}",
                             font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.WARNING_DETAIL,
                             anchor="w", wraplength=theme.WRAP_NARROW, justify="left"
                             ).pack(fill="x", padx=12, pady=1)

            ctk.CTkFrame(warn_frame, height=8, fg_color="transparent").pack()

        # Optional plugin differences (informational, shown for both outcomes)
        has_opt_diff = (result.optional_only_local or result.optional_only_remote)
        if has_opt_diff:
            opt_frame = ctk.CTkFrame(self._check_results, fg_color=theme.BG_INFO_TINT,
                                     corner_radius=8, border_width=1,
                                     border_color=theme.INFO_BORDER)
            opt_frame.pack(fill="x", pady=5)

            total_opt = len(result.optional_only_local) + len(result.optional_only_remote)
            ctk.CTkLabel(opt_frame,
                text=f"\u2139  Setup Differences ({total_opt} optional plugin(s))",
                font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS, weight="bold"),
                text_color=theme.INFO_BORDER, anchor="w"
            ).pack(fill="x", padx=12, pady=(10, 3))

            ctk.CTkLabel(opt_frame,
                text="These plugins don't affect gameplay sync and won't cause desyncs. "
                     "They only enhance the local experience for whoever has them installed.",
                font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.INFO_DETAIL, anchor="w",
                wraplength=theme.WRAP_NARROW, justify="left"
            ).pack(fill="x", padx=12, pady=(0, 6))

            if result.optional_only_local:
                ctk.CTkLabel(opt_frame,
                    text="You have (host doesn't):",
                    font=ctk.CTkFont(size=theme.FONT_BODY, weight="bold"),
                    text_color=theme.INFO_SUB, anchor="w"
                ).pack(fill="x", padx=14, pady=(2, 1))
                for p in result.optional_only_local:
                    ctk.CTkLabel(opt_frame, text=f"    \u2022  {p}",
                                 font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.INFO_LIST,
                                 anchor="w").pack(fill="x", padx=12, pady=0)

            if result.optional_only_remote:
                ctk.CTkLabel(opt_frame,
                    text="Host has (you don't):",
                    font=ctk.CTkFont(size=theme.FONT_BODY, weight="bold"),
                    text_color=theme.INFO_SUB, anchor="w"
                ).pack(fill="x", padx=14, pady=(4, 1))
                for p in result.optional_only_remote:
                    ctk.CTkLabel(opt_frame, text=f"    \u2022  {p}",
                                 font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.INFO_LIST,
                                 anchor="w").pack(fill="x", padx=12, pady=0)

            ctk.CTkFrame(opt_frame, height=8, fg_color="transparent").pack()

    def _build_issue_group(self, parent, title: str, description: str,
                           items: list[str], color: str):
        grp = ctk.CTkFrame(parent, fg_color=theme.BG_CARD_INNER, corner_radius=6)
        grp.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(grp, text=title,
                     font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM, weight="bold"),
                     text_color=color, anchor="w"
                     ).pack(fill="x", padx=10, pady=(8, 2))

        ctk.CTkLabel(grp, text=description,
                     font=ctk.CTkFont(size=theme.FONT_CAPTION), text_color=theme.TEXT_DIM,
                     anchor="w", wraplength=theme.WRAP_NARROW, justify="left"
                     ).pack(fill="x", padx=10, pady=(0, 5))

        # Show up to 15 items, collapse the rest
        display_items = items[:15]
        for item in display_items:
            # Shorten long paths for readability
            display = item
            if len(display) > 80:
                display = "..." + display[-77:]
            ctk.CTkLabel(grp, text=f"    {display}",
                         font=ctk.CTkFont(family="Consolas", size=theme.FONT_CAPTION),
                         text_color=theme.TEXT_HINT, anchor="w"
                         ).pack(fill="x", padx=10, pady=0)

        if len(items) > 15:
            ctk.CTkLabel(grp,
                text=f"    ... and {len(items) - 15} more",
                font=ctk.CTkFont(size=theme.FONT_CAPTION), text_color=theme.TEXT_DISABLED, anchor="w"
            ).pack(fill="x", padx=10, pady=(2, 0))

        ctk.CTkFrame(grp, height=6, fg_color="transparent").pack()

    # â”€â”€â”€ Utility â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _copy_text(self, text: str, label: str = "Text"):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Copied", f"{label} copied to clipboard!")
        except Exception:
            messagebox.showerror("Error", "Failed to copy to clipboard.")

    def on_show(self):
        super().on_show()

    def _analyze_mods(self):
        settings = self.app.config_manager.settings
        if not settings.mods_path:
            messagebox.showwarning("Warning", "Set up your emulator SDMC path in Settings first.")
            return

        for w in self.analysis_content.winfo_children():
            w.destroy()

        try:
            mods = self.app.mod_manager.list_mods()
            enabled = [m for m in mods if m.status == ModStatus.ENABLED]
        except Exception as e:
            ctk.CTkLabel(self.analysis_content,
                         text=f"Error loading mods: {e}",
                         font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), text_color=theme.ACCENT
                         ).pack(anchor="w", pady=5)
            return

        if not enabled:
            ctk.CTkLabel(self.analysis_content,
                         text="No enabled mods found. Enable mods in the Mods page first.",
                         font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), text_color=theme.TEXT_DIM
                         ).pack(anchor="w", pady=5)
            self._analyzed = True
            return

        # Categorize each mod
        categorized = {}
        for cat_key in COMPAT_CATEGORIES:
            categorized[cat_key] = []

        for mod in enabled:
            cat = categorize_mod_online(mod)
            categorized[cat].append(mod)

        summary_frame = ctk.CTkFrame(self.analysis_content, fg_color=theme.BG_CARD_INNER, corner_radius=8)
        summary_frame.pack(fill="x", pady=(5, 10))

        summary_items = []
        for cat_key, cat_info in COMPAT_CATEGORIES.items():
            count = len(categorized[cat_key])
            if count:
                summary_items.append(f"{cat_info['icon']} {cat_info['label']}: {count}")

        ctk.CTkLabel(summary_frame,
            text=f"Analyzed {len(enabled)} enabled mods:",
            font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS, weight="bold"), anchor="w"
        ).pack(fill="x", padx=12, pady=(10, 5))

        for item in summary_items:
            ctk.CTkLabel(summary_frame, text=f"  {item}",
                         font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), anchor="w"
                         ).pack(fill="x", padx=12, pady=1)

        ctk.CTkFrame(summary_frame, height=10, fg_color="transparent").pack()

        for cat_key, cat_info in COMPAT_CATEGORIES.items():
            mods_in_cat = categorized[cat_key]
            if not mods_in_cat:
                continue

            cat_frame = ctk.CTkFrame(self.analysis_content, fg_color=theme.BG_CARD_INNER, corner_radius=8)
            cat_frame.pack(fill="x", pady=5)

            cat_header = ctk.CTkFrame(cat_frame, fg_color="transparent")
            cat_header.pack(fill="x", padx=12, pady=(10, 5))

            ctk.CTkLabel(cat_header,
                text=f"{cat_info['icon']}  {cat_info['label']} ({len(mods_in_cat)})",
                font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS, weight="bold"),
                text_color=cat_info['color'], anchor="w"
            ).pack(side="left")

            ctk.CTkLabel(cat_frame, text=cat_info['description'],
                         font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.TEXT_DIM,
                         anchor="w", wraplength=theme.WRAP_STANDARD, justify="left"
                         ).pack(fill="x", padx=12, pady=(0, 5))

            for mod in sorted(mods_in_cat, key=lambda m: m.name.lower()):
                mod_row = ctk.CTkFrame(cat_frame, fg_color="transparent", height=28)
                mod_row.pack(fill="x", padx=16, pady=1)
                mod_row.pack_propagate(False)

                ctk.CTkLabel(mod_row,
                    text=f"  \u2022  {mod.original_name}",
                    font=ctk.CTkFont(size=theme.FONT_BODY),
                    text_color=theme.TEXT_SECONDARY, anchor="w"
                ).pack(side="left")

                if mod.metadata and mod.metadata.categories:
                    cats_text = ", ".join(mod.metadata.categories[:3])
                    ctk.CTkLabel(mod_row,
                        text=cats_text,
                        font=ctk.CTkFont(size=theme.FONT_CAPTION),
                        text_color=theme.TEXT_INACTIVE, anchor="e"
                    ).pack(side="right", padx=10)

            ctk.CTkFrame(cat_frame, height=8, fg_color="transparent").pack()

        self._show_share_summary(categorized, enabled)
        self._analyzed = True
        logger.info("OnlineCompat", f"Analyzed {len(enabled)} mods for online compatibility")

    def _show_share_summary(self, categorized: dict, enabled: list):
        try:
            self.share_section.pack_forget()
        except Exception:
            pass

        for w in self.share_section.winfo_children():
            w.destroy()

        self.share_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(self.share_section, text="Shareable Summary",
                     font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(self.share_section,
                     text="Copy this summary to share with friends so they know what mods they need.",
                     font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), text_color=theme.TEXT_MUTED, anchor="w"
                     ).pack(fill="x", padx=15, pady=(0, 5))

        lines = ["=== SSBU Online Mod Setup ===", ""]

        required = categorized.get("required_both", [])
        if required:
            lines.append("REQUIRED BY BOTH PLAYERS (gameplay mods):")
            for m in sorted(required, key=lambda m: m.name.lower()):
                lines.append(f"  - {m.original_name}")
            lines.append("")

        visual = categorized.get("visual_only", [])
        audio = categorized.get("audio_only", [])
        client_side = visual + audio
        if client_side:
            lines.append(f"CLIENT-SIDE ONLY ({len(client_side)} mods - only I need these):")
            for m in sorted(client_side, key=lambda m: m.name.lower()):
                lines.append(f"  - {m.original_name}")
            lines.append("")

        stages = categorized.get("stage_mods", [])
        if stages:
            lines.append("CUSTOM STAGES (both need if stage is selected):")
            for m in sorted(stages, key=lambda m: m.name.lower()):
                lines.append(f"  - {m.original_name}")
            lines.append("")

        lines.append(f"Total enabled mods: {len(enabled)}")

        summary_text = "\n".join(lines)

        text_box = ctk.CTkTextbox(self.share_section, height=theme.HEIGHT_SUMMARY_BOX, fg_color=theme.BG_CARD_DEEP,
                                  font=ctk.CTkFont(family="Consolas", size=theme.FONT_BODY))
        text_box.pack(fill="x", padx=15, pady=5)
        text_box.insert("1.0", summary_text)

        copy_btn = ctk.CTkButton(self.share_section, text="\u2398  Copy to Clipboard",
                                 width=160, fg_color=theme.PRIMARY, hover_color=theme.HOVER_PRIMARY,
                                 command=lambda: self._copy_text(summary_text, "Summary"),
                                 height=34, corner_radius=8)
        copy_btn.pack(padx=15, pady=(5, 15), anchor="w")

