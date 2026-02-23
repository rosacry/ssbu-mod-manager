"""Abstract base class for all page views."""
import customtkinter as ctk
import tkinter as tk


# Scroll speed multiplier (higher = faster scrolling)
SCROLL_SPEED = 5


def _patch_scrollable_frame_speed(frame: ctk.CTkScrollableFrame, speed: int = SCROLL_SPEED):
    """Patch a CTkScrollableFrame to scroll faster.

    CustomTkinter's default scroll is 1 unit per mouse tick, which is too slow.
    This patches the internal canvas to scroll `speed` units per tick instead.
    Also binds all child widgets so scrolling works regardless of mouse position.
    """
    try:
        canvas = frame._parent_canvas
        def _fast_scroll(event):
            try:
                canvas.yview_scroll(int(-speed * (event.delta / 120)), "units")
            except tk.TclError:
                pass
            return "break"
        canvas.bind("<MouseWheel>", _fast_scroll)
        # Also bind to frame itself and its interior
        frame.bind("<MouseWheel>", _fast_scroll)
        if hasattr(frame, '_scrollbar'):
            frame._scrollbar.bind("<MouseWheel>", _fast_scroll)
        # Bind all children so scroll works when hovering any child widget
        def _bind_children(widget):
            try:
                widget.bind("<MouseWheel>", _fast_scroll)
                for child in widget.winfo_children():
                    _bind_children(child)
            except Exception:
                pass
        _bind_children(frame)
    except (AttributeError, tk.TclError):
        pass


def patch_listbox_scroll_speed(listbox: tk.Listbox, speed: int = SCROLL_SPEED):
    """Patch a tk.Listbox to scroll faster."""
    def _fast_scroll(event):
        try:
            listbox.yview_scroll(int(-speed * (event.delta / 120)), "units")
        except tk.TclError:
            pass
        return "break"
    listbox.bind("<MouseWheel>", _fast_scroll)


def _patch_canvas_scroll_speed(canvas: tk.Canvas, speed: int = SCROLL_SPEED):
    """Patch a tk.Canvas to scroll faster."""
    def _fast_scroll(event):
        try:
            canvas.yview_scroll(int(-speed * (event.delta / 120)), "units")
        except tk.TclError:
            pass
        return "break"
    canvas.bind("<MouseWheel>", _fast_scroll)


def _patch_text_scroll_speed(text_widget: tk.Text, speed: int = SCROLL_SPEED):
    """Patch a tk.Text to scroll faster."""
    def _fast_scroll(event):
        try:
            text_widget.yview_scroll(int(-speed * (event.delta / 120)), "units")
        except tk.TclError:
            pass
        return "break"
    text_widget.bind("<MouseWheel>", _fast_scroll)


class BasePage(ctk.CTkFrame):
    """Base class for all pages in the application."""

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app
        # Schedule patching of all scrollable frames after build
        self.after(50, self._patch_all_scroll_speeds)

    def _patch_all_scroll_speeds(self):
        """Find and patch all scrollable widgets for faster scrolling."""
        self._recursive_patch_scroll(self)

    def _recursive_patch_scroll(self, widget):
        """Recursively patch scroll speed on all scrollable widgets.

        Handles CTkScrollableFrame, tk.Listbox, tk.Canvas, tk.Text,
        and PanedWindow children (which winfo_children() does not
        normally traverse).
        """
        if isinstance(widget, ctk.CTkScrollableFrame):
            _patch_scrollable_frame_speed(widget)
        elif isinstance(widget, tk.Listbox):
            patch_listbox_scroll_speed(widget)
        elif isinstance(widget, tk.Text):
            _patch_text_scroll_speed(widget)
        elif isinstance(widget, tk.Canvas):
            _patch_canvas_scroll_speed(widget)

        # PanedWindow.winfo_children() may not include panes added
        # via .add(); explicitly iterate panes as well.
        if isinstance(widget, tk.PanedWindow):
            try:
                for pane_id in widget.panes():
                    try:
                        pane_widget = widget.nametowidget(pane_id)
                        self._recursive_patch_scroll(pane_widget)
                    except (KeyError, tk.TclError):
                        pass
            except (AttributeError, tk.TclError):
                pass

        try:
            for child in widget.winfo_children():
                self._recursive_patch_scroll(child)
        except Exception:
            pass

    def on_show(self):
        """Called when the page is navigated to. Override to refresh data.
        Re-patches scroll speeds to catch any dynamically created widgets."""
        self.after(100, self._patch_all_scroll_speeds)

    def on_hide(self):
        """Called when navigating away from this page."""
        pass
