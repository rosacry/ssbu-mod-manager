"""Mod card widget for the mods page."""
import customtkinter as ctk
from src.models.mod import Mod, ModStatus
from src.ui import theme


class ModCard(ctk.CTkFrame):
    def __init__(self, parent, mod: Mod, on_toggle=None, on_details=None, **kwargs):
        super().__init__(parent, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS_MEDIUM, **kwargs)
        self.mod = mod
        self._on_toggle = on_toggle
        self._on_details = on_details

        # Main row
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)

        # Toggle switch
        self.switch = ctk.CTkSwitch(
            row,
            text="",
            width=45,
            command=self._toggle,
            onvalue=True,
            offvalue=False,
        )
        self.switch.pack(side="left", padx=(0, 10))
        if mod.status == ModStatus.ENABLED:
            self.switch.select()
        else:
            self.switch.deselect()

        # Info section
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)

        # Name
        name_color = theme.TEXT_PRIMARY if mod.status == ModStatus.ENABLED else theme.TEXT_DISABLED
        self.name_label = ctk.CTkLabel(
            info, text=mod.original_name,
            font=ctk.CTkFont(size=theme.FONT_CARD_HEADING, weight="bold"),
            text_color=name_color, anchor="w",
        )
        self.name_label.pack(anchor="w")

        # Details line - show status and categories if available
        details_parts = []
        if mod.status == ModStatus.DISABLED:
            details_parts.append("DISABLED")
        if mod.metadata.categories:
            details_parts.append(" | ".join(mod.metadata.categories))

        if details_parts:
            self.details_label = ctk.CTkLabel(
                info, text=" | ".join(details_parts),
                font=ctk.CTkFont(size=theme.FONT_BODY),
                text_color=theme.TEXT_DIM, anchor="w",
            )
            self.details_label.pack(anchor="w")

        # Conflict indicator
        if mod.conflicts_with:
            conflict_text = f"Conflicts: {', '.join(mod.conflicts_with[:3])}"
            if len(mod.conflicts_with) > 3:
                conflict_text += f" +{len(mod.conflicts_with) - 3} more"
            conflict_label = ctk.CTkLabel(
                info, text=conflict_text,
                font=ctk.CTkFont(size=theme.FONT_BODY),
                text_color=theme.ACCENT, anchor="w",
            )
            conflict_label.pack(anchor="w")

    def _toggle(self):
        if self._on_toggle:
            self._on_toggle(self.mod)
        try:
            if self.winfo_exists():
                if self.mod.status == ModStatus.ENABLED:
                    self.name_label.configure(text_color=theme.TEXT_PRIMARY)
                else:
                    self.name_label.configure(text_color=theme.TEXT_DISABLED)
        except Exception:
            pass

    def update_card(self):
        name_color = theme.TEXT_PRIMARY if self.mod.status == ModStatus.ENABLED else theme.TEXT_DISABLED
        self.name_label.configure(text_color=name_color)
        if self.mod.status == ModStatus.ENABLED:
            self.switch.select()
        else:
            self.switch.deselect()
