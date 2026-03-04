"""Conflict detection and resolution page with explanations."""
import threading
import traceback
import time
from pathlib import Path
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from src.ui.base_page import BasePage
from src.ui.widgets.conflict_card import ConflictCard
from src.models.conflict import ResolutionStrategy, ConflictSeverity
from src.utils.logger import logger
from src.ui import theme

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
    _TOP_ANCHOR_GUARD_MAX_SECONDS = 8.0
    _TOP_ANCHOR_MIN_HOLD_SECONDS = 0.15

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
        self._top_anchor_guard_armed_at = 0.0
        self.conflict_list = None
        self._conflict_list_host = None
        self._conflict_canvas = None
        self._conflict_scrollbar = None
        self._conflict_window_id = None
        self.conflict_search_var = tk.StringVar()
        self.conflict_view_var = ctk.StringVar(value="By Type")
        self._build_ui()
        self.conflict_search_var.trace_add("write", lambda *_: self._on_conflict_view_changed())

    def _build_ui(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(25, 10))

        title = ctk.CTkLabel(header_frame, text="Conflicts",
                             font=ctk.CTkFont(size=theme.FONT_PAGE_TITLE, weight="bold"), anchor="w")
        title.pack(side="left")

        self.header_btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        self.scan_btn = ctk.CTkButton(self.header_btn_frame, text="Rescan", width=110,
                                      command=self._force_scan, corner_radius=8, height=34)
        self.fix_text_btn_header = ctk.CTkButton(
            self.header_btn_frame, text="Fix Text Conflicts",
            fg_color=theme.WARNING_ALT, hover_color=theme.HOVER_WARNING,
            command=self._fix_text_conflicts, width=185,
            corner_radius=8, height=34,
        )
        self.restore_btn_header = ctk.CTkButton(
            self.header_btn_frame, text="Restore Originals",
            fg_color=theme.DANGER_CLEAR, hover_color=theme.HOVER_DANGER_CLEAR,
            command=self._restore_originals, width=165,
            corner_radius=8, height=34,
        )

        explain_frame = ctk.CTkFrame(self, fg_color=theme.BG_CARD_INNER, corner_radius=10)
        explain_frame.pack(fill="x", padx=30, pady=(0, 8))

        explain_inner = ctk.CTkFrame(explain_frame, fg_color="transparent")
        explain_inner.pack(fill="x", padx=15, pady=12)

        ctk.CTkLabel(explain_inner, text="What are conflicts?",
                     font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS, weight="bold"), anchor="w",
                     text_color=theme.TEXT_SECONDARY).pack(anchor="w")

        ctk.CTkLabel(explain_inner,
                     text="Conflicts occur when two or more mods modify the same game file. "
                          "When this happens, only one mod's version of the file gets loaded by the game. "
                          "Text file conflicts (.xmsbt) are the most common and can cause missing "
                          "character/stage names. These can be auto-merged. Other conflict types "
                          "(PRC, MSBT) usually don't cause crashes but may result in one mod's "
                          "changes being overridden by another.",
                     font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), text_color=theme.TEXT_MUTED, anchor="w",
                     wraplength=theme.WRAP_WIDE, justify="left").pack(anchor="w", pady=(4, 0))

        self.summary_label = ctk.CTkLabel(self, text="Click 'Scan for Conflicts' to check for mod file conflicts.",
                                          font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS),
                                          text_color=theme.TEXT_MUTED, anchor="w")
        self.summary_label.pack(fill="x", padx=30, pady=(0, 5))

        self.view_controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        view_left = ctk.CTkFrame(self.view_controls_frame, fg_color="transparent")
        view_left.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            view_left,
            text="View",
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM, weight="bold"),
            text_color=theme.INFO_SUMMARY,
            anchor="w",
        ).pack(side="left", padx=(0, 8))

        self.view_mode_menu = ctk.CTkOptionMenu(
            view_left,
            values=["By Type", "By Fighter/Form/Slot"],
            variable=self.conflict_view_var,
            command=lambda _value: self._on_conflict_view_changed(),
            width=190,
            height=34,
            corner_radius=8,
        )
        self.view_mode_menu.pack(side="left")

        self.search_entry = ctk.CTkEntry(
            self.view_controls_frame,
            textvariable=self.conflict_search_var,
            placeholder_text="Filter by mod, file, fighter, or form...",
            width=320,
            height=34,
        )
        self.search_entry.pack(side="right")

        self.auto_btn_frame = ctk.CTkFrame(self, fg_color="transparent")

        self.auto_resolve_btn = ctk.CTkButton(
            self.auto_btn_frame, text="Fix Text Conflicts",
            fg_color=theme.WARNING_ALT, hover_color=theme.HOVER_WARNING,
            command=self._fix_text_conflicts, width=210,
            corner_radius=8, height=34,
        )

        self.fix_locale_btn = ctk.CTkButton(
            self.auto_btn_frame, text="Fix Locale MSBT Files",
            fg_color=theme.PRIMARY, hover_color=theme.HOVER_PRIMARY,
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
        """Create a deterministic scroll host for conflict results."""
        if self._conflict_list_host is not None:
            try:
                if bool(self._conflict_list_host.winfo_exists()):
                    return
            except Exception:
                pass

        self._conflict_list_host = ctk.CTkFrame(self._results_stack, fg_color="transparent")
        try:
            setattr(self._conflict_list_host, "_ssbum_conflicts_scroll_host", True)
        except Exception:
            pass
        self._conflict_list_host.pack(fill="both", expand=True)

        self._conflict_canvas = tk.Canvas(
            self._conflict_list_host,
            highlightthickness=0,
            borderwidth=0,
            bg=theme.BG_APP,
        )
        # Exclude this canvas from BasePage's direct tk.Canvas wheel patch;
        # global scroll handling in App must remain the source of truth.
        try:
            setattr(self._conflict_canvas, "_ssbum_skip_base_scroll_patch", True)
        except Exception:
            pass
        self._conflict_scrollbar = ctk.CTkScrollbar(
            self._conflict_list_host,
            orientation="vertical",
            command=self._conflict_canvas.yview,
        )
        self._conflict_canvas.configure(yscrollcommand=self._conflict_scrollbar.set)

        self._conflict_list_host.grid_columnconfigure(0, weight=1)
        self._conflict_list_host.grid_rowconfigure(0, weight=1)
        self._conflict_canvas.grid(row=0, column=0, sticky="nsew")
        self._conflict_scrollbar.grid(row=0, column=1, sticky="ns")

        self.conflict_list = ctk.CTkFrame(self._conflict_canvas, fg_color="transparent")
        self._conflict_window_id = self._conflict_canvas.create_window(
            0, 0, window=self.conflict_list, anchor="nw"
        )

        # Keep scrollregion and content width in sync.
        self.conflict_list.bind(
            "<Configure>",
            lambda _e: self._conflict_canvas.configure(scrollregion=self._conflict_canvas.bbox("all")),
            add="+",
        )
        self._conflict_canvas.bind(
            "<Configure>",
            lambda _e: self._conflict_canvas.itemconfigure(
                self._conflict_window_id, width=self._conflict_canvas.winfo_width()
            ),
            add="+",
        )
        self.conflict_list.bind("<Configure>", self._on_page_configure, add="+")

        # Preserve legacy attribute access used by existing helpers.
        self.conflict_list._parent_canvas = self._conflict_canvas
        self.conflict_list._scrollbar = self._conflict_scrollbar
        self.conflict_list._create_window_id = self._conflict_window_id

    def _prune_stale_conflict_list_hosts(self):
        """Ensure only the active conflict list host remains mounted."""
        try:
            children = list(self._results_stack.winfo_children())
        except Exception:
            return
        removed = 0
        for widget in children:
            try:
                if widget is self._initial_prompt_host:
                    continue
                if not bool(getattr(widget, "_ssbum_conflicts_scroll_host", False)):
                    continue
                if self._conflict_list_host is not None and widget is self._conflict_list_host:
                    continue
                if bool(widget.winfo_exists()):
                    widget.destroy()
                    removed += 1
            except Exception:
                continue
        if removed:
            logger.warn("Conflicts", f"Removed stale scroll hosts: {removed}")

    def _recreate_conflict_list(self):
        """Reset list viewport and prune stale hosts without re-layering widgets."""
        self._create_conflict_list()
        self._prune_stale_conflict_list_hosts()
        self._show_conflict_list()
        self._reset_conflict_canvas_view()
        logger.debug("Conflicts", "Reset scroll host")

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
                     font=ctk.CTkFont(size=theme.FONT_SUBSECTION, weight="bold"),
                     text_color=theme.TEXT_SECONDARY).pack(pady=(0, 8))

        ctk.CTkLabel(self._initial_prompt_frame,
                     text="Click the button below to scan your mods for file conflicts.\n"
                          "This may take a few seconds depending on how many mods you have installed.",
                     font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS), text_color=theme.TEXT_DIM,
                     justify="center").pack(pady=(0, 20))

        scan_prompt_btn = ctk.CTkButton(
            self._initial_prompt_frame, text="\U0001F50D  Scan for Conflicts", width=220, height=40,
            fg_color=theme.PRIMARY, hover_color=theme.HOVER_PRIMARY,
            font=ctk.CTkFont(size=theme.FONT_CARD_HEADING, weight="bold"),
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
                self._set_view_controls_visible(True)
                has_actions = bool(self.auto_resolve_btn.winfo_manager() or self.fix_locale_btn.winfo_manager())
                self._set_auto_actions_visible(has_actions)
            else:
                if self.summary_label.winfo_manager():
                    self.summary_label.pack_forget()
                self._set_view_controls_visible(False)
                self._set_auto_actions_visible(False)
        except Exception:
            pass

    def _set_view_controls_visible(self, visible: bool):
        try:
            if visible:
                if not self.view_controls_frame.winfo_manager():
                    self.view_controls_frame.pack(fill="x", padx=30, pady=(0, 8), before=self._results_stack)
            else:
                if self.view_controls_frame.winfo_manager():
                    self.view_controls_frame.pack_forget()
        except Exception:
            pass

    def _set_auto_actions_visible(self, visible: bool):
        try:
            if visible:
                if not self.auto_btn_frame.winfo_manager():
                    self.auto_btn_frame.pack(fill="x", padx=30, pady=(0, 8), before=self._results_stack)
            else:
                if self.auto_btn_frame.winfo_manager():
                    self.auto_btn_frame.pack_forget()
        except Exception:
            pass

    def _on_conflict_view_changed(self):
        if self._scanning or self._initial_prompt_visible:
            return
        if not self._scanned and not self._conflicts and not self._locale_msbts:
            return
        self._render()

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
            self._prune_stale_conflict_list_hosts()
            if self._conflict_list_host is not None:
                if not self._conflict_list_host.winfo_manager():
                    self._conflict_list_host.pack(fill="both", expand=True)
                self._conflict_list_host.lift()
            if self._initial_prompt_host.winfo_manager():
                self._initial_prompt_host.lower()
        except Exception:
            pass

    def _set_rescan_visible(self, visible: bool):
        try:
            if self.scan_btn.winfo_manager():
                self.scan_btn.pack_forget()
            if self.fix_text_btn_header.winfo_manager():
                self.fix_text_btn_header.pack_forget()
            if self.restore_btn_header.winfo_manager():
                self.restore_btn_header.pack_forget()
            if self.header_btn_frame.winfo_manager():
                self.header_btn_frame.pack_forget()

            if visible:
                self.header_btn_frame.pack(side="right")
                # Pack restore first so rescan appears to its left.
                self.restore_btn_header.pack(side="right")
                self.fix_text_btn_header.pack(side="right", padx=(0, 8))
                self.scan_btn.pack(side="right", padx=(0, 8))
        except Exception:
            pass

    def _on_page_configure(self, _event=None):
        if self._initial_prompt_visible:
            self.after(0, self._reposition_initial_prompt)

    def _widget_has_meaningful_text(self, widget, depth: int = 0) -> bool:
        """Return True when widget subtree contains visible non-empty label text."""
        try:
            if isinstance(widget, ctk.CTkLabel):
                text = str(widget.cget("text") or "").strip()
                if text:
                    return True
        except Exception:
            pass
        if depth >= 3:
            return False
        try:
            for child in widget.winfo_children():
                if self._widget_has_meaningful_text(child, depth + 1):
                    return True
        except Exception:
            return False
        return False

    def _cancel_top_anchor_guard(self):
        self._top_anchor_guard_active = False
        self._top_anchor_guard_until = 0.0
        self._top_anchor_guard_armed_at = 0.0
        if self._top_anchor_after_id:
            try:
                self.after_cancel(self._top_anchor_after_id)
            except Exception:
                pass
            self._top_anchor_after_id = None

    def _arm_top_anchor_guard(self, source: str = "render"):
        """Keep results pinned to top during post-render stabilization."""
        self._cancel_top_anchor_guard()
        self._top_anchor_guard_active = True
        self._top_anchor_guard_armed_at = time.monotonic()
        self._top_anchor_guard_until = time.monotonic() + self._TOP_ANCHOR_GUARD_MAX_SECONDS
        try:
            self._top_anchor_after_id = self.after(0, self._run_top_anchor_guard)
        except Exception:
            self._top_anchor_after_id = None
        logger.debug("Conflicts", f"Top-anchor guard armed ({source})")

    def _can_release_top_anchor_guard(self) -> bool:
        if not self._top_anchor_guard_active:
            return False
        try:
            age = time.monotonic() - float(self._top_anchor_guard_armed_at)
            return age >= self._TOP_ANCHOR_MIN_HOLD_SECONDS
        except Exception:
            return True

    def release_top_anchor_guard(self, reason: str = "external", force: bool = False) -> bool:
        """Release top-anchor guard after minimum hold window or immediately when forced."""
        if not force and not self._can_release_top_anchor_guard():
            return False
        self._cancel_top_anchor_guard()
        logger.debug("Conflicts", f"Top-anchor guard released ({reason})")
        return True

    def _run_top_anchor_guard(self):
        self._top_anchor_after_id = None
        if not self._top_anchor_guard_active:
            return
        try:
            if time.monotonic() >= float(self._top_anchor_guard_until):
                self._debug_layout_snapshot("guard-expire")
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

    @staticmethod
    def _conflict_display_path(conflict) -> str:
        return str(getattr(conflict, "display_path", "") or getattr(conflict, "relative_path", "unknown"))

    @staticmethod
    def _conflict_display_line(conflict) -> str:
        path = ConflictsPage._conflict_display_path(conflict)
        slot_summary = str(getattr(conflict, "slot_summary", "") or "").strip()
        if slot_summary:
            return f"{path} | {slot_summary}"
        return path

    @staticmethod
    def _normalize_filter_text(value: str) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _conflict_filter_blob(conflict) -> str:
        parts = [
            getattr(conflict, "relative_path", ""),
            getattr(conflict, "display_path", ""),
            getattr(conflict, "slot_summary", ""),
            getattr(conflict, "slot_group_label", ""),
            getattr(conflict, "file_type", ""),
        ]
        try:
            parts.extend(getattr(conflict, "mods_involved", []) or [])
        except Exception:
            pass
        try:
            parts.extend((getattr(conflict, "mod_display_labels", {}) or {}).values())
        except Exception:
            pass
        return " ".join(str(part or "") for part in parts).lower()

    @staticmethod
    def _locale_filter_blob(entry) -> str:
        try:
            mod_name = entry[0]
            filename = entry[1]
        except Exception:
            return ""
        return f"{mod_name} {filename}".lower()

    def _filtered_conflicts(self) -> tuple[list, list, str]:
        filter_text = self._normalize_filter_text(self.conflict_search_var.get())
        conflicts = list(self._conflicts or [])
        locale_entries = list(self._locale_msbts or [])
        if not filter_text:
            return conflicts, locale_entries, ""

        filtered_conflicts = [
            conflict for conflict in conflicts
            if filter_text in self._conflict_filter_blob(conflict)
        ]
        filtered_locale = [
            entry for entry in locale_entries
            if filter_text in self._locale_filter_blob(entry)
        ]
        return filtered_conflicts, filtered_locale, filter_text

    def _build_type_sections(self, conflicts: list, severity_rank: dict) -> list[dict]:
        by_ext: dict[str, list] = {}
        for conflict in conflicts:
            ext = self._conflict_extension(conflict)
            by_ext.setdefault(ext, []).append(conflict)

        sections: list[dict] = []
        for ext, group_conflicts in by_ext.items():
            info = CONFLICT_EXPLANATIONS.get(ext)
            if info:
                title, description, can_merge = info
            else:
                title = f"{ext.upper()} Conflicts"
                description = "Files of this type are modified by multiple mods."
                can_merge = False
            sections.append({
                "key": ext,
                "title": title,
                "description": description,
                "can_merge": can_merge,
                "conflicts": group_conflicts,
            })

        sections.sort(key=lambda section: (
            min(
                (severity_rank.get(getattr(conflict, "severity", None), 99)
                 for conflict in section["conflicts"]),
                default=99,
            ),
            str(section["key"]).lower(),
        ))
        return sections

    @staticmethod
    def _summarize_group_types(conflicts: list) -> str:
        counts: dict[str, int] = {}
        for conflict in conflicts:
            ext = ConflictsPage._conflict_extension(conflict)
            counts[ext] = counts.get(ext, 0) + 1
        return ", ".join(
            f"{count} {ext}" for ext, count in sorted(counts.items(), key=lambda item: item[0])
        )

    @staticmethod
    def _preferred_slot_group_label(conflicts: list) -> str:
        labels = [
            str(getattr(conflict, "slot_group_label", "") or "").strip()
            for conflict in conflicts
            if str(getattr(conflict, "slot_group_label", "") or "").strip()
        ]
        if not labels:
            return ""
        labels.sort(key=lambda value: (-len(value), value.lower()))
        return labels[0]

    def _build_slot_sections(self, conflicts: list, severity_rank: dict) -> list[dict]:
        by_slot: dict[str, list] = {}
        for conflict in conflicts:
            slot_key = str(getattr(conflict, "slot_group_key", "") or "").strip()
            by_slot.setdefault(slot_key or "__global__", []).append(conflict)

        sections: list[dict] = []
        for slot_key, group_conflicts in by_slot.items():
            mods = {
                mod_name
                for conflict in group_conflicts
                for mod_name in (getattr(conflict, "mods_involved", None) or [])
                if mod_name
            }
            type_summary = self._summarize_group_types(group_conflicts)
            if slot_key == "__global__":
                title = "Global / Non-slot-specific"
                description = (
                    "These conflicts do not map cleanly to a single fighter slot. "
                    f"{len(group_conflicts)} conflict(s) across {len(mods)} mod(s)"
                )
            else:
                title = self._preferred_slot_group_label(group_conflicts) or "Fighter/Form/Slot Group"
                description = (
                    "All files in this group affect the same fighter/form/slot. "
                    f"{len(group_conflicts)} conflict(s) across {len(mods)} mod(s)"
                )
            if type_summary:
                description = f"{description} | {type_summary}"
            sections.append({
                "key": slot_key,
                "title": title,
                "description": description,
                "can_merge": any(bool(getattr(conflict, "is_mergeable", False)) for conflict in group_conflicts),
                "conflicts": group_conflicts,
            })

        sections.sort(key=lambda section: (
            1 if section["key"] == "__global__" else 0,
            min(
                (severity_rank.get(getattr(conflict, "severity", None), 99)
                 for conflict in section["conflicts"]),
                default=99,
            ),
            str(section["title"]).lower(),
        ))
        return sections

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
                                         text_color=theme.ACCENT)
            logger.warn("Conflicts", "No mods path configured")
            return

        if self._scanning:
            logger.debug("Conflicts", "Scan already in progress, skipping")
            return

        self._scanning = True
        current_gen = getattr(self, "_scan_generation", 0)
        self._set_rescan_visible(True)
        self._hide_initial_prompt()
        self._set_auto_actions_visible(False)
        self._recreate_conflict_list()
        self._show_conflict_list()
        self._arm_top_anchor_guard("scan-start")
        self.summary_label.configure(text="Scanning for conflicts...", text_color=theme.TEXT_MUTED)

        for w in self.conflict_list.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.conflict_list,
                     text="Scanning mod files for conflicts...",
                     font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS), text_color=theme.TEXT_DIM).pack(pady=40)
        self._reset_conflict_canvas_view()
        self._stabilize_conflict_viewport()

        logger.info("Conflicts", f"Starting conflict scan in: {settings.mods_path}")
        mods_path = settings.mods_path

        def do_scan():
            try:
                conflicts = self.app.conflict_detector.detect_conflicts(mods_path)
                logger.info("Conflicts", f"Found {len(conflicts)} total conflicts")

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
        self._set_auto_actions_visible(False)
        self._recreate_conflict_list()
        self._show_conflict_list()
        self.summary_label.configure(
            text=f"Scan failed: {error_msg}", text_color=theme.ACCENT)

        for w in self.conflict_list.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.conflict_list,
                     text=f"Scan error: {error_msg}\nClick 'Rescan' to try again.",
                     font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS), text_color=theme.ACCENT).pack(pady=40)
        self._stabilize_conflict_viewport()
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
                    text_color=theme.WARNING,
                )
                self._render_minimal_results()
            except Exception:
                pass

    def _render_impl(self):
        self._needs_render = False
        self._set_rescan_visible(True)
        self._hide_initial_prompt()
        self._recreate_conflict_list()
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
        self._set_auto_actions_visible(False)

        filtered_conflicts, filtered_locale_msbts, filter_text = self._filtered_conflicts()
        overall_mergeable_pending = (
            sum(
                1
                for c in self._conflicts
                if bool(getattr(c, "is_mergeable", False)) and not bool(getattr(c, "resolved", False))
            )
            if self._conflicts
            else 0
        )
        overall_locale_count = len(self._locale_msbts)

        if not self._conflicts and not self._locale_msbts:
            self.summary_label.configure(
                text="No conflicts detected. All your mods are compatible.",
                text_color=theme.SUCCESS)

            empty_frame = ctk.CTkFrame(self.conflict_list, fg_color="transparent")
            empty_frame.pack(fill="x", pady=(40, 24))
            ctk.CTkLabel(empty_frame, text="No Conflicts Found",
                         font=ctk.CTkFont(size=theme.FONT_SUBSECTION, weight="bold"),
                         text_color=theme.SUCCESS).pack(pady=(0, 8))
            ctk.CTkLabel(empty_frame,
                         text="All your installed mods are compatible with each other.\n"
                              "No file conflicts were detected.",
                         font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS), text_color=theme.TEXT_DIM,
                         justify="center").pack()
            self.after(theme.DELAY_DIALOG_LAYOUT, lambda: self._center_content_in_view(empty_frame))
            return

        if not filtered_conflicts and not filtered_locale_msbts and filter_text:
            self.summary_label.configure(
                text=f"No conflicts match the current filter: {self.conflict_search_var.get().strip()}",
                text_color=theme.WARNING,
            )
            empty_frame = ctk.CTkFrame(self.conflict_list, fg_color="transparent")
            empty_frame.pack(fill="x", pady=(40, 24))
            ctk.CTkLabel(
                empty_frame,
                text="No Matching Results",
                font=ctk.CTkFont(size=theme.FONT_SUBSECTION, weight="bold"),
                text_color=theme.WARNING,
            ).pack(pady=(0, 8))
            ctk.CTkLabel(
                empty_frame,
                text="Adjust the filter text or switch back to the full conflict list.",
                font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS),
                text_color=theme.TEXT_DIM,
                justify="center",
            ).pack()
            self.after(theme.DELAY_DIALOG_LAYOUT, lambda: self._center_content_in_view(empty_frame))
            return

        total = len(filtered_conflicts)
        mergeable_pending = (
            sum(
                1
                for c in filtered_conflicts
                if bool(getattr(c, "is_mergeable", False)) and not bool(getattr(c, "resolved", False))
            )
            if filtered_conflicts
            else 0
        )
        already_merged = (
            sum(
                1
                for c in filtered_conflicts
                if bool(getattr(c, "resolved", False))
                and bool(getattr(c, "is_mergeable", False))
                and getattr(c, "resolution", None) == ResolutionStrategy.MERGE
            )
            if filtered_conflicts
            else 0
        )
        already_resolved = (
            sum(1 for c in filtered_conflicts if bool(getattr(c, "resolved", False)))
            if filtered_conflicts
            else 0
        )
        already_resolved_other = max(0, already_resolved - already_merged)
        mods = set()
        for c in filtered_conflicts:
            try:
                mods.update(m for m in (getattr(c, "mods_involved", None) or []) if m)
            except Exception:
                pass

        type_counts = {}
        for c in filtered_conflicts:
            ext = self._conflict_extension(c)
            type_counts[ext] = type_counts.get(ext, 0) + 1

        type_info = ", ".join(f"{count} {ext}" for ext, count in sorted(type_counts.items()))

        locale_count = len(filtered_locale_msbts)
        summary_parts = []
        if total:
            if filter_text:
                summary_parts.append(f"Showing {total} of {len(self._conflicts)} conflicts")
            else:
                summary_parts.append(f"{total} conflicts across {len(mods)} mods")
            if type_info:
                summary_parts.append(type_info)
            if self.conflict_view_var.get() == "By Fighter/Form/Slot":
                summary_parts.append("grouped by fighter/form/slot")
            if mergeable_pending > 0:
                summary_parts.append(f"{mergeable_pending} can be auto-fixed")
            elif filter_text and overall_mergeable_pending > 0:
                summary_parts.append(f"{overall_mergeable_pending} auto-fixable total")
            if already_merged > 0:
                summary_parts.append(f"{already_merged} already merged")
            if already_resolved_other > 0:
                summary_parts.append(f"{already_resolved_other} already resolved")
        if overall_locale_count:
            if filter_text:
                summary_parts.append(f"{locale_count} of {overall_locale_count} locale MSBT file(s) shown")
            else:
                summary_parts.append(f"{locale_count} locale MSBT file(s) to fix")
        summary_text = " | ".join(summary_parts) if summary_parts else "No conflicts found."
        self.summary_label.configure(
            text=summary_text,
            text_color=theme.ACCENT if (overall_mergeable_pending > 0 or overall_locale_count > 0) else theme.SUCCESS)

        if overall_mergeable_pending > 0 or overall_locale_count > 0:
            self.auto_resolve_btn.pack(side="left")

        if overall_locale_count > 0:
            self.fix_locale_btn.pack(side="left", padx=(10, 0))
        self._set_auto_actions_visible(bool(overall_mergeable_pending > 0 or overall_locale_count > 0))

        severity_rank = {
            ConflictSeverity.CRITICAL: 0,
            ConflictSeverity.HIGH: 1,
            ConflictSeverity.MEDIUM: 2,
            ConflictSeverity.LOW: 3,
        }

        if self.conflict_view_var.get() == "By Fighter/Form/Slot":
            sections = self._build_slot_sections(filtered_conflicts, severity_rank)
        else:
            sections = self._build_type_sections(filtered_conflicts, severity_rank)

        rendered_conflict_rows = 0
        rendered_section_blocks = 0
        for section in sections:
            section_header = None
            section_title = str(section.get("title", "Conflicts"))
            section_description = str(section.get("description", "") or "").strip()
            conflicts = list(section.get("conflicts", []) or [])
            try:
                if self.conflict_view_var.get() == "By Fighter/Form/Slot":
                    conflicts.sort(key=lambda c: (
                        self._conflict_extension(c),
                        severity_rank.get(getattr(c, "severity", None), 99),
                        self._conflict_display_path(c).lower(),
                    ))
                else:
                    conflicts.sort(key=lambda c: (
                        severity_rank.get(getattr(c, "severity", None), 99),
                        self._conflict_display_path(c).lower(),
                    ))

                section_header = ctk.CTkFrame(self.conflict_list, fg_color=theme.BG_CARD_INNER, corner_radius=8)
                section_header.pack(fill="x", pady=(8, 4))
                rendered_section_blocks += 1

                header_inner = ctk.CTkFrame(section_header, fg_color="transparent")
                header_inner.pack(fill="x", padx=12, pady=8)

                ctk.CTkLabel(header_inner, text=f"{section_title} ({len(conflicts)})",
                             font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS, weight="bold"),
                             text_color=theme.TEXT_PRIMARY, anchor="w").pack(anchor="w")

                if section_description:
                    ctk.CTkLabel(header_inner, text=section_description,
                                 font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.TEXT_DIM,
                                 anchor="w", wraplength=theme.WRAP_LARGE, justify="left").pack(anchor="w")

                pending_in_group = sum(
                    1 for c in conflicts
                    if bool(getattr(c, "is_mergeable", False)) and not bool(getattr(c, "resolved", False))
                )
                merged_in_group = sum(
                    1 for c in conflicts
                    if bool(getattr(c, "is_mergeable", False))
                    and bool(getattr(c, "resolved", False))
                    and getattr(c, "resolution", None) == ResolutionStrategy.MERGE
                )
                if pending_in_group > 0:
                    merge_hint = f"{pending_in_group} conflict(s) can be automatically merged."
                elif merged_in_group > 0:
                    merge_hint = "These conflicts are already merged."
                else:
                    merge_hint = ""
                if merge_hint:
                    ctk.CTkLabel(header_inner,
                                 text=merge_hint,
                                 font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.SUCCESS,
                                 anchor="w").pack(anchor="w")

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
                        fallback_row = ctk.CTkFrame(self.conflict_list, fg_color=theme.BG_CARD, corner_radius=6)
                        fallback_row.pack(fill="x", pady=2)
                        ctk.CTkLabel(
                            fallback_row,
                            text=f"Could not render conflict row: {self._conflict_display_line(conflict)}",
                            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
                            text_color=theme.WARNING,
                            anchor="w",
                        ).pack(fill="x", padx=10, pady=8)
            except Exception as e:
                logger.warn("Conflicts", f"Failed to render conflict section '{section_title}': {e}")
                try:
                    if section_header is not None and bool(section_header.winfo_exists()):
                        section_header.destroy()
                except Exception:
                    pass
                fallback_row = ctk.CTkFrame(self.conflict_list, fg_color=theme.BG_CARD, corner_radius=6)
                fallback_row.pack(fill="x", pady=2)
                ctk.CTkLabel(
                    fallback_row,
                    text=f"Could not render section {section_title}; falling back to minimal row(s).",
                    font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
                    text_color=theme.WARNING,
                    anchor="w",
                ).pack(fill="x", padx=10, pady=(8, 4))
                for conflict in conflicts[:8]:
                    ctk.CTkLabel(
                        fallback_row,
                        text=f"  - {self._conflict_display_line(conflict)}",
                        font=ctk.CTkFont(size=theme.FONT_BODY),
                        text_color=theme.TEXT_DETAIL,
                        anchor="w",
                    ).pack(fill="x", padx=10, pady=1)
                ctk.CTkFrame(fallback_row, height=4, fg_color="transparent").pack()

        if filtered_locale_msbts:
            locale_header = ctk.CTkFrame(self.conflict_list, fg_color=theme.BG_CARD_INNER, corner_radius=8)
            locale_header.pack(fill="x", pady=(12, 4))
            rendered_section_blocks += 1

            lh_inner = ctk.CTkFrame(locale_header, fg_color="transparent")
            lh_inner.pack(fill="x", padx=12, pady=8)

            ctk.CTkLabel(lh_inner,
                         text=f"Locale-Specific MSBT Files ({len(filtered_locale_msbts)})",
                         font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS, weight="bold"),
                         text_color=theme.WARNING, anchor="w").pack(anchor="w")

            ctk.CTkLabel(lh_inner,
                         text="These MSBT files have locale suffixes (e.g. msg_bgm+us_en.msbt) which "
                              "limit them to a single language. Renaming them removes the locale suffix "
                              "(e.g. → msg_bgm.msbt) so they work for all languages and avoid conflicts "
                              "between mods. Click 'Fix Locale MSBT Files' above to rename them all.",
                         font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.TEXT_DIM,
                         anchor="w", wraplength=theme.WRAP_LARGE, justify="left").pack(anchor="w", pady=(4, 0))

            for entry in filtered_locale_msbts:
                try:
                    mod_name = entry[0]
                    filename = entry[1]
                except Exception:
                    continue
                row = ctk.CTkFrame(self.conflict_list, fg_color=theme.BG_CARD, corner_radius=6)
                row.pack(fill="x", pady=2, padx=4)

                row_inner = ctk.CTkFrame(row, fg_color="transparent")
                row_inner.pack(fill="x", padx=10, pady=6)

                ctk.CTkLabel(row_inner, text=f"\u26a0  {filename}",
                             font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), text_color=theme.WARNING,
                             anchor="w").pack(side="left")
                ctk.CTkLabel(row_inner, text=f"in {mod_name}",
                             font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.TEXT_DIM,
                             anchor="w").pack(side="left", padx=(10, 0))
                rendered_conflict_rows += 1

        if rendered_conflict_rows == 0 and rendered_section_blocks == 0 and (filtered_conflicts or filtered_locale_msbts):
            # Never leave the results area blank - show a resilient fallback.
            logger.warn("Conflicts", "No conflict rows rendered; displaying fallback list")
            fallback_frame = ctk.CTkFrame(self.conflict_list, fg_color=theme.BG_CARD_INNER, corner_radius=8)
            fallback_frame.pack(fill="x", pady=(12, 4))
            ctk.CTkLabel(
                fallback_frame,
                text="Conflicts detected but detailed cards failed to render.",
                font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS, weight="bold"),
                text_color=theme.WARNING,
                anchor="w",
            ).pack(fill="x", padx=12, pady=(10, 6))
            for conflict in filtered_conflicts[:20]:
                ctk.CTkLabel(
                    fallback_frame,
                    text=f"  - {self._conflict_display_line(conflict)}",
                    font=ctk.CTkFont(size=theme.FONT_BODY),
                    text_color=theme.TEXT_DETAIL,
                    anchor="w",
                ).pack(fill="x", padx=12, pady=1)
            ctk.CTkFrame(fallback_frame, height=8, fg_color="transparent").pack()

        self.conflict_list.update_idletasks()
        self._prune_empty_conflict_blocks()
        self._debug_layout_snapshot("render-complete")
        logger.debug(
            "Conflicts",
            f"Render complete: sections={rendered_section_blocks}, rows={rendered_conflict_rows}, "
            f"widgets={len(self.conflict_list.winfo_children())}",
        )
        self._reset_conflict_canvas_view()
        self._stabilize_conflict_viewport()
        self.after(theme.DELAY_LEADING_GAP, self._compact_leading_conflict_gap)
        self.after(theme.DELAY_SEARCH_DEBOUNCE, self._compact_leading_conflict_gap)
        self.after(theme.DELAY_RESULTS_CHECK, self._ensure_results_not_blank)
        self._arm_top_anchor_guard("render")
        self.after(theme.DELAY_SCROLL_SPEED_PATCH, self._patch_all_scroll_speeds)

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

        fallback_frame = ctk.CTkFrame(self.conflict_list, fg_color=theme.BG_CARD_INNER, corner_radius=8)
        fallback_frame.pack(fill="x", pady=(10, 4))
        ctk.CTkLabel(
            fallback_frame,
            text="Conflicts detected (fallback view)",
            font=ctk.CTkFont(size=theme.FONT_CARD_HEADING, weight="bold"),
            text_color=theme.WARNING,
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 6))

        for conflict in self._conflicts[:60]:
            ctk.CTkLabel(
                fallback_frame,
                text=f"  - {self._conflict_display_line(conflict)}",
                font=ctk.CTkFont(size=theme.FONT_BODY),
                text_color=theme.TEXT_DETAIL,
                anchor="w",
            ).pack(fill="x", padx=12, pady=1)

        if self._locale_msbts:
            ctk.CTkLabel(
                fallback_frame,
                text=f"  - {len(self._locale_msbts)} locale-specific MSBT file(s) detected",
                font=ctk.CTkFont(size=theme.FONT_BODY),
                text_color=theme.TEXT_DETAIL,
                anchor="w",
            ).pack(fill="x", padx=12, pady=(4, 1))

        ctk.CTkFrame(fallback_frame, height=8, fg_color="transparent").pack()
        self._reset_conflict_canvas_view()
        self._stabilize_conflict_viewport()
        self._arm_top_anchor_guard("minimal-render")
        self.after(theme.DELAY_LEADING_GAP, self._compact_leading_conflict_gap)

    def _reset_conflict_canvas_view(self):
        """Normalize list canvas view after prompt/results mode changes."""
        try:
            self.conflict_list.update_idletasks()
            canvas = getattr(self.conflict_list, "_parent_canvas", None)
            if canvas is not None:
                # Force canonical canvas origin to prevent top-gap drift
                # when yview=0.0 but the frame is visually offset.
                canvas_w = max(1, int(canvas.winfo_width()))
                try:
                    window_id = getattr(self.conflict_list, "_create_window_id", None)
                    if window_id is not None:
                        canvas.coords(window_id, 0, 0)
                        canvas.itemconfigure(window_id, width=canvas_w)
                except Exception:
                    pass
                try:
                    bbox = canvas.bbox("all")
                    if bbox and len(bbox) == 4:
                        x0, y0, x1, y1 = [float(v) for v in bbox]
                        x1 = max(float(canvas_w), x1)
                        y1 = max(1.0, y1)
                        canvas.configure(scrollregion=(x0, y0, x1, y1))
                    else:
                        canvas.configure(scrollregion=(0, 0, canvas_w, 1))
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
                    if self._widget_has_meaningful_text(w):
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

    def _debug_layout_snapshot(self, label: str, limit: int = 8):
        """Emit compact geometry diagnostics for top-level conflict list children."""
        try:
            if not getattr(logger, "enabled", False):
                return
            self.conflict_list.update_idletasks()
            children = [w for w in self.conflict_list.winfo_children() if bool(w.winfo_exists())]
            details = []
            for idx, widget in enumerate(children[:limit]):
                try:
                    y = int(widget.winfo_y())
                except Exception:
                    y = -1
                try:
                    h = int(widget.winfo_height())
                except Exception:
                    h = -1
                try:
                    kids = len(widget.winfo_children())
                except Exception:
                    kids = -1
                try:
                    meaningful = 1 if self._widget_has_meaningful_text(widget) else 0
                except Exception:
                    meaningful = 0
                details.append(
                    f"{idx}:{widget.__class__.__name__} y={y} h={h} kids={kids} txt={meaningful}"
                )
            logger.debug(
                "Conflicts",
                f"Layout snapshot {label}: count={len(children)} :: " + " | ".join(details),
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
                    aid = self.after(theme.DELAY_ANIMATION_TICK, lambda: _tick(remaining - 1))
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
                    f"Merged {self._conflict_display_path(conflict)}\n"
                    f"Output: {path}")
                self._render()
            else:
                messagebox.showwarning("Warning",
                    "XMSBT auto-merge output is disabled.\n"
                    "Use locale-MSBT fixes or manual mod edits.")
        except Exception as e:
            logger.error("Conflicts", f"Merge failed: {e}")
            messagebox.showerror("Error", f"Merge failed: {e}")

    def _keep_conflict(self, conflict, mod_name):
        try:
            settings = self.app.config_manager.settings
            resolver = self.app.conflict_resolver
            create_backup = settings.backup_before_merge
            out = resolver.apply_resolution(conflict, ResolutionStrategy.MANUAL, winner_mod=mod_name,
                                            create_backup=create_backup)
            if out:
                conflict.resolved = True
                logger.info("Conflicts", f"Kept {mod_name} for {conflict.relative_path}")
                self._render()
            else:
                messagebox.showwarning(
                    "Unavailable",
                    "Manual keep output is disabled because _MergedResources generation is disabled."
                )
        except Exception as e:
            logger.error("Conflicts", f"Resolution failed: {e}")
            messagebox.showerror("Error", f"Resolution failed: {e}")

    def _ignore_conflict(self, conflict):
        conflict.resolution = ResolutionStrategy.IGNORE
        conflict.resolved = True
        logger.info("Conflicts", f"Ignored: {conflict.relative_path}")
        self._render()

    def _auto_resolve_all(self):
        # Backwards-compat: keep old method name routed to unified fixer.
        self._fix_text_conflicts()

    def _fix_text_conflicts(self):
        try:
            if self._scanning:
                return
            if not self._scanned:
                should_scan = messagebox.askyesno(
                    "Scan Required",
                    "No conflict scan results are loaded yet.\n\nRun a scan now?",
                )
                if should_scan:
                    self._scan()
                return

            settings = self.app.config_manager.settings
            resolver = self.app.conflict_resolver
            unresolved = [c for c in self._conflicts if c.is_mergeable and not c.resolved]
            locale_targets = list(self._locale_msbts or [])

            if not unresolved and not locale_targets:
                messagebox.showinfo(
                    "No Fixes Needed",
                    "No unresolved text conflicts or locale-specific MSBT files were found.",
                )
                return

            summary_bits = []
            if unresolved:
                summary_bits.append(f"{len(unresolved)} unresolved XMSBT conflict(s)")
            if locale_targets:
                summary_bits.append(f"{len(locale_targets)} locale-specific MSBT file(s)")
            confirm = messagebox.askyesno(
                "Fix Text Conflicts",
                "This will fix locale-specific MSBT filenames.\n\n"
                "Note: XMSBT auto-merge output is disabled.\n\n"
                f"Targets: {', '.join(summary_bits)}.\n\nContinue?",
            )
            if not confirm:
                return

            self._scanning = True
            self.summary_label.configure(text="Fixing text conflicts...", text_color=theme.TEXT_MUTED)
            self._set_auto_actions_visible(False)
            self._set_rescan_visible(True)
            self.scan_btn.configure(state="disabled")
            self.fix_text_btn_header.configure(state="disabled")
            self.restore_btn_header.configure(state="disabled")

            create_backup = settings.backup_before_merge

            def _run_fix():
                try:
                    actually_resolved = 0
                    failed = len(unresolved)
                    locale_renamed = 0

                    if locale_targets:
                        locale_renamed = resolver.rename_locale_msbt_files()
                    self.after(
                        0,
                        lambda: self._on_fix_text_done(
                            actually_resolved, failed, locale_renamed
                        ),
                    )
                except Exception as e:
                    self.after(0, lambda err=str(e): self._on_fix_text_error(err))

            threading.Thread(target=_run_fix, daemon=True).start()
        except Exception as e:
            logger.error("Conflicts", f"Fix text conflicts failed: {e}")
            messagebox.showerror("Error", f"Fix text conflicts failed: {e}")

    def _on_fix_text_done(self, merged_count: int, failed_count: int, locale_renamed: int):
        self._scanning = False
        try:
            self.scan_btn.configure(state="normal")
            self.fix_text_btn_header.configure(state="normal")
            self.restore_btn_header.configure(state="normal")
        except Exception:
            pass

        parts = []
        if locale_renamed > 0:
            parts.append(f"Renamed {locale_renamed} locale-specific MSBT file(s).")
        if failed_count > 0:
            parts.append(
                f"{failed_count} conflict(s) were not auto-merged "
                "(XMSBT auto-merge output is disabled)."
            )
        if not parts:
            parts.append("No changes were necessary.")

        logger.info(
            "Conflicts",
            f"Fix Text Conflicts finished: merged={merged_count}, "
            f"failed={failed_count}, locale={locale_renamed}",
        )
        messagebox.showinfo("Fix Text Conflicts", "\n".join(parts))
        self._scanned = False
        self._scan()

    def _on_fix_text_error(self, error_msg: str):
        self._scanning = False
        try:
            self.scan_btn.configure(state="normal")
            self.fix_text_btn_header.configure(state="normal")
            self.restore_btn_header.configure(state="normal")
        except Exception:
            pass
        logger.error("Conflicts", f"Fix Text Conflicts failed: {error_msg}")
        messagebox.showerror("Error", f"Failed to fix text conflicts: {error_msg}")

    def _restore_originals(self):
        """Restore legacy merge artifacts and remove old generated output."""
        confirm = messagebox.askyesno(
            "Restore Originals",
            "This will:\n"
            "  - Move original XMSBT files back to their mod folders (if present)\n"
            "  - Remove legacy generated _MergedResources content\n\n"
            "This only applies to data created by older versions.\n\nContinue?"
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
            self._scanned = False
            self._scan()
        except Exception as e:
            logger.error("Conflicts", f"Fix locale MSBTs failed: {e}")
            messagebox.showerror("Error", f"Failed to fix locale MSBT files: {e}")
