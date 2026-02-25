"""Mods management page with category grouping, virtual scrolling, and undo/redo."""
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from collections import defaultdict
from pathlib import Path
from src.ui.base_page import BasePage
from src.models.mod import Mod, ModStatus
from src.core.content_importer import import_mod_package
from src.utils.logger import logger
from src.utils.action_history import action_history, Action


# Category colors for the left accent bar
CATEGORY_COLORS = {
    "Character": "#e94560",
    "Audio": "#2fa572",
    "Stage": "#1f538d",
    "UI": "#b08a2a",
    "Effect": "#9b59b6",
    "Camera": "#3498db",
    "Assist Trophy": "#e67e22",
    "Item": "#1abc9c",
    "Params": "#95a5a6",
    "Music": "#2fa572",
    "Other": "#555555",
}

# Row heights
_HEADER_HEIGHT = 40
_MOD_ROW_HEIGHT = 44
_ROW_PAD = 2


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
        """Use app-global wheel handling for parity with Plugins page."""
        # Intentionally no per-widget wheel bindings on this page.
        # This keeps Mods and Plugins scrolling behavior consistent.
        return

    def _build_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(20, 8))

        title = ctk.CTkLabel(header_frame, text="Mod Management",
                             font=ctk.CTkFont(size=24, weight="bold"), anchor="w")
        title.pack(side="left")

        refresh_btn = ctk.CTkButton(header_frame, text="Refresh", width=100,
                                    command=self._force_refresh,
                                    corner_radius=8, height=34)
        refresh_btn.pack(side="right", padx=(5, 0))

        open_btn = ctk.CTkButton(header_frame, text="Open Folder", width=110,
                                 command=self._open_folder,
                                 fg_color="#555555", hover_color="#444444",
                                 corner_radius=8, height=34)
        open_btn.pack(side="right", padx=(5, 0))

        import_btn = ctk.CTkButton(
            header_frame, text="Import", width=100,
            command=self._import_mod_folder,
            fg_color="#7a3fb0", hover_color="#633292",
            corner_radius=8, height=34,
        )
        import_btn.pack(side="right", padx=(5, 0))

        disable_all_btn = ctk.CTkButton(header_frame, text="Disable All", width=100,
                                        command=self._disable_all,
                                        fg_color="#8b2e2e", hover_color="#6e2424",
                                        corner_radius=8, height=34)
        disable_all_btn.pack(side="right", padx=(5, 0))

        enable_all_btn = ctk.CTkButton(header_frame, text="Enable All", width=100,
                                       command=self._enable_all,
                                       fg_color="#2e6b3e", hover_color="#245530",
                                       corner_radius=8, height=34)
        enable_all_btn.pack(side="right", padx=(5, 0))

        fix_nesting_btn = ctk.CTkButton(header_frame, text="Fix Nesting", width=100,
                                        command=self._fix_nesting,
                                        fg_color="#6b5b2e", hover_color="#554824",
                                        corner_radius=8, height=34)
        fix_nesting_btn.pack(side="right", padx=(5, 0))

        # Search, filter, and group toggle
        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.pack(fill="x", padx=30, pady=(0, 6))

        self.search_var = tk.StringVar()
        self._search_after_id = None
        def _debounced_search(*_a):
            if self._search_after_id:
                self.after_cancel(self._search_after_id)
            self._search_after_id = self.after(150, self._render_mods)
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
                                   font=ctk.CTkFont(size=12), width=130)
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
                                        font=ctk.CTkFont(size=12),
                                        text_color="#888888", anchor="w")
        self.count_label.pack(fill="x", padx=32, pady=(0, 4))

        # Virtual scrolling canvas
        self._canvas_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._canvas_frame.pack(fill="both", expand=True, padx=25, pady=(0, 10))

        self._canvas = tk.Canvas(
            self._canvas_frame, bg="#12121e", highlightthickness=0,
            bd=0, relief="flat",
        )
        self._scrollbar = ctk.CTkScrollbar(self._canvas_frame, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        # Inner frame for widgets
        self._inner_frame = tk.Frame(self._canvas, bg="#12121e")
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._inner_frame, anchor="nw"
        )

        # Bind events
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._inner_frame.bind("<Configure>", self._on_frame_configure)

    def _on_canvas_configure(self, event):
        """Resize inner frame to match canvas width."""
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_frame_configure(self, event):
        """Update scroll region when inner frame changes, debounced."""
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
                self._scroll_after_id = self.after(5, self._update_scroll_region)
            except Exception:
                pass

    def _update_scroll_region(self):
        """Actually update the scroll region."""
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
        self._all_mods = self.app.mod_manager.list_mods()
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

    def _render_mods(self, *_args):
        # Clear all existing widgets
        for w in self._inner_frame.winfo_children():
            w.destroy()
        self._rendered_widgets.clear()

        filtered = self._get_filtered_mods()
        enabled_count = sum(1 for m in filtered if m.status == ModStatus.ENABLED)
        disabled_count = len(filtered) - enabled_count

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
        count_text = " \u00b7 ".join(parts)

        if cat_counts:
            cat_strs = [f"{c} ({n})" for c, n in sorted(cat_counts.items(), key=lambda x: -x[1])]
            count_text += "  \u2014  " + ", ".join(cat_strs[:6])
        self.count_label.configure(text=count_text)

        if self.group_var.get():
            self._render_grouped(filtered)
        else:
            self._render_flat(filtered)

        # Force scroll region update
        self._inner_frame.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

        logger.debug("Mods", f"Rendered {len(filtered)} mod entries")

    def _render_grouped(self, mods):
        """Render mods grouped by category."""
        groups = defaultdict(list)
        for mod in mods:
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
            color = CATEGORY_COLORS.get(category, "#555555")
            is_collapsed = category in self._collapsed
            enabled = sum(1 for m in category_mods if m.status == ModStatus.ENABLED)

            self._render_category_header(
                category, color, is_collapsed, enabled, len(category_mods))

            if not is_collapsed:
                for mod in category_mods:
                    self._render_mod_row(mod, color)

    def _render_flat(self, mods):
        """Render mods as a flat list."""
        for mod in mods:
            color = CATEGORY_COLORS.get(
                mod.metadata.categories[0] if mod.metadata.categories else "Other",
                "#555555"
            )
            self._render_mod_row(mod, color)

    def _render_category_header(self, category, color, is_collapsed, enabled, total):
        """Render a category header with collapse toggle."""
        header = tk.Frame(self._inner_frame, bg="#181830", cursor="hand2",
                          height=_HEADER_HEIGHT)
        header.pack(fill="x", pady=(6, 1), padx=2)
        header.pack_propagate(False)

        arrow = "\u25b8" if is_collapsed else "\u25be"
        count_text = f"{total} mod{'s' if total != 1 else ''}"
        if enabled < total:
            count_text += f" \u00b7 {enabled} enabled"

        arrow_label = tk.Label(header, text=arrow, font=("Segoe UI", 11),
                               fg="#6a6a8a", bg="#181830", width=2)
        arrow_label.pack(side="left", padx=(10, 0))

        dot = tk.Frame(header, width=10, height=10, bg=color)
        dot.pack(side="left", padx=(4, 8), pady=15)

        name_l = tk.Label(header, text=f"{category}",
                          font=("Segoe UI", 12, "bold"),
                          fg="#b0b0cc", bg="#181830")
        name_l.pack(side="left", padx=(0, 8))

        count_l = tk.Label(header, text=count_text,
                           font=("Segoe UI", 10),
                           fg="#505068", bg="#181830")
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
        """Render a single mod row using lightweight tk widgets for performance."""
        is_enabled = mod.status == ModStatus.ENABLED

        row = tk.Frame(self._inner_frame, bg="#1c1c34", height=_MOD_ROW_HEIGHT)
        row.pack(fill="x", pady=1, padx=2)
        row.pack_propagate(False)

        # Colored accent bar
        accent = tk.Frame(row, width=4,
                          bg=accent_color if is_enabled else "#3a3a4a")
        accent.pack(side="left", fill="y", padx=(3, 0), pady=4)

        # Toggle switch (CTk needed for proper switch behavior)
        switch = ctk.CTkSwitch(
            row, text="", width=42, height=20,
            command=lambda m=mod: self._on_toggle(m),
            onvalue=True, offvalue=False,
            bg_color="#1c1c34",
        )
        switch.pack(side="left", padx=(8, 6))
        if is_enabled:
            switch.select()
        else:
            switch.deselect()

        # Name + categories label
        name = self._mod_display_name(mod)
        cats = mod.metadata.categories[:3]

        name_color = "#d0d0e8" if is_enabled else "#454560"
        cat_color = "#6a6a88" if is_enabled else "#3a3a50"

        # Use a tk.Label for speed (much faster than CTkLabel)
        name_label = tk.Label(
            row, text=name, font=("Segoe UI", 12),
            fg=name_color, bg="#1c1c34", anchor="w",
        )
        name_label.pack(side="left", padx=(2, 0))

        if cats:
            cat_label = tk.Label(
                row, text=" \u00b7 ".join(cats),
                font=("Segoe UI", 10), fg=cat_color, bg="#1c1c34", anchor="w",
            )
            cat_label.pack(side="left", padx=(8, 0))

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
        menu.configure(fg_color="#101427")

        frame = ctk.CTkFrame(
            menu,
            fg_color="#171a31",
            border_width=1,
            border_color="#2f3f6a",
            corner_radius=8,
        )
        frame.pack(fill="both", expand=True)

        self._add_context_item(
            frame,
            "Rename Mod...",
            lambda m=mod: self._rename_mod(m),
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
        """Close mod context menu when clicking outside it."""
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
            hover_color="#24375f",
            font=ctk.CTkFont(size=12),
            command=lambda cb=callback: self._invoke_context_action(cb),
        )
        btn.pack(fill="x")

    def _invoke_context_action(self, callback):
        self._close_context_menu()
        try:
            # Let context menu teardown finish before opening rename dialog.
            self.after_idle(callback)
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
        dialog.configure(fg_color="#0f1327")

        shell = ctk.CTkFrame(dialog, fg_color="#151b36", corner_radius=10,
                             border_width=1, border_color="#304378")
        shell.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            shell, text="Rename Mod", anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(fill="x", padx=14, pady=(12, 6))

        ctk.CTkLabel(
            shell,
            text="Set a new mod name.\n"
                 "Unchecked: rename in this app only.\n"
                 "Checked: also rename the actual mod folder.",
            anchor="w", justify="left",
            font=ctk.CTkFont(size=12), text_color="#b9bfd8",
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
            font=ctk.CTkFont(size=12),
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
            fg_color="#2f3557", hover_color="#3f476f",
            command=lambda: close_with(None),
        ).pack(side="right")

        ctk.CTkButton(
            btn_row, text="Save", width=96, height=30,
            fg_color="#1f538d", hover_color="#163b6a",
            command=lambda: close_with(entry.get()),
        ).pack(side="right", padx=(0, 8))

        dialog.bind("<Escape>", lambda _e: close_with(None))
        dialog.bind("<Return>", lambda _e: close_with(entry.get()))
        self._center_dialog(dialog, width=460, height=270)

        try:
            dialog.transient(self.winfo_toplevel())
        except Exception:
            pass
        try:
            dialog.update_idletasks()
        except Exception:
            pass
        dialog.deiconify()
        dialog.lift()
        try:
            dialog.wait_visibility()
        except Exception:
            pass
        try:
            dialog.grab_set()
        except Exception:
            pass
        entry.focus_set()
        self.wait_window(dialog)
        if result["value"] is None:
            return None
        return result["value"], result["rename_folder"]

    def _center_dialog(self, dialog, width: int, height: int):
        try:
            self.update_idletasks()
            x = self.winfo_rootx() + max(20, (self.winfo_width() - width) // 2)
            y = self.winfo_rooty() + max(20, (self.winfo_height() - height) // 2)
        except Exception:
            x, y = 200, 200
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    @staticmethod
    def _clamp_popup_to_screen(x: int, y: int, width: int, height: int):
        try:
            root = tk._default_root
            if root is None:
                return x, y
            sw = max(640, root.winfo_screenwidth())
            sh = max(480, root.winfo_screenheight())
            cx = min(max(6, int(x)), max(6, sw - int(width) - 6))
            cy = min(max(6, int(y)), max(6, sh - int(height) - 6))
            return cx, cy
        except Exception:
            return x, y

    def _reset_single_custom_mod_name(self, mod):
        settings = self.app.config_manager.settings
        overrides = dict(getattr(settings, "mod_name_overrides", {}) or {})
        if mod.original_name in overrides:
            overrides.pop(mod.original_name, None)
            settings.mod_name_overrides = overrides
            self.app.config_manager.save(settings)
            self._loaded = False
            self._refresh()

    def _on_toggle(self, mod):
        try:
            was_enabled = mod.status == ModStatus.ENABLED
            mod_name = mod.original_name
            mod_path = str(mod.path)

            def _find_mod_by_name(name):
                """Look up the current mod object by original name."""
                for m in self.app.mod_manager.list_mods():
                    if m.original_name == name:
                        return m
                return None

            def do_action():
                current = _find_mod_by_name(mod_name) or mod
                if was_enabled:
                    self.app.mod_manager.disable_mod(current)
                else:
                    self.app.mod_manager.enable_mod(current)

            def undo_action():
                self.app.mod_manager.invalidate_cache()
                current = _find_mod_by_name(mod_name) or mod
                if was_enabled:
                    self.app.mod_manager.enable_mod(current)
                else:
                    self.app.mod_manager.disable_mod(current)

            action = Action(
                description=f"{'Disable' if was_enabled else 'Enable'} {mod_name}",
                do=do_action, undo=undo_action, page="mods",
            )
            action_history.execute(action)

            logger.info("Mods", f"Toggled: {mod_name} -> {'disabled' if was_enabled else 'enabled'}")
            # Re-render cards preserving scroll position.
            # Do NOT re-scan list_mods() — the mod object was updated
            # in-place by enable_mod/disable_mod, so _all_mods already
            # reflects the new state.  Re-scanning would reorder the
            # list (disabled mods get appended at the end).
            scroll_pos = self._canvas.yview()[0]
            self.app.mod_manager.invalidate_cache()
            self._render_mods()
            self.after(20, lambda: self._canvas.yview_moveto(scroll_pos))
        except Exception as e:
            logger.error("Mods", f"Toggle failed: {e}")
            messagebox.showerror("Error", f"Failed to toggle mod: {e}")
            self._loaded = False
            self._refresh()

    def _enable_all(self):
        """Enable all disabled mods."""
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
        except Exception as e:
            logger.error("Mods", f"Enable all failed: {e}")
            messagebox.showerror("Error", f"Failed to enable all mods: {e}")

    def _disable_all(self):
        """Disable all enabled mods."""
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
        except Exception as e:
            logger.error("Mods", f"Disable all failed: {e}")
            messagebox.showerror("Error", f"Failed to disable all mods: {e}")

    def _fix_nesting(self):
        """Detect and fix unnecessarily nested mod folders."""
        nested = self.app.mod_manager.detect_nested_mods()
        if not nested:
            messagebox.showinfo("Info", "No unnecessarily nested mods found.")
            return

        names = "\n".join(f"  - {m.original_name}" for m in nested[:15])
        if len(nested) > 15:
            names += f"\n  ... and {len(nested) - 15} more"

        confirm = messagebox.askyesno(
            "Fix Nested Folders",
            f"Found {len(nested)} mod(s) with unnecessary subfolder nesting:\n\n"
            f"{names}\n\n"
            "This will move content up one directory level.\n"
            "Continue?")
        if not confirm:
            return

        try:
            count = self.app.mod_manager.flatten_all_nested()
            logger.info("Mods", f"Flattened {count} nested mods")
            messagebox.showinfo("Done", f"Fixed {count} mod(s).")
            self._force_refresh()
        except Exception as e:
            logger.error("Mods", f"Fix nesting failed: {e}")
            messagebox.showerror("Error", f"Failed to fix nesting: {e}")

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
            summary = import_mod_package(Path(folder), mods_path)
            logger.info(
                "Mods",
                f"Imported {summary.items_imported} mod(s), "
                f"{summary.files_copied} file(s), {summary.replaced_paths} replaced path(s)",
            )
            lines = [
                f"Imported {summary.items_imported} mod(s).",
                f"Copied {summary.files_copied} file(s).",
            ]
            if summary.flattened_mods:
                lines.append(f"Auto-flattened {summary.flattened_mods} nested mod folder(s).")
            if summary.replaced_paths:
                lines.append(f"Replaced {summary.replaced_paths} existing mod folder(s).")
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
