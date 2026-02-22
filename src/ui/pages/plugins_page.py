"""Plugins management page."""
import customtkinter as ctk
from tkinter import messagebox
from src.ui.base_page import BasePage
from src.ui.widgets.plugin_row import PluginRow
from src.models.plugin import PluginStatus
from src.utils.logger import logger


class PluginsPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._loaded = False
        self._build_ui()

    def _build_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(25, 10))

        title = ctk.CTkLabel(header_frame, text="Skyline Plugin Management",
                             font=ctk.CTkFont(size=24, weight="bold"), anchor="w")
        title.pack(side="left")

        refresh_btn = ctk.CTkButton(header_frame, text="Refresh", width=100,
                                    command=self._force_refresh,
                                    corner_radius=8, height=34)
        refresh_btn.pack(side="right")

        # Plugin count
        self.count_label = ctk.CTkLabel(self, text="",
                                        font=ctk.CTkFont(size=12),
                                        text_color="#999999", anchor="w")
        self.count_label.pack(fill="x", padx=30, pady=(0, 8))

        # Scrollable plugin list
        self.plugin_list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.plugin_list.pack(fill="both", expand=True, padx=30, pady=(0, 10))

        # Warning note
        note = ctk.CTkLabel(
            self,
            text="Note: Disabling required plugins (like ARCropolis) will prevent mods from loading.",
            font=ctk.CTkFont(size=11),
            text_color="#e94560",
        )
        note.pack(fill="x", padx=30, pady=(5, 15))

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
        self.count_label.configure(text=f"{active} active / {len(plugins)} total plugins")

        for plugin in plugins:
            row = PluginRow(self.plugin_list, plugin, on_toggle=self._on_toggle)
            row.pack(fill="x", pady=3)

        logger.info("Plugins", f"Rendered {len(plugins)} plugins")

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
