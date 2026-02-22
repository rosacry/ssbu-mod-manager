"""Settings page - path configuration and preferences."""
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path
from src.ui.base_page import BasePage
from src.paths import (auto_detect_sdmc, auto_detect_all_emulators,
                       derive_mods_path, derive_plugins_path, validate_sdmc_path)
from src.utils.logger import logger


class SettingsPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._build_ui()

    def _build_ui(self):
        title = ctk.CTkLabel(self, text="Settings",
                             font=ctk.CTkFont(size=24, weight="bold"), anchor="w")
        title.pack(fill="x", padx=30, pady=(25, 20))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=30)

        # Emulator SDMC Path
        sdmc_section = ctk.CTkFrame(scroll, fg_color="#242438", corner_radius=10)
        sdmc_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(sdmc_section, text="Emulator SDMC Path",
                     font=ctk.CTkFont(size=16, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(sdmc_section,
                     text="The root SDMC directory where your emulator stores SSBU mod data. "
                          "Supports Eden, Ryujinx, Yuzu, Suyu, Sudachi, Citron, and others.",
                     font=ctk.CTkFont(size=12), text_color="#999999", anchor="w", wraplength=700,
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

        # Detected emulators display
        self.detected_frame = ctk.CTkFrame(sdmc_section, fg_color="transparent")
        self.detected_frame.pack(fill="x", padx=15, pady=(5, 5))

        self.sdmc_status = ctk.CTkLabel(sdmc_section, text="",
                                        font=ctk.CTkFont(size=12), anchor="w")
        self.sdmc_status.pack(fill="x", padx=15, pady=(0, 15))

        # CSS Mod Folder
        css_section = ctk.CTkFrame(scroll, fg_color="#242438", corner_radius=10)
        css_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(css_section, text="CSS Mod Folder",
                     font=ctk.CTkFont(size=16, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(css_section,
                     text="Mod folder containing ui_chara_db.prc and msg_name.msbt.",
                     font=ctk.CTkFont(size=12), text_color="#999999", anchor="w"
                     ).pack(fill="x", padx=15, pady=(0, 5))

        css_frame = ctk.CTkFrame(css_section, fg_color="transparent")
        css_frame.pack(fill="x", padx=15, pady=(5, 15))

        self.css_var = ctk.StringVar(
            value=str(settings.css_mod_folder) if settings.css_mod_folder else "")
        ctk.CTkEntry(css_frame, textvariable=self.css_var, width=480, height=34).pack(side="left", padx=(0, 8))
        ctk.CTkButton(css_frame, text="Browse", width=80,
                      command=self._browse_css, height=34, corner_radius=8).pack(side="left")

        # Mod Disable Method
        method_section = ctk.CTkFrame(scroll, fg_color="#242438", corner_radius=10)
        method_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(method_section, text="Mod Disable Method",
                     font=ctk.CTkFont(size=16, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))

        self.method_var = ctk.StringVar(value=settings.mod_disable_method)
        ctk.CTkRadioButton(method_section, text='Rename (prefix with ".")',
                           variable=self.method_var, value="rename"
                           ).pack(fill="x", padx=15, pady=3)
        ctk.CTkRadioButton(method_section, text="Move to disabled folder",
                           variable=self.method_var, value="move"
                           ).pack(fill="x", padx=15, pady=(3, 15))

        # General options
        gen_section = ctk.CTkFrame(scroll, fg_color="#242438", corner_radius=10)
        gen_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(gen_section, text="General",
                     font=ctk.CTkFont(size=16, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))

        self.auto_detect_var = ctk.BooleanVar(value=settings.auto_detect_eden)
        ctk.CTkCheckBox(gen_section, text="Auto-detect emulator path on startup",
                        variable=self.auto_detect_var).pack(fill="x", padx=15, pady=3)

        self.backup_var = ctk.BooleanVar(value=settings.backup_before_merge)
        ctk.CTkCheckBox(gen_section, text="Create backup before merge operations",
                        variable=self.backup_var).pack(fill="x", padx=15, pady=(3, 15))

        # Save button
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(5, 20))

        ctk.CTkButton(btn_frame, text="Save Settings", width=160,
                      fg_color="#2fa572", hover_color="#106a43",
                      command=self._save_settings, height=38, corner_radius=8).pack(side="left", padx=(0, 10))

        ctk.CTkButton(btn_frame, text="Reset to Defaults", width=160,
                      fg_color="#555555", hover_color="#444444",
                      command=self._reset, height=38, corner_radius=8).pack(side="left")

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
                                 font=ctk.CTkFont(size=12), text_color="#999999", anchor="w")
            label.pack(anchor="w")
            for emu_name, emu_path in detected:
                btn = ctk.CTkButton(
                    self.detected_frame,
                    text=f"{emu_name}: {emu_path}",
                    fg_color="transparent", hover_color="#333355",
                    anchor="w", height=28, font=ctk.CTkFont(size=11),
                    text_color="#6688bb",
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
            self.sdmc_status.configure(text="Not configured", text_color="#888888")
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
                text_color="#2fa572")
        else:
            self.sdmc_status.configure(text=msg, text_color="#e94560")

    def _save_settings(self):
        settings = self.app.config_manager.settings

        sdmc_str = self.sdmc_var.get()
        if sdmc_str:
            sdmc = Path(sdmc_str)
            settings.eden_sdmc_path = sdmc
            settings.mods_path = derive_mods_path(sdmc)
            settings.plugins_path = derive_plugins_path(sdmc)

            # Detect which emulator this path belongs to
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

        self.app.config_manager.save(settings)
        self.app._update_managers()
        logger.info("Settings", "Settings saved successfully")

        messagebox.showinfo("Saved", "Settings saved successfully.")

    def _reset(self):
        from src.models.settings import AppSettings
        self.app.config_manager.save(AppSettings())
        self.sdmc_var.set("")
        self.css_var.set("")
        self.method_var.set("rename")
        self.auto_detect_var.set(True)
        self.backup_var.set(True)
        self.sdmc_status.configure(text="Reset to defaults", text_color="#888888")
        self.app._update_managers()
        logger.info("Settings", "Settings reset to defaults")
