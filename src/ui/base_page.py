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
        # Full-page containers must be square-cornered. Rounded transparent
        # corners can render as visible corner dots on some systems.
        kwargs.setdefault("corner_radius", 0)
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app
        # Schedule patching of standalone scrollable widgets after build.
        # CTkScrollableFrame scrolling is handled globally by
        # ModManagerApp._global_fast_scroll (bind_all), so we only patch
        # tk.Listbox / tk.Text / tk.Canvas here to override their slower
        # class-level default scrolling.
        self.after(50, self._patch_all_scroll_speeds)

    def _patch_all_scroll_speeds(self):
        """Find and patch standalone scrollable widgets for faster scrolling.

        CTkScrollableFrame is intentionally SKIPPED — its scrolling is
        handled by the application-wide bind_all("<MouseWheel>") handler
        in ModManagerApp._global_fast_scroll.  Adding per-widget bindings
        on CTkScrollableFrame children that return ``"break"`` would block
        the bind_all handler from ever firing, completely breaking scroll.
        """
        self._recursive_patch_scroll(self)

    def _recursive_patch_scroll(self, widget):
        """Recursively patch scroll speed on standalone scrollable widgets.

        Skips CTkScrollableFrame subtrees entirely — those are handled
        by the global bind_all handler.  Patches tk.Listbox, tk.Canvas,
        and tk.Text widgets that live *outside* a CTkScrollableFrame.
        """
        # CTkScrollableFrame is fully handled by the global handler.
        # Do NOT add per-widget bindings on it or its children — a
        # handler that returns "break" blocks bind_all from firing.
        if isinstance(widget, ctk.CTkScrollableFrame):
            return

        if isinstance(widget, tk.Listbox):
            patch_listbox_scroll_speed(widget)
        elif isinstance(widget, tk.Text):
            _patch_text_scroll_speed(widget)
        elif isinstance(widget, tk.Canvas):
            try:
                if bool(getattr(widget, "_ssbum_skip_base_scroll_patch", False)):
                    pass
                else:
                    _patch_canvas_scroll_speed(widget)
            except Exception:
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

    def _present_modal_dialog(self, dialog, focus_widget=None, animate_open: bool = True):
        """Show a modal dialog with icon/focus applied before first paint."""
        try:
            dialog.transient(self.winfo_toplevel())
        except Exception:
            pass
        try:
            self.app.apply_window_icon(dialog)
        except Exception:
            pass
        try:
            dialog.update_idletasks()
        except Exception:
            pass

        fade_supported = False
        alpha_hidden = False
        if animate_open:
            try:
                dialog.attributes("-alpha", 0.0)
                fade_supported = True
                alpha_hidden = True
            except Exception:
                pass
        else:
            try:
                # Keep dialog invisible until one full draw pass finishes so
                # users never see half-rendered controls.
                dialog.attributes("-alpha", 0.0)
                alpha_hidden = True
            except Exception:
                pass

        try:
            dialog.deiconify()
            dialog.lift()
            dialog.update_idletasks()
        except Exception:
            pass
        try:
            # Force one full composition pass before showing fade frames.
            dialog.update()
        except Exception:
            pass

        if fade_supported:
            fade_values = (0.82, 0.94, 1.0)

            def _fade_step(index=0):
                try:
                    if not dialog.winfo_exists():
                        return
                except Exception:
                    return
                try:
                    dialog.attributes("-alpha", fade_values[index])
                except Exception:
                    return
                if index + 1 < len(fade_values):
                    try:
                        dialog.after(10, lambda: _fade_step(index + 1))
                    except Exception:
                        pass

            _fade_step(0)
        else:
            if alpha_hidden:
                try:
                    dialog.attributes("-alpha", 1.0)
                except Exception:
                    pass

        try:
            dialog.grab_set()
        except Exception:
            pass
        if focus_widget is not None:
            try:
                focus_widget.focus_set()
            except Exception:
                pass

    def on_show(self):
        """Called when the page is navigated to. Override to refresh data."""
        pass

    def on_hide(self):
        """Called when navigating away from this page."""
        pass
