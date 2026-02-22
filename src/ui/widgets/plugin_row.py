"""Plugin row widget for the plugins page."""
import customtkinter as ctk
from src.models.plugin import Plugin, PluginStatus
from src.utils.file_utils import format_size


class PluginRow(ctk.CTkFrame):
    def __init__(self, parent, plugin: Plugin, on_toggle=None, **kwargs):
        super().__init__(parent, fg_color="#242438", corner_radius=8, **kwargs)
        self.plugin = plugin
        self._on_toggle = on_toggle

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)

        # Toggle switch
        self.switch = ctk.CTkSwitch(
            row, text="", width=45,
            command=self._toggle,
            onvalue=True, offvalue=False,
        )
        self.switch.pack(side="left", padx=(0, 10))
        if plugin.status == PluginStatus.ENABLED:
            self.switch.select()
        else:
            self.switch.deselect()

        # Info section
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)

        # Display name
        name_color = "white" if plugin.status == PluginStatus.ENABLED else "#666666"
        ctk.CTkLabel(
            info, text=plugin.display_name,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=name_color, anchor="w",
        ).pack(anchor="w")

        # Filename (if different)
        clean_name = plugin.filename.replace(".disabled", "")
        if clean_name != plugin.display_name:
            ctk.CTkLabel(
                info, text=clean_name,
                font=ctk.CTkFont(size=11),
                text_color="#666666", anchor="w",
            ).pack(anchor="w")

        # Description
        ctk.CTkLabel(
            info, text=plugin.description,
            font=ctk.CTkFont(size=12),
            text_color="#999999", anchor="w",
            wraplength=500,
        ).pack(anchor="w", pady=(2, 0))

        # Size
        ctk.CTkLabel(
            row, text=format_size(plugin.file_size),
            font=ctk.CTkFont(size=12),
            text_color="#888888",
        ).pack(side="right", padx=10)

        # Required badge
        if plugin.known_info and plugin.known_info.required:
            ctk.CTkLabel(
                row, text="REQUIRED",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="#e94560",
            ).pack(side="right", padx=5)

    def _toggle(self):
        if self._on_toggle:
            self._on_toggle(self.plugin)
