"""Sidebar navigation component with icons and active indicator."""
import customtkinter as ctk

SIDEBAR_WIDTH = 220
SIDEBAR_BG = "#141422"
SIDEBAR_HOVER = "#1e1e38"
SIDEBAR_ACTIVE = "#0f3460"

# Navigation items with Unicode icons
NAV_ITEMS = [
    ("dashboard", "\u2302  Dashboard"),
    ("mods", "\u25a3  Mods"),
    ("plugins", "\u2699  Plugins"),
    ("css", "\u270e  CSS Editor"),
    ("music", "\u266b  Music"),
    ("conflicts", "\u26a0  Conflicts"),
    ("share", "\u21c4  Profiles"),
]


class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, on_navigate, **kwargs):
        super().__init__(parent, width=SIDEBAR_WIDTH, fg_color=SIDEBAR_BG, corner_radius=0, **kwargs)
        self.on_navigate = on_navigate
        self.buttons = {}
        self.indicators = {}
        self.active_page = "dashboard"

        self.pack_propagate(False)

        # App title
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.pack(fill="x", padx=18, pady=(22, 5))

        title = ctk.CTkLabel(title_frame, text="SSBU",
                             font=ctk.CTkFont(size=22, weight="bold"),
                             text_color="#e94560")
        title.pack(anchor="w")
        subtitle = ctk.CTkLabel(title_frame, text="Mod Manager",
                                font=ctk.CTkFont(size=13),
                                text_color="#888888")
        subtitle.pack(anchor="w")

        # Separator
        sep = ctk.CTkFrame(self, height=1, fg_color="#2a2a44")
        sep.pack(fill="x", padx=15, pady=(10, 8))

        # Navigation buttons with active indicator bars
        for page_id, label in NAV_ITEMS:
            row = ctk.CTkFrame(self, fg_color="transparent", height=38)
            row.pack(fill="x", padx=6, pady=1)
            row.pack_propagate(False)

            # Active indicator bar (left edge)
            indicator = ctk.CTkFrame(row, width=3, fg_color="transparent",
                                     corner_radius=2)
            indicator.pack(side="left", fill="y", pady=4)
            self.indicators[page_id] = indicator

            btn = ctk.CTkButton(
                row,
                text=label,
                font=ctk.CTkFont(size=13),
                fg_color="transparent",
                hover_color=SIDEBAR_HOVER,
                anchor="w",
                height=38,
                corner_radius=8,
                command=lambda pid=page_id: self._on_click(pid),
            )
            btn.pack(side="left", fill="both", expand=True, padx=(2, 4))
            self.buttons[page_id] = btn

        # Spacer
        spacer = ctk.CTkFrame(self, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        # Bottom section
        sep2 = ctk.CTkFrame(self, height=1, fg_color="#2a2a44")
        sep2.pack(fill="x", padx=15, pady=5)

        # Developer button
        self._add_bottom_btn("developer", "\u2630  Developer", text_color="#777777")

        # Settings button
        self._add_bottom_btn("settings", "\u2731  Settings", bottom_pad=True)

        self._highlight("dashboard")

    def _add_bottom_btn(self, page_id, label, text_color="#bbbbbb", bottom_pad=False):
        """Add a bottom section nav button with indicator."""
        row = ctk.CTkFrame(self, fg_color="transparent", height=38)
        row.pack(fill="x", padx=6, pady=(1, 18) if bottom_pad else 1)
        row.pack_propagate(False)

        indicator = ctk.CTkFrame(row, width=3, fg_color="transparent",
                                 corner_radius=2)
        indicator.pack(side="left", fill="y", pady=4)
        self.indicators[page_id] = indicator

        btn = ctk.CTkButton(
            row,
            text=label,
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            hover_color=SIDEBAR_HOVER,
            anchor="w",
            height=38,
            corner_radius=8,
            text_color=text_color,
            command=lambda: self._on_click(page_id),
        )
        btn.pack(side="left", fill="both", expand=True, padx=(2, 4))
        self.buttons[page_id] = btn

    def _on_click(self, page_id):
        self._highlight(page_id)
        self.on_navigate(page_id)

    def _highlight(self, page_id):
        self.active_page = page_id
        for pid, btn in self.buttons.items():
            indicator = self.indicators.get(pid)
            if pid == page_id:
                btn.configure(fg_color=SIDEBAR_ACTIVE, text_color="white")
                if indicator:
                    indicator.configure(fg_color="#e94560")
            else:
                if pid in ("developer",):
                    btn.configure(fg_color="transparent", text_color="#777777")
                else:
                    btn.configure(fg_color="transparent", text_color="#bbbbbb")
                if indicator:
                    indicator.configure(fg_color="transparent")

    def set_active(self, page_id):
        self._highlight(page_id)
