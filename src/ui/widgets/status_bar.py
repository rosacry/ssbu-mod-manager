"""Bottom status bar widget."""
import customtkinter as ctk
from src import __version__


class StatusBar(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, height=32, fg_color="#0c0c18", corner_radius=0, **kwargs)
        self.pack_propagate(False)

        # Left separator accent
        ctk.CTkFrame(self, width=3, fg_color="#e94560",
                     corner_radius=0).pack(side="left", fill="y")

        self.status_label = ctk.CTkLabel(
            self,
            text="\u2022  Ready",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#6a6a8a",
        )
        self.status_label.pack(side="left", padx=12)

        # Version label
        ver_label = ctk.CTkLabel(
            self,
            text=f"SSBU Mod Manager v{__version__}",
            font=ctk.CTkFont(size=10),
            text_color="#353550",
        )
        ver_label.pack(side="right", padx=12)

        # Zoom indicator
        self.zoom_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="#555570",
        )
        self.zoom_label.pack(side="right", padx=(0, 4))

        self.stats_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#6a6a8a",
        )
        self.stats_label.pack(side="right", padx=8)

    def set_status(self, text: str):
        self.status_label.configure(text=f"\u2022  {text}")

    def set_stats(self, mods=0, plugins=0, conflicts=0):
        parts = []
        if mods > 0:
            parts.append(f"\u25a3 {mods} mods")
        if plugins > 0:
            parts.append(f"\u2699 {plugins} plugins")
        if conflicts > 0:
            parts.append(f"\u26a0 {conflicts} conflicts")
        self.stats_label.configure(text="  \u00b7  ".join(parts))

    def set_zoom(self, percent: int):
        """Update zoom level display."""
        if percent == 100:
            self.zoom_label.configure(text="")
        else:
            self.zoom_label.configure(text=f"\u2315 {percent}%")
