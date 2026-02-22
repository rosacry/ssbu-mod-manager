"""Mods management page with category grouping and undo/redo."""
import customtkinter as ctk
from tkinter import messagebox
from collections import defaultdict
from src.ui.base_page import BasePage
from src.ui.widgets.mod_card import ModCard
from src.ui.widgets.search_bar import SearchBar
from src.models.mod import Mod, ModStatus
from src.utils.logger import logger
from src.utils.action_history import action_history, Action


# Category colors for visual grouping
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
    "Other": "#666666",
}


class ModsPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._all_mods = []
        self._loaded = False
        self._group_by_category = True
        self._build_ui()

    def _build_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(25, 10))

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
        filter_frame.pack(fill="x", padx=30, pady=(0, 8))

        self.search_bar = SearchBar(filter_frame, placeholder="Search mods...",
                                    on_change=self._on_search)
        self.search_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.group_var = ctk.BooleanVar(value=True)
        group_cb = ctk.CTkCheckBox(filter_frame, text="Group by type",
                                   variable=self.group_var,
                                   command=self._on_group_change,
                                   font=ctk.CTkFont(size=12), width=130)
        group_cb.pack(side="right", padx=(0, 10))

        self.filter_var = ctk.StringVar(value="All")
        filter_menu = ctk.CTkOptionMenu(
            filter_frame, values=["All", "Enabled", "Disabled"],
            variable=self.filter_var, command=self._on_filter_change, width=120,
            corner_radius=8, height=34,
        )
        filter_menu.pack(side="right")

        # Mod count + category summary
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(fill="x", padx=30, pady=(0, 5))

        self.count_label = ctk.CTkLabel(info_frame, text="",
                                        font=ctk.CTkFont(size=12),
                                        text_color="#999999", anchor="w")
        self.count_label.pack(side="left")

        self.category_label = ctk.CTkLabel(info_frame, text="",
                                            font=ctk.CTkFont(size=11),
                                            text_color="#666666", anchor="e")
        self.category_label.pack(side="right")

        # Scrollable mod list
        self.mod_list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.mod_list.pack(fill="both", expand=True, padx=30, pady=(0, 10))

    def on_show(self):
        if not self._loaded:
            self._refresh()

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

    def _render_mods(self):
        # Clear old widgets
        for widget in self.mod_list.winfo_children():
            widget.destroy()

        search = self.search_bar.get().lower()
        filter_val = self.filter_var.get()

        filtered = []
        for mod in self._all_mods:
            if search and search not in mod.original_name.lower():
                # Also search in categories
                cat_match = any(search in c.lower() for c in mod.metadata.categories)
                if not cat_match:
                    continue
            if filter_val == "Enabled" and mod.status != ModStatus.ENABLED:
                continue
            if filter_val == "Disabled" and mod.status != ModStatus.DISABLED:
                continue
            filtered.append(mod)

        enabled_count = sum(1 for m in filtered if m.status == ModStatus.ENABLED)
        self.count_label.configure(
            text=f"{len(filtered)} mods ({enabled_count} enabled, {len(filtered) - enabled_count} disabled)")

        # Category summary
        cat_counts = defaultdict(int)
        for m in filtered:
            for c in m.metadata.categories:
                cat_counts[c] += 1
        cat_text = " | ".join(f"{c}: {n}" for c, n in sorted(cat_counts.items()))
        self.category_label.configure(text=cat_text)

        if self._group_by_category and self.group_var.get():
            self._render_grouped(filtered)
        else:
            self._render_flat(filtered)

        logger.debug("Mods", f"Rendered {len(filtered)} mod cards")

    def _render_grouped(self, mods):
        """Render mods grouped by their primary category."""
        groups = defaultdict(list)
        for mod in mods:
            primary = mod.metadata.categories[0] if mod.metadata.categories else "Other"
            groups[primary].append(mod)

        # Sort groups by name, but put "Character" first
        order = ["Character", "Audio", "Stage", "UI", "Effect", "Other"]
        sorted_groups = []
        for key in order:
            if key in groups:
                sorted_groups.append((key, groups.pop(key)))
        for key in sorted(groups.keys()):
            sorted_groups.append((key, groups[key]))

        for category, category_mods in sorted_groups:
            color = CATEGORY_COLORS.get(category, "#666666")

            # Category header
            header = ctk.CTkFrame(self.mod_list, fg_color="transparent")
            header.pack(fill="x", pady=(10, 4))

            badge = ctk.CTkLabel(header, text=f"  {category}  ",
                                 font=ctk.CTkFont(size=11, weight="bold"),
                                 text_color="white", fg_color=color,
                                 corner_radius=4)
            badge.pack(side="left")

            count = ctk.CTkLabel(header, text=f"  {len(category_mods)} mods",
                                 font=ctk.CTkFont(size=11),
                                 text_color="#888888")
            count.pack(side="left")

            # Mod cards in this category
            for mod in category_mods:
                card = ModCard(self.mod_list, mod, on_toggle=self._on_toggle)
                card.pack(fill="x", pady=2)

    def _render_flat(self, mods):
        """Render mods as a flat list."""
        for mod in mods:
            card = ModCard(self.mod_list, mod, on_toggle=self._on_toggle)
            card.pack(fill="x", pady=2)

    def _on_toggle(self, mod):
        try:
            was_enabled = mod.status == ModStatus.ENABLED
            mod_name = mod.original_name

            # Create undo/redo action
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
                do=do_action,
                undo=undo_action,
                page="mods",
            )
            action_history.execute(action)

            logger.info("Mods", f"Toggled: {mod_name} -> {mod.status.value}")
            self._loaded = False
            self._refresh()
        except Exception as e:
            logger.error("Mods", f"Toggle failed: {e}")
            messagebox.showerror("Error", f"Failed to toggle mod: {e}")

    def _on_search(self, text):
        self._render_mods()

    def _on_filter_change(self, value):
        self._render_mods()

    def _on_group_change(self):
        self._render_mods()

    def _open_folder(self):
        import os
        settings = self.app.config_manager.settings
        if settings.mods_path and settings.mods_path.exists():
            os.startfile(str(settings.mods_path))
