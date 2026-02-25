"""Dashboard page - overview and quick actions."""
import threading
import customtkinter as ctk
from tkinter import messagebox
from src.ui.base_page import BasePage
from src.models.mod import ModStatus
from src.models.plugin import PluginStatus
from src.utils.logger import logger


class DashboardPage(BasePage):
    _SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    _STARTUP_SCAN_DELAY_MS = 4200
    _STARTUP_SCAN_RETRY_MS = 900

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._conflict_cache = None
        self._locale_msbt_cache = None
        self._loading = False
        self._startup_scan_scheduled = False
        self._spinner_active = False
        self._spinner_index = 0
        self._stats_refresh_after_id = None
        self._startup_refresh_after_id = None
        self._build_ui()

    def _build_ui(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # Header
        header_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(25, 5))

        title = ctk.CTkLabel(header_frame, text="Dashboard",
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

        # Conflict info banner
        self.info_frame = ctk.CTkFrame(scroll, fg_color="#1e1e30", corner_radius=12)
        self.info_frame.pack(fill="x", padx=30, pady=(15, 0))

        self.xmsbt_info = ctk.CTkLabel(
            self.info_frame, text="Click 'Refresh All' to scan your mod setup.",
            font=ctk.CTkFont(size=13), text_color="#7a7a9a", anchor="w", wraplength=900,
        )
        self.xmsbt_info.pack(fill="x", padx=20, pady=14)

        # Getting started section (shows when not configured)
        self.getting_started = ctk.CTkFrame(scroll, fg_color="#141430", corner_radius=12)
        self.getting_started.pack(fill="x", padx=30, pady=(15, 20))

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

    def _start_spinner(self, text: str = "Loading"):
        """Start an animated loading spinner in the loading label."""
        self._spinner_active = True
        self._spinner_index = 0
        self._spinner_text = text
        self._animate_spinner()

    def _stop_spinner(self):
        """Stop the loading spinner."""
        self._spinner_active = False
        self.loading_label.configure(text="")

    def _animate_spinner(self):
        """Animate the spinner by cycling through braille frames."""
        if not self._spinner_active:
            return
        frame = self._SPINNER_FRAMES[self._spinner_index % len(self._SPINNER_FRAMES)]
        self.loading_label.configure(text=f"{frame} {self._spinner_text}...")
        self._spinner_index += 1
        self.after(100, self._animate_spinner)

    def on_show(self):
        logger.debug("Dashboard", "Page shown, scheduling stats refresh")
        if self._stats_refresh_after_id:
            try:
                self.after_cancel(self._stats_refresh_after_id)
            except Exception:
                pass
        delay = 260 if self._conflict_cache is None else 40
        self._stats_refresh_after_id = self.after(delay, self._refresh_stats_fast)
        # Auto-scan conflicts in background if we haven't yet
        if self._conflict_cache is None and not self._startup_scan_scheduled:
            # Delay heavy startup scan so initial interaction stays responsive.
            self._startup_scan_scheduled = True
            self._schedule_startup_refresh(self._STARTUP_SCAN_DELAY_MS)

    def _startup_refresh(self):
        """Run delayed first refresh after app startup settles."""
        self._startup_refresh_after_id = None
        if self.app.shutting_down:
            return
        try:
            if getattr(self.app.main_window, "current_page", None) != "dashboard":
                # User left dashboard: do not scan in the background.
                self._startup_scan_scheduled = False
                return
        except Exception:
            pass
        try:
            if self.app.has_recent_user_activity(1.2):
                self._schedule_startup_refresh(self._STARTUP_SCAN_RETRY_MS)
                return
        except Exception:
            pass
        self._startup_scan_scheduled = False
        if self._conflict_cache is None and not self._loading:
            self._force_refresh()

    def on_hide(self):
        if self._stats_refresh_after_id:
            try:
                self.after_cancel(self._stats_refresh_after_id)
            except Exception:
                pass
            self._stats_refresh_after_id = None
        if self._startup_refresh_after_id:
            try:
                self.after_cancel(self._startup_refresh_after_id)
            except Exception:
                pass
            self._startup_refresh_after_id = None
            self._startup_scan_scheduled = False

    def _schedule_startup_refresh(self, delay_ms: int):
        if self._startup_refresh_after_id:
            try:
                self.after_cancel(self._startup_refresh_after_id)
            except Exception:
                pass
            self._startup_refresh_after_id = None
        self._startup_refresh_after_id = self.after(delay_ms, self._startup_refresh)

    def _refresh_stats_fast(self):
        """Quick refresh using cached data."""
        self._stats_refresh_after_id = None
        try:
            settings = self.app.config_manager.settings
            configured = bool(settings.eden_sdmc_path)

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

            # Use cached conflict count (including locale MSBTs)
            if self._conflict_cache is not None:
                total = self._conflict_cache + (self._locale_msbt_cache or 0)
                self.stat_cards["conflicts"].configure(text=str(total))
        except Exception as e:
            logger.error("Dashboard", f"Stats refresh error: {e}")

    def _force_refresh(self):
        """Full refresh with conflict scanning in background thread."""
        if self._loading:
            return
        self._loading = True
        self._start_spinner("Scanning")
        logger.info("Dashboard", "Starting full refresh...")

        # Invalidate mod cache
        self.app.mod_manager.invalidate_cache()

        def scan():
            try:
                settings = self.app.config_manager.settings
                count = 0
                locale_count = 0
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

                    # Also detect locale-specific MSBT files
                    locale_msbts = self.app.conflict_resolver.detect_locale_msbts()
                    locale_count = len(locale_msbts)
                    logger.info("Dashboard", f"Conflict scan: {count} unresolved conflicts, {locale_count} locale MSBT(s) found")

                if not self.app.shutting_down:
                    try:
                        self.after(0, lambda: self._on_scan_done(count, locale_count))
                    except Exception:
                        self._loading = False
                else:
                    self._loading = False
            except Exception as e:
                logger.error("Dashboard", f"Scan failed: {e}")
                if not self.app.shutting_down:
                    try:
                        self.after(0, lambda: self._on_scan_done(0, 0))
                    except Exception:
                        self._loading = False
                else:
                    self._loading = False

        threading.Thread(target=scan, daemon=True).start()

    def _on_scan_done(self, conflict_count, locale_count=0):
        self._loading = False
        self._conflict_cache = conflict_count
        self._locale_msbt_cache = locale_count
        self._stop_spinner()
        total_issues = conflict_count + locale_count
        self.stat_cards["conflicts"].configure(text=str(total_issues))

        if total_issues > 0:
            self.info_frame.configure(fg_color="#2a1820")
            parts = []
            if conflict_count > 0:
                parts.append(f"{conflict_count} text file conflict(s)")
            if locale_count > 0:
                parts.append(f"{locale_count} locale-specific MSBT file(s) to fix")
            issue_text = " and ".join(parts)
            self.xmsbt_info.configure(
                text=f"\u26a0  Found {issue_text}. Click 'Fix Text Conflicts' to auto-resolve.",
                text_color="#e94560")
        else:
            self.info_frame.configure(fg_color="#142820")
            self.xmsbt_info.configure(
                text="\u2714  No text file conflicts detected. Your mods are compatible.",
                text_color="#2fa572")

        self._refresh_stats_fast()

    def _fix_xmsbt_conflicts(self):
        if self._loading:
            return
        settings = self.app.config_manager.settings
        if not settings.mods_path or not settings.mods_path.exists():
            messagebox.showwarning("Warning", "No mods path configured. Go to Settings first.")
            return

        self._loading = True
        self._start_spinner("Scanning conflicts")
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

                # Also detect locale-specific MSBT files
                locale_msbts = self.app.conflict_resolver.detect_locale_msbts()

                logger.info("Dashboard", f"Found {len(mergeable)} mergeable conflicts, {len(locale_msbts)} locale MSBTs")
                if not self.app.shutting_down:
                    try:
                        self.after(0, lambda: self._show_fix_dialog(mergeable, locale_msbts))
                    except Exception:
                        self._loading = False
            except Exception as e:
                logger.error("Dashboard", f"Conflict fix failed: {e}")
                if not self.app.shutting_down:
                    try:
                        self.after(0, lambda: self._fix_error(str(e)))
                    except Exception:
                        self._loading = False
                else:
                    self._loading = False

        threading.Thread(target=do_fix, daemon=True).start()

    def _show_fix_dialog(self, mergeable, locale_msbts=None):
        self._stop_spinner()
        self._loading = False

        locale_msbts = locale_msbts or []

        if not mergeable and not locale_msbts:
            messagebox.showinfo("No Conflicts",
                "No unresolved MBST/XMSBT text conflicts found.")
            self._conflict_cache = 0
            self._locale_msbt_cache = 0
            self.stat_cards["conflicts"].configure(text="0")
            self.info_frame.configure(fg_color="#142820")
            self.xmsbt_info.configure(
                text="\u2714  No text file conflicts detected. Your mods are compatible.",
                text_color="#2fa572",
            )
            return

        # Build description of what will be fixed
        desc_parts = []
        if mergeable:
            files_list = "\n".join(
                f"  \u2022 {c.relative_path}\n     Mods: {', '.join(c.mods_involved)}"
                for c in mergeable[:10])
            if len(mergeable) > 10:
                files_list += f"\n  ... and {len(mergeable) - 10} more"
            desc_parts.append(f"{len(mergeable)} XMSBT text conflict(s):\n\n{files_list}")

        if locale_msbts:
            locale_list = "\n".join(
                f"  \u2022 {fn} in {mod}" for mod, fn, _ in locale_msbts[:5])
            if len(locale_msbts) > 5:
                locale_list += f"\n  ... and {len(locale_msbts) - 5} more"
            desc_parts.append(
                f"{len(locale_msbts)} locale-specific MSBT file(s) to rename:\n\n{locale_list}")

        full_desc = "\n\n".join(desc_parts)

        actions = []
        if mergeable:
            actions.append("merge conflicting text files into _MergedResources")
        if locale_msbts:
            actions.append("rename locale-specific MSBT files to locale-independent names")
        action_text = " and ".join(actions)

        confirm = messagebox.askyesno(
            "Fix Text Conflicts",
            f"Found {full_desc}\n\n"
            f"This will {action_text}.\n\nContinue?")
        if not confirm:
            return

        settings = self.app.config_manager.settings
        resolver = self.app.conflict_resolver

        self._loading = True
        self._start_spinner("Resolving conflicts")

        def do_resolve():
            try:
                actually_resolved = 0
                failed = 0
                locale_renamed = 0

                if mergeable:
                    resolver.resolve_all_auto(mergeable, create_backup=settings.backup_before_merge)
                    actually_resolved = sum(1 for c in mergeable if c.resolved)
                    failed = len(mergeable) - actually_resolved
                    logger.info("Dashboard", f"Resolved {actually_resolved}/{len(mergeable)} conflicts")

                if locale_msbts:
                    locale_renamed = resolver.rename_locale_msbt_files()
                    logger.info("Dashboard", f"Renamed {locale_renamed} locale MSBT file(s)")

                msbt_overlays = resolver.generate_msbt_overlays()
                if msbt_overlays > 0:
                    logger.info("Dashboard",
                                f"Generated {msbt_overlays} XMSBT overlay(s) from binary MSBT file(s)")

                if not self.app.shutting_down:
                    try:
                        self.after(0, lambda: self._on_resolve_done(
                            actually_resolved, failed, msbt_overlays, len(mergeable),
                            locale_renamed))
                    except Exception:
                        self._loading = False
                else:
                    self._loading = False
            except Exception as e:
                logger.error("Dashboard", f"Resolution failed: {e}")
                if not self.app.shutting_down:
                    try:
                        self.after(0, lambda: self._fix_error(str(e)))
                    except Exception:
                        self._loading = False
                else:
                    self._loading = False

        threading.Thread(target=do_resolve, daemon=True).start()

    def _on_resolve_done(self, actually_resolved, failed, msbt_overlays, total,
                          locale_renamed=0):
        self._stop_spinner()
        self._loading = False

        self._conflict_cache = failed
        self._locale_msbt_cache = 0  # All locale MSBTs were handled
        self.stat_cards["conflicts"].configure(text=str(failed))

        if failed == 0:
            self.info_frame.configure(fg_color="#142820")
            self.xmsbt_info.configure(text="\u2714  All text conflicts resolved.", text_color="#2fa572")
        else:
            self.info_frame.configure(fg_color="#2a1820")
            self.xmsbt_info.configure(
                text=f"{failed} conflict(s) could not be auto-merged (overlapping labels).",
                text_color="#e94560")

        msg_parts = []
        if actually_resolved > 0:
            msg_parts.append(f"Merged {actually_resolved} text file(s) into _MergedResources.")
        if locale_renamed > 0:
            msg_parts.append(f"Renamed {locale_renamed} locale-specific MSBT file(s).")
        if msbt_overlays > 0:
            msg_parts.append(f"Generated {msbt_overlays} XMSBT overlay(s) from binary MSBT file(s).")
        if failed > 0:
            msg_parts.append(f"\n{failed} conflict(s) could not be auto-merged.")
        msg_parts.append("\nText should now display correctly in-game.")
        msg = "\n".join(msg_parts)
        messagebox.showinfo("Fixed", msg)

    def _fix_error(self, error_msg):
        self._stop_spinner()
        self._loading = False
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
