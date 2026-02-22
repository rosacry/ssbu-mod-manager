"""Sidebar navigation component."""
import customtkinter as ctk

SIDEBAR_WIDTH = 220
SIDEBAR_BG = "#141422"
SIDEBAR_HOVER = "#1e1e38"
SIDEBAR_ACTIVE = "#0f3460"

NAV_ITEMS = [
    ("dashboard", "Dashboard"),
    ("mods", "Mods"),
    ("plugins", "Plugins"),
    ("css", "CSS Editor"),
    ("music", "Music"),
    ("conflicts", "Conflicts"),
    ("share", "Profiles"),
]


class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, on_navigate, **kwargs):
        super().__init__(parent, width=SIDEBAR_WIDTH, fg_color=SIDEBAR_BG, corner_radius=0, **kwargs)
        self.on_navigate = on_navigate
        self.buttons = {}
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

        # Navigation buttons
        for page_id, label in NAV_ITEMS:
            btn = ctk.CTkButton(
                self,
                text=f"  {label}",
                font=ctk.CTkFont(size=13),
                fg_color="transparent",
                hover_color=SIDEBAR_HOVER,
                anchor="w",
                height=38,
                corner_radius=8,
                command=lambda pid=page_id: self._on_click(pid),
            )
            btn.pack(fill="x", padx=10, pady=1)
            self.buttons[page_id] = btn

        # Spacer
        spacer = ctk.CTkFrame(self, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        # Bottom section
        sep2 = ctk.CTkFrame(self, height=1, fg_color="#2a2a44")
        sep2.pack(fill="x", padx=15, pady=5)

        # Developer button
        dev_btn = ctk.CTkButton(
            self,
            text="  Developer",
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            hover_color=SIDEBAR_HOVER,
            anchor="w",
            height=38,
            corner_radius=8,
            text_color="#777777",
            command=lambda: self._on_click("developer"),
        )
        dev_btn.pack(fill="x", padx=10, pady=1)
        self.buttons["developer"] = dev_btn

        # Settings button
        settings_btn = ctk.CTkButton(
            self,
            text="  Settings",
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            hover_color=SIDEBAR_HOVER,
            anchor="w",
            height=38,
            corner_radius=8,
            command=lambda: self._on_click("settings"),
        )
        settings_btn.pack(fill="x", padx=10, pady=(1, 18))
        self.buttons["settings"] = settings_btn

        self._highlight("dashboard")

    def _on_click(self, page_id):
        self._highlight(page_id)
        self.on_navigate(page_id)

    def _highlight(self, page_id):
        self.active_page = page_id
        for pid, btn in self.buttons.items():
            if pid == page_id:
                btn.configure(fg_color=SIDEBAR_ACTIVE, text_color="white")
            else:
                if pid in ("developer",):
                    btn.configure(fg_color="transparent", text_color="#777777")
                else:
                    btn.configure(fg_color="transparent", text_color="#bbbbbb")

    def set_active(self, page_id):
        self._highlight(page_id)
