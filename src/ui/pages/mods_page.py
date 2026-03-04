"""Mods management page with category grouping, virtual scrolling, and undo/redo."""
import customtkinter as ctk
import tkinter as tk
import threading
from tkinter import filedialog, messagebox
from collections import defaultdict
from pathlib import Path
from src.ui.base_page import BasePage
from src.ui import theme
from src.models.mod import Mod, ModStatus
from src.core.content_importer import (
    MultiSlotPackSelectionInfo,
    apply_mod_camera_pack_scope,
    apply_mod_effect_pack_scope,
    apply_mod_voice_pack_scope,
    import_mod_package,
    inspect_mod_camera_pack,
    inspect_mod_effect_pack,
    inspect_mod_voice_pack,
    resolve_mod_slot_labels,
)
from src.core.skin_slot_utils import analyze_mod_directory
from src.core.runtime_guard import ContentOperationBlockedError
from src.utils.logger import logger
from src.utils.action_history import action_history, Action


# Category colors for the left accent bar
CATEGORY_COLORS = {
    "Character": theme.ACCENT,
    "Audio": theme.SUCCESS,
    "Stage": theme.PRIMARY,
    "UI": theme.WARNING_ALT,
    "Effect": theme.PURPLE_CATEGORY,
    "Camera": theme.BLUE_CATEGORY,
    "Assist Trophy": theme.ORANGE_CATEGORY,
    "Item": theme.TEAL_CATEGORY,
    "Params": theme.GRAY_CATEGORY,
    "Music": theme.SUCCESS,
    "Other": theme.BTN_NEUTRAL,
}

_HEADER_HEIGHT = 40
_MOD_ROW_HEIGHT = 44
_ROW_PAD = 2

MOD_RISK_BADGES = {
    "desync_vulnerable": ("DESYNC", theme.ACCENT),
    "conditionally_shared": ("CONDITIONAL", theme.WARNING),
    "unknown_needs_review": ("REVIEW", theme.WARNING_ALT),
    "safe_client_only": ("SAFE", theme.SUCCESS),
}

SUPPORT_PACK_LABELS = {
    "voice": "Voice Pack",
    "effect": "Effect Pack",
    "camera": "Camera Pack",
}


class ModsPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._all_mods = []
        self._loaded = False
        self._group_by_category = True
        self._collapsed = set()
        self._visible_items = []  # list of (type, data, y_pos, height)
        self._rendered_widgets = {}  # index -> widget
        self._last_scroll_region = (0, 0)
        self._scroll_after_id = None
        self._context_menu = None
        self.app.bind("<Button-1>", self._close_context_menu_on_global_click, add="+")
        self._build_ui()

    def _patch_all_scroll_speeds(self):
        """Rely on app-global wheel handling for consistent scroll behavior."""
        return

    def _build_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(20, 8))

        title = ctk.CTkLabel(header_frame, text="Mods",
                             font=ctk.CTkFont(size=theme.FONT_PAGE_TITLE, weight="bold"), anchor="w")
        title.pack(side="left")

        refresh_btn = ctk.CTkButton(header_frame, text="Refresh", width=100,
                                    command=self._force_refresh,
                                    corner_radius=8, height=34)
        refresh_btn.pack(side="right", padx=(5, 0))

        open_btn = ctk.CTkButton(header_frame, text="Open Folder", width=110,
                                 command=self._open_folder,
                                 fg_color=theme.BTN_NEUTRAL, hover_color=theme.HOVER_NEUTRAL,
                                 corner_radius=8, height=34)
        open_btn.pack(side="right", padx=(5, 0))

        import_btn = ctk.CTkButton(
            header_frame, text="Import", width=100,
            command=self._import_mod_folder,
            fg_color=theme.PURPLE, hover_color=theme.HOVER_PURPLE,
            corner_radius=8, height=34,
        )
        import_btn.pack(side="right", padx=(5, 0))

        disable_all_btn = ctk.CTkButton(header_frame, text="Disable All", width=100,
                                        command=self._disable_all,
                                        fg_color=theme.DANGER_BUTTON, hover_color=theme.HOVER_DANGER_ALL,
                                        corner_radius=8, height=34)
        disable_all_btn.pack(side="right", padx=(5, 0))

        enable_all_btn = ctk.CTkButton(header_frame, text="Enable All", width=100,
                                       command=self._enable_all,
                                       fg_color=theme.SUCCESS_BUTTON, hover_color=theme.HOVER_SUCCESS_ALL,
                                       corner_radius=8, height=34)
        enable_all_btn.pack(side="right", padx=(5, 0))

        wifi_safe_btn = ctk.CTkButton(header_frame, text="Wi-Fi Safe", width=110,
                                      command=self._enable_wifi_safe_only,
                                      fg_color=theme.PRIMARY, hover_color=theme.HOVER_PRIMARY,
                                      corner_radius=8, height=34)
        wifi_safe_btn.pack(side="right", padx=(5, 0))

        repair_btn = ctk.CTkButton(header_frame, text="Repair Installed", width=130,
                                   command=self._repair_installed_mods,
                                   fg_color=theme.BTN_SECONDARY, hover_color=theme.HOVER_SECONDARY,
                                   corner_radius=8, height=34)
        repair_btn.pack(side="right", padx=(5, 0))

        runtime_btn = ctk.CTkButton(header_frame, text="Repair Runtime", width=126,
                                    command=self._repair_runtime_environment,
                                    fg_color=theme.BTN_STAGE, hover_color=theme.HOVER_STAGE,
                                    corner_radius=8, height=34)
        runtime_btn.pack(side="right", padx=(5, 0))

        # Search, filter, and group toggle
        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.pack(fill="x", padx=30, pady=(0, 6))

        self.search_var = tk.StringVar()
        self._search_after_id = None
        def _debounced_search(*_a):
            if self._search_after_id:
                self.after_cancel(self._search_after_id)
            self._search_after_id = self.after(theme.DELAY_SEARCH_DEBOUNCE, self._render_mods)
        self.search_var.trace("w", _debounced_search)
        search_entry = ctk.CTkEntry(filter_frame, placeholder_text="Search mods...",
                                    textvariable=self.search_var, height=34,
                                    corner_radius=8)
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        right_filters = ctk.CTkFrame(filter_frame, fg_color="transparent")
        right_filters.pack(side="right")

        self.group_var = ctk.BooleanVar(value=True)
        group_cb = ctk.CTkCheckBox(right_filters, text="Group by type",
                                   variable=self.group_var,
                                   command=self._render_mods,
                                   font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), width=130)
        group_cb.pack(side="right", padx=(14, 0))

        self.filter_var = ctk.StringVar(value="All")
        filter_menu = ctk.CTkOptionMenu(
            right_filters, values=["All", "Enabled", "Disabled"],
            variable=self.filter_var, command=lambda v: self._render_mods(), width=125,
            corner_radius=8, height=34,
        )
        filter_menu.pack(side="right")

        # Mod count summary
        self.count_label = ctk.CTkLabel(self, text="",
                                        font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
                                        text_color=theme.TEXT_DIM, anchor="w")
        self.count_label.pack(fill="x", padx=32, pady=(0, 4))

        # Virtual scrolling canvas
        self._canvas_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._canvas_frame.pack(fill="both", expand=True, padx=25, pady=(0, 10))

        self._canvas = tk.Canvas(
            self._canvas_frame, bg=theme.BG_APP, highlightthickness=0,
            bd=0, relief="flat",
        )
        self._scrollbar = ctk.CTkScrollbar(self._canvas_frame, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        # Inner frame for widgets
        self._inner_frame = tk.Frame(self._canvas, bg=theme.BG_APP)
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._inner_frame, anchor="nw"
        )

        # Bind events
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._inner_frame.bind("<Configure>", self._on_frame_configure)

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_frame_configure(self, event):
        # Debounce to prevent scroll jumps when scrollbar is being dragged
        new_region = (event.width, event.height)
        if new_region != self._last_scroll_region:
            self._last_scroll_region = new_region
            if self._scroll_after_id:
                try:
                    self.after_cancel(self._scroll_after_id)
                except Exception:
                    pass
            try:
                self._scroll_after_id = self.after(theme.DELAY_SCROLL_UPDATE, self._update_scroll_region)
            except Exception:
                pass

    def _update_scroll_region(self):
        self._scroll_after_id = None
        try:
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        except tk.TclError:
            pass

    def on_show(self):
        if not self._loaded:
            self._refresh()

    def on_hide(self):
        self._close_context_menu()

    def _force_refresh(self):
        self.app.mod_manager.invalidate_cache()
        self._loaded = False
        self._refresh()

    def _refresh(self):
        settings = self.app.config_manager.settings
        if not settings.mods_path or not settings.mods_path.exists():
            self.count_label.configure(text="No mods path configured. Go to Settings first.")
            return

        logger.info("Mods", "Loading mod list...")
        self.count_label.configure(text="Loading mods...")

        def _load():
            mods = self.app.mod_manager.list_mods()
            try:
                self.after(0, lambda: self._on_mods_loaded(mods))
            except Exception:
                pass

        threading.Thread(target=_load, daemon=True).start()

    def _on_mods_loaded(self, mods):
        self._all_mods = mods
        self._loaded = True
        logger.info("Mods", f"Found {len(self._all_mods)} mods")
        self._render_mods()

    def _get_filtered_mods(self):
        search = self.search_var.get().lower()
        filter_val = self.filter_var.get()

        filtered = []
        for mod in self._all_mods:
            if search:
                display_name = self._mod_display_name(mod)
                name_match = (
                    search in mod.original_name.lower()
                    or search in display_name.lower()
                )
                cat_match = any(search in c.lower() for c in mod.metadata.categories)
                if not name_match and not cat_match:
                    continue
            if filter_val == "Enabled" and mod.status != ModStatus.ENABLED:
                continue
            if filter_val == "Disabled" and mod.status != ModStatus.DISABLED:
                continue
            filtered.append(mod)
        return filtered

    # Number of mod rows to render per event-loop tick during batched rendering.
    _RENDER_BATCH_SIZE = 25

    def _render_mods(self, *_args):
        # Cancel any in-flight batched render
        if getattr(self, "_render_batch_id", None) is not None:
            try:
                self.after_cancel(self._render_batch_id)
            except Exception:
                pass
            self._render_batch_id = None

        # Clear all existing widgets
        for w in self._inner_frame.winfo_children():
            w.destroy()
        self._rendered_widgets.clear()

        filtered = self._get_filtered_mods()
        enabled_count = sum(1 for m in filtered if m.status == ModStatus.ENABLED)
        disabled_count = len(filtered) - enabled_count
        desync_count = sum(
            1 for m in filtered
            if (m.metadata.online_risk or "") == "desync_vulnerable"
        )

        # Build count text with category breakdown
        cat_counts = defaultdict(int)
        for m in filtered:
            for c in m.metadata.categories:
                cat_counts[c] += 1

        parts = [f"{len(filtered)} mods"]
        if enabled_count:
            parts.append(f"{enabled_count} enabled")
        if disabled_count:
            parts.append(f"{disabled_count} disabled")
        if desync_count:
            parts.append(f"{desync_count} desync-vulnerable")
        count_text = " \u00b7 ".join(parts)

        if cat_counts:
            cat_strs = [f"{c} ({n})" for c, n in sorted(cat_counts.items(), key=lambda x: -x[1])]
            count_text += "  \u2014  " + ", ".join(cat_strs[:6])
        self.count_label.configure(text=count_text)

        # Build the flat list of render jobs [(type, args), ...]
        jobs = self._build_render_jobs(filtered)
        if not jobs:
            self.after(10, self._update_scroll_region)
            return

        # Render first batch immediately so the page isn't blank, then schedule
        # the rest in ticks to keep the UI responsive.
        self._render_batch_queue = jobs
        self._render_batch_gen = getattr(self, '_render_batch_token', 0) + 1
        self._render_batch_token = self._render_batch_gen
        self._process_render_batch()

    def _build_render_jobs(self, filtered):
        """Build a flat list of (type, args) render jobs for batched dispatch."""
        jobs = []
        if self.group_var.get():
            groups = defaultdict(list)
            for mod in filtered:
                primary = mod.metadata.categories[0] if mod.metadata.categories else "Other"
                groups[primary].append(mod)

            order = ["Character", "Stage", "Music", "Audio", "UI", "Effect",
                     "Camera", "Assist Trophy", "Item", "Params", "Other"]
            sorted_groups = []
            for key in order:
                if key in groups:
                    sorted_groups.append((key, groups.pop(key)))
            for key in sorted(groups.keys()):
                sorted_groups.append((key, groups[key]))

            for category, category_mods in sorted_groups:
                color = CATEGORY_COLORS.get(category, theme.BTN_NEUTRAL)
                is_collapsed = category in self._collapsed
                enabled = sum(1 for m in category_mods if m.status == ModStatus.ENABLED)
                jobs.append(("header", (category, color, is_collapsed, enabled, len(category_mods))))
                if not is_collapsed:
                    for mod in category_mods:
                        jobs.append(("row", (mod, color)))
        else:
            for mod in filtered:
                color = CATEGORY_COLORS.get(
                    mod.metadata.categories[0] if mod.metadata.categories else "Other",
                    theme.BTN_NEUTRAL,
                )
                jobs.append(("row", (mod, color)))
        return jobs

    def _process_render_batch(self):
        """Render the next batch of rows, then yield to the event loop."""
        self._render_batch_id = None
        token = self._render_batch_token
        if token != self._render_batch_gen:
            return  # superseded by a newer render call
        queue = self._render_batch_queue
        batch_size = self._RENDER_BATCH_SIZE
        count = 0
        while queue and count < batch_size:
            kind, args = queue.pop(0)
            if kind == "header":
                self._render_category_header(*args)
            else:
                self._render_mod_row(*args)
            count += 1

        if queue:
            self._render_batch_id = self.after(1, self._process_render_batch)
        else:
            self.after(10, self._update_scroll_region)
            logger.debug("Mods", "Batched render complete")

    def _render_category_header(self, category, color, is_collapsed, enabled, total):
        header = tk.Frame(self._inner_frame, bg=theme.BG_ROW_HEADER, cursor="hand2",
                          height=_HEADER_HEIGHT)
        header.pack(fill="x", pady=(6, 1), padx=2)
        header.pack_propagate(False)

        arrow = "\u25b8" if is_collapsed else "\u25be"
        count_text = f"{total} mod{'s' if total != 1 else ''}"
        if enabled < total:
            count_text += f" \u00b7 {enabled} enabled"

        arrow_label = tk.Label(header, text=arrow, font=("Segoe UI", theme.FONT_BODY),
                               fg=theme.TEXT_FAINT, bg=theme.BG_ROW_HEADER, width=2)
        arrow_label.pack(side="left", padx=(10, 0))

        dot = tk.Frame(header, width=10, height=10, bg=color)
        dot.pack(side="left", padx=(4, 8), pady=15)

        name_l = tk.Label(header, text=f"{category}",
                          font=("Segoe UI", theme.FONT_BODY_MEDIUM, "bold"),
                          fg=theme.TEXT_LOG, bg=theme.BG_ROW_HEADER)
        name_l.pack(side="left", padx=(0, 8))

        count_l = tk.Label(header, text=count_text,
                           font=("Segoe UI", theme.FONT_CAPTION),
                           fg=theme.TEXT_DISABLED_CATEGORY, bg=theme.BG_ROW_HEADER)
        count_l.pack(side="left")

        def on_click(e, cat=category):
            if cat in self._collapsed:
                self._collapsed.discard(cat)
            else:
                self._collapsed.add(cat)
            self._render_mods()

        for w in [header, arrow_label, name_l, count_l, dot]:
            w.bind("<Button-1>", on_click)

    def _render_mod_row(self, mod, accent_color):
        is_enabled = mod.status == ModStatus.ENABLED

        row = tk.Frame(self._inner_frame, bg=theme.BG_ROW, height=_MOD_ROW_HEIGHT)
        row.pack(fill="x", pady=1, padx=2)
        row.pack_propagate(False)

        accent = tk.Frame(row, width=4,
                          bg=accent_color if is_enabled else theme.ACCENT_STRIPE_DISABLED)
        accent.pack(side="left", fill="y", padx=(3, 0), pady=4)

        switch = ctk.CTkSwitch(
            row, text="", width=42, height=20,
            command=lambda m=mod: self._on_toggle(m),
            onvalue=True, offvalue=False,
            bg_color=theme.BG_ROW,
        )
        switch.pack(side="left", padx=(8, 6))
        if is_enabled:
            switch.select()
        else:
            switch.deselect()

        # Name + categories label
        name = self._mod_display_name(mod)
        cats = mod.metadata.categories[:3]
        risk_key = mod.metadata.online_risk or "unknown_needs_review"
        badge_text, badge_color = MOD_RISK_BADGES.get(
            risk_key,
            ("REVIEW", theme.WARNING_ALT),
        )

        name_color = theme.TEXT_BODY if is_enabled else theme.TEXT_VERY_DIM
        cat_color = theme.TEXT_CATEGORY if is_enabled else theme.TEXT_DISABLED_CATEGORY

        text_frame = tk.Frame(row, bg=theme.BG_ROW)
        text_frame.pack(side="left", fill="x", expand=True)

        name_label = tk.Label(
            text_frame, text=name, font=("Segoe UI", theme.FONT_BODY_MEDIUM),
            fg=name_color, bg=theme.BG_ROW, anchor="w",
        )
        name_label.pack(side="left", padx=(2, 0))

        if cats:
            cat_label = tk.Label(
                text_frame, text=" \u00b7 ".join(cats),
                font=("Segoe UI", theme.FONT_CAPTION), fg=cat_color, bg=theme.BG_ROW, anchor="w",
            )
            cat_label.pack(side="left", padx=(8, 0))

        tk.Label(
            row,
            text=badge_text,
            font=("Segoe UI", theme.FONT_TINY, "bold"),
            fg=badge_color if is_enabled else theme.TEXT_DISABLED_RISK,
            bg=theme.BG_ROW,
            anchor="e",
        ).pack(side="right", padx=(0, 10))

        self._bind_context_menu_recursive(row, mod)

    def _mod_display_name(self, mod) -> str:
        settings = self.app.config_manager.settings
        overrides = dict(getattr(settings, "mod_name_overrides", {}) or {})
        custom = overrides.get(mod.original_name, "").strip()
        if custom:
            return custom
        return mod.original_name

    def _has_custom_mod_name(self, mod) -> bool:
        settings = self.app.config_manager.settings
        overrides = dict(getattr(settings, "mod_name_overrides", {}) or {})
        return bool(overrides.get(mod.original_name, "").strip())

    def _bind_context_menu_recursive(self, widget, mod):
        for seq in ("<ButtonRelease-3>", "<Button-2>", "<Control-Button-1>"):
            try:
                widget.bind(seq,
                            lambda e, m=mod: self._show_mod_context_menu(e, m), add="+")
            except Exception:
                pass
        try:
            for child in widget.winfo_children():
                self._bind_context_menu_recursive(child, mod)
        except Exception:
            pass

    def _show_mod_context_menu(self, event, mod):
        self._close_context_menu()
        menu = ctk.CTkToplevel(self)
        menu.withdraw()
        menu.overrideredirect(True)
        menu.attributes("-topmost", True)
        menu.configure(fg_color=theme.BG_CONTEXT_MENU)

        frame = ctk.CTkFrame(
            menu,
            fg_color=theme.BG_CONTEXT_MENU_INNER,
            border_width=1,
            border_color=theme.BORDER_CONTEXT,
            corner_radius=8,
        )
        frame.pack(fill="both", expand=True)

        self._add_context_item(
            frame,
            "Rename Mod...",
            lambda m=mod: self._rename_mod(m),
        )
        self._add_context_item(
            frame,
            "Copy Online Risk Details",
            lambda m=mod: self._copy_mod_risk_details(m),
        )
        voice_info = self._inspect_support_pack_info(mod, "voice")
        if voice_info is not None:
            self._add_context_item(
                frame,
                "Configure Voice Pack...",
                lambda m=mod: self._configure_voice_pack_scope(m),
            )
        effect_info = self._inspect_support_pack_info(mod, "effect")
        if effect_info is not None:
            self._add_context_item(
                frame,
                "Configure Effect Pack...",
                lambda m=mod: self._configure_effect_pack_scope(m),
            )
        camera_info = self._inspect_support_pack_info(mod, "camera")
        if camera_info is not None:
            self._add_context_item(
                frame,
                "Configure Camera Pack...",
                lambda m=mod: self._configure_camera_pack_scope(m),
            )
        if self._has_custom_mod_name(mod):
            self._add_context_item(
                frame,
                "Reset Custom Name",
                lambda m=mod: self._reset_single_custom_mod_name(m),
            )

        menu.update_idletasks()
        menu_w = max(frame.winfo_reqwidth(), 220)
        menu_h = max(frame.winfo_reqheight(), 30)
        x, y = self._clamp_popup_to_screen(event.x_root + 4, event.y_root + 2, menu_w, menu_h)
        menu.geometry(f"{menu_w}x{menu_h}+{x}+{y}")
        menu.deiconify()
        menu.lift()
        menu.bind("<Escape>", lambda _e: self._close_context_menu(), add="+")
        self._context_menu = menu
        return "break"

    def _close_context_menu_on_global_click(self, event):
        menu = self._context_menu
        if menu is None:
            return
        try:
            if not menu.winfo_exists():
                self._context_menu = None
                return
        except Exception:
            self._context_menu = None
            return

        w = getattr(event, "widget", None)
        while w is not None:
            if w == menu:
                return
            try:
                w = w.master
            except Exception:
                break
        self._close_context_menu()

    def _add_context_item(self, parent, text: str, callback):
        btn = ctk.CTkButton(
            parent,
            text=text,
            anchor="w",
            width=220,
            height=30,
            corner_radius=0,
            fg_color="transparent",
            hover_color=theme.HOVER_CONTEXT,
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
            command=lambda cb=callback: self._invoke_context_action(cb),
        )
        btn.pack(fill="x")

    def _invoke_context_action(self, callback):
        self._close_context_menu()
        try:
            # Give context-menu teardown one frame so rename dialogs
            # never show partially during focus handoff on Windows.
            self.update_idletasks()
            self.after(theme.DELAY_CONTEXT_TEARDOWN, callback)
        except Exception:
            callback()

    def _close_context_menu(self):
        menu = self._context_menu
        self._context_menu = None
        if menu is None:
            return
        try:
            menu.destroy()
        except Exception:
            pass

    def _rename_mod(self, mod):
        current_name = mod.original_name
        default_display = self._mod_display_name(mod)
        result = self._show_rename_mod_dialog(default_display)
        if result is None:
            return
        new_name, rename_folder = result
        cleaned = new_name.strip()
        if not cleaned:
            messagebox.showerror("Invalid Name", "Mod name cannot be empty.")
            return
        if any(ch in cleaned for ch in ('\\', '/', ':', '*', '?', '"', '<', '>', '|')):
            messagebox.showerror(
                "Invalid Name",
                "Mod name contains characters that are not valid for a folder name.",
            )
            return
        if cleaned in (".", ".."):
            messagebox.showerror("Invalid Name", "Choose a different mod name.")
            return

        settings = self.app.config_manager.settings
        overrides = dict(getattr(settings, "mod_name_overrides", {}) or {})

        if rename_folder:
            target = mod.path.parent / cleaned
            if target.exists() and target != mod.path:
                messagebox.showerror(
                    "Rename Failed",
                    f"A folder named '{cleaned}' already exists.",
                )
                return
            try:
                if target != mod.path:
                    mod.path.rename(target)
                overrides.pop(current_name, None)
                settings.mod_name_overrides = overrides
                self.app.config_manager.save(settings)
                self.app.mod_manager.invalidate_cache()
                self._loaded = False
                self._refresh()
                logger.info("Mods", f"Renamed folder: {current_name} -> {cleaned}")
            except Exception as e:
                logger.error("Mods", f"Rename folder failed: {e}")
                messagebox.showerror("Error", f"Failed to rename mod folder: {e}")
            return

        if cleaned == current_name:
            overrides.pop(current_name, None)
        else:
            overrides[current_name] = cleaned

        settings.mod_name_overrides = overrides
        self.app.config_manager.save(settings)
        self._loaded = False
        self._refresh()

    def _show_rename_mod_dialog(self, initial_value: str):
        result = {"value": None, "rename_folder": False}
        dialog = ctk.CTkToplevel(self)
        dialog.withdraw()
        dialog.title("Rename Mod")
        dialog.resizable(False, False)
        dialog.configure(fg_color=theme.BG_DIALOG)

        shell = ctk.CTkFrame(dialog, fg_color=theme.BG_DIALOG_SHELL, corner_radius=10,
                             border_width=1, border_color=theme.BORDER_DIALOG)
        shell.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            shell, text="Rename Mod", anchor="w",
            font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"),
        ).pack(fill="x", padx=14, pady=(12, 6))

        ctk.CTkLabel(
            shell,
            text="Set a new mod name.\n"
                 "Unchecked: rename in this app only.\n"
                 "Checked: also rename the actual mod folder.",
            anchor="w", justify="left",
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM), text_color=theme.TEXT_SOFT,
        ).pack(fill="x", padx=14)

        entry = ctk.CTkEntry(shell, height=32)
        entry.pack(fill="x", padx=14, pady=(12, 8))
        entry.insert(0, initial_value or "")
        entry.select_range(0, "end")

        rename_folder_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            shell,
            text="Rename actual mod folder too",
            variable=rename_folder_var,
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
        ).pack(anchor="w", padx=14, pady=(0, 12))

        btn_row = ctk.CTkFrame(shell, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 12))

        def close_with(value=None):
            result["value"] = value
            result["rename_folder"] = bool(rename_folder_var.get())
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()

        ctk.CTkButton(
            btn_row, text="Cancel", width=96, height=30,
            fg_color=theme.BTN_SECONDARY, hover_color=theme.HOVER_SECONDARY,
            command=lambda: close_with(None),
        ).pack(side="right")

        ctk.CTkButton(
            btn_row, text="Save", width=96, height=30,
            fg_color=theme.PRIMARY, hover_color=theme.HOVER_PRIMARY,
            command=lambda: close_with(entry.get()),
        ).pack(side="right", padx=(0, 8))

        dialog.bind("<Escape>", lambda _e: close_with(None))
        dialog.bind("<Return>", lambda _e: close_with(entry.get()))
        self._center_dialog(dialog, width=460, height=270)
        self._present_modal_dialog(dialog, focus_widget=entry, animate_open=False)
        self.wait_window(dialog)
        if result["value"] is None:
            return None
        return result["value"], result["rename_folder"]

    def _reset_single_custom_mod_name(self, mod):
        settings = self.app.config_manager.settings
        overrides = dict(getattr(settings, "mod_name_overrides", {}) or {})
        if mod.original_name in overrides:
            overrides.pop(mod.original_name, None)
            settings.mod_name_overrides = overrides
            self.app.config_manager.save(settings)
            self._loaded = False
            self._refresh()

    def _copy_mod_risk_details(self, mod):
        risk = mod.metadata.online_risk or "unknown_needs_review"
        reasons = list(mod.metadata.online_reasons or [])
        badge_text, _color = MOD_RISK_BADGES.get(risk, ("REVIEW", theme.WARNING_ALT))
        lines = [
            f"Mod: {mod.original_name}",
            f"Online Risk: {risk} ({badge_text})",
        ]
        if reasons:
            lines.append("Reasons:")
            lines.extend(f"- {reason}" for reason in reasons[:12])
        else:
            lines.append("Reasons: none recorded")
        text = "\n".join(lines)
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Copied", "Online risk details copied to clipboard.")
        except Exception:
            messagebox.showerror("Error", "Failed to copy risk details.")

    def _inspect_support_pack_info(self, mod, support_kind: str):
        inspectors = {
            "voice": inspect_mod_voice_pack,
            "effect": inspect_mod_effect_pack,
            "camera": inspect_mod_camera_pack,
        }
        inspector = inspectors.get(str(support_kind).strip().lower())
        if inspector is None:
            return None
        try:
            return inspector(mod.path)
        except Exception:
            return None

    def _configure_voice_pack_scope(self, mod):
        self._configure_support_pack_scope(mod, "voice")

    def _configure_effect_pack_scope(self, mod):
        self._configure_support_pack_scope(mod, "effect")

    def _configure_camera_pack_scope(self, mod):
        self._configure_support_pack_scope(mod, "camera")

    def _configure_support_pack_scope(self, mod, support_kind: str):
        normalized_kind = str(support_kind).strip().lower()
        support_label = SUPPORT_PACK_LABELS.get(normalized_kind, "Support Pack")
        settings = self.app.config_manager.settings
        mods_path = settings.mods_path
        if not mods_path:
            messagebox.showerror(support_label, "Mods path is not configured in Settings.")
            return

        info = self._inspect_support_pack_info(mod, normalized_kind)
        if info is None:
            messagebox.showinfo(
                support_label,
                f"This mod does not contain a slot-scoped {normalized_kind} pack.",
            )
            return

        result = self._show_support_pack_scope_dialog(mod, info)
        if result is None:
            return
        slot_labels, occupied_slots = self._build_support_slot_label_map(mod, info)

        appliers = {
            "voice": apply_mod_voice_pack_scope,
            "effect": apply_mod_effect_pack_scope,
            "camera": apply_mod_camera_pack_scope,
        }
        applier = appliers[normalized_kind]
        try:
            summary = applier(
                mod.path,
                mods_path,
                mode=result["mode"],
                source_slot=result["source_slot"],
                target_slot=result.get("target_slot"),
            )
            source_text = self._format_support_slot_choice(
                summary.source_slot,
                slot_labels,
                occupied_slots,
            )
            lines = [
                f"Configured {normalized_kind} pack for {summary.fighter}.",
                f"Source slot: {source_text}.",
            ]
            if len(summary.target_slots) == 8:
                lines.append("Applied to all 8 default slots.")
            else:
                target_text = self._format_support_slot_choice(
                    summary.target_slots[0],
                    slot_labels,
                    occupied_slots,
                )
                lines.append(f"Applied only to {target_text}.")
            lines.append(f"Wrote {summary.files_written} {normalized_kind} file(s).")
            if summary.support_mod_adjustments:
                lines.append(
                    f"Adjusted {summary.support_mod_adjustments} support mod(s) and pruned "
                    f"{summary.support_files_pruned} conflicting support file(s)."
                )
            if summary.warnings:
                lines.append("")
                lines.extend(summary.warnings[:5])
                if len(summary.warnings) > 5:
                    lines.append(f"...and {len(summary.warnings) - 5} more warning(s).")
            messagebox.showinfo(f"{support_label} Updated", "\n".join(lines))
            self._force_refresh()
        except Exception as e:
            logger.error("Mods", f"{normalized_kind} pack configuration failed: {e}")
            messagebox.showerror(f"{support_label} Failed", str(e))

    def _show_support_pack_scope_dialog(self, mod, info):
        support_kind = getattr(info, "support_kind", "voice")
        support_label = SUPPORT_PACK_LABELS.get(support_kind, "Support Pack")
        slot_labels, occupied_slots = self._build_support_slot_label_map(mod, info)
        result = {"value": None}
        dialog = ctk.CTkToplevel(self)
        dialog.withdraw()
        dialog.title(f"Configure {support_label}")
        dialog.resizable(False, False)
        dialog.configure(fg_color=theme.BG_DIALOG)

        shell = ctk.CTkFrame(dialog, fg_color=theme.BG_DIALOG_SHELL, corner_radius=10,
                             border_width=1, border_color=theme.BORDER_DIALOG)
        shell.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            shell, text=f"Configure {support_label}", anchor="w",
            font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"),
        ).pack(fill="x", padx=14, pady=(12, 6))

        current_visual = self._format_support_slot_list(
            info.visual_slots,
            slot_labels,
            occupied_slots,
        ) or "none"
        current_support = self._format_support_slot_list(
            info.source_slots,
            slot_labels,
            occupied_slots,
        )
        ctk.CTkLabel(
            shell,
            text=(
                f"Mod: {mod.original_name}\n"
                f"Fighter: {info.fighter}\n"
                f"Visual slots in this mod: {current_visual}\n"
                f"{support_label} slots currently present: {current_support}\n"
                "Friendly form names and installed slot occupants are shown when they can be detected."
            ),
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
            text_color=theme.TEXT_SOFT,
        ).pack(fill="x", padx=14)

        form = ctk.CTkFrame(shell, fg_color="transparent")
        form.pack(fill="x", padx=14, pady=(12, 10))

        ctk.CTkLabel(form, text=f"Use {support_label} From", anchor="w").pack(fill="x")
        source_options = {
            self._format_support_slot_choice(slot, slot_labels, occupied_slots): slot
            for slot in info.source_slots
        }
        source_default = next(
            label for label, slot in source_options.items()
            if slot == info.recommended_source_slot
        )
        source_var = tk.StringVar(value=source_default)
        source_menu = ctk.CTkOptionMenu(
            form,
            values=list(source_options.keys()),
            variable=source_var,
            width=150,
            corner_radius=8,
            height=32,
        )
        source_menu.pack(anchor="w", pady=(4, 10))

        ctk.CTkLabel(form, text="Scope", anchor="w").pack(fill="x")
        mode_var = tk.StringVar(value="single_slot")
        scope_row = ctk.CTkFrame(form, fg_color="transparent")
        scope_row.pack(fill="x", pady=(4, 10))

        ctk.CTkRadioButton(
            scope_row,
            text="Single Slot",
            variable=mode_var,
            value="single_slot",
        ).pack(anchor="w")
        ctk.CTkRadioButton(
            scope_row,
            text="Whole Character",
            variable=mode_var,
            value="character_wide",
        ).pack(anchor="w", pady=(4, 0))

        ctk.CTkLabel(form, text="Target Slot", anchor="w").pack(fill="x")
        default_target = info.visual_slots[0] if info.visual_slots else info.recommended_source_slot
        target_options = {
            self._format_support_slot_choice(
                slot,
                slot_labels,
                occupied_slots,
                show_open_default=True,
            ): slot
            for slot in range(8)
        }
        target_default = next(
            label for label, slot in target_options.items()
            if slot == default_target
        )
        target_var = tk.StringVar(value=target_default)
        target_menu = ctk.CTkOptionMenu(
            form,
            values=list(target_options.keys()),
            variable=target_var,
            width=150,
            corner_radius=8,
            height=32,
        )
        target_menu.pack(anchor="w", pady=(4, 10))

        note_label = ctk.CTkLabel(
            form,
            text=(
                f"Single Slot: apply the selected {support_kind} files only to one costume slot.\n"
                f"Whole Character: duplicate the selected {support_kind} files across c00-c07."
            ),
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=theme.FONT_BODY),
            text_color=theme.TEXT_MERGED,
        )
        note_label.pack(fill="x")

        btn_row = ctk.CTkFrame(shell, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(4, 12))

        def close_with(value=None):
            result["value"] = value
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()

        def on_apply():
            mode = mode_var.get()
            payload = {
                "mode": mode,
                "source_slot": int(source_options[source_var.get()]),
            }
            if mode == "single_slot":
                payload["target_slot"] = int(target_options[target_var.get()])
            close_with(payload)

        ctk.CTkButton(
            btn_row, text="Cancel", width=96, height=30,
            fg_color=theme.BTN_SECONDARY, hover_color=theme.HOVER_SECONDARY,
            command=lambda: close_with(None),
        ).pack(side="right")

        ctk.CTkButton(
            btn_row, text="Apply", width=96, height=30,
            fg_color=theme.PRIMARY, hover_color=theme.HOVER_PRIMARY,
            command=on_apply,
        ).pack(side="right", padx=(0, 8))

        dialog.bind("<Escape>", lambda _e: close_with(None))
        dialog.bind("<Return>", lambda _e: on_apply())
        self._center_dialog(dialog, width=500, height=390)
        self._present_modal_dialog(dialog, animate_open=False)
        self.wait_window(dialog)
        return result["value"]

    def _build_support_slot_label_map(self, mod, info):
        fighter = str(getattr(info, "fighter", "") or "").lower()
        current_labels = {
            int(slot): str(label).strip()
            for slot, label in getattr(info, "slot_labels", {}).items()
            if str(label or "").strip()
        }
        installed_labels: dict[int, str] = {}
        mods = self._all_mods if self._loaded else self.app.mod_manager.list_mods()
        for candidate in mods:
            if candidate.status != ModStatus.ENABLED:
                continue
            try:
                analysis = analyze_mod_directory(candidate.path, [candidate.original_name])
            except Exception:
                continue
            candidate_slots = [int(slot) for slot in analysis.visual_fighter_slots.get(fighter, [])]
            if not candidate_slots:
                continue
            candidate_labels = resolve_mod_slot_labels(
                candidate.path,
                {fighter: candidate_slots},
                analysis=analysis,
            )
            for slot in candidate_slots:
                label = candidate_labels.get((fighter, slot))
                if not label and len(candidate_slots) == 1:
                    label = self._mod_display_name(candidate)
                if not label:
                    continue
                existing = installed_labels.get(slot)
                if existing and label != existing:
                    if label not in existing.split(" / "):
                        installed_labels[slot] = f"{existing} / {label}"
                else:
                    installed_labels[slot] = label

        effective_labels: dict[int, str] = {}
        if len(getattr(info, "visual_slots", [])) == 1:
            effective_labels[int(info.visual_slots[0])] = self._mod_display_name(mod)
        if len(getattr(info, "source_slots", [])) == 1:
            effective_labels.setdefault(int(info.source_slots[0]), self._mod_display_name(mod))
        effective_labels.update(installed_labels)
        effective_labels.update(current_labels)
        return effective_labels, set(installed_labels.keys())

    def _format_support_slot_choice(self, slot, slot_labels, occupied_slots, show_open_default=False):
        slot_num = int(slot)
        slot_token = f"c{slot_num:02d}"
        label = str((slot_labels or {}).get(slot_num, "") or "").strip()
        if label:
            return f"{label} ({slot_token})"
        if show_open_default and slot_num not in set(occupied_slots or set()):
            return f"Open default slot ({slot_token})"
        return slot_token

    def _format_support_slot_list(self, slots, slot_labels, occupied_slots):
        return ", ".join(
            self._format_support_slot_choice(slot, slot_labels, occupied_slots)
            for slot in slots
        )

    def _on_toggle(self, mod):
        try:
            was_enabled = mod.status == ModStatus.ENABLED
            mod_name = mod.original_name

            def _set_enabled(target: Mod, enabled: bool) -> None:
                """Toggle a specific rendered mod instance in-place."""
                if enabled:
                    self.app.mod_manager.enable_mod(target)
                else:
                    self.app.mod_manager.disable_mod(target)

            def do_action():
                _set_enabled(mod, not was_enabled)

            def undo_action():
                _set_enabled(mod, was_enabled)

            action = Action(
                description=f"{'Disable' if was_enabled else 'Enable'} {mod_name}",
                do=do_action, undo=undo_action, page="mods",
            )
            action_history.execute(action)

            logger.info("Mods", f"Toggled: {mod_name} -> {'disabled' if was_enabled else 'enabled'}")
            # Re-render cards preserving scroll position.
            # Do NOT re-scan list_mods() - the mod object was updated
            # in-place by enable_mod/disable_mod, so _all_mods already
            # reflects the new state. Re-scanning would reorder the
            # list (disabled mods get appended at the end).
            scroll_pos = self._canvas.yview()[0]
            self._render_mods()
            self.after(theme.DELAY_SCROLL_RESTORE, lambda: self._canvas.yview_moveto(scroll_pos))
        except ContentOperationBlockedError as e:
            logger.warn("Mods", f"Toggle blocked: {e}")
            messagebox.showerror(e.info.title, e.info.message)
            self._loaded = False
            self._refresh()
        except Exception as e:
            logger.error("Mods", f"Toggle failed: {e}")
            messagebox.showerror("Error", f"Failed to toggle mod: {e}")
            self._loaded = False
            self._refresh()

    def _enable_all(self):
        disabled = [m for m in self._all_mods if m.status == ModStatus.DISABLED]
        if not disabled:
            messagebox.showinfo("Info", "All mods are already enabled.")
            return
        confirm = messagebox.askyesno(
            "Enable All Mods",
            f"Enable all {len(disabled)} disabled mod(s)?")
        if not confirm:
            return
        try:
            count = self.app.mod_manager.enable_all()
            logger.info("Mods", f"Enabled {count} mods")
            messagebox.showinfo("Done", f"Enabled {count} mod(s).")
            self._force_refresh()
        except ContentOperationBlockedError as e:
            logger.warn("Mods", f"Enable all blocked: {e}")
            messagebox.showerror(e.info.title, e.info.message)
        except Exception as e:
            logger.error("Mods", f"Enable all failed: {e}")
            messagebox.showerror("Error", f"Failed to enable all mods: {e}")

    def _enable_wifi_safe_only(self):
        safe_disabled = [
            m for m in self._all_mods
            if m.status == ModStatus.DISABLED and (m.metadata.online_risk or "") == "safe_client_only"
        ]
        unsafe_enabled = [
            m for m in self._all_mods
            if m.status == ModStatus.ENABLED and (m.metadata.online_risk or "") != "safe_client_only"
        ]
        if not safe_disabled and not unsafe_enabled:
            messagebox.showinfo("Wi-Fi Safe", "Only Wi-Fi-safe mods are already enabled.")
            return
        confirm = messagebox.askyesno(
            "Enable Only Wi-Fi-Safe Mods",
            f"Enable {len(safe_disabled)} safe mod(s) and disable {len(unsafe_enabled)} non-safe mod(s)?\n\n"
            "This keeps only mods classified as SAFE enabled.",
        )
        if not confirm:
            return
        try:
            enabled_count, disabled_count = self.app.mod_manager.enable_only_safe_mods()
            logger.info(
                "Mods",
                f"Enabled {enabled_count} Wi-Fi-safe mod(s) and disabled {disabled_count} non-safe mod(s)",
            )
            messagebox.showinfo(
                "Wi-Fi Safe Enabled",
                f"Enabled {enabled_count} safe mod(s) and disabled {disabled_count} non-safe mod(s).",
            )
            self._force_refresh()
        except ContentOperationBlockedError as e:
            logger.warn("Mods", f"Wi-Fi-safe toggle blocked: {e}")
            messagebox.showerror(e.info.title, e.info.message)
        except Exception as e:
            logger.error("Mods", f"Wi-Fi-safe toggle failed: {e}")
            messagebox.showerror("Error", f"Failed to enable only Wi-Fi-safe mods: {e}")

    def _disable_all(self):
        enabled = [m for m in self._all_mods if m.status == ModStatus.ENABLED]
        if not enabled:
            messagebox.showinfo("Info", "All mods are already disabled.")
            return
        confirm = messagebox.askyesno(
            "Disable All Mods",
            f"Disable all {len(enabled)} enabled mod(s)?\n\n"
            "This will disable every mod in your mods folder.")
        if not confirm:
            return
        try:
            count = self.app.mod_manager.disable_all()
            logger.info("Mods", f"Disabled {count} mods")
            messagebox.showinfo("Done", f"Disabled {count} mod(s).")
            self._force_refresh()
        except ContentOperationBlockedError as e:
            logger.warn("Mods", f"Disable all blocked: {e}")
            messagebox.showerror(e.info.title, e.info.message)
        except Exception as e:
            logger.error("Mods", f"Disable all failed: {e}")
            messagebox.showerror("Error", f"Failed to disable all mods: {e}")

    def _open_folder(self):
        from src.utils.file_utils import open_folder
        settings = self.app.config_manager.settings
        if settings.mods_path and settings.mods_path.exists():
            open_folder(settings.mods_path)

    def _import_mod_folder(self):
        settings = self.app.config_manager.settings
        mods_path = settings.mods_path
        if not mods_path:
            messagebox.showerror("Import Failed", "Mods path is not configured in Settings.")
            return

        folder = filedialog.askdirectory(title="Select Mod Folder to Import")
        if not folder:
            return

        try:
            summary = import_mod_package(
                Path(folder),
                mods_path,
                slot_conflict_resolver=self._resolve_import_slot_conflict,
                multi_slot_pack_resolver=self._resolve_multi_slot_pack_selection,
            )
            logger.info(
                "Mods",
                f"Imported {summary.items_imported} mod(s), "
                f"{summary.files_copied} file(s), {summary.replaced_paths} replaced path(s)",
            )
            lines = [
                f"Imported {summary.items_imported} mod(s).",
                f"Copied {summary.files_copied} file(s).",
            ]
            if summary.archives_processed:
                lines.append(f"Processed {summary.archives_processed} archive(s).")
            if summary.flattened_mods:
                lines.append(f"Auto-flattened {summary.flattened_mods} nested mod folder(s).")
            if summary.slot_reassignments:
                lines.append(f"Adjusted {summary.slot_reassignments} slot assignment(s).")
            if summary.support_mod_adjustments:
                lines.append(
                    f"Adjusted {summary.support_mod_adjustments} support mod(s) and pruned "
                    f"{summary.support_files_pruned} exact support file(s)."
                )
            if summary.manifest_repairs:
                lines.append(f"Auto-repaired {summary.manifest_repairs} manifest/config issue(s).")
            if summary.ui_portrait_repairs:
                lines.append(f"Filled {summary.ui_portrait_repairs} missing required UI portrait file(s).")
            if summary.identical_files_pruned:
                lines.append(
                    f"Deduped {summary.identical_files_pruned} byte-identical exact overlap file(s)."
                )
            if summary.remaining_exact_overlaps:
                lines.append(
                    f"{summary.remaining_exact_overlaps} exact active overlap(s) still need manual review."
                )
            if summary.replaced_paths:
                lines.append(f"Replaced {summary.replaced_paths} existing mod folder(s).")
            if summary.skipped_items:
                lines.append(f"Skipped {len(summary.skipped_items)} item(s) that could not be placed cleanly.")
            if summary.warnings:
                lines.append("")
                lines.extend(summary.warnings[:5])
                if len(summary.warnings) > 5:
                    lines.append(f"...and {len(summary.warnings) - 5} more warning(s).")
            messagebox.showinfo("Import Complete", "\n".join(lines))
            self._force_refresh()
        except Exception as e:
            logger.error("Mods", f"Import failed: {e}")
            messagebox.showerror("Import Failed", str(e))

    def _repair_installed_mods(self):
        enabled = [m for m in self._all_mods if m.status == ModStatus.ENABLED]
        disabled = [m for m in self._all_mods if m.status == ModStatus.DISABLED]
        confirm = messagebox.askyesno(
            "Repair Installed Mods",
            f"Audit and repair {len(enabled)} enabled mod(s)"
            f"{f' plus {len(disabled)} disabled mod(s)' if disabled else ''}?\n\n"
            "This will auto-fix safe issues like legacy config.txt manifests, missing effect config.json files, "
            "stale config references, nested wrappers, support-file overlaps where a visual mod should win, "
            "and byte-identical exact overlap files. Backups are kept under _import_backups.\n\n"
            "Any remaining differing exact overlaps will be reported for manual review.",
        )
        if not confirm:
            return
        try:
            summary = self.app.mod_manager.repair_installed_mods(include_disabled=True)
            logger.info(
                "Mods",
                f"Repair scanned {summary.mods_scanned} mod(s), changed {summary.mods_changed}, "
                f"resolved {summary.resolved_exact_overlaps} exact overlap(s), "
                f"remaining {summary.remaining_exact_overlaps}",
            )
            lines = [
                f"Scanned {summary.mods_scanned} mod(s).",
            ]
            if summary.mods_changed:
                lines.append(f"Changed {summary.mods_changed} mod(s).")
            if summary.flattened_mods:
                lines.append(f"Flattened {summary.flattened_mods} nested mod folder(s).")
            if summary.configs_normalized:
                lines.append(f"Normalized {summary.configs_normalized} legacy config.txt file(s).")
            if summary.configs_created:
                lines.append(f"Created {summary.configs_created} missing config.json manifest(s).")
            if summary.configs_updated:
                lines.append(f"Updated {summary.configs_updated} existing config manifest(s).")
            if summary.ui_portrait_repairs:
                lines.append(f"Filled {summary.ui_portrait_repairs} missing required UI portrait file(s).")
            if summary.support_mod_adjustments:
                lines.append(
                    f"Adjusted {summary.support_mod_adjustments} support mod(s) and pruned "
                    f"{summary.support_files_pruned} conflicting support file(s)."
                )
            if summary.identical_files_pruned:
                lines.append(
                    f"Deduped {summary.identical_files_pruned} byte-identical exact overlap file(s)."
                )
            if summary.resolved_exact_overlaps:
                lines.append(f"Resolved {summary.resolved_exact_overlaps} exact overlap group(s).")
            if summary.remaining_exact_overlaps:
                lines.append(
                    f"{summary.remaining_exact_overlaps} exact active overlap(s) still need manual review."
                )
            if len(lines) == 1:
                lines.append("No repairable issues were found.")
            if summary.warnings:
                lines.append("")
                lines.extend(summary.warnings[:6])
                if len(summary.warnings) > 6:
                    lines.append(f"...and {len(summary.warnings) - 6} more warning(s).")
            messagebox.showinfo("Repair Complete", "\n".join(lines))
            self._force_refresh()
        except ContentOperationBlockedError as e:
            logger.warn("Mods", f"Repair blocked: {e}")
            messagebox.showerror(e.info.title, e.info.message)
        except Exception as e:
            logger.error("Mods", f"Repair failed: {e}")
            messagebox.showerror("Repair Failed", str(e))

    def _repair_runtime_environment(self):
        confirm = messagebox.askyesno(
            "Repair Yuzu Runtime",
            "Back up and reset Smash's Yuzu runtime state to a stable baseline?\n\n"
            "This will:\n"
            "- replace the Smash-specific Yuzu renderer profile with a stable profile\n"
            "- clear Smash shader and per-game pipeline cache files\n"
            "- clear stale ARCropolis cache/conflict files\n\n"
            "A backup will be kept under the Yuzu data root.",
        )
        if not confirm:
            return
        try:
            summary = self.app.mod_manager.repair_runtime_environment()
            logger.info(
                "Mods",
                f"Repaired {summary.emulator_name} runtime: "
                f"shader={summary.shader_files_cleared}, pipeline={summary.pipeline_files_cleared}, "
                f"arcropolis={summary.arcropolis_cache_files_cleared}",
            )
            lines = [
                f"Repaired {summary.emulator_name} runtime for Smash.",
            ]
            if summary.title_profile_backed_up:
                lines.append("Backed up the previous Smash-specific Yuzu profile.")
            if summary.title_profile_written:
                lines.append("Wrote a stable Smash-specific Yuzu renderer profile.")
            if summary.shader_files_cleared:
                lines.append(f"Cleared {summary.shader_files_cleared} shader cache file(s).")
            if summary.pipeline_files_cleared:
                lines.append(f"Cleared {summary.pipeline_files_cleared} per-game pipeline cache file(s).")
            if summary.arcropolis_cache_files_cleared:
                lines.append(
                    f"Cleared {summary.arcropolis_cache_files_cleared} ARCropolis/plugin cache file(s)."
                )
            if summary.backup_root is not None:
                lines.append(f"Backup: {summary.backup_root}")
            if summary.warnings:
                lines.append("")
                lines.extend(summary.warnings[:5])
                if len(summary.warnings) > 5:
                    lines.append(f"...and {len(summary.warnings) - 5} more warning(s).")
            messagebox.showinfo("Runtime Repair Complete", "\n".join(lines))
        except ContentOperationBlockedError as e:
            logger.warn("Mods", f"Runtime repair blocked: {e}")
            messagebox.showerror(e.info.title, e.info.message)
        except Exception as e:
            logger.error("Mods", f"Runtime repair failed: {e}")
            messagebox.showerror("Runtime Repair Failed", str(e))

    def _resolve_import_slot_conflict(self, conflict):
        slot_text = str(getattr(conflict, "requested_label", "") or f"{conflict.fighter} c{conflict.requested_slot:02d}")
        open_slot_text = ", ".join(
            str(getattr(conflict, "open_slot_descriptions", {}).get(slot, f"Open default slot (c{slot:02d})"))
            for slot in conflict.open_slots[:4]
        )
        if len(conflict.open_slots) > 4:
            open_slot_text += f", and {len(conflict.open_slots) - 4} more"

        if conflict.open_slots and len(conflict.conflicting_mods) == 1:
            existing_mod = conflict.conflicting_mods[0]
            existing_text = str(
                getattr(conflict, "conflicting_mod_descriptions", {}).get(existing_mod, slot_text)
            )
            message = (
                f"'{conflict.mod_name}' wants {slot_text}, but that slot is already used by "
                f"'{existing_mod}' on {existing_text}.\n"
                f"Open default slots: {open_slot_text}.\n\n"
                "Yes: replace the existing skin by disabling the current mod.\n"
                "No: move the existing mod into an open default slot.\n"
                "Cancel: skip importing this skin."
            )
            choice = messagebox.askyesnocancel("Skin Slot Conflict", message)
            if choice is True:
                return "replace"
            if choice is False:
                return "move_existing"
            return "skip"

        if conflict.open_slots:
            lines = [
                f"'{conflict.mod_name}' wants {slot_text}, but that slot is already used by "
                f"{len(conflict.conflicting_mods)} mod(s):",
            ]
            for mod_name in conflict.conflicting_mods[:4]:
                existing_text = str(
                    getattr(conflict, "conflicting_mod_descriptions", {}).get(mod_name, slot_text)
                )
                lines.append(f"- {mod_name}: {existing_text}")
            if len(conflict.conflicting_mods) > 4:
                lines.append(f"- ...and {len(conflict.conflicting_mods) - 4} more")
            lines.extend([
                "",
                f"Open default slots: {open_slot_text}.",
                "",
                "Yes: disable the existing mod(s) and replace that slot.",
                "No/Cancel: skip importing this skin.",
            ])
            message = (
                "\n".join(lines)
            )
            choice = messagebox.askyesnocancel("Skin Slot Conflict", message)
            return "replace" if choice is True else "skip"

        messagebox.showwarning(
            "No Open Skin Slot",
            f"'{conflict.mod_name}' wants {slot_text}, but there are no open default slots left for "
            f"{conflict.fighter}. This skin will be skipped.",
        )
        return "skip"

    def _resolve_multi_slot_pack_selection(self, info: MultiSlotPackSelectionInfo):
        return self._show_multi_slot_pack_dialog(info)

    def _show_multi_slot_pack_dialog(self, info: MultiSlotPackSelectionInfo):
        result = {"value": None}
        dialog = ctk.CTkToplevel(self)
        dialog.withdraw()
        dialog.title("Select Skins to Import")
        dialog.resizable(False, False)
        dialog.configure(fg_color=theme.BG_DIALOG)

        shell = ctk.CTkFrame(
            dialog,
            fg_color=theme.BG_DIALOG_SHELL,
            corner_radius=10,
            border_width=1,
            border_color=theme.BORDER_DIALOG,
        )
        shell.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            shell,
            text="Select Skins to Import",
            anchor="w",
            font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"),
        ).pack(fill="x", padx=14, pady=(12, 6))

        ctk.CTkLabel(
            shell,
            text=(
                f"Pack: {info.mod_name}\n"
                f"Source: {info.package_name}\n"
                "This pack contains multiple costume-slot skins. Choose exactly which ones to import.\n"
                "Friendly form names are shown when the pack includes slot metadata."
            ),
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
            text_color=theme.TEXT_SOFT,
        ).pack(fill="x", padx=14)

        options_frame = ctk.CTkFrame(shell, fg_color=theme.BG_OPTIONS_FRAME, corner_radius=8)
        options_frame.pack(fill="x", padx=14, pady=(12, 10))

        option_vars: dict[str, tk.BooleanVar] = {}
        for option in info.options:
            default_checked = bool(option.recommended)
            var = tk.BooleanVar(value=default_checked)
            option_vars[option.option_id] = var
            label = option.label + (" (Recommended)" if option.recommended else "")
            ctk.CTkCheckBox(
                options_frame,
                text=label,
                variable=var,
                font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
            ).pack(anchor="w", padx=12, pady=6)

        quick_row = ctk.CTkFrame(shell, fg_color="transparent")
        quick_row.pack(fill="x", padx=14, pady=(0, 6))

        def select_only_recommended():
            for option in info.options:
                option_vars[option.option_id].set(bool(option.recommended))

        def select_all():
            for option in info.options:
                option_vars[option.option_id].set(True)

        ctk.CTkButton(
            quick_row,
            text="Base Only",
            width=96,
            height=30,
            fg_color=theme.BTN_SECONDARY,
            hover_color=theme.HOVER_SECONDARY,
            command=select_only_recommended,
        ).pack(side="left")

        ctk.CTkButton(
            quick_row,
            text="Select All",
            width=96,
            height=30,
            fg_color=theme.BTN_SECONDARY,
            hover_color=theme.HOVER_SECONDARY,
            command=select_all,
        ).pack(side="left", padx=(8, 0))

        btn_row = ctk.CTkFrame(shell, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(4, 12))

        def close_with(value=None):
            result["value"] = value
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()

        def on_import_selected():
            chosen = [
                option.option_id
                for option in info.options
                if bool(option_vars[option.option_id].get())
            ]
            close_with(chosen)

        ctk.CTkButton(
            btn_row,
            text="Skip Pack",
            width=96,
            height=30,
            fg_color=theme.BTN_SECONDARY,
            hover_color=theme.HOVER_SECONDARY,
            command=lambda: close_with([]),
        ).pack(side="right")

        ctk.CTkButton(
            btn_row,
            text="Import Selected",
            width=124,
            height=30,
            fg_color=theme.PRIMARY,
            hover_color=theme.HOVER_PRIMARY,
            command=on_import_selected,
        ).pack(side="right", padx=(0, 8))

        dialog.bind("<Escape>", lambda _e: close_with([]))
        dialog.bind("<Return>", lambda _e: on_import_selected())
        dialog.bind("<Control-a>", lambda _e: (select_all(), "break"))
        self._center_dialog(dialog, width=theme.WIDTH_MULTI_SLOT_DIALOG, height=max(theme.HEIGHT_MULTI_SLOT_BASE, theme.HEIGHT_MULTI_SLOT_MIN_CONTENT + len(info.options) * theme.HEIGHT_MULTI_SLOT_OPTION))
        self._present_modal_dialog(dialog, animate_open=False)
        self.wait_window(dialog)
        return result["value"]
