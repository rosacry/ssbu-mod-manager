"""Online Compatibility page — guides users on what mods are needed for online play
and provides a Compatibility Code system for tournament/multiplayer verification.

Features:
1. Online Mod Compatibility Guide — explains which mods need to match
2. Mod Analysis — categorizes your enabled mods by online impact
3. Compatibility Checker — generate a code the TO/host shares; participants
   paste it to verify their gameplay setup is compatible.

The checker ONLY fingerprints gameplay-affecting files (fighter params, stage
collision, gameplay plugins, ExeFS patches). Visual-only mods (skins, audio,
UI, effects) are completely ignored — they never cause desyncs.
"""

import threading
import customtkinter as ctk
from pathlib import Path
from tkinter import messagebox
from src.ui.base_page import BasePage
from src.models.mod import Mod, ModStatus
from src.utils.logger import logger


# ─── Online compatibility categories ─────────────────────────────────

COMPAT_CATEGORIES = {
    "required_both": {
        "label": "Required by Both Players",
        "icon": "\u26a0",
        "color": "#e94560",
        "description": "These mods change gameplay mechanics and MUST be identical "
                       "on both players' setups to avoid desyncs.",
    },
    "visual_only": {
        "label": "Client-Side Only (Visual)",
        "icon": "\u2713",
        "color": "#2fa572",
        "description": "These mods only change visuals (skins, textures, UI). "
                       "Only the player using them needs to have them installed.",
    },
    "audio_only": {
        "label": "Client-Side Only (Audio)",
        "icon": "\u2713",
        "color": "#2fa572",
        "description": "These mods only change audio/music. "
                       "Only the player using them needs to have them installed.",
    },
    "stage_mods": {
        "label": "Shared if Stage is Used",
        "icon": "\u25b2",
        "color": "#d4a017",
        "description": "Custom stages must be installed by both players if that stage is selected. "
                       "Standard stages are fine with one-sided mods.",
    },
    "unknown": {
        "label": "Unknown / Mixed",
        "icon": "?",
        "color": "#888888",
        "description": "Could not determine online impact. Check mod documentation.",
    },
}

# Keywords and patterns for categorizing mods
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

# Known gameplay-modifying plugins
GAMEPLAY_PLUGINS = {
    "libhdr.nro", "libhdr_hooks.nro", "libtraining_modpack.nro",
    "libnro_hook.nro",
}

# Known visual-only plugins
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

    # Check gameplay keywords (highest priority)
    for kw in GAMEPLAY_KEYWORDS:
        if kw in name_lower:
            return "required_both"

    # Check if mod has PRC files with gameplay-related paths
    if mod.metadata and mod.metadata.has_prc:
        # PRC files in fighter/ or param/ directories are gameplay-affecting
        if mod.metadata.fighter_kind:
            return "required_both"

    # Check audio keywords
    for kw in AUDIO_KEYWORDS:
        if kw in name_lower:
            return "audio_only"
    if mod.metadata and mod.metadata.has_music:
        return "audio_only"
    if "Audio" in cats:
        return "audio_only"

    # Check stage keywords
    for kw in STAGE_KEYWORDS:
        if kw in name_lower:
            return "stage_mods"
    if "Stage" in cats:
        return "stage_mods"

    # Check visual keywords
    for kw in VISUAL_KEYWORDS:
        if kw in name_lower:
            return "visual_only"
    if mod.metadata and mod.metadata.has_css_data:
        return "visual_only"
    if any(c in cats for c in ("Character", "UI", "Effect")):
        return "visual_only"

    # Check by file types if we have metadata
    if mod.metadata:
        # Mods with only visual data (textures, models) are client-side
        if not mod.metadata.has_prc and not mod.metadata.has_msbt and not mod.metadata.has_xmsbt:
            return "visual_only"

    return "unknown"


class OnlineCompatPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._analyzed = False
        self._checker_generating = False
        self._checker_checking = False
        self._build_ui()

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(25, 5))

        ctk.CTkLabel(header, text="Online Compatibility",
                     font=ctk.CTkFont(size=24, weight="bold"), anchor="w"
                     ).pack(side="left")

        ctk.CTkButton(header, text="\u21bb  Analyze Mods", width=140,
                      fg_color="#1f538d", hover_color="#163b6a",
                      command=self._analyze_mods, height=34, corner_radius=8
                      ).pack(side="right")

        desc = ctk.CTkLabel(self,
            text="Understand which mods are needed by both players for online multiplayer via emulator LDN networks, "
                 "and which mods are client-side only. Use the Compatibility Checker to verify setups before playing.",
            font=ctk.CTkFont(size=12), text_color="#999999", anchor="w", wraplength=800,
            justify="left")
        desc.pack(fill="x", padx=30, pady=(0, 15))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=30)
        self._scroll = scroll

        # === Compatibility Checker (TOP — most important feature) ===
        self._build_checker_section(scroll)

        # === Info Guide ===
        guide_section = ctk.CTkFrame(scroll, fg_color="#242438", corner_radius=10)
        guide_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(guide_section, text="Online Mod Compatibility Guide",
                     font=ctk.CTkFont(size=16, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 10))

        rules = [
            ("\u26a0  Gameplay / Moveset Mods (e.g., HDR)",
             "BOTH players MUST have the exact same gameplay mods installed. "
             "Different gameplay code causes immediate desyncs. Both players also need "
             "compatible versions of required plugins (ARCropolis, Skyline).",
             "#e94560"),
            ("\u2713  Custom Skins / Costumes",
             "Only the player using the custom skin needs it installed. The other player "
             "will see the default character skin. No desync occurs because skins are "
             "purely visual and processed client-side only.",
             "#2fa572"),
            ("\u2713  Custom Audio / Music",
             "Only the player using custom audio needs it installed. Music and sound "
             "effects are processed locally. The other player hears their own music.",
             "#2fa572"),
            ("\u25b2  Custom Stages",
             "If a custom stage is selected for play, BOTH players need the same stage mod. "
             "If playing on standard/vanilla stages, no stage mods are needed by either player.",
             "#d4a017"),
            ("\u2713  UI / CSS Mods",
             "Character Select Screen mods, portraits, stock icons, and other UI changes "
             "are client-side only. Only the player using them needs them.",
             "#2fa572"),
            ("\u26a0  Plugins (ARCropolis, Skyline)",
             "Both players should use compatible versions of core plugins. ARCropolis "
             "itself doesn't usually cause desyncs, but gameplay-modifying plugins "
             "(like HDR hooks) MUST match on both sides.",
             "#d4a017"),
        ]

        for title, desc_text, color in rules:
            rule_frame = ctk.CTkFrame(guide_section, fg_color="#1e1e38", corner_radius=6)
            rule_frame.pack(fill="x", padx=15, pady=3)

            ctk.CTkLabel(rule_frame, text=title,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=color, anchor="w"
                         ).pack(fill="x", padx=12, pady=(8, 2))
            ctk.CTkLabel(rule_frame, text=desc_text,
                         font=ctk.CTkFont(size=11), text_color="#aaaaaa",
                         anchor="w", wraplength=700, justify="left"
                         ).pack(fill="x", padx=12, pady=(0, 8))

        # Emulator note
        emu_note = ctk.CTkFrame(guide_section, fg_color="#1a1a30", corner_radius=6)
        emu_note.pack(fill="x", padx=15, pady=(10, 15))
        ctk.CTkLabel(emu_note,
            text="\u2139  Important: Emulator Cross-Compatibility",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#6688bb", anchor="w"
        ).pack(fill="x", padx=12, pady=(10, 2))
        ctk.CTkLabel(emu_note,
            text="Different emulators run separate multiplayer networks. Ryujinx LDN rooms, "
                 "Yuzu rooms, and other emulator lobbies are NOT cross-compatible. Both players "
                 "must use the same emulator (or a compatible fork) to play together online. "
                 "Use the Migration page to transfer your data between emulators.",
            font=ctk.CTkFont(size=11), text_color="#8899aa", anchor="w",
            wraplength=700, justify="left"
        ).pack(fill="x", padx=12, pady=(0, 10))

        # === Analysis Results ===
        self.analysis_section = ctk.CTkFrame(scroll, fg_color="#242438", corner_radius=10)
        self.analysis_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(self.analysis_section, text="Your Mod Analysis",
                     font=ctk.CTkFont(size=16, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(self.analysis_section,
                     text="Click 'Analyze Mods' to categorize your enabled mods by online compatibility.",
                     font=ctk.CTkFont(size=12), text_color="#999999", anchor="w"
                     ).pack(fill="x", padx=15, pady=(0, 5))

        self.analysis_content = ctk.CTkFrame(self.analysis_section, fg_color="transparent")
        self.analysis_content.pack(fill="x", padx=15, pady=(5, 15))

        # === Shareable Summary ===
        self.share_section = ctk.CTkFrame(scroll, fg_color="#242438", corner_radius=10)
        # Not shown until analysis is done

    # ─── Compatibility Checker ────────────────────────────────────────

    def _build_checker_section(self, parent):
        """Build the Compatibility Code checker section."""
        checker = ctk.CTkFrame(parent, fg_color="#242438", corner_radius=10)
        checker.pack(fill="x", pady=(0, 15))
        self._checker_frame = checker

        # Section header
        header_row = ctk.CTkFrame(checker, fg_color="transparent")
        header_row.pack(fill="x", padx=15, pady=(15, 5))

        ctk.CTkLabel(header_row, text="\u2611  Compatibility Checker",
                     font=ctk.CTkFont(size=18, weight="bold"), anchor="w"
                     ).pack(side="left")

        ctk.CTkLabel(checker,
            text="Generate a compatibility code to share with tournament hosts or friends. "
                 "Only gameplay-affecting files are fingerprinted — skins, music, and UI mods are "
                 "completely ignored since they never cause desyncs.",
            font=ctk.CTkFont(size=12), text_color="#999999", anchor="w",
            wraplength=760, justify="left"
        ).pack(fill="x", padx=15, pady=(0, 12))

        # ── Tournament workflow explanation ──
        workflow = ctk.CTkFrame(checker, fg_color="#1a1a30", corner_radius=8)
        workflow.pack(fill="x", padx=15, pady=(0, 12))

        ctk.CTkLabel(workflow,
            text="\u2139  How It Works (Tournament Setup)",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#6688bb", anchor="w"
        ).pack(fill="x", padx=12, pady=(10, 4))

        steps = [
            "1.  The host/TO clicks 'Generate My Code' and copies the code.",
            "2.  The host pastes the code in their Discord server or tournament page.",
            "3.  Each participant pastes the host's code into 'Check Against Code' below.",
            "4.  The tool compares ONLY gameplay files — if you have different skins or music,",
            "     that's fine! Only mismatched gameplay mods, plugins, or stage data are flagged.",
        ]
        for step in steps:
            ctk.CTkLabel(workflow, text=step,
                         font=ctk.CTkFont(size=11), text_color="#8899bb",
                         anchor="w").pack(fill="x", padx=12, pady=1)
        ctk.CTkFrame(workflow, height=8, fg_color="transparent").pack()

        # ── Generate Code ──
        gen_frame = ctk.CTkFrame(checker, fg_color="#1e1e38", corner_radius=8)
        gen_frame.pack(fill="x", padx=15, pady=(0, 10))

        gen_header = ctk.CTkFrame(gen_frame, fg_color="transparent")
        gen_header.pack(fill="x", padx=12, pady=(10, 5))

        ctk.CTkLabel(gen_header, text="Generate My Compatibility Code",
                     font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
                     ).pack(side="left")

        self._gen_btn = ctk.CTkButton(gen_header, text="\u2192  Generate My Code",
                                      width=180, height=34, corner_radius=8,
                                      fg_color="#2fa572", hover_color="#248a5d",
                                      command=self._generate_code)
        self._gen_btn.pack(side="right")

        ctk.CTkLabel(gen_frame,
            text="Scans all your enabled mods and generates a code containing only gameplay file hashes. "
                 "Your skins, music, and UI mods are NOT included.",
            font=ctk.CTkFont(size=11), text_color="#888888", anchor="w",
            wraplength=700, justify="left"
        ).pack(fill="x", padx=12, pady=(0, 5))

        # Status / progress
        self._gen_status = ctk.CTkLabel(gen_frame, text="",
                                        font=ctk.CTkFont(size=11),
                                        text_color="#6688bb", anchor="w")
        self._gen_status.pack(fill="x", padx=12, pady=(0, 3))

        self._gen_progress = ctk.CTkProgressBar(gen_frame, height=4,
                                                fg_color="#2a2a45",
                                                progress_color="#2fa572")
        self._gen_progress.pack(fill="x", padx=12, pady=(0, 5))
        self._gen_progress.set(0)

        # Generated code display
        self._gen_code_frame = ctk.CTkFrame(gen_frame, fg_color="transparent")
        self._gen_code_frame.pack(fill="x", padx=12, pady=(0, 10))
        # Content populated on generation

        # ── Check Against Code ──
        check_frame = ctk.CTkFrame(checker, fg_color="#1e1e38", corner_radius=8)
        check_frame.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkLabel(check_frame, text="Check Against a Code",
                     font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=12, pady=(10, 5))

        ctk.CTkLabel(check_frame,
            text="Paste the host's / opponent's compatibility code below, then click Check.",
            font=ctk.CTkFont(size=11), text_color="#888888", anchor="w"
        ).pack(fill="x", padx=12, pady=(0, 5))

        input_row = ctk.CTkFrame(check_frame, fg_color="transparent")
        input_row.pack(fill="x", padx=12, pady=(0, 5))

        self._check_entry = ctk.CTkTextbox(input_row, height=60, fg_color="#151528",
                                           font=ctk.CTkFont(family="Consolas", size=10),
                                           border_width=1, border_color="#3a3a55")
        self._check_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_col = ctk.CTkFrame(input_row, fg_color="transparent", width=140)
        btn_col.pack(side="right")
        btn_col.pack_propagate(False)

        self._check_btn = ctk.CTkButton(btn_col, text="\u2713  Check", width=130,
                                        height=34, corner_radius=8,
                                        fg_color="#1f538d", hover_color="#163b6a",
                                        command=self._check_code)
        self._check_btn.pack(pady=(0, 4))

        self._paste_btn = ctk.CTkButton(btn_col, text="\u2398  Paste", width=130,
                                        height=26, corner_radius=6,
                                        fg_color="#333352", hover_color="#444470",
                                        font=ctk.CTkFont(size=11),
                                        command=self._paste_from_clipboard)
        self._paste_btn.pack()

        # Check status
        self._check_status = ctk.CTkLabel(check_frame, text="",
                                          font=ctk.CTkFont(size=11),
                                          text_color="#6688bb", anchor="w")
        self._check_status.pack(fill="x", padx=12, pady=(0, 3))

        self._check_progress = ctk.CTkProgressBar(check_frame, height=4,
                                                   fg_color="#2a2a45",
                                                   progress_color="#1f538d")
        self._check_progress.pack(fill="x", padx=12, pady=(0, 5))
        self._check_progress.set(0)

        # Results container
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
            # ExeFS path
            exefs_path = (sdmc / "atmosphere" / "contents" / SSBU_TITLE_ID / "exefs")
        else:
            exefs_path = None

        return mods_path, plugins_path, exefs_path, emulator

    def _generate_code(self):
        """Generate a compatibility code in a background thread."""
        if self._checker_generating:
            return

        mods_path, plugins_path, exefs_path, emulator = self._get_paths()

        if not mods_path or not mods_path.exists():
            messagebox.showwarning("Warning",
                "Set up your emulator SDMC path in Settings first.")
            return

        self._checker_generating = True
        self._gen_btn.configure(state="disabled", text="Generating...")
        self._gen_status.configure(text="Starting scan...", text_color="#6688bb")
        self._gen_progress.set(0)

        # Clear previous code
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
                    progress_callback=progress_cb,
                )
                code = encode_fingerprint(fp)

                self.after(0, lambda: self._show_generated_code(fp, code))
            except Exception as e:
                logger.error("CompatChecker", f"Code generation failed: {e}")
                self.after(0, lambda: self._gen_status.configure(
                    text=f"Error: {e}", text_color="#e94560"))
            finally:
                self._checker_generating = False
                self.after(0, lambda: self._gen_btn.configure(
                    state="normal", text="\u2192  Generate My Code"))

        threading.Thread(target=run, daemon=True).start()

    def _show_generated_code(self, fp, code: str):
        """Display the generated compatibility code."""
        from src.core.compat_checker import CompatFingerprint

        opt_text = ""
        if fp.optional_plugins:
            opt_text = f", {len(fp.optional_plugins)} optional"
        self._gen_status.configure(
            text=f"Done! {len(fp.gameplay_hashes)} gameplay files, "
                 f"{len(fp.plugin_hashes)} plugins{opt_text} fingerprinted. "
                 f"Digest: {fp.digest[:16]}...",
            text_color="#2fa572")
        self._gen_progress.set(1.0)

        for w in self._gen_code_frame.winfo_children():
            w.destroy()

        # Code text box
        code_box = ctk.CTkTextbox(self._gen_code_frame, height=70,
                                  fg_color="#151528",
                                  font=ctk.CTkFont(family="Consolas", size=10),
                                  border_width=1, border_color="#2fa572")
        code_box.pack(fill="x", pady=(5, 5))
        code_box.insert("1.0", code)

        btn_row = ctk.CTkFrame(self._gen_code_frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 5))

        ctk.CTkButton(btn_row, text="\u2398  Copy Code", width=130,
                      height=30, corner_radius=6,
                      fg_color="#2fa572", hover_color="#248a5d",
                      command=lambda: self._copy_text(code, "Compatibility code")
                      ).pack(side="left", padx=(0, 8))

        # Stats
        if fp.gameplay_mod_names:
            mods_text = ", ".join(fp.gameplay_mod_names[:5])
            if len(fp.gameplay_mod_names) > 5:
                mods_text += f" +{len(fp.gameplay_mod_names) - 5} more"
            ctk.CTkLabel(btn_row, text=f"Gameplay mods: {mods_text}",
                         font=ctk.CTkFont(size=10), text_color="#888888",
                         anchor="w").pack(side="left", fill="x", expand=True)

        if not fp.gameplay_hashes and not fp.plugin_hashes:
            note = ctk.CTkLabel(self._gen_code_frame,
                text="\u2713  No gameplay-affecting mods detected — you're running "
                     "vanilla or visual-only mods. Compatible with anyone else running vanilla!",
                font=ctk.CTkFont(size=11), text_color="#2fa572", anchor="w",
                wraplength=700, justify="left")
            note.pack(fill="x", pady=(0, 5))

    def _paste_from_clipboard(self):
        """Paste clipboard contents into check entry."""
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

        # Validate code format immediately
        from src.core.compat_checker import decode_fingerprint
        ref_fp = decode_fingerprint(code)
        if ref_fp is None:
            messagebox.showerror("Invalid Code",
                "The pasted code is invalid or uses an unsupported format.\n\n"
                "Make sure you copied the entire code starting with 'SSBU-COMPAT-v2:'")
            return

        mods_path, plugins_path, exefs_path, emulator = self._get_paths()

        if not mods_path or not mods_path.exists():
            messagebox.showwarning("Warning",
                "Set up your emulator SDMC path in Settings first.")
            return

        self._checker_checking = True
        self._check_btn.configure(state="disabled", text="Checking...")
        self._check_status.configure(text="Generating local fingerprint...",
                                     text_color="#6688bb")
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
                    progress_callback=progress_cb,
                )
                result = compare_fingerprints(local_fp, ref_fp)

                self.after(0, lambda: self._show_check_result(result, ref_fp, local_fp))
            except Exception as e:
                logger.error("CompatChecker", f"Check failed: {e}")
                self.after(0, lambda: self._check_status.configure(
                    text=f"Error: {e}", text_color="#e94560"))
            finally:
                self._checker_checking = False
                self.after(0, lambda: self._check_btn.configure(
                    state="normal", text="\u2713  Check"))

        threading.Thread(target=run, daemon=True).start()

    def _show_check_result(self, result, ref_fp, local_fp):
        """Display compatibility check results."""
        self._check_progress.set(1.0)

        for w in self._check_results.winfo_children():
            w.destroy()

        if result.compatible:
            self._check_status.configure(
                text="\u2713  COMPATIBLE — Your gameplay setup matches!",
                text_color="#2fa572")

            compat_frame = ctk.CTkFrame(self._check_results, fg_color="#1a2e22",
                                        corner_radius=8, border_width=1,
                                        border_color="#2fa572")
            compat_frame.pack(fill="x", pady=5)

            ctk.CTkLabel(compat_frame,
                text="\u2713  COMPATIBLE",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="#2fa572", anchor="w"
            ).pack(fill="x", padx=12, pady=(10, 3))

            ctk.CTkLabel(compat_frame,
                text="Your gameplay-affecting files match the host's setup. "
                     "You're good to play online without desyncs!",
                font=ctk.CTkFont(size=12), text_color="#88bb88", anchor="w",
                wraplength=700, justify="left"
            ).pack(fill="x", padx=12, pady=(0, 5))

            details = []
            details.append(f"Gameplay files compared: {len(ref_fp.gameplay_hashes)}")
            details.append(f"Plugins compared: {len(ref_fp.plugin_hashes)}")
            details.append(f"Host emulator: {ref_fp.emulator or 'Unknown'}")
            details.append(f"Code generated: {ref_fp.timestamp or 'Unknown'}")

            for d in details:
                ctk.CTkLabel(compat_frame, text=f"  \u2022  {d}",
                             font=ctk.CTkFont(size=11), text_color="#669966",
                             anchor="w").pack(fill="x", padx=12, pady=1)

            ctk.CTkFrame(compat_frame, height=8, fg_color="transparent").pack()

        else:
            self._check_status.configure(
                text=f"\u2716  INCOMPATIBLE — {result.issue_count} issue(s) found",
                text_color="#e94560")

            incompat_frame = ctk.CTkFrame(self._check_results, fg_color="#2e1a1a",
                                          corner_radius=8, border_width=1,
                                          border_color="#e94560")
            incompat_frame.pack(fill="x", pady=5)

            ctk.CTkLabel(incompat_frame,
                text=f"\u2716  INCOMPATIBLE — {result.issue_count} issue(s)",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="#e94560", anchor="w"
            ).pack(fill="x", padx=12, pady=(10, 3))

            ctk.CTkLabel(incompat_frame,
                text="Your gameplay setup differs from the host's. Playing online "
                     "will likely cause desyncs. See details below:",
                font=ctk.CTkFont(size=12), text_color="#bb8888", anchor="w",
                wraplength=700, justify="left"
            ).pack(fill="x", padx=12, pady=(0, 8))

            # Missing gameplay files
            if result.missing_gameplay:
                self._build_issue_group(incompat_frame,
                    f"\u2716  Missing Gameplay Files ({len(result.missing_gameplay)})",
                    "The host has these gameplay files but you don't. "
                    "You may be missing a required gameplay mod.",
                    result.missing_gameplay, "#e94560")

            # Extra gameplay files
            if result.extra_gameplay:
                self._build_issue_group(incompat_frame,
                    f"\u26a0  Extra Gameplay Files ({len(result.extra_gameplay)})",
                    "You have these gameplay files but the host doesn't. "
                    "You have a gameplay mod the host doesn't use.",
                    result.extra_gameplay, "#d4a017")

            # Mismatched gameplay files
            if result.mismatched_gameplay:
                self._build_issue_group(incompat_frame,
                    f"\u2716  Mismatched Gameplay Files ({len(result.mismatched_gameplay)})",
                    "Both you and the host have these files but they differ. "
                    "You may have a different version of the same mod.",
                    result.mismatched_gameplay, "#e94560")

            # Plugin issues
            if result.missing_plugins:
                self._build_issue_group(incompat_frame,
                    f"\u2716  Missing Plugins ({len(result.missing_plugins)})",
                    "The host has these gameplay plugins but you don't.",
                    result.missing_plugins, "#e94560")

            if result.extra_plugins:
                self._build_issue_group(incompat_frame,
                    f"\u26a0  Extra Plugins ({len(result.extra_plugins)})",
                    "You have these gameplay plugins but the host doesn't.",
                    result.extra_plugins, "#d4a017")

            if result.mismatched_plugins:
                self._build_issue_group(incompat_frame,
                    f"\u2716  Mismatched Plugins ({len(result.mismatched_plugins)})",
                    "Both sides have these plugins but versions differ.",
                    result.mismatched_plugins, "#e94560")

            # ExeFS
            if result.mismatched_exefs:
                self._build_issue_group(incompat_frame,
                    f"\u26a0  ExeFS Differences ({len(result.mismatched_exefs)})",
                    "Framework-level hooks differ between setups.",
                    result.mismatched_exefs, "#d4a017")

            ctk.CTkFrame(incompat_frame, height=8, fg_color="transparent").pack()

        # Warnings (shown for both compatible and incompatible)
        if result.warnings:
            warn_frame = ctk.CTkFrame(self._check_results, fg_color="#2e2a1a",
                                      corner_radius=8, border_width=1,
                                      border_color="#d4a017")
            warn_frame.pack(fill="x", pady=5)

            ctk.CTkLabel(warn_frame,
                text=f"\u25b2  Warnings ({len(result.warnings)})",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#d4a017", anchor="w"
            ).pack(fill="x", padx=12, pady=(10, 5))

            for w in result.warnings:
                ctk.CTkLabel(warn_frame, text=f"  \u2022  {w}",
                             font=ctk.CTkFont(size=11), text_color="#bbaa66",
                             anchor="w", wraplength=680, justify="left"
                             ).pack(fill="x", padx=12, pady=1)

            ctk.CTkFrame(warn_frame, height=8, fg_color="transparent").pack()

        # Optional plugin differences (informational, shown for both outcomes)
        has_opt_diff = (result.optional_only_local or result.optional_only_remote)
        if has_opt_diff:
            opt_frame = ctk.CTkFrame(self._check_results, fg_color="#1a2a2e",
                                     corner_radius=8, border_width=1,
                                     border_color="#4488aa")
            opt_frame.pack(fill="x", pady=5)

            total_opt = len(result.optional_only_local) + len(result.optional_only_remote)
            ctk.CTkLabel(opt_frame,
                text=f"\u2139  Setup Differences ({total_opt} optional plugin(s))",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#4488aa", anchor="w"
            ).pack(fill="x", padx=12, pady=(10, 3))

            ctk.CTkLabel(opt_frame,
                text="These plugins don't affect gameplay sync and won't cause desyncs. "
                     "They only enhance the local experience for whoever has them installed.",
                font=ctk.CTkFont(size=11), text_color="#6699aa", anchor="w",
                wraplength=680, justify="left"
            ).pack(fill="x", padx=12, pady=(0, 6))

            if result.optional_only_local:
                ctk.CTkLabel(opt_frame,
                    text="You have (host doesn't):",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color="#5599bb", anchor="w"
                ).pack(fill="x", padx=14, pady=(2, 1))
                for p in result.optional_only_local:
                    ctk.CTkLabel(opt_frame, text=f"    \u2022  {p}",
                                 font=ctk.CTkFont(size=11), text_color="#88bbcc",
                                 anchor="w").pack(fill="x", padx=12, pady=0)

            if result.optional_only_remote:
                ctk.CTkLabel(opt_frame,
                    text="Host has (you don't):",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color="#5599bb", anchor="w"
                ).pack(fill="x", padx=14, pady=(4, 1))
                for p in result.optional_only_remote:
                    ctk.CTkLabel(opt_frame, text=f"    \u2022  {p}",
                                 font=ctk.CTkFont(size=11), text_color="#88bbcc",
                                 anchor="w").pack(fill="x", padx=12, pady=0)

            ctk.CTkFrame(opt_frame, height=8, fg_color="transparent").pack()

    def _build_issue_group(self, parent, title: str, description: str,
                           items: list[str], color: str):
        """Build a collapsible issue group in check results."""
        grp = ctk.CTkFrame(parent, fg_color="#1e1e38", corner_radius=6)
        grp.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(grp, text=title,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=color, anchor="w"
                     ).pack(fill="x", padx=10, pady=(8, 2))

        ctk.CTkLabel(grp, text=description,
                     font=ctk.CTkFont(size=10), text_color="#888888",
                     anchor="w", wraplength=680, justify="left"
                     ).pack(fill="x", padx=10, pady=(0, 5))

        # Show up to 15 items, collapse the rest
        display_items = items[:15]
        for item in display_items:
            # Shorten long paths for readability
            display = item
            if len(display) > 80:
                display = "..." + display[-77:]
            ctk.CTkLabel(grp, text=f"    {display}",
                         font=ctk.CTkFont(family="Consolas", size=10),
                         text_color="#aaaaaa", anchor="w"
                         ).pack(fill="x", padx=10, pady=0)

        if len(items) > 15:
            ctk.CTkLabel(grp,
                text=f"    ... and {len(items) - 15} more",
                font=ctk.CTkFont(size=10), text_color="#666666", anchor="w"
            ).pack(fill="x", padx=10, pady=(2, 0))

        ctk.CTkFrame(grp, height=6, fg_color="transparent").pack()

    # ─── Utility ──────────────────────────────────────────────────────

    def _copy_text(self, text: str, label: str = "Text"):
        """Copy text to clipboard with feedback."""
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Copied", f"{label} copied to clipboard!")
        except Exception:
            messagebox.showerror("Error", "Failed to copy to clipboard.")

    # ─── Existing features ────────────────────────────────────────────

    def on_show(self):
        """Auto-analyze on first visit, but don't block UI."""
        pass  # User clicks 'Analyze Mods' button when ready

    def _analyze_mods(self):
        """Analyze all enabled mods and categorize them."""
        settings = self.app.config_manager.settings
        if not settings.mods_path:
            messagebox.showwarning("Warning", "Set up your emulator SDMC path in Settings first.")
            return

        # Clear previous results
        for w in self.analysis_content.winfo_children():
            w.destroy()

        try:
            mods = self.app.mod_manager.list_mods()
            enabled = [m for m in mods if m.status == ModStatus.ENABLED]
        except Exception as e:
            ctk.CTkLabel(self.analysis_content,
                         text=f"Error loading mods: {e}",
                         font=ctk.CTkFont(size=12), text_color="#e94560"
                         ).pack(anchor="w", pady=5)
            return

        if not enabled:
            ctk.CTkLabel(self.analysis_content,
                         text="No enabled mods found. Enable mods in the Mods page first.",
                         font=ctk.CTkFont(size=12), text_color="#888888"
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

        # Summary stats
        summary_frame = ctk.CTkFrame(self.analysis_content, fg_color="#1e1e38", corner_radius=8)
        summary_frame.pack(fill="x", pady=(5, 10))

        summary_items = []
        for cat_key, cat_info in COMPAT_CATEGORIES.items():
            count = len(categorized[cat_key])
            if count:
                summary_items.append(f"{cat_info['icon']} {cat_info['label']}: {count}")

        ctk.CTkLabel(summary_frame,
            text=f"Analyzed {len(enabled)} enabled mods:",
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
        ).pack(fill="x", padx=12, pady=(10, 5))

        for item in summary_items:
            ctk.CTkLabel(summary_frame, text=f"  {item}",
                         font=ctk.CTkFont(size=12), anchor="w"
                         ).pack(fill="x", padx=12, pady=1)

        # Pad bottom of summary
        ctk.CTkFrame(summary_frame, height=10, fg_color="transparent").pack()

        # Show each category with mods
        for cat_key, cat_info in COMPAT_CATEGORIES.items():
            mods_in_cat = categorized[cat_key]
            if not mods_in_cat:
                continue

            cat_frame = ctk.CTkFrame(self.analysis_content, fg_color="#1e1e38", corner_radius=8)
            cat_frame.pack(fill="x", pady=5)

            # Header
            cat_header = ctk.CTkFrame(cat_frame, fg_color="transparent")
            cat_header.pack(fill="x", padx=12, pady=(10, 5))

            ctk.CTkLabel(cat_header,
                text=f"{cat_info['icon']}  {cat_info['label']} ({len(mods_in_cat)})",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=cat_info['color'], anchor="w"
            ).pack(side="left")

            ctk.CTkLabel(cat_frame, text=cat_info['description'],
                         font=ctk.CTkFont(size=11), text_color="#888888",
                         anchor="w", wraplength=700, justify="left"
                         ).pack(fill="x", padx=12, pady=(0, 5))

            # Mod list
            for mod in sorted(mods_in_cat, key=lambda m: m.name.lower()):
                mod_row = ctk.CTkFrame(cat_frame, fg_color="transparent", height=28)
                mod_row.pack(fill="x", padx=16, pady=1)
                mod_row.pack_propagate(False)

                ctk.CTkLabel(mod_row,
                    text=f"  \u2022  {mod.original_name}",
                    font=ctk.CTkFont(size=11),
                    text_color="#cccccc", anchor="w"
                ).pack(side="left")

                # Show categories if available
                if mod.metadata and mod.metadata.categories:
                    cats_text = ", ".join(mod.metadata.categories[:3])
                    ctk.CTkLabel(mod_row,
                        text=cats_text,
                        font=ctk.CTkFont(size=10),
                        text_color="#555570", anchor="e"
                    ).pack(side="right", padx=10)

            ctk.CTkFrame(cat_frame, height=8, fg_color="transparent").pack()

        # Generate shareable summary
        self._show_share_summary(categorized, enabled)
        self._analyzed = True
        logger.info("OnlineCompat", f"Analyzed {len(enabled)} mods for online compatibility")

    def _show_share_summary(self, categorized: dict, enabled: list):
        """Show a text summary that can be copied to share with friends."""
        try:
            self.share_section.pack_forget()
        except Exception:
            pass

        # Rebuild share section
        for w in self.share_section.winfo_children():
            w.destroy()

        self.share_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(self.share_section, text="Shareable Summary",
                     font=ctk.CTkFont(size=16, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(self.share_section,
                     text="Copy this summary to share with friends so they know what mods they need.",
                     font=ctk.CTkFont(size=12), text_color="#999999", anchor="w"
                     ).pack(fill="x", padx=15, pady=(0, 5))

        # Build summary text
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

        text_box = ctk.CTkTextbox(self.share_section, height=200, fg_color="#1a1a30",
                                  font=ctk.CTkFont(family="Consolas", size=11))
        text_box.pack(fill="x", padx=15, pady=5)
        text_box.insert("1.0", summary_text)

        copy_btn = ctk.CTkButton(self.share_section, text="\u2398  Copy to Clipboard",
                                 width=160, fg_color="#1f538d", hover_color="#163b6a",
                                 command=lambda: self._copy_text(summary_text, "Summary"),
                                 height=34, corner_radius=8)
        copy_btn.pack(padx=15, pady=(5, 15), anchor="w")
