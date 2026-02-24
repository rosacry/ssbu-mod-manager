"""Sidebar navigation component with icons and active indicator."""
import customtkinter as ctk

SIDEBAR_WIDTH = 230
SIDEBAR_BG = "#0e0e1a"
SIDEBAR_HOVER = "#1c1c34"
SIDEBAR_ACTIVE = "#162850"
ACCENT_COLOR = "#e94560"

# Navigation items with Unicode icons
NAV_ITEMS = [
    ("dashboard", "\u2302", "Dashboard"),
    ("mods", "\u25a3", "Mods"),
    ("plugins", "\u2699", "Plugins"),
    ("css", "\u270e", "CSS Editor"),
    ("music", "\u266b", "Music"),
    ("conflicts", "\u26a0", "Conflicts"),
    ("share", "\u21c4", "Profiles"),
    ("migration", "\u21e8", "Migration"),
    ("online_compat", "\u21af", "Online Guide"),
]


class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, on_navigate, **kwargs):
        super().__init__(parent, width=SIDEBAR_WIDTH, fg_color=SIDEBAR_BG, corner_radius=0, **kwargs)
        self.on_navigate = on_navigate
        self.buttons = {}
        self.indicators = {}
        self.active_page = "dashboard"

        self.pack_propagate(False)

        # Brand header with accent (fixed, not scrollable)
        brand_area = ctk.CTkFrame(self, fg_color="transparent")
        brand_area.pack(fill="x", padx=0, pady=(0, 0))

        # Top accent line
        ctk.CTkFrame(brand_area, height=3, fg_color=ACCENT_COLOR,
                      corner_radius=0).pack(fill="x")

        brand_inner = ctk.CTkFrame(brand_area, fg_color="transparent")
        brand_inner.pack(fill="x", padx=22, pady=(16, 4))

        title = ctk.CTkLabel(brand_inner, text="SSBU",
                             font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
                             text_color=ACCENT_COLOR)
        title.pack(anchor="w")
        subtitle = ctk.CTkLabel(brand_inner, text="Mod Manager",
                                font=ctk.CTkFont(family="Segoe UI", size=14),
                                text_color="#6a6a8a")
        subtitle.pack(anchor="w", pady=(0, 0))

        # Separator
        ctk.CTkFrame(self, height=1, fg_color="#1e1e34").pack(fill="x", padx=18, pady=(10, 8))

        # Non-scroll container with compact spacing so the full menu fits.
        self._nav_container = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._nav_container.pack(fill="both", expand=True, padx=0, pady=0)

        # Section label
        ctk.CTkLabel(self._nav_container, text="NAVIGATION",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#3a3a55", anchor="w"
                     ).pack(fill="x", padx=16, pady=(2, 4))

        # Navigation buttons with active indicator bars
        for page_id, icon, label in NAV_ITEMS:
            self._add_nav_btn(page_id, f"{icon}  {label}")

        # Separator before tools
        ctk.CTkFrame(self._nav_container, height=1, fg_color="#1e1e34"
                     ).pack(fill="x", padx=10, pady=(8, 6))

        ctk.CTkLabel(self._nav_container, text="TOOLS",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#3a3a55", anchor="w"
                     ).pack(fill="x", padx=16, pady=(0, 4))

        # Developer button
        self._add_nav_btn("developer", "\u2630  Developer", text_color="#555570")

        # Settings button
        self._add_nav_btn("settings", "\u2731  Settings", bottom_pad=True)

        self._highlight("dashboard")

    def _add_nav_btn(self, page_id, label, text_color="#9a9ab0", bottom_pad=False):
        """Add a navigation button with active indicator."""
        row = ctk.CTkFrame(self._nav_container, fg_color="transparent", height=36)
        row.pack(fill="x", padx=0, pady=(0, 10) if bottom_pad else (0, 1))
        row.pack_propagate(False)

        # Active indicator bar (left edge)
        indicator = ctk.CTkFrame(row, width=3, fg_color="transparent",
                                 corner_radius=2)
        indicator.pack(side="left", fill="y", pady=5)
        self.indicators[page_id] = indicator

        btn = ctk.CTkButton(
            row,
            text=label,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="transparent",
            hover_color=SIDEBAR_HOVER,
            anchor="w",
            height=36,
            corner_radius=8,
            text_color=text_color,
            command=lambda pid=page_id: self._on_click(pid),
        )
        btn.pack(side="left", fill="both", expand=True, padx=(3, 5))
        self.buttons[page_id] = btn

    def _on_click(self, page_id):
        if page_id == self.active_page:
            return  # Already on this page
        self.on_navigate(page_id)

    def set_active(self, page_id):
        """Public API: highlight a specific page (used by programmatic navigation)."""
        self._highlight(page_id)

    def _highlight(self, page_id):
        self.active_page = page_id
        for pid, btn in self.buttons.items():
            indicator = self.indicators.get(pid)
            if pid == page_id:
                btn.configure(fg_color=SIDEBAR_ACTIVE, text_color="white")
                if indicator:
                    indicator.configure(fg_color=ACCENT_COLOR)
            else:
                if pid == "developer":
                    btn.configure(fg_color="transparent", text_color="#555570")
                else:
                    btn.configure(fg_color="transparent", text_color="#9a9ab0")
                if indicator:
                    indicator.configure(fg_color="transparent")
