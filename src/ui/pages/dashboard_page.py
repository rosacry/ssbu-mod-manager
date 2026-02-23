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
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # Header
        header_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(25, 5))

        title = ctk.CTkLabel(header_frame, text="SSBU Mod Manager",
                             font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
                             anchor="w")
        title.pack(side="left")

        self.loading_label = ctk.CTkLabel(header_frame, text="",
                                          font=ctk.CTkFont(size=12), text_color="#6a6a8a")
        self.loading_label.pack(side="right")

        desc = ctk.CTkLabel(scroll,
                            text="Manage your Super Smash Bros. Ultimate mods, plugins, music, and more.",
                            font=ctk.CTkFont(size=13), text_color="#7a7a9a", anchor="w")
        desc.pack(fill="x", padx=30, pady=(0, 18))

        # Stats cards row
        stats_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        stats_frame.pack(fill="x", padx=28, pady=(0, 18))

        self.stat_cards = {}
        stats = [
            ("mods_enabled", "Mods Enabled", "0", "#2fa572", "\u25a3"),
            ("mods_disabled", "Mods Disabled", "0", "#555570", "\u25a2"),
            ("plugins", "Plugins Active", "0", "#1f538d", "\u2699"),
            ("conflicts", "Text Conflicts", "0", "#e94560", "\u26a0"),
        ]

        for i, (key, title_text, value, color, icon) in enumerate(stats):
            card = ctk.CTkFrame(stats_frame, fg_color="#1a1a30", corner_radius=14)
            card.grid(row=0, column=i, padx=6, pady=5, sticky="nsew")
            stats_frame.columnconfigure(i, weight=1)

            # Colored left accent
            accent = ctk.CTkFrame(card, width=4, fg_color=color, corner_radius=2)
            accent.pack(side="left", fill="y", padx=(6, 0), pady=10)

            card_inner = ctk.CTkFrame(card, fg_color="transparent")
            card_inner.pack(fill="both", expand=True, padx=(10, 16), pady=12)

            # Icon + value row
            top_row = ctk.CTkFrame(card_inner, fg_color="transparent")
            top_row.pack(fill="x")

            ctk.CTkLabel(top_row, text=icon,
                         font=ctk.CTkFont(size=18), text_color=color,
                         ).pack(side="left", padx=(0, 8))

            val_label = ctk.CTkLabel(top_row, text=value,
                                     font=ctk.CTkFont(size=32, weight="bold"),
                                     text_color=color)
            val_label.pack(side="left")

            title_label = ctk.CTkLabel(card_inner, text=title_text,
                                       font=ctk.CTkFont(size=11),
                                       text_color="#6a6a8a", anchor="w")
            title_label.pack(fill="x", pady=(2, 0))

            self.stat_cards[key] = val_label

        # Quick Actions
        actions_label = ctk.CTkLabel(scroll, text="Quick Actions",
                                     font=ctk.CTkFont(size=18, weight="bold"), anchor="w")
        actions_label.pack(fill="x", padx=30, pady=(5, 10))

        actions_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        actions_frame.pack(fill="x", padx=30)

        btn_style = {"height": 40, "corner_radius": 10,
                     "font": ctk.CTkFont(family="Segoe UI", size=13)}

        scan_btn = ctk.CTkButton(actions_frame, text="\u26a0  Scan Conflicts",
                                 command=self._go_to_conflicts, width=170, **btn_style)
        scan_btn.pack(side="left", padx=(0, 8))

        fix_btn = ctk.CTkButton(actions_frame, text="\u2714  Fix Text Conflicts",
                                command=self._fix_xmsbt_conflicts, width=180,
                                fg_color="#b08a2a", hover_color="#8a6a1a", **btn_style)
        fix_btn.pack(side="left", padx=(0, 8))

        refresh_btn = ctk.CTkButton(actions_frame, text="\u27f3  Refresh All",
                                    command=self._force_refresh, width=130,
                                    fg_color="#2a2a44", hover_color="#3a3a55", **btn_style)
        refresh_btn.pack(side="left", padx=(0, 8))

        open_btn = ctk.CTkButton(actions_frame, text="\u2750  Mods Folder",
                                 command=self._open_mods_folder, width=140,
                                 fg_color="#2a2a44", hover_color="#3a3a55", **btn_style)
        open_btn.pack(side="left", padx=(0, 8))

        music_btn = ctk.CTkButton(actions_frame, text="\u266b  Music",
                                  command=lambda: self.app.navigate("music"), width=100,
                                  fg_color="#2a2a44", hover_color="#3a3a55", **btn_style)
        music_btn.pack(side="left")

        # Conflict info banner
        self.info_frame = ctk.CTkFrame(scroll, fg_color="#1e1e30", corner_radius=12)
        self.info_frame.pack(fill="x", padx=30, pady=(15, 0))

        self.xmsbt_info = ctk.CTkLabel(
            self.info_frame, text="Click 'Refresh All' to scan your mod setup.",
            font=ctk.CTkFont(size=13), text_color="#7a7a9a", anchor="w", wraplength=900,
        )
        self.xmsbt_info.pack(fill="x", padx=20, pady=14)

        # Emulator path status
        path_frame = ctk.CTkFrame(scroll, fg_color="#1a1a30", corner_radius=12)
        path_frame.pack(fill="x", padx=30, pady=(15, 10))

        self.path_label = ctk.CTkLabel(
            path_frame, text="\u2022  Emulator: Not configured",
            font=ctk.CTkFont(size=13), text_color="#7a7a9a", anchor="w",
        )
        self.path_label.pack(fill="x", padx=20, pady=14)

        # Getting started section (shows when not configured)
        self.getting_started = ctk.CTkFrame(scroll, fg_color="#141430", corner_radius=12)
        self.getting_started.pack(fill="x", padx=30, pady=(5, 20))

        gs_inner = ctk.CTkFrame(self.getting_started, fg_color="transparent")
        gs_inner.pack(fill="x", padx=20, pady=15)

        ctk.CTkLabel(gs_inner, text="Getting Started",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     anchor="w").pack(fill="x")

        steps = [
            "1.  Go to Settings and configure your emulator SDMC path",
            "2.  Your mods and plugins will be detected automatically",
            "3.  Use the Mods page to enable/disable individual mods",
            "4.  Use Conflicts to detect and auto-fix text conflicts",
            "5.  Use Music to assign custom tracks to stages",
        ]
        for step in steps:
            ctk.CTkLabel(gs_inner, text=step,
                         font=ctk.CTkFont(size=12), text_color="#7a7a9a",
                         anchor="w").pack(fill="x", pady=1)

    def on_show(self):
        logger.debug("Dashboard", "Page shown, refreshing stats")
        self._refresh_stats_fast()
        # Auto-scan conflicts in background if we haven't yet
        if self._conflict_cache is None:
            self._force_refresh()

    def _refresh_stats_fast(self):
        """Quick refresh using cached data."""
        try:
            settings = self.app.config_manager.settings
            configured = False

            if settings.eden_sdmc_path:
                emu = settings.emulator or "Emulator"
                self.path_label.configure(
                    text=f"\u2022  {emu}: {settings.eden_sdmc_path}",
                    text_color="#2fa572")
                configured = True
            else:
                self.path_label.configure(
                    text="\u2022  Emulator: Not configured \u2014 go to Settings to set up",
                    text_color="#e94560")

            # Show/hide getting started based on config state
            if configured:
                self.getting_started.pack_forget()
            else:
                # Re-show if not currently packed (e.g., after settings reset)
                if not self.getting_started.winfo_ismapped():
                    self.getting_started.pack(fill="x", padx=30, pady=(5, 20))

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
                            if f.is_file() and ".originals" not in f.parts:
                                merged_files.add(str(f.relative_to(merged_dir)).replace("\\", "/"))

                    conflicts = self.app.conflict_detector.detect_conflicts(settings.mods_path)
                    count = sum(1 for c in conflicts
                               if c.is_mergeable and c.relative_path not in merged_files)
                    logger.info("Dashboard", f"Conflict scan: {count} unresolved conflicts found")

                if not self.app.shutting_down:
                    try:
                        self.after(0, lambda: self._on_scan_done(count))
                    except Exception:
                        self._loading = False
            except Exception as e:
                logger.error("Dashboard", f"Scan failed: {e}")
                if not self.app.shutting_down:
                    try:
                        self.after(0, lambda: self._on_scan_done(0))
                    except Exception:
                        self._loading = False
                else:
                    self._loading = False

        threading.Thread(target=scan, daemon=True).start()

    def _on_scan_done(self, conflict_count):
        self._loading = False
        self._conflict_cache = conflict_count
        self.loading_label.configure(text="")
        self.stat_cards["conflicts"].configure(text=str(conflict_count))

        if conflict_count > 0:
            self.info_frame.configure(fg_color="#2a1820")
            self.xmsbt_info.configure(
                text=f"\u26a0  Found {conflict_count} text file conflict(s). These can cause missing "
                     f"text in-game. Click 'Fix Text Conflicts' to auto-resolve.",
                text_color="#e94560")
        else:
            self.info_frame.configure(fg_color="#142820")
            self.xmsbt_info.configure(
                text="\u2714  No text file conflicts detected. Your mods are compatible.",
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
                        if f.is_file() and ".originals" not in f.parts:
                            merged_files.add(str(f.relative_to(merged_dir)).replace("\\", "/"))

                mergeable = [c for c in conflicts
                            if c.is_mergeable and c.relative_path not in merged_files]

                logger.info("Dashboard", f"Found {len(mergeable)} mergeable conflicts")
                if not self.app.shutting_down:
                    try:
                        self.after(0, lambda: self._show_fix_dialog(mergeable))
                    except Exception:
                        pass
            except Exception as e:
                logger.error("Dashboard", f"Conflict fix failed: {e}")
                if not self.app.shutting_down:
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

        self.loading_label.configure(text="Resolving conflicts...")

        def do_resolve():
            try:
                resolver.resolve_all_auto(mergeable, create_backup=settings.backup_before_merge)
                actually_resolved = sum(1 for c in mergeable if c.resolved)
                failed = len(mergeable) - actually_resolved
                logger.info("Dashboard", f"Resolved {actually_resolved}/{len(mergeable)} conflicts")

                msbt_overlays = resolver.generate_msbt_overlays()
                if msbt_overlays > 0:
                    logger.info("Dashboard",
                                f"Generated {msbt_overlays} XMSBT overlay(s) from binary MSBT file(s)")

                if not self.app.shutting_down:
                    self.after(0, lambda: self._on_resolve_done(
                        actually_resolved, failed, msbt_overlays, len(mergeable)))
            except Exception as e:
                logger.error("Dashboard", f"Resolution failed: {e}")
                if not self.app.shutting_down:
                    self.after(0, lambda: self._fix_error(str(e)))

        threading.Thread(target=do_resolve, daemon=True).start()

    def _on_resolve_done(self, actually_resolved, failed, msbt_overlays, total):
        self.loading_label.configure(text="")

        self._conflict_cache = failed
        self.stat_cards["conflicts"].configure(text=str(failed))

        if failed == 0:
            self.info_frame.configure(fg_color="#142820")
            self.xmsbt_info.configure(text="\u2714  All text conflicts resolved.", text_color="#2fa572")
        else:
            self.info_frame.configure(fg_color="#2a1820")
            self.xmsbt_info.configure(
                text=f"{failed} conflict(s) could not be auto-merged (overlapping labels).",
                text_color="#e94560")

        msg = f"Merged {actually_resolved} text file(s) into _MergedResources."
        if msbt_overlays > 0:
            msg += f"\nGenerated {msbt_overlays} XMSBT overlay(s) from binary MSBT file(s)."
        if failed > 0:
            msg += f"\n\n{failed} conflict(s) could not be auto-merged."
        msg += "\n\nText should now display correctly in-game."
        messagebox.showinfo("Fixed", msg)

    def _fix_error(self, error_msg):
        self.loading_label.configure(text="")
        messagebox.showerror("Error", f"Failed to fix conflicts: {error_msg}")

    def _go_to_conflicts(self):
        self.app.navigate("conflicts")

    def _open_mods_folder(self):
        from src.utils.file_utils import open_folder
        settings = self.app.config_manager.settings
        if settings.mods_path and settings.mods_path.exists():
            open_folder(settings.mods_path)
            logger.info("Dashboard", f"Opened mods folder: {settings.mods_path}")
        else:
            messagebox.showwarning("Warning", "No mods path configured. Go to Settings first.")
