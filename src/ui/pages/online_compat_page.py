"""Online Compatibility page — guides users on what mods are needed for online play.

This page provides information about mod compatibility when playing SSBU online
via emulator multiplayer (LDN) networks. It also analyzes the user's current
mod setup and categorizes each mod by its online impact.
"""

import threading
import customtkinter as ctk
from tkinter import messagebox
from src.ui.base_page import BasePage
from src.models.mod import Mod, ModStatus
from src.utils.logger import logger


# Online compatibility categories
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
                 "and which mods are client-side only.",
            font=ctk.CTkFont(size=12), text_color="#999999", anchor="w", wraplength=800,
            justify="left")
        desc.pack(fill="x", padx=30, pady=(0, 15))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=30)
        self._scroll = scroll

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
                                 command=lambda: self._copy_summary(summary_text),
                                 height=34, corner_radius=8)
        copy_btn.pack(padx=15, pady=(5, 15), anchor="w")

    def _copy_summary(self, text: str):
        """Copy summary text to clipboard."""
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Copied", "Summary copied to clipboard!")
        except Exception:
            messagebox.showerror("Error", "Failed to copy to clipboard.")
