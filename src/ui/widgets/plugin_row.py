import customtkinter as ctk
from src.models.plugin import Plugin, PluginStatus
from src.ui import theme
from src.utils.file_utils import format_size


class PluginRow(ctk.CTkFrame):
    def __init__(self, parent, plugin: Plugin, on_toggle=None, **kwargs):
        super().__init__(parent, fg_color=theme.BG_CARD, corner_radius=8, **kwargs)
        self.plugin = plugin
        self._on_toggle = on_toggle

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)

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

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)

        name_color = theme.TEXT_PRIMARY if plugin.status == PluginStatus.ENABLED else theme.TEXT_DISABLED
        ctk.CTkLabel(
            info, text=plugin.display_name,
            font=ctk.CTkFont(size=theme.FONT_CARD_HEADING, weight="bold"),
            text_color=name_color, anchor="w",
        ).pack(anchor="w")

        clean_name = plugin.filename
        if clean_name.lower().endswith(".disabled"):
            clean_name = clean_name[:-len(".disabled")]
        if clean_name != plugin.display_name:
            ctk.CTkLabel(
                info, text=clean_name,
                font=ctk.CTkFont(size=theme.FONT_BODY),
                text_color=theme.TEXT_DISABLED, anchor="w",
            ).pack(anchor="w")

        ctk.CTkLabel(
            info, text=plugin.description,
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
            text_color=theme.TEXT_MUTED, anchor="w",
            wraplength=theme.WRAP_DIALOG,
        ).pack(anchor="w", pady=(2, 0))

        ctk.CTkLabel(
            row, text=format_size(plugin.file_size),
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
            text_color=theme.TEXT_DIM,
        ).pack(side="right", padx=10)

        if plugin.known_info and plugin.known_info.required:
            ctk.CTkLabel(
                row, text="REQUIRED",
                font=ctk.CTkFont(size=theme.FONT_CAPTION, weight="bold"),
                text_color=theme.ACCENT,
            ).pack(side="right", padx=5)

    def _toggle(self):
        if self._on_toggle:
            self._on_toggle(self.plugin)
