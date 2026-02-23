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
        self.sidebar = Sidebar(self, on_navigate=app.navigate)
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

        # Separator between undo/redo and save/discard
        sep_label = ctk.CTkLabel(toolbar_inner, text="|", text_color="#333355",
                                 font=ctk.CTkFont(size=14))
        sep_label.pack(side="left", padx=(0, 12))

        # Action label (between undo/redo and save/discard)
        self.action_label = ctk.CTkLabel(
            toolbar_inner, text="",
            font=ctk.CTkFont(size=11), text_color="#666666",
        )
        self.action_label.pack(side="left")

        # Save & Discard buttons — right-aligned
        self.save_btn = ctk.CTkButton(
            toolbar_inner, text="\u2713 Save", width=80, height=30,
            fg_color="#27ae60", hover_color="#2ecc71",
            font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6,
            state="disabled", command=self._save,
            text_color="#ffffff",
        )
        self.save_btn.pack(side="right", padx=(4, 0))

        self.discard_btn = ctk.CTkButton(
            toolbar_inner, text="\u2716 Discard", width=90, height=30,
            fg_color="#555570", hover_color="#666688",
            font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6,
            state="disabled", command=self._discard,
            text_color="#ffffff",
        )
        self.discard_btn.pack(side="right", padx=(0, 4))

        # Keyboard shortcuts
        parent.bind("<Control-z>", lambda e: self._undo())
        parent.bind("<Control-Z>", lambda e: self._undo())
        parent.bind("<Control-y>", lambda e: self._redo())
        parent.bind("<Control-Y>", lambda e: self._redo())
        parent.bind("<Control-s>", lambda e: self._save())
        parent.bind("<Control-S>", lambda e: self._save())

        # Listen for action history changes
        action_history.add_listener(self._update_undo_redo)
        # Listen for unsaved changes
        self._unsaved_listener_id = None

        self.content = ctk.CTkFrame(right, fg_color="transparent", corner_radius=0)
        self.content.pack(fill="both", expand=True)

        self.status_bar = StatusBar(right)
        self.status_bar.pack(fill="x", side="bottom")

    def _safe_after(self, ms, callback):
        """Schedule a callback, catching TclError if widget is destroyed."""
        try:
            self.after(ms, callback)
        except Exception:
            pass

    def _undo(self):
        try:
            desc = action_history.undo()
        except Exception as e:
            self.action_label.configure(text=f"Undo failed: {e}", text_color="#e94560")
            self._safe_after(3000, lambda: self.action_label.configure(text=""))
            return
        if desc:
            self.action_label.configure(text=f"Undone: {desc}", text_color="#e94560")
            self._safe_after(3000, lambda: self.action_label.configure(text=""))
            # Refresh current page
            if self.current_page and self.current_page in self.pages:
                page = self.pages[self.current_page]
                if hasattr(page, '_loaded'):
                    page._loaded = False
                page.on_show()

    def _redo(self):
        try:
            desc = action_history.redo()
        except Exception as e:
            self.action_label.configure(text=f"Redo failed: {e}", text_color="#e94560")
            self._safe_after(3000, lambda: self.action_label.configure(text=""))
            return
        if desc:
            self.action_label.configure(text=f"Redone: {desc}", text_color="#2fa572")
            self._safe_after(3000, lambda: self.action_label.configure(text=""))
            if self.current_page and self.current_page in self.pages:
                page = self.pages[self.current_page]
                if hasattr(page, '_loaded'):
                    page._loaded = False
                page.on_show()

    def _save(self):
        """Invoke save on the current page (if it has unsaved changes)."""
        if not self.app._has_unsaved_changes:
            return
        # Try current page first
        if self.current_page and self.current_page in self.pages:
            page = self.pages[self.current_page]
            if hasattr(page, 'save_changes') and callable(page.save_changes):
                page.save_changes()
                self.update_save_discard()
                return
        # Fallback: try all pages that have unsaved changes
        for page_id, page in self.pages.items():
            if hasattr(page, 'save_changes') and callable(page.save_changes):
                page.save_changes()
                self.update_save_discard()
                return

    def _discard(self):
        """Discard unsaved changes by reloading the current page."""
        from tkinter import messagebox
        confirm = messagebox.askyesno(
            "Discard Changes",
            "Discard all unsaved changes?")
        if not confirm:
            return
        self.app.mark_saved()
        self.update_save_discard()
        # Reload current page
        if self.current_page and self.current_page in self.pages:
            page = self.pages[self.current_page]
            if hasattr(page, '_loaded'):
                page._loaded = False
            page.on_show()
        self.action_label.configure(text="Changes discarded", text_color="#e94560")
        self._safe_after(3000, lambda: self.action_label.configure(text=""))

    def update_save_discard(self):
        """Update save/discard button states based on unsaved changes."""
        self._safe_after(0, self._update_save_discard_impl)

    def _update_save_discard_impl(self):
        try:
            if self.app._has_unsaved_changes:
                self.save_btn.configure(state="normal",
                                        fg_color="#27ae60",
                                        text_color="#ffffff")
                self.discard_btn.configure(state="normal",
                                           fg_color="#555570",
                                           text_color="#ffffff")
            else:
                self.save_btn.configure(state="disabled",
                                        fg_color="#1a2a1e",
                                        text_color="#3a5a3a")
                self.discard_btn.configure(state="disabled",
                                           fg_color="#2a2a38",
                                           text_color="#4a4a5a")
        except Exception:
            pass

    def _update_undo_redo(self):
        """Update undo/redo button states (thread-safe)."""
        self._safe_after(0, self._update_undo_redo_impl)

    def _update_undo_redo_impl(self):
        """Actually update undo/redo button states on the main thread."""
        try:
            if action_history.can_undo():
                self.undo_btn.configure(state="normal")
            else:
                self.undo_btn.configure(state="disabled")

            if action_history.can_redo():
                self.redo_btn.configure(state="normal")
            else:
                self.redo_btn.configure(state="disabled")
        except Exception:
            pass

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
        page = self.pages[page_id]
        page.lift()
        page.on_show()
        # Set focus on the page so the user doesn't have to click it
        # after selecting a sidebar item.
        page.focus_set()
        # Re-patch scroll speeds after page content may have changed
        if hasattr(page, '_patch_all_scroll_speeds'):
            page.after(150, page._patch_all_scroll_speeds)
        self.sidebar.set_active(page_id)

    def update_status(self, text: str):
        self.status_bar.set_status(text)

    def update_stats(self, **kwargs):
        self.status_bar.set_stats(**kwargs)
