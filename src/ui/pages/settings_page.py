"""Settings page."""
import re
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path
from src.ui.base_page import BasePage
from src.ui import theme
from src.paths import (auto_detect_sdmc, auto_detect_all_emulators,
                       derive_mods_path, derive_plugins_path, validate_sdmc_path)
from src.utils.logger import logger

_GAME_VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+){0,3}$")


def normalize_game_version(value: str) -> str:
    """Normalize game version text for compatibility metadata.

    Examples:
    - "v13.0.1" -> "13.0.1"
    - "13,0,1" -> "13.0.1"
    """
    normalized = (value or "").strip().replace(",", ".").replace(" ", "")
    if normalized.lower().startswith("v") and len(normalized) > 1 and normalized[1].isdigit():
        normalized = normalized[1:]
    return normalized


def is_valid_game_version(value: str) -> bool:
    normalized = normalize_game_version(value)
    if not normalized:
        return True
    return bool(_GAME_VERSION_PATTERN.fullmatch(normalized))


class SettingsPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._build_ui()

    def _build_ui(self):
        title = ctk.CTkLabel(self, text="Settings",
                             font=ctk.CTkFont(size=theme.FONT_PAGE_TITLE, weight="bold"), anchor="w")
        title.pack(fill="x", padx=30, pady=(25, 20))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=30)

        sdmc_section = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=10)
        sdmc_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(sdmc_section, text="Emulator SDMC Path",
                     font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(sdmc_section,
                     text="The root SDMC directory where your emulator stores SSBU mod data. "
                          "Supports Eden, Ryujinx, Yuzu, Suyu, Sudachi, Citron, and others.",
                     font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), text_color=theme.TEXT_MUTED,
                     anchor="w", wraplength=700,
                     ).pack(fill="x", padx=15, pady=(0, 5))

        path_frame = ctk.CTkFrame(sdmc_section, fg_color="transparent")
        path_frame.pack(fill="x", padx=15, pady=5)

        settings = self.app.config_manager.settings
        self.sdmc_var = ctk.StringVar(
            value=str(settings.eden_sdmc_path) if settings.eden_sdmc_path else "")

        self.sdmc_entry = ctk.CTkEntry(path_frame, textvariable=self.sdmc_var, width=480, height=34)
        self.sdmc_entry.pack(side="left", padx=(0, 8))

        ctk.CTkButton(path_frame, text="Browse", width=80,
                      command=self._browse_sdmc, height=34, corner_radius=8).pack(side="left", padx=(0, 5))

        ctk.CTkButton(path_frame, text="Auto-Detect", width=110,
                      command=self._auto_detect, height=34, corner_radius=8).pack(side="left")

        self.detected_frame = ctk.CTkFrame(sdmc_section, fg_color="transparent")
        self.detected_frame.pack(fill="x", padx=15, pady=(5, 5))

        self.sdmc_status = ctk.CTkLabel(sdmc_section, text="",
                                        font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), anchor="w")
        self.sdmc_status.pack(fill="x", padx=15, pady=(0, 15))

        css_section = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=10)
        css_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(css_section, text="CSS Mod Folder",
                     font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(css_section,
                     text="Mod folder containing ui_chara_db.prc and msg_name.msbt.",
                     font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), text_color=theme.TEXT_MUTED, anchor="w"
                     ).pack(fill="x", padx=15, pady=(0, 5))

        css_frame = ctk.CTkFrame(css_section, fg_color="transparent")
        css_frame.pack(fill="x", padx=15, pady=(5, 15))

        self.css_var = ctk.StringVar(
            value=str(settings.css_mod_folder) if settings.css_mod_folder else "")
        ctk.CTkEntry(css_frame, textvariable=self.css_var, width=480, height=34).pack(side="left", padx=(0, 8))
        ctk.CTkButton(css_frame, text="Browse", width=80,
                      command=self._browse_css, height=34, corner_radius=8).pack(side="left")

        # "move" is the only method that prevents ARCropolis from loading.
        self.method_var = ctk.StringVar(value="move")

        gen_section = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=10)
        gen_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(gen_section, text="General",
                     font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))

        self.auto_detect_var = ctk.BooleanVar(value=settings.auto_detect_eden)
        ctk.CTkCheckBox(gen_section, text="Auto-detect emulator path on startup",
                        variable=self.auto_detect_var).pack(fill="x", padx=15, pady=3)

        self.backup_var = ctk.BooleanVar(value=settings.backup_before_merge)
        ctk.CTkCheckBox(gen_section, text="Create backup before merge operations",
                        variable=self.backup_var).pack(fill="x", padx=15, pady=(3, 15))

        # --- Music Scanning section ---
        music_section = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=10)
        music_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            music_section, text="Music Scanning",
            font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"), anchor="w",
        ).pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(
            music_section,
            text=(
                "Control which directories are scanned for custom BGM tracks. "
                "Only .nus3audio files whose name starts with bgm_ are detected."
            ),
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
            text_color=theme.TEXT_MUTED, anchor="w", wraplength=700, justify="left",
        ).pack(fill="x", padx=15, pady=(0, 8))

        self.music_scan_disabled_var = ctk.BooleanVar(
            value=bool(getattr(settings, "music_scan_disabled_mods", True))
        )
        ctk.CTkCheckBox(
            music_section,
            text="Include tracks from the disabled_mods folder",
            variable=self.music_scan_disabled_var,
        ).pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkLabel(
            music_section, text="Extra Track Directories:",
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), anchor="w",
        ).pack(fill="x", padx=15, pady=(5, 3))
        ctk.CTkLabel(
            music_section,
            text="Add additional folders to scan for custom .nus3audio tracks.",
            font=ctk.CTkFont(size=theme.FONT_CAPTION),
            text_color=theme.TEXT_DIM, anchor="w",
        ).pack(fill="x", padx=15, pady=(0, 5))

        self._extra_dirs_frame = ctk.CTkFrame(music_section, fg_color="transparent")
        self._extra_dirs_frame.pack(fill="x", padx=15, pady=(0, 5))

        self._extra_dir_rows: list[tuple[ctk.CTkEntry, ctk.CTkButton]] = []
        for d in (getattr(settings, "music_extra_track_dirs", None) or []):
            self._add_extra_dir_row(d)

        extra_btn_frame = ctk.CTkFrame(music_section, fg_color="transparent")
        extra_btn_frame.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkButton(
            extra_btn_frame, text="+ Add Directory", width=140,
            fg_color=theme.BTN_NEUTRAL, hover_color=theme.HOVER_NEUTRAL,
            command=self._browse_extra_dir, height=32, corner_radius=8,
        ).pack(side="left")

        online_meta = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=10)
        online_meta.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(online_meta, text="Online Compatibility Metadata",
                     font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(
            online_meta,
            text="Optional but recommended: include exact emulator build and SSBU game update "
                 "so compatibility checks can enforce environment parity.",
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
            text_color=theme.TEXT_MUTED,
            anchor="w",
            wraplength=760,
            justify="left",
        ).pack(fill="x", padx=15, pady=(0, 8))

        meta_grid = ctk.CTkFrame(online_meta, fg_color="transparent")
        meta_grid.pack(fill="x", padx=15, pady=(0, 15))
        meta_grid.grid_columnconfigure(1, weight=1)

        self.emu_version_var = ctk.StringVar(value=str(getattr(settings, "emulator_version", "") or ""))
        self.game_version_var = ctk.StringVar(value=str(getattr(settings, "game_version", "") or ""))

        ctk.CTkLabel(meta_grid, text="Emulator Build:", anchor="w").grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 8)
        )
        ctk.CTkEntry(
            meta_grid,
            textvariable=self.emu_version_var,
            height=32,
            placeholder_text="e.g. v0.0.4-rc3",
        ).grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(meta_grid, text="SSBU Game Version:", anchor="w").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=(0, 0)
        )
        ctk.CTkEntry(
            meta_grid,
            textvariable=self.game_version_var,
            height=32,
            placeholder_text="e.g. 13.0.1",
        ).grid(row=1, column=1, sticky="ew", pady=(0, 0))

        self.online_meta_status = ctk.CTkLabel(
            online_meta,
            text="",
            font=ctk.CTkFont(size=theme.FONT_BODY),
            anchor="w",
        )
        self.online_meta_status.pack(fill="x", padx=15, pady=(0, 10))
        self._refresh_online_metadata_status()

        experimental_section = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=10)
        experimental_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            experimental_section,
            text="Experimental",
            font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(
            experimental_section,
            text=(
                "Spotify playlist export is optional and remains behind an explicit "
                "experimental toggle."
            ),
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
            text_color=theme.TEXT_MUTED,
            anchor="w",
            wraplength=760,
            justify="left",
        ).pack(fill="x", padx=15, pady=(0, 8))

        self.experimental_spotify_var = ctk.BooleanVar(
            value=bool(getattr(settings, "experimental_spotify_enabled", False))
        )
        ctk.CTkCheckBox(
            experimental_section,
            text="Enable Spotify playlist export (experimental)",
            variable=self.experimental_spotify_var,
        ).pack(fill="x", padx=15, pady=(0, 15))

        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(5, 20))

        ctk.CTkButton(btn_frame, text="Reset to Defaults", width=160,
                      fg_color=theme.BTN_NEUTRAL, hover_color=theme.HOVER_NEUTRAL,
                      command=self._reset, height=38, corner_radius=8).pack(side="left")

        self._auto_save_active = True
        self.sdmc_var.trace_add("write", lambda *_: self._auto_save())
        self.css_var.trace_add("write", lambda *_: self._auto_save())
        self.auto_detect_var.trace_add("write", lambda *_: self._auto_save())
        self.backup_var.trace_add("write", lambda *_: self._auto_save())
        self.emu_version_var.trace_add("write", lambda *_: self._on_online_meta_change())
        self.game_version_var.trace_add("write", lambda *_: self._on_online_meta_change())
        self.experimental_spotify_var.trace_add("write", lambda *_: self._auto_save())
        self.music_scan_disabled_var.trace_add("write", lambda *_: self._auto_save())

    # --- Extra track directory helpers ---
    def _add_extra_dir_row(self, value: str = ""):
        """Add a row showing an extra track directory with a remove button."""
        row_frame = ctk.CTkFrame(self._extra_dirs_frame, fg_color="transparent")
        row_frame.pack(fill="x", pady=2)

        entry = ctk.CTkEntry(row_frame, height=30, width=480)
        entry.pack(side="left", padx=(0, 6))
        if value:
            entry.insert(0, value)

        remove_btn = ctk.CTkButton(
            row_frame, text="Remove", width=70, height=30,
            fg_color=theme.BTN_NEUTRAL, hover_color=theme.HOVER_NEUTRAL,
            corner_radius=6,
            command=lambda rf=row_frame: self._remove_extra_dir_row(rf),
        )
        remove_btn.pack(side="left")

        self._extra_dir_rows.append((entry, remove_btn))
        entry.bind("<FocusOut>", lambda *_: self._auto_save())

    def _remove_extra_dir_row(self, row_frame: ctk.CTkFrame):
        """Remove a single extra-dir row and trigger auto-save."""
        self._extra_dir_rows = [
            (e, b) for (e, b) in self._extra_dir_rows
            if e.master is not row_frame
        ]
        row_frame.destroy()
        self._auto_save()

    def _browse_extra_dir(self):
        """Let the user pick a directory, then add a row for it."""
        folder = filedialog.askdirectory(title="Select Extra Track Directory")
        if folder:
            self._add_extra_dir_row(folder)
            self._auto_save()

    def _collect_extra_dirs(self) -> list[str]:
        """Return the list of non-empty extra track directories from the UI."""
        dirs: list[str] = []
        for entry, _ in self._extra_dir_rows:
            val = entry.get().strip()
            if val:
                dirs.append(val)
        return dirs

    def _auto_save(self):
        if not self._auto_save_active:
            return
        if hasattr(self, '_auto_save_id') and self._auto_save_id:
            try:
                self.after_cancel(self._auto_save_id)
            except Exception:
                pass
        self._auto_save_id = self.after(300, self._do_auto_save)

    def _on_online_meta_change(self):
        self._refresh_online_metadata_status()
        self._auto_save()

    def _refresh_online_metadata_status(self):
        build = (self.emu_version_var.get() or "").strip()
        game = (self.game_version_var.get() or "").strip()
        if not build and not game:
            self.online_meta_status.configure(
                text="Optional: fill both values for stronger online compatibility checks.",
                text_color=theme.TEXT_DIM,
            )
            return

        if not is_valid_game_version(game):
            self.online_meta_status.configure(
                text="Game version format looks invalid. Use values like 13.0.1.",
                text_color=theme.ACCENT,
            )
            return

        self.online_meta_status.configure(
            text="Metadata format looks good. Values will be included in compatibility codes.",
            text_color=theme.SUCCESS,
        )

    def _do_auto_save(self):
        self._auto_save_id = None
        self._save_settings(quiet=True)

    def on_show(self):
        self._validate_sdmc()
        self._show_detected_emulators()

    def _show_detected_emulators(self):
        for w in self.detected_frame.winfo_children():
            w.destroy()

        detected = auto_detect_all_emulators()
        if detected:
            label = ctk.CTkLabel(self.detected_frame,
                                 text="Detected emulators:",
                                 font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
                                 text_color=theme.TEXT_MUTED, anchor="w")
            label.pack(anchor="w")
            for emu_name, emu_path in detected:
                btn = ctk.CTkButton(
                    self.detected_frame,
                    text=f"{emu_name}: {emu_path}",
                    fg_color="transparent", hover_color=theme.HOVER_SETTINGS,
                    anchor="w", height=28, font=ctk.CTkFont(size=theme.FONT_BODY),
                    text_color=theme.INFO,
                    command=lambda p=str(emu_path): self._select_emulator(p),
                )
                btn.pack(fill="x", pady=1)

    def _select_emulator(self, path):
        self.sdmc_var.set(path)
        self._validate_sdmc()

    def _browse_sdmc(self):
        folder = filedialog.askdirectory(title="Select Emulator SDMC Directory")
        if folder:
            self.sdmc_var.set(folder)
            self._validate_sdmc()

    def _browse_css(self):
        folder = filedialog.askdirectory(title="Select CSS Mod Folder")
        if folder:
            self.css_var.set(folder)

    def _auto_detect(self):
        path = auto_detect_sdmc()
        if path:
            self.sdmc_var.set(str(path))
            self._validate_sdmc()
            messagebox.showinfo("Found", f"Emulator SDMC detected at:\n{path}")
        else:
            messagebox.showwarning("Not Found",
                "Could not auto-detect any emulator SDMC path.\n\n"
                "Supported: Eden, Ryujinx, Yuzu, Suyu, Sudachi, Citron\n\n"
                "Please browse to it manually.")

    def _validate_sdmc(self):
        path_str = self.sdmc_var.get()
        if not path_str:
            self.sdmc_status.configure(text="Not configured", text_color=theme.TEXT_DIM)
            return

        path = Path(path_str)
        valid, msg = validate_sdmc_path(path)
        if valid:
            mods = derive_mods_path(path)
            try:
                mod_count = sum(1 for f in mods.iterdir() if f.is_dir()) if mods.exists() else 0
            except (PermissionError, OSError):
                mod_count = 0
            self.sdmc_status.configure(
                text=f"Valid - {mod_count} mods detected | {msg}",
                text_color=theme.SUCCESS)
        else:
            self.sdmc_status.configure(text=msg, text_color=theme.ACCENT)

    def _save_settings(self, quiet: bool = False):
        settings = self.app.config_manager.settings

        sdmc_str = self.sdmc_var.get()
        if sdmc_str:
            sdmc = Path(sdmc_str)
            settings.eden_sdmc_path = sdmc
            settings.mods_path = derive_mods_path(sdmc)
            settings.plugins_path = derive_plugins_path(sdmc)

            detected = auto_detect_all_emulators()
            for emu_name, emu_path in detected:
                if str(emu_path) == sdmc_str:
                    settings.emulator = emu_name
                    break
        else:
            settings.eden_sdmc_path = None
            settings.mods_path = None
            settings.plugins_path = None
            settings.emulator = ""

        css_str = self.css_var.get()
        settings.css_mod_folder = Path(css_str) if css_str else None
        settings.mod_disable_method = self.method_var.get()
        settings.auto_detect_eden = self.auto_detect_var.get()
        settings.backup_before_merge = self.backup_var.get()
        settings.emulator_version = (self.emu_version_var.get() or "").strip()
        settings.game_version = normalize_game_version(self.game_version_var.get())
        settings.experimental_spotify_enabled = bool(self.experimental_spotify_var.get())
        settings.music_scan_disabled_mods = bool(self.music_scan_disabled_var.get())
        settings.music_extra_track_dirs = self._collect_extra_dirs()

        self.app.config_manager.save(settings)
        self.app._update_managers()
        logger.info("Settings", "Settings saved successfully")

        if not quiet:
            messagebox.showinfo("Saved", "Settings saved successfully.")

    def _reset(self):
        from src.models.settings import AppSettings
        self._auto_save_active = False
        self.app.config_manager.save(AppSettings())
        self.sdmc_var.set("")
        self.css_var.set("")
        self.method_var.set("move")
        self.auto_detect_var.set(True)
        self.backup_var.set(True)
        self.emu_version_var.set("")
        self.game_version_var.set("")
        self.experimental_spotify_var.set(False)
        self.music_scan_disabled_var.set(True)
        # Remove all extra-dir rows
        for entry, _ in list(self._extra_dir_rows):
            entry.master.destroy()
        self._extra_dir_rows.clear()
        self.sdmc_status.configure(text="Reset to defaults", text_color=theme.TEXT_DIM)
        logger.enabled = False
        self.app._update_managers()
        self._auto_save_active = True
        logger.info("Settings", "Settings reset to defaults")
