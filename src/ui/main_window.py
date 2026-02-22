"""Main window with sidebar navigation, toolbar, and page container."""
import customtkinter as ctk
from src.ui.sidebar import Sidebar
from src.ui.widgets.status_bar import StatusBar
from src.utils.action_history import action_history


class MainWindow(ctk.CTkFrame):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app
        self.pages = {}
        self.current_page = None

        # Layout: sidebar | separator | content
        self.sidebar = Sidebar(self, on_navigate=self.navigate)
        self.sidebar.pack(side="left", fill="y")

        # Subtle vertical separator between sidebar and content
        import tkinter as tk
        sep = tk.Frame(self, width=1, bg="#1a1a30")
        sep.pack(side="left", fill="y")

        # Right side: toolbar + content + status bar
        right = ctk.CTkFrame(self, fg_color="#12121e", corner_radius=0)
        right.pack(side="left", fill="both", expand=True)

        # Toolbar with undo/redo - sleeker design
        self.toolbar = ctk.CTkFrame(right, height=40, fg_color="#14142a", corner_radius=0)
        self.toolbar.pack(fill="x", side="top")
        self.toolbar.pack_propagate(False)

        toolbar_inner = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        toolbar_inner.pack(fill="x", padx=14, pady=4)

        self.undo_btn = ctk.CTkButton(
            toolbar_inner, text="\u21b6 Undo", width=80, height=30,
            fg_color="#1e1e38", hover_color="#2a2a4a",
            font=ctk.CTkFont(size=11), corner_radius=6,
            state="disabled", command=self._undo,
            text_color="#8888aa",
        )
        self.undo_btn.pack(side="left", padx=(0, 4))

        self.redo_btn = ctk.CTkButton(
            toolbar_inner, text="\u21b7 Redo", width=80, height=30,
            fg_color="#1e1e38", hover_color="#2a2a4a",
            font=ctk.CTkFont(size=11), corner_radius=6,
            state="disabled", command=self._redo,
            text_color="#8888aa",
        )
        self.redo_btn.pack(side="left", padx=(0, 12))

        self.action_label = ctk.CTkLabel(
            toolbar_inner, text="",
            font=ctk.CTkFont(size=11), text_color="#666666",
        )
        self.action_label.pack(side="left")

        # Keyboard shortcuts
        parent.bind("<Control-z>", lambda e: self._undo())
        parent.bind("<Control-Z>", lambda e: self._undo())
        parent.bind("<Control-y>", lambda e: self._redo())
        parent.bind("<Control-Y>", lambda e: self._redo())

        # Listen for action history changes
        action_history.add_listener(self._update_undo_redo)

        self.content = ctk.CTkFrame(right, fg_color="transparent", corner_radius=0)
        self.content.pack(fill="both", expand=True)

        self.status_bar = StatusBar(right)
        self.status_bar.pack(fill="x", side="bottom")

    def _undo(self):
        desc = action_history.undo()
        if desc:
            self.action_label.configure(text=f"Undone: {desc}", text_color="#e94560")
            self.after(3000, lambda: self.action_label.configure(text=""))
            # Refresh current page
            if self.current_page and self.current_page in self.pages:
                page = self.pages[self.current_page]
                if hasattr(page, '_loaded'):
                    page._loaded = False
                page.on_show()

    def _redo(self):
        desc = action_history.redo()
        if desc:
            self.action_label.configure(text=f"Redone: {desc}", text_color="#2fa572")
            self.after(3000, lambda: self.action_label.configure(text=""))
            if self.current_page and self.current_page in self.pages:
                page = self.pages[self.current_page]
                if hasattr(page, '_loaded'):
                    page._loaded = False
                page.on_show()

    def _update_undo_redo(self):
        """Update undo/redo button states."""
        if action_history.can_undo():
            self.undo_btn.configure(state="normal")
        else:
            self.undo_btn.configure(state="disabled")

        if action_history.can_redo():
            self.redo_btn.configure(state="normal")
        else:
            self.redo_btn.configure(state="disabled")

    def register_page(self, page_id: str, page):
        """Register a page for navigation."""
        self.pages[page_id] = page
        page.place(in_=self.content, x=0, y=0, relwidth=1, relheight=1)
        page.lower()  # Hide initially

    def navigate(self, page_id: str):
        """Navigate to a page."""
        if page_id not in self.pages:
            return

        # Hide current page
        if self.current_page and self.current_page in self.pages:
            self.pages[self.current_page].lower()
            self.pages[self.current_page].on_hide()

        # Show new page
        self.current_page = page_id
        self.pages[page_id].lift()
        self.pages[page_id].on_show()
        self.sidebar.set_active(page_id)

    def update_status(self, text: str):
        self.status_bar.set_status(text)

    def update_stats(self, **kwargs):
        self.status_bar.set_stats(**kwargs)
