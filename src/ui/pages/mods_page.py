"""Mods management page with category grouping, batch rendering, and undo/redo."""
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from collections import defaultdict
from src.ui.base_page import BasePage
from src.models.mod import Mod, ModStatus
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
    "Other": "#555555",
}

# Render batch size - render N items per frame to keep UI responsive
_BATCH_SIZE = 25


class ModsPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._all_mods = []
        self._loaded = False
        self._group_by_category = True
        self._collapsed = set()  # collapsed category names
        self._render_queue = []  # pending items to render
        self._render_after_id = None
        self._build_ui()

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

        # Search, filter, and group toggle
        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.pack(fill="x", padx=30, pady=(0, 6))

        # Search entry
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *a: self._render_mods())
        search_entry = ctk.CTkEntry(filter_frame, placeholder_text="Search mods...",
                                    textvariable=self.search_var, height=34,
                                    corner_radius=8)
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.group_var = ctk.BooleanVar(value=True)
        group_cb = ctk.CTkCheckBox(filter_frame, text="Group by type",
                                   variable=self.group_var,
                                   command=self._render_mods,
                                   font=ctk.CTkFont(size=12), width=130)
        group_cb.pack(side="right", padx=(0, 10))

        self.filter_var = ctk.StringVar(value="All")
        filter_menu = ctk.CTkOptionMenu(
            filter_frame, values=["All", "Enabled", "Disabled"],
            variable=self.filter_var, command=lambda v: self._render_mods(), width=110,
            corner_radius=8, height=34,
        )
        filter_menu.pack(side="right")

        # Mod count summary
        self.count_label = ctk.CTkLabel(self, text="",
                                        font=ctk.CTkFont(size=12),
                                        text_color="#888888", anchor="w")
        self.count_label.pack(fill="x", padx=32, pady=(0, 4))

        # Scrollable mod list
        self.mod_list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.mod_list.pack(fill="both", expand=True, padx=25, pady=(0, 10))

    def on_show(self):
        if not self._loaded:
            self._refresh()

    def on_hide(self):
        """Cancel pending batch renders when leaving the page."""
        self._cancel_batch_render()

    def _cancel_batch_render(self):
        if self._render_after_id:
            try:
                self.after_cancel(self._render_after_id)
            except Exception:
                pass
            self._render_after_id = None
        self._render_queue = []

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
                name_match = search in mod.original_name.lower()
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
        # Cancel any in-progress batch render
        self._cancel_batch_render()

        # Clear
        for w in self.mod_list.winfo_children():
            w.destroy()

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

        logger.debug("Mods", f"Rendered {len(filtered)} mod entries")

    def _render_grouped(self, mods):
        """Render mods grouped by category with collapsible sections."""
        groups = defaultdict(list)
        for mod in mods:
            primary = mod.metadata.categories[0] if mod.metadata.categories else "Other"
            groups[primary].append(mod)

        # Sort groups by priority
        order = ["Character", "Audio", "Stage", "UI", "Effect",
                 "Camera", "Assist Trophy", "Item", "Params", "Other"]
        sorted_groups = []
        for key in order:
            if key in groups:
                sorted_groups.append((key, groups.pop(key)))
        for key in sorted(groups.keys()):
            sorted_groups.append((key, groups[key]))

        # Build all items to render (headers + mod rows)
        render_items = []
        for category, category_mods in sorted_groups:
            color = CATEGORY_COLORS.get(category, "#555555")
            is_collapsed = category in self._collapsed
            enabled = sum(1 for m in category_mods if m.status == ModStatus.ENABLED)

            # Header item
            render_items.append(("header", category, color, is_collapsed,
                                 enabled, len(category_mods)))

            # Mod items (if not collapsed)
            if not is_collapsed:
                for mod in category_mods:
                    render_items.append(("mod", mod, color, None, None, None))

        # Batch render
        self._render_queue = render_items
        self._render_batch()

    def _render_flat(self, mods):
        """Render mods as a flat list using batch rendering."""
        render_items = []
        for mod in mods:
            color = CATEGORY_COLORS.get(
                mod.metadata.categories[0] if mod.metadata.categories else "Other",
                "#555555"
            )
            render_items.append(("mod", mod, color, None, None, None))

        self._render_queue = render_items
        self._render_batch()

    def _render_batch(self):
        """Render items in batches to keep the UI responsive during scroll."""
        self._render_after_id = None

        if not self._render_queue:
            return

        batch = self._render_queue[:_BATCH_SIZE]
        self._render_queue = self._render_queue[_BATCH_SIZE:]

        for item in batch:
            item_type = item[0]
            if item_type == "header":
                _, category, color, is_collapsed, enabled, total = item
                self._render_category_header(
                    self.mod_list, category, color, is_collapsed, enabled, total)
            elif item_type == "mod":
                _, mod, color, _, _, _ = item
                self._render_mod_row(self.mod_list, mod, color)

        # Schedule next batch if there are more items
        if self._render_queue:
            self._render_after_id = self.after(1, self._render_batch)

    def _render_category_header(self, parent, category, color, is_collapsed, enabled, total):
        """Render a category header with collapse toggle."""
        header = ctk.CTkFrame(parent, fg_color="#1e1e30", corner_radius=8,
                              cursor="hand2")
        header.pack(fill="x", pady=(6, 1))

        # Collapse arrow + colored dot + name + count - all in one row, no inner frame
        arrow = "\u25b8" if is_collapsed else "\u25be"
        count_text = f"{total} mod{'s' if total != 1 else ''}"
        if enabled < total:
            count_text += f" \u00b7 {enabled} enabled"

        arrow_label = ctk.CTkLabel(header, text=arrow,
                                   font=ctk.CTkFont(size=12),
                                   text_color="#888888", width=20)
        arrow_label.pack(side="left", padx=(10, 0))

        dot = ctk.CTkFrame(header, width=10, height=10,
                           fg_color=color, corner_radius=5)
        dot.pack(side="left", padx=(2, 8), pady=10)

        name_label = ctk.CTkLabel(
            header, text=f"{category}  ",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#cccccc", anchor="w")
        name_label.pack(side="left", pady=8)

        count_label = ctk.CTkLabel(
            header, text=count_text,
            font=ctk.CTkFont(size=11),
            text_color="#666666")
        count_label.pack(side="left", pady=8)

        # Click handler
        def on_header_click(e, cat=category):
            if cat in self._collapsed:
                self._collapsed.discard(cat)
            else:
                self._collapsed.add(cat)
            self._render_mods()

        for widget in [header, arrow_label, name_label, count_label]:
            widget.bind("<Button-1>", on_header_click)

    def _render_mod_row(self, parent, mod, accent_color):
        """Render a single mod as a compact row - minimal widgets for scroll performance."""
        is_enabled = mod.status == ModStatus.ENABLED

        row = ctk.CTkFrame(parent, fg_color="#242438", corner_radius=6, height=42)
        row.pack(fill="x", pady=1, padx=(0, 2))
        row.pack_propagate(False)

        # Colored left accent bar
        accent = ctk.CTkFrame(row, width=4,
                              fg_color=accent_color if is_enabled else "#3a3a4a",
                              corner_radius=2)
        accent.pack(side="left", fill="y", padx=(3, 0), pady=4)

        # Toggle switch - directly in row, no wrapper frame
        switch = ctk.CTkSwitch(
            row, text="", width=42, height=20,
            command=lambda m=mod: self._on_toggle(m),
            onvalue=True, offvalue=False,
        )
        switch.pack(side="left", padx=(8, 6))
        if is_enabled:
            switch.select()
        else:
            switch.deselect()

        # Combined name + category as single label (avoids extra label widgets)
        name = mod.original_name
        cats = mod.metadata.categories[:2]
        if cats:
            cat_suffix = "  \u00b7  " + " \u00b7 ".join(cats)
        else:
            cat_suffix = ""

        name_color = "white" if is_enabled else "#666666"
        ctk.CTkLabel(
            row, text=name + cat_suffix,
            font=ctk.CTkFont(size=13),
            text_color=name_color, anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

    def _on_toggle(self, mod):
        try:
            was_enabled = mod.status == ModStatus.ENABLED
            mod_name = mod.original_name

            def do_action():
                if was_enabled:
                    self.app.mod_manager.disable_mod(mod)
                else:
                    self.app.mod_manager.enable_mod(mod)

            def undo_action():
                if was_enabled:
                    self.app.mod_manager.enable_mod(mod)
                else:
                    self.app.mod_manager.disable_mod(mod)

            action = Action(
                description=f"{'Disable' if was_enabled else 'Enable'} {mod_name}",
                do=do_action, undo=undo_action, page="mods",
            )
            action_history.execute(action)

            logger.info("Mods", f"Toggled: {mod_name} -> {mod.status.value}")
            self._loaded = False
            self._refresh()
        except Exception as e:
            logger.error("Mods", f"Toggle failed: {e}")
            messagebox.showerror("Error", f"Failed to toggle mod: {e}")

    def _open_folder(self):
        import os
        settings = self.app.config_manager.settings
        if settings.mods_path and settings.mods_path.exists():
            os.startfile(str(settings.mods_path))
