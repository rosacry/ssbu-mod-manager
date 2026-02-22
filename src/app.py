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
from src.ui.pages.migration_page import MigrationPage
from src.ui.pages.online_compat_page import OnlineCompatPage


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
        self._is_maximized = False
        self._zoom_indicator_id = None

        # Initialize customtkinter
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # Set consistent dark background
        self.configure(fg_color="#0e0e1a")

        # Set window icon
        try:
            from src.utils.resource_path import resource_path
            icon_path = resource_path("assets/icon.ico")
            if Path(icon_path).exists():
                self.iconbitmap(icon_path)
                logger.info("App", f"Window icon loaded from {icon_path}")
            else:
                logger.warn("App", f"Icon file not found: {icon_path}")
        except Exception as e:
            logger.warn("App", f"Failed to set window icon: {e}")

        # Load param labels in background to avoid blocking startup
        import threading
        def _load_labels_bg():
            if not load_param_labels():
                logger.warn("App", "ParamLabels.csv not found. Hash resolution will be limited.")
            else:
                logger.info("App", "ParamLabels.csv loaded successfully")
        threading.Thread(target=_load_labels_bg, daemon=True).start()

        # Initialize config
        self.config_manager = ConfigManager()
        settings = self.config_manager.load()

        # Initialize logger (INFO always logged, DEBUG needs dev mode)
        logger.enabled = settings.debug_mode
        logger.info("App", "SSBU Mod Manager starting up...")
        logger.info("App", f"Config loaded - debug_mode={settings.debug_mode}")

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

        # Lazy page registry - pages are created on first navigation
        self._page_classes = {}
        self._register_page_classes()

        # Navigate to dashboard (creates only the dashboard page)
        self.navigate("dashboard")

        # Update status bar in background
        self.after(100, self._update_status)

        # Handle window close properly
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Resize debounce for smoother resizing
        self.bind("<Configure>", self._on_configure)

        # Zoom / scaling keybindings (Ctrl+Plus, Ctrl+Minus, Ctrl+0)
        self._current_scale = settings.ui_scale
        self._apply_scale(self._current_scale, save=False)
        # Bind multiple key combinations for zoom to ensure cross-platform reliability
        self.bind("<Control-plus>", lambda e: self._zoom_in())
        self.bind("<Control-equal>", lambda e: self._zoom_in())     # Ctrl+= (unshifted +)
        self.bind("<Control-minus>", lambda e: self._zoom_out())
        self.bind("<Control-0>", lambda e: self._zoom_reset())
        # Windows-specific: also bind KeyPress with keysym check for reliability
        self.bind("<Control-Key-=>", lambda e: self._zoom_in())
        self.bind("<Control-Key-minus>", lambda e: self._zoom_out())
        self.bind("<Control-Key-0>", lambda e: self._zoom_reset())
        # Numpad keys
        self.bind("<Control-KP_Add>", lambda e: self._zoom_in())
        self.bind("<Control-KP_Subtract>", lambda e: self._zoom_out())
        self.bind("<Control-KP_0>", lambda e: self._zoom_reset())
        # Fallback: low-level key handler for Windows where keysyms may mismatch
        self.bind_all("<KeyPress>", self._on_keypress_zoom)

        logger.info("App", "Application startup complete")

    def _apply_scale(self, scale: float, save: bool = True):
        """Apply UI scaling factor and optionally persist it."""
        self._current_scale = scale
        ctk.set_widget_scaling(scale)
        if save:
            settings = self.config_manager.settings
            settings.ui_scale = scale
            self.config_manager.save(settings)
        logger.info("App", f"UI scale set to {int(scale * 100)}%")
        # Show brief zoom indicator in status bar
        if hasattr(self, "main_window"):
            self.main_window.update_status(f"Zoom: {int(scale * 100)}%")
            if hasattr(self.main_window, "status_bar"):
                self.main_window.status_bar.set_zoom(int(scale * 100))
            # Clear the status message after a short delay
            if self._zoom_indicator_id:
                self.after_cancel(self._zoom_indicator_id)
            self._zoom_indicator_id = self.after(2000, self._update_status)

    def _zoom_in(self):
        """Increase UI scale by 10%, max 200%."""
        new_scale = min(2.0, round(self._current_scale + 0.1, 1))
        if new_scale != self._current_scale:
            self._apply_scale(new_scale)

    def _zoom_out(self):
        """Decrease UI scale by 10%, min 60%."""
        new_scale = max(0.6, round(self._current_scale - 0.1, 1))
        if new_scale != self._current_scale:
            self._apply_scale(new_scale)

    def _zoom_reset(self):
        """Reset UI scale to 100%."""
        if self._current_scale != 1.0:
            self._apply_scale(1.0)

    def _on_keypress_zoom(self, event):
        """Low-level key handler for zoom shortcuts on Windows."""
        # Check if Ctrl is held (state bit 0x4 on Windows)
        if not (event.state & 0x4):
            return
        # Avoid double-handling if explicit bindings already caught it
        char = event.char
        keysym = event.keysym
        if char == '+' or char == '=' or keysym in ('plus', 'equal', 'KP_Add'):
            self._zoom_in()
            return "break"
        elif char == '-' or keysym in ('minus', 'KP_Subtract'):
            self._zoom_out()
            return "break"
        elif char == '0' or keysym in ('0', 'KP_0'):
            self._zoom_reset()
            return "break"

    def _on_configure(self, event):
        """Handle window resize events smoothly."""
        if event.widget != self or self._shutting_down:
            return

        w, h = event.width, event.height
        if w == self._last_width and h == self._last_height:
            return

        # Detect maximize/restore (large instant change)
        is_state_change = (
            abs(w - self._last_width) > 100 or abs(h - self._last_height) > 100
        )

        self._last_width = w
        self._last_height = h

        if is_state_change:
            # For maximize/restore, just force immediate relayout
            if self._resize_after_id:
                self.after_cancel(self._resize_after_id)
                self._resize_after_id = None
            self.update_idletasks()
        else:
            # For drag resize, debounce the relayout
            if self._resize_after_id:
                self.after_cancel(self._resize_after_id)
            try:
                self._resize_after_id = self.after(16, self._finalize_resize)
            except Exception:
                pass

    def _finalize_resize(self):
        """Finalize layout after resize settles."""
        self._resize_after_id = None
        try:
            self.update_idletasks()
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
        try:
            if self._zoom_indicator_id:
                self.after_cancel(self._zoom_indicator_id)
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

    def _register_page_classes(self):
        """Register page classes for lazy instantiation."""
        self._page_classes = {
            "dashboard": DashboardPage,
            "mods": ModsPage,
            "plugins": PluginsPage,
            "css": CSSPage,
            "music": MusicPage,
            "conflicts": ConflictsPage,
            "share": SharePage,
            "migration": MigrationPage,
            "online_compat": OnlineCompatPage,
            "settings": SettingsPage,
            "developer": DeveloperPage,
        }

    def navigate(self, page_id: str):
        """Navigate to a page, creating it lazily if needed."""
        if self._shutting_down:
            return
        # Lazy page creation
        if page_id not in self.main_window.pages and page_id in self._page_classes:
            page_class = self._page_classes[page_id]
            page = page_class(self.main_window.content, self)
            self.main_window.register_page(page_id, page)
            logger.info("App", f"Created page: {page_id}")
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
        except Exception as e:
            logger.warn("App", f"Status bar update failed: {e}")
            self.main_window.update_status("Ready")
