"""Conflict detection and resolution page with explanations."""
import threading
import traceback
import time
from pathlib import Path
import customtkinter as ctk
from tkinter import messagebox
from src.ui.base_page import BasePage
from src.ui.widgets.conflict_card import ConflictCard
from src.models.conflict import ResolutionStrategy, ConflictSeverity
from src.utils.logger import logger

# Explanations for conflict types
CONFLICT_EXPLANATIONS = {
    ".nestedmod": (
        "Folder Structure Conflicts",
        "A mod folder contains an extra wrapper subfolder. ARCropolis may not load "
        "the mod correctly until its actual content folders (fighter/ui/sound/etc.) "
        "are moved up one level.",
        False,
    ),
    ".xmsbt": (
        "Text Conflicts (XMSBT)",
        "Multiple mods change the same text file. This causes one mod's text "
        "to overwrite the other, leading to missing character names, stage names, "
        "or menu text in-game. These can usually be auto-merged.",
        True,
    ),
    ".msbt": (
        "Message Conflicts (MSBT)",
        "Multiple mods modify the same compiled message file. Only one mod's "
        "version will be loaded. This may cause missing or incorrect text.",
        False,
    ),
    ".prc": (
        "Parameter Conflicts (PRC)",
        "Multiple mods change the same game parameter file. This affects gameplay "
        "mechanics like character stats, stage behavior, or UI layout. Only one "
        "mod's version will be loaded — usually the last one alphabetically.",
        False,
    ),
    ".stprm": (
        "Stage Parameter Conflicts",
        "Multiple mods change the same stage parameter file. This can cause "
        "stage behavior issues but rarely crashes. The last mod loaded wins.",
        False,
    ),
    ".stdat": (
        "Stage Data Conflicts",
        "Multiple mods change the same stage data file. Only one version will "
        "load. This may cause visual or gameplay issues on affected stages.",
        False,
    ),
}


class ConflictsPage(BasePage):
    _TOP_ANCHOR_GUARD_INTERVAL_MS = 140
    _TOP_ANCHOR_GUARD_MAX_SECONDS = 30.0

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._conflicts = []
        self._locale_msbts = []  # locale-specific MSBT files detected
        self._scanned = False
        self._scanning = False
        self._needs_render = False
        self._scan_generation = 0
        self._initial_prompt_frame = None
        self._initial_prompt_host = None
        self._initial_prompt_visible = False
        self._viewport_stabilize_after_ids = []
        self._top_anchor_after_id = None
        self._top_anchor_guard_until = 0.0
        self._top_anchor_guard_active = False
        self._top_anchor_released_by_user = False
        self.conflict_list = None
        self._build_ui()

    def _build_ui(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(25, 10))

        title = ctk.CTkLabel(header_frame, text="Conflicts",
                             font=ctk.CTkFont(size=24, weight="bold"), anchor="w")
        title.pack(side="left")

        self.header_btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        self.scan_btn = ctk.CTkButton(self.header_btn_frame, text="Rescan", width=110,
                                      command=self._force_scan, corner_radius=8, height=34)
        self.restore_btn_header = ctk.CTkButton(
            self.header_btn_frame, text="Restore Originals",
            fg_color="#b08a2a", hover_color="#8a6b1f",
            command=self._restore_originals, width=165,
            corner_radius=8, height=34,
        )

        # Explanation section
        explain_frame = ctk.CTkFrame(self, fg_color="#1e1e38", corner_radius=10)
        explain_frame.pack(fill="x", padx=30, pady=(0, 8))

        explain_inner = ctk.CTkFrame(explain_frame, fg_color="transparent")
        explain_inner.pack(fill="x", padx=15, pady=12)

        ctk.CTkLabel(explain_inner, text="What are conflicts?",
                     font=ctk.CTkFont(size=13, weight="bold"), anchor="w",
                     text_color="#cccccc").pack(anchor="w")

        ctk.CTkLabel(explain_inner,
                     text="Conflicts occur when two or more mods modify the same game file. "
                          "When this happens, only one mod's version of the file gets loaded by the game. "
                          "Text file conflicts (.xmsbt) are the most common and can cause missing "
                          "character/stage names. These can be auto-merged. Other conflict types "
                          "(PRC, MSBT) usually don't cause crashes but may result in one mod's "
                          "changes being overridden by another.",
                     font=ctk.CTkFont(size=12), text_color="#999999", anchor="w",
                     wraplength=900, justify="left").pack(anchor="w", pady=(4, 0))

        self.summary_label = ctk.CTkLabel(self, text="Click 'Scan for Conflicts' to check for mod file conflicts.",
                                          font=ctk.CTkFont(size=13),
                                          text_color="#999999", anchor="w")
        self.summary_label.pack(fill="x", padx=30, pady=(0, 5))

        self.auto_btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.auto_btn_frame.pack(fill="x", padx=30, pady=(0, 8))

        self.auto_resolve_btn = ctk.CTkButton(
            self.auto_btn_frame, text="Auto-Resolve All Mergeable",
            fg_color="#2fa572", hover_color="#106a43",
            command=self._auto_resolve_all, width=240,
            corner_radius=8, height=34,
        )

        self.fix_locale_btn = ctk.CTkButton(
            self.auto_btn_frame, text="Fix Locale MSBT Files",
            fg_color="#1f538d", hover_color="#163b6a",
            command=self._fix_locale_msbts, width=200,
            corner_radius=8, height=34,
        )

        self._results_stack = ctk.CTkFrame(self, fg_color="transparent")
        self._results_stack.pack(fill="both", expand=True, padx=30, pady=(0, 10))

        self._create_conflict_list()

        # Keep initial prompt in a separate non-scroll host so prompt placement
        # cannot corrupt the scrollable canvas region for real results.
        self._initial_prompt_host = ctk.CTkFrame(self._results_stack, fg_color="transparent")
        self._initial_prompt_host.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)
        self.bind("<Configure>", self._on_page_configure, add="+")

    def _create_conflict_list(self):
        """Create the scrollable conflict results host."""
        self.conflict_list = ctk.CTkScrollableFrame(self._results_stack, fg_color="transparent")
        self.conflict_list.pack(fill="both", expand=True)
        self.conflict_list.bind("<Configure>", self._on_page_configure, add="+")
        self._bind_conflict_scroll_intent_handlers()

    def _recreate_conflict_list(self):
        """Hard-reset the scroll host to avoid stale canvas/scrollregion state."""
        try:
            if self.conflict_list is not None and bool(self.conflict_list.winfo_exists()):
                self.conflict_list.destroy()
        except Exception:
            pass
        self._create_conflict_list()
        self._show_conflict_list()
        self._reset_conflict_canvas_view()

    def on_show(self):
        if self._scanning:
            self._set_rescan_visible(True)
            self._hide_initial_prompt()
        elif not self._scanned:
            self._show_initial_prompt()
        elif self._needs_render:
            self._render()
        else:
            self._set_rescan_visible(True)
            self._hide_initial_prompt()
            self.conflict_list.update_idletasks()
            self._stabilize_conflict_viewport()
            self._arm_top_anchor_guard("on_show")

    def on_hide(self):
        self._cancel_conflict_viewport_stabilization()
        self._cancel_top_anchor_guard()

    def _show_initial_prompt(self):
        """Show initial centered scan prompt and keep results list hidden/cleared."""
        self._cancel_conflict_viewport_stabilization()
        self._cancel_top_anchor_guard()
        self._set_rescan_visible(False)
        self._set_results_chrome_visible(False)
        self.auto_resolve_btn.pack_forget()
        self.fix_locale_btn.pack_forget()
        for w in self.conflict_list.winfo_children():
            w.destroy()
        self._show_empty_state_host()
        for w in self._initial_prompt_host.winfo_children():
            w.destroy()

        self._initial_prompt_frame = ctk.CTkFrame(self._initial_prompt_host, fg_color="transparent")
        self._initial_prompt_frame.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(self._initial_prompt_frame, text="No scan performed yet",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="#cccccc").pack(pady=(0, 8))

        ctk.CTkLabel(self._initial_prompt_frame,
                     text="Click the button below to scan your mods for file conflicts.\n"
                          "This may take a few seconds depending on how many mods you have installed.",
                     font=ctk.CTkFont(size=13), text_color="#888888",
                     justify="center").pack(pady=(0, 20))

        scan_prompt_btn = ctk.CTkButton(
            self._initial_prompt_frame, text="\U0001F50D  Scan for Conflicts", width=220, height=40,
            fg_color="#1f538d", hover_color="#163b6a",
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=8, command=self._scan,
        )
        scan_prompt_btn.pack()

        self._initial_prompt_visible = True
        self._reposition_initial_prompt()
        self._show_empty_state_host()

    def _hide_initial_prompt(self):
        self._cancel_conflict_viewport_stabilization()
        self._initial_prompt_visible = False
        self._set_results_chrome_visible(True)
        if self._initial_prompt_frame is not None:
            try:
                self._initial_prompt_frame.destroy()
            except Exception:
                pass
            self._initial_prompt_frame = None
        try:
            for w in self._initial_prompt_host.winfo_children():
                w.destroy()
        except Exception:
            pass
        self._show_conflict_list()

    def _set_results_chrome_visible(self, visible: bool):
        try:
            if visible:
                if not self.summary_label.winfo_manager():
                    self.summary_label.pack(fill="x", padx=30, pady=(0, 5), before=self._results_stack)
                if not self.auto_btn_frame.winfo_manager():
                    self.auto_btn_frame.pack(fill="x", padx=30, pady=(0, 8), before=self._results_stack)
            else:
                if self.summary_label.winfo_manager():
                    self.summary_label.pack_forget()
                if self.auto_btn_frame.winfo_manager():
                    self.auto_btn_frame.pack_forget()
        except Exception:
            pass

    def _show_empty_state_host(self):
        try:
            if not self._initial_prompt_host.winfo_manager():
                self._initial_prompt_host.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)
            self._initial_prompt_host.lift()
        except Exception:
            pass

    def _show_conflict_list(self):
        try:
            if self.conflict_list is None or not bool(self.conflict_list.winfo_exists()):
                self._create_conflict_list()
            if not self.conflict_list.winfo_manager():
                self.conflict_list.pack(fill="both", expand=True)
            self.conflict_list.lift()
            if self._initial_prompt_host.winfo_manager():
                self._initial_prompt_host.lower()
        except Exception:
            pass

    def _set_rescan_visible(self, visible: bool):
        try:
            if self.scan_btn.winfo_manager():
                self.scan_btn.pack_forget()
            if self.restore_btn_header.winfo_manager():
                self.restore_btn_header.pack_forget()
            if self.header_btn_frame.winfo_manager():
                self.header_btn_frame.pack_forget()

            if visible:
                self.header_btn_frame.pack(side="right")
                # Pack restore first so rescan appears to its left.
                self.restore_btn_header.pack(side="right")
                self.scan_btn.pack(side="right", padx=(0, 8))
        except Exception:
            pass

    def _on_page_configure(self, _event=None):
        if self._initial_prompt_visible:
            self.after(0, self._reposition_initial_prompt)

    def _bind_conflict_scroll_intent_handlers(self):
        """Bind one-time handlers that detect explicit user scroll intent."""
        if self.conflict_list is None:
            return

        def _bind_once(widget):
            if widget is None:
                return
            try:
                if getattr(widget, "_ssbum_conflict_intent_bound", False):
                    return
                setattr(widget, "_ssbum_conflict_intent_bound", True)
            except Exception:
                pass
            try:
                widget.bind("<MouseWheel>", self._on_conflict_user_intent, add="+")
                widget.bind("<ButtonPress-1>", self._on_conflict_user_intent, add="+")
                widget.bind("<B1-Motion>", self._on_conflict_user_intent, add="+")
            except Exception:
                pass

        _bind_once(self.conflict_list)
        try:
            _bind_once(getattr(self.conflict_list, "_parent_canvas", None))
        except Exception:
            pass
        try:
            _bind_once(getattr(self.conflict_list, "_scrollbar", None))
        except Exception:
            pass

        try:
            for child in self.conflict_list.winfo_children():
                _bind_once(child)
        except Exception:
            pass

    def _on_conflict_user_intent(self, _event=None):
        """Release top-anchor guard once the user intentionally interacts."""
        if not self._top_anchor_guard_active:
            return
        self._top_anchor_released_by_user = True
        self._cancel_top_anchor_guard()
        logger.debug("Conflicts", "Top-anchor guard released by user interaction")

    def _cancel_top_anchor_guard(self):
        self._top_anchor_guard_active = False
        self._top_anchor_guard_until = 0.0
        if self._top_anchor_after_id:
            try:
                self.after_cancel(self._top_anchor_after_id)
            except Exception:
                pass
            self._top_anchor_after_id = None

    def _arm_top_anchor_guard(self, source: str = "render"):
        """Keep results pinned to top until user scroll intent is observed."""
        self._cancel_top_anchor_guard()
        self._top_anchor_released_by_user = False
        self._top_anchor_guard_active = True
        self._top_anchor_guard_until = time.monotonic() + self._TOP_ANCHOR_GUARD_MAX_SECONDS
        try:
            self._top_anchor_after_id = self.after(0, self._run_top_anchor_guard)
        except Exception:
            self._top_anchor_after_id = None
        logger.debug("Conflicts", f"Top-anchor guard armed ({source})")

    def _run_top_anchor_guard(self):
        self._top_anchor_after_id = None
        if not self._top_anchor_guard_active:
            return
        if self._top_anchor_released_by_user:
            self._cancel_top_anchor_guard()
            return
        try:
            if time.monotonic() >= float(self._top_anchor_guard_until):
                logger.debug("Conflicts", "Top-anchor guard expired")
                self._cancel_top_anchor_guard()
                return
        except Exception:
            self._cancel_top_anchor_guard()
            return

        try:
            current_page = getattr(self.app.main_window, "current_page", None)
        except Exception:
            current_page = None
        if current_page != "conflicts":
            # Keep guard armed; resume checks when page is visible again.
            try:
                self._top_anchor_after_id = self.after(
                    self._TOP_ANCHOR_GUARD_INTERVAL_MS, self._run_top_anchor_guard
                )
            except Exception:
                self._top_anchor_after_id = None
            return

        if self._scanning:
            try:
                self._top_anchor_after_id = self.after(
                    self._TOP_ANCHOR_GUARD_INTERVAL_MS, self._run_top_anchor_guard
                )
            except Exception:
                self._top_anchor_after_id = None
            return

        try:
            canvas = getattr(self.conflict_list, "_parent_canvas", None)
            before_y0 = 0.0
            if canvas is not None:
                try:
                    before_y0 = float(canvas.yview()[0])
                except Exception:
                    before_y0 = 0.0
            self._reset_conflict_canvas_view()
            self._compact_leading_conflict_gap()
            if before_y0 > 0.0015:
                logger.debug("Conflicts", f"Top-anchor guard corrected y0={before_y0:.4f}")
        except Exception:
            pass

        try:
            self._top_anchor_after_id = self.after(
                self._TOP_ANCHOR_GUARD_INTERVAL_MS, self._run_top_anchor_guard
            )
        except Exception:
            self._top_anchor_after_id = None

    def _reposition_initial_prompt(self):
        """Keep the initial prompt centered in the available viewport."""
        if not self._initial_prompt_visible or self._initial_prompt_frame is None:
            return
        try:
            if self._initial_prompt_frame.winfo_exists():
                self._initial_prompt_frame.place_configure(relx=0.5, rely=0.5, anchor="center")
        except Exception:
            pass

    def _center_content_in_view(self, frame, spacer=None, bias: int = 0):
        """Center an empty-state block in the visible viewport."""
        try:
            canvas = getattr(self.conflict_list, "_parent_canvas", None)
            if canvas is None:
                return
            canvas.update_idletasks()
            frame.update_idletasks()
            visible_h = max(0, canvas.winfo_height())
            frame_h = frame.winfo_reqheight()
            top_pad = max(20, ((visible_h - frame_h) // 2) + bias)
            if spacer is not None and spacer.winfo_exists():
                spacer.configure(height=top_pad)
            else:
                frame.pack_configure(pady=(top_pad, 24))
            canvas.yview_moveto(0.0)
        except Exception:
            pass

    @staticmethod
    def _conflict_extension(conflict) -> str:
        """Return normalized conflict file extension."""
        rel = str(getattr(conflict, "relative_path", "") or "").strip()
        if not rel:
            return ".other"
        ext = Path(rel).suffix.lower()
        return ext if ext else ".other"

    def _force_scan(self):
        self._scanned = True
        # Cancel any in-progress scan by bumping generation
        self._scan_generation = getattr(self, "_scan_generation", 0) + 1
        self._scanning = False
        self._scan()

    def _scan(self):
        settings = self.app.config_manager.settings
        if not settings.mods_path or not settings.mods_path.exists():
            self.summary_label.configure(text="No mods path configured. Go to Settings first.",
                                         text_color="#e94560")
            logger.warn("Conflicts", "No mods path configured")
            return

        if self._scanning:
            logger.debug("Conflicts", "Scan already in progress, skipping")
            return

        self._scanning = True
        current_gen = getattr(self, "_scan_generation", 0)
        self._set_rescan_visible(True)
        self._hide_initial_prompt()
        self._show_conflict_list()
        self._arm_top_anchor_guard("scan-start")
        self.summary_label.configure(text="Scanning for conflicts...", text_color="#999999")

        for w in self.conflict_list.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.conflict_list,
                     text="Scanning mod files for conflicts...",
                     font=ctk.CTkFont(size=13), text_color="#888888").pack(pady=40)
        self._reset_conflict_canvas_view()
        self._stabilize_conflict_viewport()

        logger.info("Conflicts", f"Starting conflict scan in: {settings.mods_path}")
        mods_path = settings.mods_path

        def do_scan():
            try:
                conflicts = self.app.conflict_detector.detect_conflicts(mods_path)
                logger.info("Conflicts", f"Found {len(conflicts)} total conflicts")

                # Detect locale-specific MSBT files
                locale_msbts = self.app.conflict_resolver.detect_locale_msbts()
                if locale_msbts:
                    logger.info("Conflicts",
                                f"Found {len(locale_msbts)} locale-specific MSBT file(s)")

                merged_dir = mods_path / "_MergedResources"
                merged_files = set()
                if merged_dir.exists():
                    for f in merged_dir.rglob("*"):
                        if f.is_file() and ".originals" not in f.parts:
                            merged_files.add(str(f.relative_to(merged_dir)).replace("\\", "/"))

                for c in conflicts:
                    if c.is_mergeable and c.relative_path in merged_files:
                        c.resolved = True
                        c.resolution = ResolutionStrategy.MERGE

                # Only deliver results if this scan hasn't been superseded
                if not self.app.shutting_down and getattr(self, "_scan_generation", 0) == current_gen:
                    self.after(0, lambda: self._on_scan_done(conflicts, locale_msbts))
            except Exception as e:
                tb = traceback.format_exc()
                logger.error("Conflicts", f"Scan failed: {e}\n{tb}")
                if not self.app.shutting_down and getattr(self, "_scan_generation", 0) == current_gen:
                    self.after(0, lambda: self._on_scan_error(str(e)))

        threading.Thread(target=do_scan, daemon=True).start()

    def _on_scan_error(self, error_msg):
        self._scanning = False
        self._scanned = True
        self._needs_render = False
        self._set_rescan_visible(True)
        self._hide_initial_prompt()
        self._show_conflict_list()
        self.summary_label.configure(
            text=f"Scan failed: {error_msg}", text_color="#e94560")

        for w in self.conflict_list.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.conflict_list,
                     text=f"Scan error: {error_msg}\nClick 'Rescan' to try again.",
                     font=ctk.CTkFont(size=13), text_color="#e94560").pack(pady=40)
        self._stabilize_conflict_viewport()
        self._bind_conflict_scroll_intent_handlers()
        self._arm_top_anchor_guard("scan-error")

    def _on_scan_done(self, conflicts, locale_msbts=None):
        self._scanning = False
        self._scanned = True
        self._conflicts = conflicts
        self._locale_msbts = locale_msbts or []
        # Always render the latest scan snapshot. Relying on current_page state
        # here can race during navigation transitions and leave stale/blank UI.
        self._needs_render = False
        try:
            self.after_idle(self._render)
        except Exception:
            self._render()

    def _render(self):
        try:
            self._render_impl()
        except Exception as e:
            logger.error("Conflicts", f"Render failed unexpectedly: {e}")
            try:
                self._set_rescan_visible(True)
                self._hide_initial_prompt()
                self._show_conflict_list()
                self.summary_label.configure(
                    text="Conflicts detected (fallback rendering active).",
                    text_color="#d4a017",
                )
                self._render_minimal_results()
            except Exception:
                pass

    def _render_impl(self):
        self._needs_render = False
        self._set_rescan_visible(True)
        self._hide_initial_prompt()
        self._show_conflict_list()

        # Normalize scan outputs so malformed rows never break rendering.
        safe_conflicts = []
        for conflict in self._conflicts or []:
            if conflict is not None:
                safe_conflicts.append(conflict)
        self._conflicts = safe_conflicts

        safe_locale = []
        for item in self._locale_msbts or []:
            try:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    safe_locale.append(item)
            except Exception:
                continue
        self._locale_msbts = safe_locale

        for w in self.conflict_list.winfo_children():
            w.destroy()
        self.auto_resolve_btn.pack_forget()
        self.fix_locale_btn.pack_forget()

        if not self._conflicts and not self._locale_msbts:
            self.summary_label.configure(
                text="No conflicts detected. All your mods are compatible.",
                text_color="#2fa572")

            empty_frame = ctk.CTkFrame(self.conflict_list, fg_color="transparent")
            empty_frame.pack(fill="x", pady=(40, 24))
            ctk.CTkLabel(empty_frame, text="No Conflicts Found",
                         font=ctk.CTkFont(size=18, weight="bold"),
                         text_color="#2fa572").pack(pady=(0, 8))
            ctk.CTkLabel(empty_frame,
                         text="All your installed mods are compatible with each other.\n"
                              "No file conflicts were detected.",
                         font=ctk.CTkFont(size=13), text_color="#888888",
                         justify="center").pack()
            self.after(10, lambda: self._center_content_in_view(empty_frame))
            return

        total = len(self._conflicts)
        mergeable = (
            sum(
                1
                for c in self._conflicts
                if bool(getattr(c, "is_mergeable", False)) and not bool(getattr(c, "resolved", False))
            )
            if self._conflicts
            else 0
        )
        resolved = (
            sum(1 for c in self._conflicts if bool(getattr(c, "resolved", False)))
            if self._conflicts
            else 0
        )
        mods = set()
        for c in self._conflicts:
            try:
                mods.update(m for m in (getattr(c, "mods_involved", None) or []) if m)
            except Exception:
                pass

        # Count by type
        type_counts = {}
        for c in self._conflicts:
            ext = self._conflict_extension(c)
            type_counts[ext] = type_counts.get(ext, 0) + 1

        type_info = ", ".join(f"{count} {ext}" for ext, count in sorted(type_counts.items()))

        locale_count = len(self._locale_msbts)
        summary_parts = []
        if total:
            summary_parts.append(f"{total} conflicts across {len(mods)} mods")
            summary_parts.append(type_info)
            summary_parts.append(f"{mergeable} auto-resolvable")
            summary_parts.append(f"{resolved} resolved")
        if locale_count:
            summary_parts.append(f"{locale_count} locale MSBT file(s) to fix")
        summary_text = " | ".join(summary_parts) if summary_parts else "No conflicts found."
        self.summary_label.configure(
            text=summary_text,
            text_color="#e94560" if (mergeable > 0 or locale_count > 0) else "#2fa572")

        if mergeable > 0:
            self.auto_resolve_btn.pack(side="left")

        if locale_count > 0:
            self.fix_locale_btn.pack(side="left", padx=(10, 0))

        # Group conflicts by type and render with explanations
        by_ext = {}
        for c in self._conflicts:
            ext = self._conflict_extension(c)
            if ext not in by_ext:
                by_ext[ext] = []
            by_ext[ext].append(c)

        severity_rank = {
            ConflictSeverity.CRITICAL: 0,
            ConflictSeverity.HIGH: 1,
            ConflictSeverity.MEDIUM: 2,
            ConflictSeverity.LOW: 3,
        }

        sorted_groups = sorted(
            by_ext.items(),
            key=lambda item: (
                min((severity_rank.get(getattr(c, "severity", None), 99) for c in item[1]), default=99),
                item[0],
            ),
        )

        rendered_conflict_rows = 0
        rendered_section_blocks = 0
        for ext, conflicts in sorted_groups:
            type_header = None
            try:
                conflicts.sort(key=lambda c: (
                    severity_rank.get(getattr(c, "severity", None), 99),
                    str(getattr(c, "relative_path", "")).lower(),
                ))
                # Type header with explanation
                info = CONFLICT_EXPLANATIONS.get(ext)
                if info:
                    type_name, description, can_merge = info
                else:
                    type_name = f"{ext.upper()} Conflicts"
                    description = "Files of this type are modified by multiple mods."
                    can_merge = False

                type_header = ctk.CTkFrame(self.conflict_list, fg_color="#1e1e38", corner_radius=8)
                type_header.pack(fill="x", pady=(8, 4))
                rendered_section_blocks += 1

                header_inner = ctk.CTkFrame(type_header, fg_color="transparent")
                header_inner.pack(fill="x", padx=12, pady=8)

                ctk.CTkLabel(header_inner, text=f"{type_name} ({len(conflicts)})",
                             font=ctk.CTkFont(size=13, weight="bold"),
                             text_color="white", anchor="w").pack(anchor="w")

                ctk.CTkLabel(header_inner, text=description,
                             font=ctk.CTkFont(size=11), text_color="#888888",
                             anchor="w", wraplength=800, justify="left").pack(anchor="w")

                if can_merge:
                    ctk.CTkLabel(header_inner,
                                 text="These conflicts can be automatically merged.",
                                 font=ctk.CTkFont(size=11), text_color="#2fa572",
                                 anchor="w").pack(anchor="w")

                # Conflict cards for this type
                for conflict in conflicts:
                    try:
                        card = ConflictCard(
                            self.conflict_list, conflict,
                            on_merge=self._merge_conflict,
                            on_keep=self._keep_conflict,
                            on_ignore=self._ignore_conflict,
                        )
                        card.pack(fill="x", pady=3)
                        rendered_conflict_rows += 1
                    except Exception as e:
                        logger.warn(
                            "Conflicts",
                            f"Failed to render conflict card for {getattr(conflict, 'relative_path', 'unknown')}: {e}",
                        )
                        fallback_row = ctk.CTkFrame(self.conflict_list, fg_color="#242438", corner_radius=6)
                        fallback_row.pack(fill="x", pady=2)
                        ctk.CTkLabel(
                            fallback_row,
                            text=f"Could not render conflict row: {getattr(conflict, 'relative_path', 'unknown')}",
                            font=ctk.CTkFont(size=12),
                            text_color="#d4a017",
                            anchor="w",
                        ).pack(fill="x", padx=10, pady=8)
            except Exception as e:
                logger.warn("Conflicts", f"Failed to render conflict section '{ext}': {e}")
                try:
                    if type_header is not None and bool(type_header.winfo_exists()):
                        type_header.destroy()
                except Exception:
                    pass
                fallback_row = ctk.CTkFrame(self.conflict_list, fg_color="#242438", corner_radius=6)
                fallback_row.pack(fill="x", pady=2)
                ctk.CTkLabel(
                    fallback_row,
                    text=f"Could not render section {ext}; falling back to minimal row(s).",
                    font=ctk.CTkFont(size=12),
                    text_color="#d4a017",
                    anchor="w",
                ).pack(fill="x", padx=10, pady=(8, 4))
                for conflict in conflicts[:8]:
                    ctk.CTkLabel(
                        fallback_row,
                        text=f"  - {getattr(conflict, 'relative_path', 'unknown')}",
                        font=ctk.CTkFont(size=11),
                        text_color="#bbbbcc",
                        anchor="w",
                    ).pack(fill="x", padx=10, pady=1)
                ctk.CTkFrame(fallback_row, height=4, fg_color="transparent").pack()

        # Render locale-specific MSBT section if any were found
        if self._locale_msbts:
            locale_header = ctk.CTkFrame(self.conflict_list, fg_color="#1e1e38", corner_radius=8)
            locale_header.pack(fill="x", pady=(12, 4))
            rendered_section_blocks += 1

            lh_inner = ctk.CTkFrame(locale_header, fg_color="transparent")
            lh_inner.pack(fill="x", padx=12, pady=8)

            ctk.CTkLabel(lh_inner,
                         text=f"Locale-Specific MSBT Files ({len(self._locale_msbts)})",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#d4a017", anchor="w").pack(anchor="w")

            ctk.CTkLabel(lh_inner,
                         text="These MSBT files have locale suffixes (e.g. msg_bgm+us_en.msbt) which "
                              "limit them to a single language. Renaming them removes the locale suffix "
                              "(e.g. → msg_bgm.msbt) so they work for all languages and avoid conflicts "
                              "between mods. Click 'Fix Locale MSBT Files' above to rename them all.",
                         font=ctk.CTkFont(size=11), text_color="#888888",
                         anchor="w", wraplength=800, justify="left").pack(anchor="w", pady=(4, 0))

            # List each locale MSBT file
            for entry in self._locale_msbts:
                try:
                    mod_name = entry[0]
                    filename = entry[1]
                except Exception:
                    continue
                row = ctk.CTkFrame(self.conflict_list, fg_color="#242438", corner_radius=6)
                row.pack(fill="x", pady=2, padx=4)

                row_inner = ctk.CTkFrame(row, fg_color="transparent")
                row_inner.pack(fill="x", padx=10, pady=6)

                ctk.CTkLabel(row_inner, text=f"\u26a0  {filename}",
                             font=ctk.CTkFont(size=12), text_color="#d4a017",
                             anchor="w").pack(side="left")
                ctk.CTkLabel(row_inner, text=f"in {mod_name}",
                             font=ctk.CTkFont(size=11), text_color="#888888",
                             anchor="w").pack(side="left", padx=(10, 0))
                rendered_conflict_rows += 1

        if rendered_conflict_rows == 0 and rendered_section_blocks == 0 and (self._conflicts or self._locale_msbts):
            # Never leave the results area blank - show a resilient fallback.
            logger.warn("Conflicts", "No conflict rows rendered; displaying fallback list")
            fallback_frame = ctk.CTkFrame(self.conflict_list, fg_color="#1e1e38", corner_radius=8)
            fallback_frame.pack(fill="x", pady=(12, 4))
            ctk.CTkLabel(
                fallback_frame,
                text="Conflicts detected but detailed cards failed to render.",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#d4a017",
                anchor="w",
            ).pack(fill="x", padx=12, pady=(10, 6))
            for conflict in self._conflicts[:20]:
                ctk.CTkLabel(
                    fallback_frame,
                    text=f"  - {getattr(conflict, 'relative_path', 'unknown')}",
                    font=ctk.CTkFont(size=11),
                    text_color="#bbbbcc",
                    anchor="w",
                ).pack(fill="x", padx=12, pady=1)
            ctk.CTkFrame(fallback_frame, height=8, fg_color="transparent").pack()

        self.conflict_list.update_idletasks()
        self._bind_conflict_scroll_intent_handlers()
        self._prune_empty_conflict_blocks()
        logger.debug(
            "Conflicts",
            f"Render complete: sections={rendered_section_blocks}, rows={rendered_conflict_rows}, "
            f"widgets={len(self.conflict_list.winfo_children())}",
        )
        self._reset_conflict_canvas_view()
        self._stabilize_conflict_viewport()
        self.after(30, self._compact_leading_conflict_gap)
        self.after(150, self._compact_leading_conflict_gap)
        self.after(22, self._ensure_results_not_blank)
        self._arm_top_anchor_guard("render")
        # Re-patch scroll speed after rendering new widgets
        self.after(100, self._patch_all_scroll_speeds)

    def _ensure_results_not_blank(self):
        """Guarantee the results area is never left empty after a completed scan."""
        if self._scanning:
            return
        if not (self._conflicts or self._locale_msbts):
            return
        self._show_conflict_list()
        try:
            children = [w for w in self.conflict_list.winfo_children() if bool(w.winfo_exists())]
        except Exception:
            children = []
        if children:
            return
        logger.warn("Conflicts", "Results were blank after render; building minimal fallback rows")
        self._render_minimal_results()

    def _render_minimal_results(self):
        """Render a plain fallback list when detailed card rendering fails."""
        for w in self.conflict_list.winfo_children():
            w.destroy()

        fallback_frame = ctk.CTkFrame(self.conflict_list, fg_color="#1e1e38", corner_radius=8)
        fallback_frame.pack(fill="x", pady=(10, 4))
        ctk.CTkLabel(
            fallback_frame,
            text="Conflicts detected (fallback view)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#d4a017",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 6))

        for conflict in self._conflicts[:60]:
            ctk.CTkLabel(
                fallback_frame,
                text=f"  - {getattr(conflict, 'relative_path', 'unknown')}",
                font=ctk.CTkFont(size=11),
                text_color="#bbbbcc",
                anchor="w",
            ).pack(fill="x", padx=12, pady=1)

        if self._locale_msbts:
            ctk.CTkLabel(
                fallback_frame,
                text=f"  - {len(self._locale_msbts)} locale-specific MSBT file(s) detected",
                font=ctk.CTkFont(size=11),
                text_color="#bbbbcc",
                anchor="w",
            ).pack(fill="x", padx=12, pady=(4, 1))

        ctk.CTkFrame(fallback_frame, height=8, fg_color="transparent").pack()
        self._reset_conflict_canvas_view()
        self._stabilize_conflict_viewport()
        self._bind_conflict_scroll_intent_handlers()
        self._arm_top_anchor_guard("minimal-render")
        self.after(30, self._compact_leading_conflict_gap)

    def _reset_conflict_canvas_view(self):
        """Normalize list canvas view after prompt/results mode changes."""
        try:
            self.conflict_list.update_idletasks()
            canvas = getattr(self.conflict_list, "_parent_canvas", None)
            if canvas is not None:
                # Force canvas window origin/scrollregion to stay canonical.
                # This prevents occasional top-gap drift where yview=0.0 but
                # the embedded frame is visually offset downward.
                try:
                    window_id = getattr(self.conflict_list, "_create_window_id", None)
                    if window_id is not None:
                        canvas.coords(window_id, 0, 0)
                except Exception:
                    pass
                try:
                    bbox = canvas.bbox("all")
                    if bbox:
                        canvas.configure(scrollregion=bbox)
                except Exception:
                    pass
                try:
                    canvas.xview_moveto(0.0)
                except Exception:
                    pass
                canvas.yview_moveto(0.0)
        except Exception:
            pass

    def _prune_empty_conflict_blocks(self):
        """Remove orphan top-level frames left by partial render failures."""
        try:
            children = list(self.conflict_list.winfo_children())
        except Exception:
            return
        for child in children:
            try:
                if not bool(child.winfo_exists()):
                    continue
                # Remove only clearly orphaned rows (large, childless blocks).
                if not child.winfo_children() and int(child.winfo_reqheight()) >= 40:
                    child.destroy()
            except Exception:
                continue

    def _compact_leading_conflict_gap(self):
        """Collapse abnormal leading blank space before first rendered block."""
        if self._scanning:
            return
        if not (self._conflicts or self._locale_msbts):
            return
        try:
            self.conflict_list.update_idletasks()
            canvas = getattr(self.conflict_list, "_parent_canvas", None)
            if canvas is None:
                return
            children = [w for w in self.conflict_list.winfo_children() if bool(w.winfo_exists())]
            if not children:
                return

            first_content = None
            for w in children:
                try:
                    if isinstance(w, ConflictCard):
                        first_content = w
                        break
                    if w.winfo_children():
                        first_content = w
                        break
                except Exception:
                    continue
            if first_content is None:
                return

            first_y = int(first_content.winfo_y())
            window_id = getattr(self.conflict_list, "_create_window_id", None)
            window_y = 0.0
            try:
                if window_id is not None:
                    coords = canvas.coords(window_id)
                    if coords and len(coords) >= 2:
                        window_y = float(coords[1])
            except Exception:
                window_y = 0.0

            view_top = 0.0
            try:
                view_top = float(canvas.canvasy(0))
            except Exception:
                view_top = 0.0

            first_canvas_y = float(first_y) + window_y
            leading_gap = first_canvas_y - view_top
            # Normal renders start near the top (~0-30px). If we detect a large
            # leading gap in true canvas space, jump to the first real block.
            if leading_gap <= 120.0:
                return

            scrollregion = canvas.cget("scrollregion")
            total_h = 0.0
            if scrollregion:
                parts = [float(p) for p in str(scrollregion).split()]
                if len(parts) == 4:
                    total_h = max(0.0, parts[3] - parts[1])
            if total_h <= 1.0:
                bbox = canvas.bbox("all")
                if bbox:
                    total_h = max(0.0, float(bbox[3] - bbox[1]))
            view_h = max(1.0, float(canvas.winfo_height()))
            scroll_h = max(1.0, total_h - view_h)
            target_px = max(0.0, min(scroll_h, float(first_canvas_y - 8.0)))
            canvas.yview_moveto(target_px / scroll_h)
            logger.warn(
                "Conflicts",
                f"Compacted leading gap (first_y={first_y}, window_y={window_y:.1f}, "
                f"view_top={view_top:.1f}, gap={leading_gap:.1f}, target_px={target_px:.1f})",
            )
        except Exception:
            pass

    def _cancel_conflict_viewport_stabilization(self):
        pending = getattr(self, "_viewport_stabilize_after_ids", None) or []
        self._viewport_stabilize_after_ids = []
        for aid in pending:
            try:
                self.after_cancel(aid)
            except Exception:
                pass

    def _stabilize_conflict_viewport(self, passes: int = 4):
        """Run a short multi-pass viewport settle so results always start at the top."""
        self._cancel_conflict_viewport_stabilization()

        def _tick(remaining: int):
            if self._scanning and remaining < passes:
                return
            self._reset_conflict_canvas_view()
            try:
                canvas = getattr(self.conflict_list, "_parent_canvas", None)
                children = [w for w in self.conflict_list.winfo_children() if bool(w.winfo_exists())]
                y0 = 0.0
                first_y = -1
                window_y = 0.0
                view_top = 0.0
                leading_gap = 0.0
                if canvas is not None:
                    try:
                        bbox = canvas.bbox("all")
                        if bbox:
                            canvas.configure(scrollregion=bbox)
                    except Exception:
                        pass
                    try:
                        window_id = getattr(self.conflict_list, "_create_window_id", None)
                        if window_id is not None:
                            canvas.coords(window_id, 0, 0)
                            coords = canvas.coords(window_id)
                            if coords and len(coords) >= 2:
                                window_y = float(coords[1])
                    except Exception:
                        window_y = 0.0
                    try:
                        y0 = float(canvas.yview()[0])
                    except Exception:
                        y0 = 0.0
                    try:
                        view_top = float(canvas.canvasy(0))
                    except Exception:
                        view_top = 0.0
                if children:
                    try:
                        first_y = int(children[0].winfo_y())
                    except Exception:
                        first_y = -1
                first_canvas_y = float(first_y if first_y >= 0 else 0) + window_y
                leading_gap = first_canvas_y - view_top
                if canvas is not None and (y0 > 0.0015 or leading_gap > 60.0):
                    if leading_gap > 60.0:
                        scrollregion = canvas.cget("scrollregion")
                        total_h = 0.0
                        if scrollregion:
                            parts = [float(p) for p in str(scrollregion).split()]
                            if len(parts) == 4:
                                total_h = max(0.0, parts[3] - parts[1])
                        if total_h <= 1.0:
                            bbox = canvas.bbox("all")
                            if bbox:
                                total_h = max(0.0, float(bbox[3] - bbox[1]))
                        view_h = max(1.0, float(canvas.winfo_height()))
                        scroll_h = max(1.0, total_h - view_h)
                        target_px = max(0.0, min(scroll_h, float(first_canvas_y - 8.0)))
                        canvas.yview_moveto(target_px / scroll_h)
                    else:
                        canvas.yview_moveto(0.0)
                logger.debug(
                    "Conflicts",
                    f"Viewport settle pass={passes - remaining + 1}/{passes} y0={y0:.4f} first_y={first_y} "
                    f"window_y={window_y:.1f} view_top={view_top:.1f} gap={leading_gap:.1f} "
                    f"children={len(children)}",
                )
            except Exception:
                pass

            if remaining > 1:
                try:
                    aid = self.after(40, lambda: _tick(remaining - 1))
                    self._viewport_stabilize_after_ids.append(aid)
                except Exception:
                    pass

        _tick(passes)

    def _merge_conflict(self, conflict):
        try:
            settings = self.app.config_manager.settings
            resolver = self.app.conflict_resolver
            create_backup = settings.backup_before_merge
            path = resolver.auto_merge_xmsbt(conflict, create_backup=create_backup)
            if path:
                conflict.resolved = True
                conflict.resolution = ResolutionStrategy.MERGE
                logger.info("Conflicts", f"Merged: {conflict.relative_path}")
                messagebox.showinfo("Merged",
                    f"Merged {conflict.relative_path}\n"
                    f"Output: {path}\n\n"
                    f"Original files have been moved to _MergedResources/.originals/\n"
                    f"to prevent double-loading by ARCropolis.")
                self._render()
            else:
                messagebox.showwarning("Warning",
                    "Could not auto-merge — no entries found in the files.\n"
                    "Use 'Keep' to choose which version to use.")
        except Exception as e:
            logger.error("Conflicts", f"Merge failed: {e}")
            messagebox.showerror("Error", f"Merge failed: {e}")

    def _keep_conflict(self, conflict, mod_name):
        try:
            settings = self.app.config_manager.settings
            resolver = self.app.conflict_resolver
            create_backup = settings.backup_before_merge
            resolver.apply_resolution(conflict, ResolutionStrategy.MANUAL, winner_mod=mod_name,
                                      create_backup=create_backup)
            conflict.resolved = True
            logger.info("Conflicts", f"Kept {mod_name} for {conflict.relative_path}")
            self._render()
        except Exception as e:
            logger.error("Conflicts", f"Resolution failed: {e}")
            messagebox.showerror("Error", f"Resolution failed: {e}")

    def _ignore_conflict(self, conflict):
        conflict.resolution = ResolutionStrategy.IGNORE
        conflict.resolved = True
        logger.info("Conflicts", f"Ignored: {conflict.relative_path}")
        self._render()

    def _auto_resolve_all(self):
        try:
            settings = self.app.config_manager.settings
            resolver = self.app.conflict_resolver
            unresolved = [c for c in self._conflicts if c.is_mergeable and not c.resolved]
            create_backup = settings.backup_before_merge
            resolved = resolver.resolve_all_auto(unresolved, create_backup=create_backup)
            # Only count conflicts that were actually resolved by resolve_all_auto
            # (auto_merge_xmsbt sets conflict.resolved = True on success)
            actually_resolved = sum(1 for c in unresolved if c.resolved)
            failed = len(unresolved) - actually_resolved
            msg = f"Resolved {actually_resolved} conflict(s) into _MergedResources."
            msg += f"\nOriginal files moved to _MergedResources/.originals/ to prevent double-loading."
            if failed > 0:
                msg += f"\n\n{failed} conflict(s) could not be auto-merged."
            logger.info("Conflicts", f"Auto-resolved {actually_resolved}/{len(unresolved)} conflicts")
            messagebox.showinfo("Resolved", msg)
            self._render()
        except Exception as e:
            logger.error("Conflicts", f"Auto-resolve failed: {e}")
            messagebox.showerror("Error", f"Auto-resolve failed: {e}")

    def _restore_originals(self):
        """Restore all previously merged XMSBT files to their original state."""
        confirm = messagebox.askyesno(
            "Restore Originals",
            "This will:\n"
            "  - Move original XMSBT files back to their mod folders\n"
            "  - Remove merged files from _MergedResources\n\n"
            "This undoes previous conflict merges so you can re-merge\n"
            "or let individual mods handle text independently.\n\nContinue?"
        )
        if not confirm:
            return
        try:
            resolver = self.app.conflict_resolver
            count = resolver.restore_originals()
            logger.info("Conflicts", f"Restored {count} original files")
            messagebox.showinfo("Restored", f"Restored {count} file(s) to original state.")
            self._scanned = False
            self._scan()
        except Exception as e:
            logger.error("Conflicts", f"Restore failed: {e}")
            messagebox.showerror("Error", f"Restore failed: {e}")

    def _fix_locale_msbts(self):
        """Rename locale-specific MSBT files to locale-independent names."""
        if not self._locale_msbts:
            messagebox.showinfo("Info", "No locale-specific MSBT files to fix.")
            return

        count = len(self._locale_msbts)
        examples = "\n".join(
            f"  {fn}  →  {fn.split('+')[0]}.msbt  (in {mod})"
            for mod, fn, _ in self._locale_msbts[:5]
        )
        if count > 5:
            examples += f"\n  ... and {count - 5} more"

        confirm = messagebox.askyesno(
            "Fix Locale MSBT Files",
            f"This will rename {count} locale-specific MSBT file(s) "
            f"to locale-independent names:\n\n{examples}\n\n"
            f"This makes them work for all languages and avoids conflicts "
            f"between mods.\n\nContinue?"
        )
        if not confirm:
            return

        try:
            resolver = self.app.conflict_resolver
            renamed = resolver.rename_locale_msbt_files()
            logger.info("Conflicts", f"Fixed {renamed} locale MSBT file(s)")
            messagebox.showinfo("Done", f"Renamed {renamed} locale-specific MSBT file(s).")
            # Re-scan to update the view
            self._scanned = False
            self._scan()
        except Exception as e:
            logger.error("Conflicts", f"Fix locale MSBTs failed: {e}")
            messagebox.showerror("Error", f"Failed to fix locale MSBT files: {e}")
