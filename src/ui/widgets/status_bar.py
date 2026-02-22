"""Bottom status bar widget."""
import customtkinter as ctk


class StatusBar(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, height=30, fg_color="#1a1a2e", corner_radius=0, **kwargs)
        self.pack_propagate(False)

        self.status_label = ctk.CTkLabel(
            self,
            text="Ready",
            font=ctk.CTkFont(size=11),
            text_color="#888888",
        )
        self.status_label.pack(side="left", padx=15)

        self.stats_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#888888",
        )
        self.stats_label.pack(side="right", padx=15)

    def set_status(self, text: str):
        self.status_label.configure(text=text)

    def set_stats(self, mods=0, plugins=0, conflicts=0):
        parts = []
        if mods > 0:
            parts.append(f"{mods} mods")
        if plugins > 0:
            parts.append(f"{plugins} plugins")
        if conflicts > 0:
            parts.append(f"{conflicts} conflicts")
        self.stats_label.configure(text=" | ".join(parts))
