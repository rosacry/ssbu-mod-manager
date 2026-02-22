"""Dashboard page - overview and quick actions."""
import threading
import customtkinter as ctk
from tkinter import messagebox
from src.ui.base_page import BasePage
from src.models.mod import ModStatus
from src.models.plugin import PluginStatus
from src.utils.logger import logger


class DashboardPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._conflict_cache = None
        self._loading = False
        self._build_ui()

    def _build_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(25, 5))

        title = ctk.CTkLabel(header_frame, text="SSBU Mod Manager",
                             font=ctk.CTkFont(size=28, weight="bold"), anchor="w")
        title.pack(side="left")

        self.loading_label = ctk.CTkLabel(header_frame, text="",
                                          font=ctk.CTkFont(size=12), text_color="#888888")
        self.loading_label.pack(side="right")

        desc = ctk.CTkLabel(self, text="Manage your Super Smash Bros. Ultimate mods, plugins, music, and more.",
                            font=ctk.CTkFont(size=13), text_color="#999999", anchor="w")
        desc.pack(fill="x", padx=30, pady=(0, 20))

        # Stats cards row
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(fill="x", padx=30, pady=(0, 20))

        self.stat_cards = {}
        stats = [
            ("mods_enabled", "Mods Enabled", "0", "#2fa572"),
            ("mods_disabled", "Mods Disabled", "0", "#666666"),
            ("plugins", "Plugins Active", "0", "#1f538d"),
            ("conflicts", "Text Conflicts", "0", "#e94560"),
        ]

        for i, (key, title_text, value, color) in enumerate(stats):
            card = ctk.CTkFrame(stats_frame, fg_color="#242438", corner_radius=12)
            card.grid(row=0, column=i, padx=6, pady=5, sticky="nsew")
            stats_frame.columnconfigure(i, weight=1)

            val_label = ctk.CTkLabel(card, text=value,
                                     font=ctk.CTkFont(size=36, weight="bold"),
                                     text_color=color)
            val_label.pack(padx=20, pady=(18, 4))

            title_label = ctk.CTkLabel(card, text=title_text,
                                       font=ctk.CTkFont(size=12),
                                       text_color="#999999")
            title_label.pack(padx=20, pady=(0, 18))

            self.stat_cards[key] = val_label

        # Quick Actions
        actions_label = ctk.CTkLabel(self, text="Quick Actions",
                                     font=ctk.CTkFont(size=18, weight="bold"), anchor="w")
        actions_label.pack(fill="x", padx=30, pady=(5, 10))

        actions_frame = ctk.CTkFrame(self, fg_color="transparent")
        actions_frame.pack(fill="x", padx=30)

        btn_style = {"height": 38, "corner_radius": 8, "font": ctk.CTkFont(size=13)}

        scan_btn = ctk.CTkButton(actions_frame, text="Scan for Conflicts",
                                 command=self._go_to_conflicts, width=180, **btn_style)
        scan_btn.pack(side="left", padx=(0, 8))

        fix_btn = ctk.CTkButton(actions_frame, text="Fix Text Conflicts",
                                command=self._fix_xmsbt_conflicts, width=180,
                                fg_color="#b08a2a", hover_color="#8a6a1a", **btn_style)
        fix_btn.pack(side="left", padx=(0, 8))

        refresh_btn = ctk.CTkButton(actions_frame, text="Refresh All",
                                    command=self._force_refresh, width=130,
                                    fg_color="#555555", hover_color="#444444", **btn_style)
        refresh_btn.pack(side="left", padx=(0, 8))

        open_btn = ctk.CTkButton(actions_frame, text="Open Mods Folder",
                                 command=self._open_mods_folder, width=160,
                                 fg_color="#555555", hover_color="#444444", **btn_style)
        open_btn.pack(side="left", padx=(0, 8))

        music_btn = ctk.CTkButton(actions_frame, text="Music Manager",
                                  command=lambda: self.app.navigate("music"), width=160,
                                  fg_color="#555555", hover_color="#444444", **btn_style)
        music_btn.pack(side="left")

        # Conflict info banner
        self.info_frame = ctk.CTkFrame(self, fg_color="#2a2a1e", corner_radius=10)
        self.info_frame.pack(fill="x", padx=30, pady=(15, 0))

        self.xmsbt_info = ctk.CTkLabel(
            self.info_frame, text="Click 'Refresh All' to scan your mod setup.",
            font=ctk.CTkFont(size=13), text_color="#bbbb88", anchor="w", wraplength=900,
        )
        self.xmsbt_info.pack(fill="x", padx=20, pady=14)

        # Emulator path status
        path_frame = ctk.CTkFrame(self, fg_color="#242438", corner_radius=10)
        path_frame.pack(fill="x", padx=30, pady=(15, 20))

        self.path_label = ctk.CTkLabel(
            path_frame, text="Emulator: Not configured",
            font=ctk.CTkFont(size=13), text_color="#999999", anchor="w",
        )
        self.path_label.pack(fill="x", padx=20, pady=14)

    def on_show(self):
        logger.debug("Dashboard", "Page shown, refreshing stats")
        self._refresh_stats_fast()

    def _refresh_stats_fast(self):
        """Quick refresh using cached data."""
        try:
            settings = self.app.config_manager.settings
            if settings.eden_sdmc_path:
                emu = settings.emulator or "Emulator"
                self.path_label.configure(
                    text=f"{emu}: {settings.eden_sdmc_path}",
                    text_color="#2fa572")
            else:
                self.path_label.configure(
                    text="Emulator: Not configured - go to Settings to set up",
                    text_color="#e94560")

            if settings.mods_path and settings.mods_path.exists():
                mods = self.app.mod_manager.list_mods()
                enabled = sum(1 for m in mods if m.status == ModStatus.ENABLED)
                disabled = sum(1 for m in mods if m.status == ModStatus.DISABLED)
                self.stat_cards["mods_enabled"].configure(text=str(enabled))
                self.stat_cards["mods_disabled"].configure(text=str(disabled))
                logger.debug("Dashboard", f"Mods: {enabled} enabled, {disabled} disabled")

            if settings.plugins_path and settings.plugins_path.exists():
                plugins = self.app.plugin_manager.list_plugins()
                active = sum(1 for p in plugins if p.status == PluginStatus.ENABLED)
                self.stat_cards["plugins"].configure(text=str(active))
                logger.debug("Dashboard", f"Plugins: {active} active")

            # Use cached conflict count
            if self._conflict_cache is not None:
                self.stat_cards["conflicts"].configure(text=str(self._conflict_cache))
        except Exception as e:
            logger.error("Dashboard", f"Stats refresh error: {e}")

    def _force_refresh(self):
        """Full refresh with conflict scanning in background thread."""
        if self._loading:
            return
        self._loading = True
        self.loading_label.configure(text="Scanning...")
        logger.info("Dashboard", "Starting full refresh...")

        # Invalidate mod cache
        self.app.mod_manager.invalidate_cache()

        def scan():
            try:
                settings = self.app.config_manager.settings
                count = 0
                if settings.mods_path and settings.mods_path.exists():
                    # Check for already-merged files
                    merged_dir = settings.mods_path / "_MergedResources"
                    merged_files = set()
                    if merged_dir.exists():
                        for f in merged_dir.rglob("*"):
                            if f.is_file():
                                merged_files.add(str(f.relative_to(merged_dir)).replace("\\", "/"))

                    conflicts = self.app.conflict_detector.detect_conflicts(settings.mods_path)
                    count = sum(1 for c in conflicts
                               if c.is_mergeable and c.relative_path not in merged_files)
                    logger.info("Dashboard", f"Conflict scan: {count} unresolved conflicts found")

                self.after(0, lambda: self._on_scan_done(count))
            except Exception as e:
                logger.error("Dashboard", f"Scan failed: {e}")
                self.after(0, lambda: self._on_scan_done(0))

        threading.Thread(target=scan, daemon=True).start()

    def _on_scan_done(self, conflict_count):
        self._loading = False
        self._conflict_cache = conflict_count
        self.loading_label.configure(text="")
        self.stat_cards["conflicts"].configure(text=str(conflict_count))

        if conflict_count > 0:
            self.info_frame.configure(fg_color="#2e2020")
            self.xmsbt_info.configure(
                text=f"Found {conflict_count} text file conflict(s). These can cause missing "
                     f"text in-game. Click 'Fix Text Conflicts' to auto-resolve.",
                text_color="#e94560")
        else:
            self.info_frame.configure(fg_color="#1e2e20")
            self.xmsbt_info.configure(
                text="No text file conflicts detected. Your mods are compatible.",
                text_color="#2fa572")

        self._refresh_stats_fast()

    def _fix_xmsbt_conflicts(self):
        settings = self.app.config_manager.settings
        if not settings.mods_path or not settings.mods_path.exists():
            messagebox.showwarning("Warning", "No mods path configured. Go to Settings first.")
            return

        self.loading_label.configure(text="Scanning conflicts...")
        logger.info("Dashboard", "Starting conflict fix...")

        def do_fix():
            try:
                conflicts = self.app.conflict_detector.detect_conflicts(settings.mods_path)

                # Check which are already merged
                merged_dir = settings.mods_path / "_MergedResources"
                merged_files = set()
                if merged_dir.exists():
                    for f in merged_dir.rglob("*"):
                        if f.is_file():
                            merged_files.add(str(f.relative_to(merged_dir)).replace("\\", "/"))

                mergeable = [c for c in conflicts
                            if c.is_mergeable and c.relative_path not in merged_files]

                logger.info("Dashboard", f"Found {len(mergeable)} mergeable conflicts")
                self.after(0, lambda: self._show_fix_dialog(mergeable))
            except Exception as e:
                logger.error("Dashboard", f"Conflict fix failed: {e}")
                self.after(0, lambda: self._fix_error(str(e)))

        threading.Thread(target=do_fix, daemon=True).start()

    def _show_fix_dialog(self, mergeable):
        self.loading_label.configure(text="")

        if not mergeable:
            messagebox.showinfo("No Conflicts",
                "No unresolved XMSBT text conflicts found.")
            self._conflict_cache = 0
            self.stat_cards["conflicts"].configure(text="0")
            self.info_frame.configure(fg_color="#1e2e20")
            self.xmsbt_info.configure(text="No text file conflicts detected.", text_color="#2fa572")
            return

        files_list = "\n".join(f"  - {c.relative_path} ({len(c.mods_involved)} mods)"
                               for c in mergeable[:10])
        if len(mergeable) > 10:
            files_list += f"\n  ... and {len(mergeable) - 10} more"

        confirm = messagebox.askyesno(
            "Fix Text Conflicts",
            f"Found {len(mergeable)} XMSBT text conflict(s):\n\n"
            f"{files_list}\n\n"
            "This will merge conflicting text files into _MergedResources.\n\nContinue?")
        if not confirm:
            return

        settings = self.app.config_manager.settings
        resolver = self.app.conflict_resolver
        if settings.backup_before_merge:
            for conflict in mergeable:
                try:
                    resolver.backup_originals(conflict)
                except Exception:
                    pass

        resolved = resolver.resolve_all_auto(mergeable)
        logger.info("Dashboard", f"Resolved {len(resolved)} conflicts")

        self._conflict_cache = 0
        self.stat_cards["conflicts"].configure(text="0")
        self.info_frame.configure(fg_color="#1e2e20")
        self.xmsbt_info.configure(text="All text conflicts resolved.", text_color="#2fa572")

        messagebox.showinfo("Fixed",
            f"Merged {len(resolved)} text file(s) into _MergedResources.\n\n"
            "Text should now display correctly in-game.")

    def _fix_error(self, error_msg):
        self.loading_label.configure(text="")
        messagebox.showerror("Error", f"Failed to fix conflicts: {error_msg}")

    def _go_to_conflicts(self):
        self.app.navigate("conflicts")

    def _open_mods_folder(self):
        import os
        settings = self.app.config_manager.settings
        if settings.mods_path and settings.mods_path.exists():
            os.startfile(str(settings.mods_path))
            logger.info("Dashboard", f"Opened mods folder: {settings.mods_path}")
        else:
            messagebox.showwarning("Warning", "No mods path configured. Go to Settings first.")
