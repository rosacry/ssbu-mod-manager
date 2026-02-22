"""Profile sharing page - export/import mod profiles."""
import customtkinter as ctk
from tkinter import filedialog, messagebox
from src.ui.base_page import BasePage
from src.utils.logger import logger


class SharePage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._build_ui()

    def _build_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(25, 5))

        title = ctk.CTkLabel(header_frame, text="Profiles",
                             font=ctk.CTkFont(size=24, weight="bold"), anchor="w")
        title.pack(side="left")

        desc = ctk.CTkLabel(self, text="Export and import your mod configuration to share with others.",
                            font=ctk.CTkFont(size=13), text_color="#999999", anchor="w")
        desc.pack(fill="x", padx=30, pady=(0, 15))

        # Export section
        export_frame = ctk.CTkFrame(self, fg_color="#242438", corner_radius=10)
        export_frame.pack(fill="x", padx=30, pady=(0, 15))

        export_header = ctk.CTkFrame(export_frame, fg_color="transparent")
        export_header.pack(fill="x", padx=15, pady=(15, 10))

        ctk.CTkLabel(export_header, text="Export Profile",
                     font=ctk.CTkFont(size=16, weight="bold"), anchor="w").pack(side="left")

        export_btn = ctk.CTkButton(export_header, text="Export to File",
                                   command=self._export, width=140,
                                   fg_color="#2fa572", hover_color="#106a43",
                                   corner_radius=8, height=34)
        export_btn.pack(side="right")

        # Profile name
        name_frame = ctk.CTkFrame(export_frame, fg_color="transparent")
        name_frame.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(name_frame, text="Profile Name:", width=120, anchor="w",
                     font=ctk.CTkFont(size=13)).pack(side="left")
        self.profile_name_var = ctk.StringVar(value="My SSBU Setup")
        ctk.CTkEntry(name_frame, textvariable=self.profile_name_var, width=350,
                     height=32).pack(side="left", padx=10)

        # Description
        desc_frame = ctk.CTkFrame(export_frame, fg_color="transparent")
        desc_frame.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(desc_frame, text="Description:", width=120, anchor="w",
                     font=ctk.CTkFont(size=13)).pack(side="left")
        self.desc_var = ctk.StringVar()
        ctk.CTkEntry(desc_frame, textvariable=self.desc_var, width=350,
                     placeholder_text="Optional description...", height=32).pack(side="left", padx=10)

        # Include options
        include_frame = ctk.CTkFrame(export_frame, fg_color="transparent")
        include_frame.pack(fill="x", padx=15, pady=(5, 15))
        ctk.CTkLabel(include_frame, text="Include:", width=120, anchor="w",
                     font=ctk.CTkFont(size=13)).pack(side="left", anchor="n")

        opts = ctk.CTkFrame(include_frame, fg_color="transparent")
        opts.pack(side="left", padx=10)

        self.include_mods = ctk.BooleanVar(value=True)
        self.include_plugins = ctk.BooleanVar(value=True)
        self.include_music = ctk.BooleanVar(value=True)

        ctk.CTkCheckBox(opts, text="Mod list & status", variable=self.include_mods,
                        font=ctk.CTkFont(size=13)).pack(anchor="w", pady=2)
        ctk.CTkCheckBox(opts, text="Plugin list & status", variable=self.include_plugins,
                        font=ctk.CTkFont(size=13)).pack(anchor="w", pady=2)
        ctk.CTkCheckBox(opts, text="Music configuration", variable=self.include_music,
                        font=ctk.CTkFont(size=13)).pack(anchor="w", pady=2)

        # Import section
        import_frame = ctk.CTkFrame(self, fg_color="#242438", corner_radius=10)
        import_frame.pack(fill="x", padx=30, pady=(0, 15))

        import_header = ctk.CTkFrame(import_frame, fg_color="transparent")
        import_header.pack(fill="x", padx=15, pady=(15, 10))

        ctk.CTkLabel(import_header, text="Import Profile",
                     font=ctk.CTkFont(size=16, weight="bold"), anchor="w").pack(side="left")

        import_btn = ctk.CTkButton(import_header, text="Browse for Profile",
                                   command=self._import, width=160,
                                   fg_color="#555555", hover_color="#444444",
                                   corner_radius=8, height=34)
        import_btn.pack(side="right")

        self.import_result_frame = ctk.CTkScrollableFrame(import_frame, fg_color="transparent", height=250)
        self.import_result_frame.pack(fill="x", padx=15, pady=(0, 15))

        # Empty state for import section
        self.import_empty = ctk.CTkLabel(
            self.import_result_frame,
            text="Select a .smbprofile file to compare against your current setup.",
            font=ctk.CTkFont(size=12), text_color="#666666",
        )
        self.import_empty.pack(pady=20)

    def _export(self):
        settings = self.app.config_manager.settings
        if not settings.mods_path:
            messagebox.showwarning("Warning", "Set up your emulator SDMC path in Settings first.")
            return

        output_path = filedialog.asksaveasfilename(
            title="Save Profile",
            defaultextension=".smbprofile",
            filetypes=[("SSBU Mod Profile", "*.smbprofile"), ("All Files", "*.*")],
            initialfile=f"{self.profile_name_var.get()}.smbprofile",
        )
        if not output_path:
            return

        try:
            from pathlib import Path
            mods = self.app.mod_manager.list_mods() if self.include_mods.get() else []
            plugins = self.app.plugin_manager.list_plugins() if self.include_plugins.get() else []

            profile = self.app.share_manager.export_profile(
                mods=mods,
                plugins=plugins,
                profile_name=self.profile_name_var.get(),
                description=self.desc_var.get(),
                embed_plugins=False,
            )
            self.app.share_manager.save_profile(profile, Path(output_path))
            logger.info("Profiles", f"Exported profile to {output_path}")
            messagebox.showinfo("Exported", f"Profile saved to {output_path}")
        except Exception as e:
            logger.error("Profiles", f"Export failed: {e}")
            messagebox.showerror("Error", f"Export failed: {e}")

    def _import(self):
        input_path = filedialog.askopenfilename(
            title="Select Profile File",
            filetypes=[("SSBU Mod Profile", "*.smbprofile"), ("All Files", "*.*")],
        )
        if not input_path:
            return

        try:
            from pathlib import Path
            profile = self.app.share_manager.load_profile(Path(input_path))
            logger.info("Profiles", f"Loaded profile: {profile.profile_name}")

            # Clear previous results
            for w in self.import_result_frame.winfo_children():
                w.destroy()

            # Show profile info header
            info_frame = ctk.CTkFrame(self.import_result_frame, fg_color="#1e1e38", corner_radius=8)
            info_frame.pack(fill="x", pady=(5, 10))

            ctk.CTkLabel(info_frame,
                text=f"Profile: {profile.profile_name}",
                font=ctk.CTkFont(size=14, weight="bold"), anchor="w",
            ).pack(fill="x", padx=12, pady=(10, 2))

            if profile.description:
                ctk.CTkLabel(info_frame,
                    text=profile.description,
                    font=ctk.CTkFont(size=12), text_color="#999999", anchor="w",
                ).pack(fill="x", padx=12, pady=(0, 2))

            ctk.CTkLabel(info_frame,
                text=f"Mods: {len(profile.mods)} | Plugins: {len(profile.plugins)}",
                font=ctk.CTkFont(size=12), text_color="#888888", anchor="w",
            ).pack(fill="x", padx=12, pady=(0, 10))

            # Compare against current setup
            current_mods = self.app.mod_manager.list_mods()
            current_plugins = self.app.plugin_manager.list_plugins()
            comparison = self.app.share_manager.compare_profile(
                profile, current_mods, current_plugins)

            # Show comparison
            for section, data in [("Mods", comparison["mods"]), ("Plugins", comparison["plugins"])]:
                header = ctk.CTkLabel(self.import_result_frame, text=section,
                                      font=ctk.CTkFont(size=14, weight="bold"), anchor="w")
                header.pack(fill="x", pady=(8, 4))

                if data["matching"]:
                    for name in data["matching"]:
                        row = ctk.CTkFrame(self.import_result_frame, fg_color="transparent")
                        row.pack(fill="x")
                        ctk.CTkLabel(row,
                            text=f"  [OK] {name}", text_color="#2fa572", anchor="w",
                            font=ctk.CTkFont(size=12),
                        ).pack(side="left")

                if data["missing"]:
                    for name in data["missing"]:
                        row = ctk.CTkFrame(self.import_result_frame, fg_color="transparent")
                        row.pack(fill="x")
                        ctk.CTkLabel(row,
                            text=f"  [MISSING] {name}", text_color="#e94560", anchor="w",
                            font=ctk.CTkFont(size=12),
                        ).pack(side="left")

                if data.get("extra"):
                    for name in data["extra"]:
                        row = ctk.CTkFrame(self.import_result_frame, fg_color="transparent")
                        row.pack(fill="x")
                        ctk.CTkLabel(row,
                            text=f"  [EXTRA] {name}", text_color="#888888", anchor="w",
                            font=ctk.CTkFont(size=12),
                        ).pack(side="left")

            # Install embedded plugins button (still support importing from old profiles that had them)
            embeddable = comparison["plugins"].get("embeddable", [])
            if embeddable:
                install_frame = ctk.CTkFrame(self.import_result_frame, fg_color="transparent")
                install_frame.pack(fill="x", pady=(10, 5))

                install_btn = ctk.CTkButton(
                    install_frame,
                    text=f"Install {len(embeddable)} Embedded Plugin(s)",
                    width=250,
                    fg_color="#2fa572", hover_color="#106a43",
                    corner_radius=8, height=34,
                    command=lambda p=profile: self._install_plugins(p),
                )
                install_btn.pack(side="left")

                ctk.CTkLabel(
                    install_frame,
                    text=f"  Plugins available: {', '.join(embeddable)}",
                    font=ctk.CTkFont(size=11),
                    text_color="#aaaaaa", anchor="w",
                ).pack(side="left", padx=10)

            # Store the loaded profile for later use
            self._loaded_profile = profile

        except Exception as e:
            logger.error("Profiles", f"Import failed: {e}")
            messagebox.showerror("Error", f"Import failed: {e}")

    def _install_plugins(self, profile):
        """Install embedded plugins from a loaded profile."""
        settings = self.app.config_manager.settings
        if not settings.plugins_path:
            messagebox.showwarning("Warning",
                "No plugins path configured. Set up your emulator SDMC path in Settings first.")
            return

        confirm = messagebox.askyesno(
            "Install Plugins",
            "This will install the embedded plugin files to your Skyline plugins directory.\n\n"
            "Continue?")
        if not confirm:
            return

        try:
            result = self.app.share_manager.install_embedded_plugins(
                profile, settings.plugins_path)

            msg = ""
            if result["installed"]:
                msg += f"Installed {len(result['installed'])} plugin(s):\n"
                for name in result["installed"]:
                    msg += f"  - {name}\n"

            if result["failed"]:
                msg += f"\nFailed to install {len(result['failed'])} plugin(s):\n"
                for err in result["failed"]:
                    msg += f"  - {err}\n"

            if not result["installed"] and not result["failed"]:
                msg = "All embedded plugins are already installed."

            logger.info("Profiles", f"Plugin installation: {result}")
            messagebox.showinfo("Plugin Installation", msg)

            # Refresh the import comparison
            self._import_refresh()
        except Exception as e:
            logger.error("Profiles", f"Plugin installation failed: {e}")
            messagebox.showerror("Error", f"Plugin installation failed: {e}")

    def _import_refresh(self):
        """Re-run comparison after installing plugins."""
        if hasattr(self, '_loaded_profile') and self._loaded_profile:
            for w in self.import_result_frame.winfo_children():
                w.destroy()

            current_mods = self.app.mod_manager.list_mods()
            current_plugins = self.app.plugin_manager.list_plugins()
            comparison = self.app.share_manager.compare_profile(
                self._loaded_profile, current_mods, current_plugins)

            for section, data in [("Mods", comparison["mods"]), ("Plugins", comparison["plugins"])]:
                header = ctk.CTkLabel(self.import_result_frame, text=section,
                                      font=ctk.CTkFont(size=14, weight="bold"), anchor="w")
                header.pack(fill="x", pady=(5, 3))

                for name in data.get("matching", []):
                    ctk.CTkLabel(self.import_result_frame,
                        text=f"  [OK] {name}", text_color="#2fa572", anchor="w",
                        font=ctk.CTkFont(size=12),
                    ).pack(fill="x")

                for name in data.get("missing", []):
                    ctk.CTkLabel(self.import_result_frame,
                        text=f"  [MISSING] {name}", text_color="#e94560", anchor="w",
                        font=ctk.CTkFont(size=12),
                    ).pack(fill="x")
