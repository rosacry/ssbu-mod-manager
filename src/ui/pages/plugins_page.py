"""Plugins management page - compact rows with accent bars."""
import customtkinter as ctk
from tkinter import messagebox
from src.ui.base_page import BasePage
from src.models.plugin import PluginStatus
from src.utils.logger import logger
from src.utils.file_utils import format_size


class PluginsPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._loaded = False
        self._build_ui()

    def _build_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(20, 8))

        title = ctk.CTkLabel(header_frame, text="Skyline Plugin Management",
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

        # Plugin count
        self.count_label = ctk.CTkLabel(self, text="",
                                        font=ctk.CTkFont(size=12),
                                        text_color="#888888", anchor="w")
        self.count_label.pack(fill="x", padx=32, pady=(0, 6))

        # Scrollable plugin list
        self.plugin_list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.plugin_list.pack(fill="both", expand=True, padx=25, pady=(0, 10))

        # Warning note
        note_frame = ctk.CTkFrame(self, fg_color="#2e2020", corner_radius=8)
        note_frame.pack(fill="x", padx=30, pady=(5, 15))

        ctk.CTkLabel(
            note_frame,
            text="\u26a0  Disabling required plugins (like ARCropolis) will prevent mods from loading.",
            font=ctk.CTkFont(size=11),
            text_color="#e94560",
        ).pack(fill="x", padx=15, pady=8)

    def on_show(self):
        if not self._loaded:
            self._refresh()

    def _force_refresh(self):
        self.app.plugin_manager.invalidate_cache()
        self._loaded = False
        self._refresh()

    def _refresh(self):
        settings = self.app.config_manager.settings
        if not settings.plugins_path or not settings.plugins_path.exists():
            self.count_label.configure(text="No plugins path configured. Go to Settings first.")
            return

        logger.info("Plugins", "Loading plugin list...")
        plugins = self.app.plugin_manager.list_plugins()
        self._loaded = True

        # Clear old rows
        for widget in self.plugin_list.winfo_children():
            widget.destroy()

        active = sum(1 for p in plugins if p.status == PluginStatus.ENABLED)
        self.count_label.configure(
            text=f"{active} active \u00b7 {len(plugins)} total plugins")

        if not plugins:
            ctk.CTkLabel(self.plugin_list,
                         text="No plugins found in the plugins directory.",
                         font=ctk.CTkFont(size=13), text_color="#666666",
                         ).pack(pady=40)
            return

        for plugin in plugins:
            self._render_plugin_row(plugin)

        logger.info("Plugins", f"Rendered {len(plugins)} plugins")

    def _render_plugin_row(self, plugin):
        """Render a single plugin as a compact row with accent bar."""
        is_enabled = plugin.status == PluginStatus.ENABLED
        is_required = plugin.known_info and plugin.known_info.required

        row = ctk.CTkFrame(self.plugin_list, fg_color="#242438", corner_radius=6,
                           height=52)
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)

        # Colored left accent bar
        accent_color = "#1f538d" if is_enabled else "#3a3a4a"
        if is_required and is_enabled:
            accent_color = "#e94560"
        accent = ctk.CTkFrame(row, width=4, fg_color=accent_color, corner_radius=2)
        accent.pack(side="left", fill="y", padx=(3, 0), pady=4)

        # Toggle switch
        switch = ctk.CTkSwitch(
            row, text="", width=42, height=20,
            command=lambda p=plugin: self._on_toggle(p),
            onvalue=True, offvalue=False,
        )
        switch.pack(side="left", padx=(8, 6))
        if is_enabled:
            switch.select()
        else:
            switch.deselect()

        # Plugin info - name + description in single label
        name = plugin.display_name
        desc = plugin.description
        name_color = "white" if is_enabled else "#666666"

        display_text = name
        if desc and desc != name:
            display_text += f"  \u2014  {desc}"

        ctk.CTkLabel(
            row, text=display_text,
            font=ctk.CTkFont(size=13),
            text_color=name_color, anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Size
        ctk.CTkLabel(
            row, text=format_size(plugin.file_size),
            font=ctk.CTkFont(size=11),
            text_color="#666666",
        ).pack(side="right", padx=(0, 10))

        # Required badge
        if is_required:
            ctk.CTkLabel(
                row, text="REQUIRED",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="#e94560",
            ).pack(side="right", padx=(0, 5))

    def _on_toggle(self, plugin):
        try:
            if plugin.status == PluginStatus.ENABLED:
                if plugin.known_info and plugin.known_info.required:
                    confirm = messagebox.askyesno(
                        "Warning",
                        f"{plugin.display_name} is marked as REQUIRED.\n\n"
                        "Disabling it may prevent mods from loading.\n\n"
                        "Are you sure?",
                    )
                    if not confirm:
                        return
                self.app.plugin_manager.disable_plugin(plugin)
                logger.info("Plugins", f"Disabled: {plugin.display_name}")
            else:
                self.app.plugin_manager.enable_plugin(plugin)
                logger.info("Plugins", f"Enabled: {plugin.display_name}")
            self._loaded = False
            self._refresh()
        except Exception as e:
            logger.error("Plugins", f"Toggle failed: {e}")
            messagebox.showerror("Error", f"Failed to toggle plugin: {e}")

    def _enable_all(self):
        """Enable all disabled plugins."""
        plugins = self.app.plugin_manager.list_plugins()
        disabled = [p for p in plugins if p.status == PluginStatus.DISABLED]
        if not disabled:
            messagebox.showinfo("Info", "All plugins are already enabled.")
            return
        confirm = messagebox.askyesno(
            "Enable All Plugins",
            f"Enable all {len(disabled)} disabled plugin(s)?")
        if not confirm:
            return
        try:
            count = self.app.plugin_manager.enable_all()
            logger.info("Plugins", f"Enabled {count} plugins")
            messagebox.showinfo("Done", f"Enabled {count} plugin(s).")
            self._force_refresh()
        except Exception as e:
            logger.error("Plugins", f"Enable all failed: {e}")
            messagebox.showerror("Error", f"Failed to enable all plugins: {e}")

    def _disable_all(self):
        """Disable all enabled plugins (skips required ones by default)."""
        plugins = self.app.plugin_manager.list_plugins()
        enabled = [p for p in plugins if p.status == PluginStatus.ENABLED]
        if not enabled:
            messagebox.showinfo("Info", "All plugins are already disabled.")
            return
        required = [p for p in enabled if p.known_info and p.known_info.required]
        skip_msg = ""
        if required:
            names = ", ".join(p.display_name for p in required)
            skip_msg = f"\n\nRequired plugins will be skipped: {names}"
        confirm = messagebox.askyesno(
            "Disable All Plugins",
            f"Disable all {len(enabled)} enabled plugin(s)?{skip_msg}")
        if not confirm:
            return
        try:
            count = self.app.plugin_manager.disable_all(skip_required=True)
            logger.info("Plugins", f"Disabled {count} plugins")
            messagebox.showinfo("Done", f"Disabled {count} plugin(s).")
            self._force_refresh()
        except Exception as e:
            logger.error("Plugins", f"Disable all failed: {e}")
            messagebox.showerror("Error", f"Failed to disable all plugins: {e}")

    def _open_folder(self):
        from src.utils.file_utils import open_folder
        settings = self.app.config_manager.settings
        if settings.plugins_path and settings.plugins_path.exists():
            open_folder(settings.plugins_path)
