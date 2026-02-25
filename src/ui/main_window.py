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
        self._shown_pages = set()
        self._render_settle_after_id = None
        self._render_settle_page_id = None
        self._nav_token = 0
        self._nav_overlay_after_id = None

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

        # Keyboard shortcuts — skip when focus is in a text input widget
        # so Ctrl+Z/Y/S perform their native text-editing functions instead.
        def _skip_if_text(func):
            def wrapper(event):
                try:
                    wc = event.widget.winfo_class()
                    if wc in ("Entry", "Text", "TEntry", "Spinbox", "TSpinbox"):
                        return  # let native text undo/redo/save handle it
                except Exception:
                    pass
                return func()
            return wrapper
        parent.bind("<Control-z>", _skip_if_text(self._undo))
        parent.bind("<Control-Z>", _skip_if_text(self._undo))
        parent.bind("<Control-y>", _skip_if_text(self._redo))
        parent.bind("<Control-Y>", _skip_if_text(self._redo))
        parent.bind("<Control-s>", _skip_if_text(self._save))
        parent.bind("<Control-S>", _skip_if_text(self._save))

        # Listen for action history changes
        action_history.add_listener(self._update_undo_redo)
        # Listen for unsaved changes
        self._unsaved_listener_id = None

        self.content = ctk.CTkFrame(right, fg_color="#12121e", corner_radius=0)
        self.content.pack(fill="both", expand=True)
        self._nav_overlay = ctk.CTkFrame(self.content, fg_color="#12121e", corner_radius=0)
        self._nav_overlay_label = ctk.CTkLabel(
            self._nav_overlay,
            text="Loading...",
            font=ctk.CTkFont(size=13),
            text_color="#6a6a8a",
        )
        self._nav_overlay_label.place(relx=0.5, rely=0.5, anchor="center")

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
        # Keep lazily created pages unmapped until first navigation so hidden
        # pages do not participate in every resize/reflow.
        page.place(in_=self.content, x=0, y=0, relwidth=1, relheight=1)
        page.lower()
        page.place_forget()

    def _map_page(self, page):
        """Place a page into the content region if not already mapped."""
        try:
            if not page.winfo_manager():
                page.place(in_=self.content, x=0, y=0, relwidth=1, relheight=1)
        except Exception:
            try:
                page.place(in_=self.content, x=0, y=0, relwidth=1, relheight=1)
            except Exception:
                pass

    def prime_page_layout(self, page_id: str):
        """Prime widget layout for a hidden page without running page data loads."""
        page = self.pages.get(page_id)
        if page is None:
            return
        self._map_page(page)
        page.lower()
        try:
            page.update_idletasks()
            self.content.update_idletasks()
        except Exception:
            pass
        try:
            page.place_forget()
        except Exception:
            pass

    def navigate(self, page_id: str):
        """Navigate to a page."""
        if page_id not in self.pages:
            return
        if page_id == self.current_page:
            return
        self._nav_token += 1
        token = self._nav_token
        self._show_navigation_overlay()
        self.after(0, lambda pid=page_id, t=token: self._complete_navigation(pid, t))

    def navigate_immediate(self, page_id: str):
        """Navigate synchronously without delayed overlay transitions."""
        if page_id not in self.pages:
            return
        if page_id == self.current_page:
            return
        self._nav_token += 1
        token = self._nav_token
        try:
            if self._nav_overlay_after_id:
                self.after_cancel(self._nav_overlay_after_id)
                self._nav_overlay_after_id = None
        except Exception:
            pass
        self._complete_navigation(page_id, token, overlay_delay_ms=0)

    def _complete_navigation(self, page_id: str, token: int, overlay_delay_ms: int = 36):
        if token != self._nav_token:
            return
        prev_page = self.pages.get(self.current_page) if self.current_page else None
        page = self.pages[page_id]
        first_visit = page_id not in self._shown_pages
        self._map_page(page)
        try:
            page.lower()
        except Exception:
            pass
        try:
            page.on_show()
            page.update_idletasks()
            self.content.update_idletasks()
            if first_visit:
                page.update_idletasks()
                self.content.update_idletasks()
        except Exception:
            pass

        if prev_page is not None:
            try:
                prev_page.on_hide()
            except Exception:
                pass

        self.current_page = page_id
        self._shown_pages.add(page_id)
        try:
            page.lift()
        except Exception:
            pass
        try:
            page.update_idletasks()
            self.content.update_idletasks()
        except Exception:
            pass
        if prev_page is not None and prev_page is not page:
            try:
                prev_page.place_forget()
            except Exception:
                pass
        page.focus_set()
        if hasattr(page, '_patch_all_scroll_speeds'):
            page.after(150, page._patch_all_scroll_speeds)
        self._schedule_render_settle(page_id)
        self.sidebar.set_active(page_id)
        self._hide_navigation_overlay(token, delay_ms=overlay_delay_ms)

    def _show_navigation_overlay(self):
        try:
            if self._nav_overlay_after_id:
                self.after_cancel(self._nav_overlay_after_id)
                self._nav_overlay_after_id = None
        except Exception:
            pass
        try:
            self._nav_overlay.place(in_=self.content, x=0, y=0, relwidth=1, relheight=1)
            self._nav_overlay.lift()
            self._nav_overlay.update_idletasks()
        except Exception:
            pass

    def _hide_navigation_overlay(self, token: int, delay_ms: int = 36):
        def _clear():
            self._nav_overlay_after_id = None
            if token != self._nav_token:
                return
            try:
                self._nav_overlay.place_forget()
            except Exception:
                pass

        try:
            if self._nav_overlay_after_id:
                self.after_cancel(self._nav_overlay_after_id)
        except Exception:
            pass
        if int(delay_ms) <= 0:
            _clear()
            return
        self._nav_overlay_after_id = self.after(int(delay_ms), _clear)

    def _schedule_render_settle(self, page_id: str):
        """Run a delayed idle/layout settle pass for the visible page."""
        self._render_settle_page_id = page_id
        if self._render_settle_after_id:
            try:
                self.after_cancel(self._render_settle_after_id)
            except Exception:
                pass
            self._render_settle_after_id = None

        def _settle():
            self._render_settle_after_id = None
            if self.current_page != self._render_settle_page_id:
                return
            page = self.pages.get(self.current_page)
            if page is None:
                return
            try:
                page.update_idletasks()
                self.content.update_idletasks()
                page.after_idle(page.update_idletasks)
            except Exception:
                pass

        self._render_settle_after_id = self.after(18, _settle)

    def update_status(self, text: str):
        self.status_bar.set_status(text)

    def update_stats(self, **kwargs):
        self.status_bar.set_stats(**kwargs)
