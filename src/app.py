"""Main application class - wires all managers and UI together."""
import customtkinter as ctk
from pathlib import Path

from src.config import ConfigManager
from src.paths import auto_detect_sdmc, derive_mods_path, derive_plugins_path
from src.utils.hashing import load_param_labels
from src.utils.logger import logger
from src.utils.action_history import action_history
from src.utils.audio_player import audio_player

from src.core.prc_handler import PRCHandler
from src.core.msbt_handler import MSBTHandler
from src.core.css_manager import CSSManager
from src.core.mod_manager import ModManager
from src.core.plugin_manager import PluginManager
from src.core.music_manager import MusicManager
from src.core.conflict_detector import ConflictDetector
from src.core.conflict_resolver import ConflictResolver
from src.core.share_code import ShareCodeManager
from src.models.mod import ModStatus
from src.models.plugin import PluginStatus

from src.ui.main_window import MainWindow
from src.ui.pages.dashboard_page import DashboardPage
from src.ui.pages.mods_page import ModsPage
from src.ui.pages.plugins_page import PluginsPage
from src.ui.pages.css_page import CSSPage
from src.ui.pages.music_page import MusicPage
from src.ui.pages.conflicts_page import ConflictsPage
from src.ui.pages.share_page import SharePage
from src.ui.pages.settings_page import SettingsPage
from src.ui.pages.developer_page import DeveloperPage


class ModManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SSBU Mod Manager")
        self.geometry("1400x900")
        self.minsize(1050, 650)

        # Shutdown flag for background threads
        self._shutting_down = False
        self._resize_after_id = None
        self._last_width = 0
        self._last_height = 0
        self._resize_overlay = None

        # Initialize customtkinter
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # Set window icon
        try:
            from src.utils.resource_path import resource_path
            icon_path = resource_path("assets/icon.ico")
            if Path(icon_path).exists():
                self.iconbitmap(icon_path)
        except Exception:
            pass

        # Load param labels
        if not load_param_labels():
            from tkinter import messagebox
            messagebox.showwarning("Warning",
                "ParamLabels.csv not found. Hash resolution will be limited.")

        # Initialize config
        self.config_manager = ConfigManager()
        settings = self.config_manager.load()

        # Initialize logger
        logger.enabled = settings.debug_mode

        # Initialize action history
        self.action_history = action_history

        # Auto-detect emulator path if configured and not set
        if settings.auto_detect_eden and not settings.eden_sdmc_path:
            detected = auto_detect_sdmc(settings.emulator)
            if detected:
                settings.eden_sdmc_path = detected
                settings.mods_path = derive_mods_path(detected)
                settings.plugins_path = derive_plugins_path(detected)
                self.config_manager.save(settings)
                logger.info("App", f"Auto-detected emulator path: {detected}")

        # Initialize core handlers
        self.prc_handler = PRCHandler()
        self.msbt_handler = MSBTHandler()

        # Initialize managers
        self.css_manager = CSSManager(self.prc_handler, self.msbt_handler)
        self.mod_manager = ModManager(
            settings.mods_path or Path("."),
            settings.mod_disable_method,
        )
        self.plugin_manager = PluginManager(settings.plugins_path or Path("."))
        self.music_manager = MusicManager()
        self.conflict_detector = ConflictDetector()
        self.conflict_resolver = ConflictResolver(settings.mods_path or Path("."))
        self.share_manager = ShareCodeManager()

        logger.info("App", "All managers initialized")

        # Build UI
        self.main_window = MainWindow(self, self)
        self.main_window.pack(fill="both", expand=True)

        # Create and register pages
        self._create_pages()

        # Navigate to dashboard
        self.navigate("dashboard")

        # Update status bar
        self._update_status()

        # Handle window close properly
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Resize debounce for smoother resizing
        self.bind("<Configure>", self._on_configure)

        logger.info("App", "Application startup complete")

    def _on_configure(self, event):
        """Hide content during resize to prevent visual glitching."""
        if event.widget != self or self._shutting_down:
            return

        w, h = event.width, event.height
        if w == self._last_width and h == self._last_height:
            return
        self._last_width = w
        self._last_height = h

        # Show a solid overlay to hide the re-layout
        if self._resize_overlay is None:
            import tkinter as tk
            self._resize_overlay = tk.Frame(self, bg="#1a1a2e")
        self._resize_overlay.place(x=0, y=0, relwidth=1, relheight=1)
        self._resize_overlay.lift()

        if self._resize_after_id:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(80, self._finalize_resize)

    def _finalize_resize(self):
        """Remove overlay after resize settles."""
        self._resize_after_id = None
        try:
            self.update_idletasks()
            if self._resize_overlay:
                self._resize_overlay.place_forget()
        except Exception:
            pass

    def _on_close(self):
        """Clean shutdown - stop threads and audio before destroying window."""
        self._shutting_down = True
        logger.info("App", "Shutting down...")

        # Stop audio playback
        try:
            audio_player.cleanup()
        except Exception:
            pass

        # Clear action history
        try:
            action_history.clear()
        except Exception:
            pass

        # Cancel any pending after() callbacks
        try:
            if self._resize_after_id:
                self.after_cancel(self._resize_after_id)
        except Exception:
            pass

        # Destroy the window
        try:
            self.quit()
            self.destroy()
        except Exception:
            pass

    @property
    def shutting_down(self) -> bool:
        return self._shutting_down

    def _create_pages(self):
        pages = {
            "dashboard": DashboardPage(self.main_window.content, self),
            "mods": ModsPage(self.main_window.content, self),
            "plugins": PluginsPage(self.main_window.content, self),
            "css": CSSPage(self.main_window.content, self),
            "music": MusicPage(self.main_window.content, self),
            "conflicts": ConflictsPage(self.main_window.content, self),
            "share": SharePage(self.main_window.content, self),
            "settings": SettingsPage(self.main_window.content, self),
            "developer": DeveloperPage(self.main_window.content, self),
        }

        for page_id, page in pages.items():
            self.main_window.register_page(page_id, page)

    def navigate(self, page_id: str):
        """Navigate to a page."""
        if self._shutting_down:
            return
        logger.info("App", f"Navigate to: {page_id}")
        self.main_window.navigate(page_id)

    def _update_managers(self):
        """Update manager paths after settings change."""
        settings = self.config_manager.settings
        self.mod_manager = ModManager(
            settings.mods_path or Path("."),
            settings.mod_disable_method,
        )
        self.plugin_manager = PluginManager(settings.plugins_path or Path("."))
        self.conflict_resolver = ConflictResolver(settings.mods_path or Path("."))
        self._update_status()
        logger.info("App", "Managers updated with new paths")

    def _update_status(self):
        """Update the status bar with current stats."""
        settings = self.config_manager.settings
        try:
            mods = 0
            plugins = 0
            if settings.mods_path and settings.mods_path.exists():
                mod_list = self.mod_manager.list_mods()
                mods = sum(1 for m in mod_list if m.status == ModStatus.ENABLED)
            if settings.plugins_path and settings.plugins_path.exists():
                plugin_list = self.plugin_manager.list_plugins()
                plugins = sum(1 for p in plugin_list if p.status == PluginStatus.ENABLED)

            emu_name = settings.emulator or "Emulator"
            if settings.eden_sdmc_path:
                self.main_window.update_status(f"{emu_name}: {settings.eden_sdmc_path}")
            else:
                self.main_window.update_status("Emulator not configured")

            self.main_window.update_stats(mods=mods, plugins=plugins)
        except Exception:
            self.main_window.update_status("Ready")
