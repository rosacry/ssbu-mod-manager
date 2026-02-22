"""Reusable search bar widget."""
import tkinter as tk
import customtkinter as ctk


class SearchBar(ctk.CTkFrame):
    def __init__(self, parent, placeholder="Search...", on_change=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._on_change = on_change

        self.search_var = tk.StringVar()
        self.search_var.trace("w", self._on_search_change)

        self.entry = ctk.CTkEntry(
            self,
            placeholder_text=placeholder,
            textvariable=self.search_var,
            height=35,
            font=ctk.CTkFont(size=13),
        )
        self.entry.pack(fill="x")

    def _on_search_change(self, *args):
        if self._on_change:
            self._on_change(self.search_var.get())

    def get(self) -> str:
        return self.search_var.get()

    def clear(self):
        self.search_var.set("")
