"""Abstract base class for all page views."""
import customtkinter as ctk


class BasePage(ctk.CTkFrame):
    """Base class for all pages in the application."""

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app

    def on_show(self):
        """Called when the page is navigated to. Override to refresh data."""
        pass

    def on_hide(self):
        """Called when navigating away from this page."""
        pass
