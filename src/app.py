"""Main application class - wires all managers and UI together."""
import customtkinter as ctk
import importlib
import re
import threading
import time
from pathlib import Path
from tkinter import PhotoImage, messagebox

from src.config import ConfigManager
from src.paths import auto_detect_sdmc, derive_mods_path, derive_plugins_path
from src.utils.hashing import load_param_labels
from src.utils.logger import logger
from src.utils.action_history import action_history
from src.utils.audio_player import audio_player

from src.core.mod_manager import ModManager
from src.core.plugin_manager import PluginManager
from src.core.conflict_resolver import ConflictResolver
from src.models.mod import ModStatus
from src.models.plugin import PluginStatus

from src.ui.main_window import MainWindow


class ModManagerApp(ctk.CTk):
    # Base dimensions (at 100% scale)
    _BASE_WIDTH = 1480
    _BASE_HEIGHT = 940
    _MIN_WIDTH = 1100
    _MIN_HEIGHT = 680
    # "100%" should match the old 120% visual density.
    _DEFAULT_VISUAL_SCALE = 1.2
    _MIN_SCALE = 0.6
    _MAX_SCALE = 2.0
    _ZOOM_APPLY_DEBOUNCE_MS = 220
    _ZOOM_LAYOUT_SETTLE_DEBOUNCE_MS = 340
    _ZOOM_PERSIST_DEBOUNCE_MS = 850
    _RESIZE_SETTLE_MS = 84
    _DRAG_REDRAW_INTERVAL_MS = 10
    _SCROLL_REFRESH_INTERVAL_MS = 10
    _DRAG_FORCE_UPDATE_EVERY_TICKS = 1
    _WINDOW_FADE_STEP_MS = 15
    _WINDOW_FADE_IN_MS = 120
    _WINDOW_FADE_OUT_MS = 120
    _ENABLE_WINDOW_FADE = False
    _PAGE_WARMUP_INITIAL_DELAY_MS = 2600
    _PAGE_WARMUP_STEP_DELAY_MS = 260
    _PAGE_WARMUP_IDLE_REQUIRED_MS = 1600
    _PAGE_WARMUP_RETRY_DELAY_MS = 320
    _PAGE_WARMUP_PAGE_IDS = ()
    _STARTUP_PREWARM_PAGE_IDS = (
    )
    _STARTUP_PREWARM_ON_SHOW_PAGE_IDS = (
    )

    def __init__(self):
        import sys as _sys
        def _dbg(msg):
            try:
                _sys.stderr.write(f"[INIT] {msg}\n")
                _sys.stderr.flush()
            except Exception:
                pass

        # CustomTkinter's Windows header manipulation temporarily withdraws/
        # re-shows windows. For the main app window this can cause a visible
        # top-left flash before final centering.
        try:
            if _sys.platform.startswith("win"):
                from customtkinter.windows import ctk_tk as _ctk_tk
                _ctk_tk.CTk._deactivate_windows_window_header_manipulation = True
        except Exception:
            pass

        _dbg("super().__init__() ...")
        super().__init__()
        _dbg("super().__init__() OK")

        # Keep the window hidden until startup is complete so users never
        # see intermediate layout states. Prefer withdraw as the primary
        # strategy to prevent any visible top-left startup flash.
        self._startup_hidden_withdraw = False
        self._startup_hidden_alpha = False
        try:
            self.withdraw()
            self._startup_hidden_withdraw = True
        except Exception:
            try:
                self.attributes("-alpha", 0.0)
                self._startup_hidden_alpha = True
            except Exception:
                pass

        self.title("SSBU Mod Manager")

        # Apply a base geometry immediately; final scaled size/position
        # is set before the window is shown.
        self.geometry(f"{self._BASE_WIDTH}x{self._BASE_HEIGHT}")
        self.minsize(self._MIN_WIDTH, self._MIN_HEIGHT)

        # Shutdown flag for background threads
        self._shutting_down = False
        self._has_unsaved_changes = False
        self._resize_after_id = None
        self._last_width = 0
        self._last_height = 0
        self._is_maximized = False
        self._zoom_indicator_id = None
        self._zoom_apply_after_id = None
        self._zoom_persist_after_id = None
        self._pending_scale_apply = None
        self._pending_scale_save = None
        self._scroll_debug_keys = set()
        self._scroll_refresh_after_id = None
        self._scroll_refresh_widgets = set()
        self._scroll_refresh_full_counter = 0
        self._scroll_refresh_drag_counter = 0
        self._drag_refresh_after_id = None
        self._drag_redraw_counter = 0
        self._scrollbar_drag_active = False
        self._active_drag_scroll_widget = None
        self._pointer_left_down = False
        self._suppress_scroll_refresh_until = 0.0
        self._last_window_activity_size = (0, 0)
        self._last_user_activity_monotonic = time.monotonic()
        self._last_scale_apply_monotonic = 0.0
        self._last_zoom_input_monotonic = 0.0
        self._last_drag_widget_refresh_monotonic = 0.0
        self._page_warmup_after_id = None
        self._page_warmup_queue = []
        self._icon_bitmap_path = None
        self._app_icon_photo = None
        self._window_fade_after_id = None
        self._startup_nav_after_id = None
        self._scale_layout_settle_after_id = None
        self._zoom_overlay = None
        self._zoom_overlay_label = None
        self._status_refresh_generation = 0
        self._status_refresh_thread_active = False
        self._status_refresh_pending = False

        # Initialize customtkinter
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # Set consistent dark background
        self.configure(fg_color="#0e0e1a")

        # Patch CTkScrollbar drag behavior so grabbing the thumb doesn't
        # jump/recenter to the cursor position on first movement.
        try:
            self._patch_ctk_scrollbar_drag_behavior()
        except Exception as e:
            logger.warn("App", f"Failed to patch CTk scrollbar drag behavior: {e}")

        # Set window/icon assets. Use iconbitmap for Windows shell integration
        # and iconphoto as a fallback for titlebar/toplevel consistency.
        try:
            from src.utils.resource_path import resource_path
            icon_path = resource_path("assets/icon.ico")
            loaded_any = False
            if Path(icon_path).exists():
                self._icon_bitmap_path = str(icon_path)
                try:
                    self.iconbitmap(default=self._icon_bitmap_path)
                except TypeError:
                    self.iconbitmap(self._icon_bitmap_path)
                loaded_any = True
                logger.info("App", f"Window icon loaded from {icon_path}")

            # Prefer iconphoto generated from the same .ico file so child
            # dialogs/toplevels always match the app icon exactly.
            icon_photo = None
            if Path(icon_path).exists():
                try:
                    from PIL import Image, ImageTk
                    with Image.open(icon_path) as icon_img:
                        icon_photo = ImageTk.PhotoImage(icon_img.convert("RGBA"))
                except Exception:
                    try:
                        icon_photo = PhotoImage(file=icon_path)
                    except Exception:
                        icon_photo = None

            if icon_photo is None:
                for fallback_rel in ("assets/icon.png", "assets/logo.png"):
                    fallback_path = resource_path(fallback_rel)
                    if not Path(fallback_path).exists():
                        continue
                    try:
                        icon_photo = PhotoImage(file=fallback_path)
                        logger.info("App", f"Window icon photo fallback loaded from {fallback_path}")
                        break
                    except Exception:
                        continue

            if icon_photo is not None:
                # Keep a strong reference so Tk does not garbage-collect the image.
                self._app_icon_photo = icon_photo
                self.iconphoto(True, self._app_icon_photo)
                loaded_any = True

            self._patch_ctk_toplevel_icon_behavior()
            if not loaded_any:
                logger.warn("App", f"Icon files not found/usable: {icon_path}")
        except Exception as e:
            logger.warn("App", f"Failed to set window icon: {e}")

        # Load param labels in background to avoid blocking startup
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

        # Initialize startup-critical managers eagerly.
        self.mod_manager = ModManager(
            settings.mods_path or Path("."),
            settings.mod_disable_method,
        )
        self.plugin_manager = PluginManager(settings.plugins_path or Path("."))
        # Heavy managers are lazy-loaded on first use to reduce startup latency.
        self._prc_handler = None
        self._msbt_handler = None
        self._css_manager = None
        self._music_manager = None
        self._conflict_detector = None
        self._share_manager = None
        self.conflict_resolver = ConflictResolver(settings.mods_path or Path("."))

        # One-time restore: move any files from .originals back to mod folders
        # (only runs if .originals exists from a previous version's merge logic)
        originals_dir = (settings.mods_path or Path(".")) / "_MergedResources" / ".originals"
        if originals_dir.exists():
            try:
                restored = self.conflict_resolver.restore_originals()
                if restored:
                    logger.info("App", f"Restored {restored} previously moved mod file(s)")
            except Exception as e:
                logger.warn("App", f"Failed to restore moved files: {e}")

        # Migrate mods from legacy .disabled subfolder to the new
        # disabled_mods sibling directory (ARCropolis loads all folders
        # inside mods regardless of name, so .disabled didn't work).
        mods_p = settings.mods_path or Path(".")
        legacy_disabled = mods_p / ".disabled"
        if legacy_disabled.exists() and legacy_disabled.is_dir():
            new_disabled = mods_p.parent / "disabled_mods"
            new_disabled.mkdir(exist_ok=True)
            migrated = 0
            for item in list(legacy_disabled.iterdir()):
                if item.is_dir():
                    dest = new_disabled / item.name
                    if not dest.exists():
                        try:
                            item.rename(dest)
                            migrated += 1
                        except OSError:
                            pass
            if migrated:
                logger.info("App", f"Migrated {migrated} mod(s) from .disabled to disabled_mods")
            # Remove legacy dir if empty
            try:
                if not any(legacy_disabled.iterdir()):
                    legacy_disabled.rmdir()
            except OSError:
                pass

        logger.info("App", "All managers initialized")
        _dbg("managers initialized")

        # Build UI
        _dbg("building MainWindow...")
        self.main_window = MainWindow(self, self)
        self.main_window.pack(fill="both", expand=True)
        _dbg("MainWindow built")

        # Lazy page registry - pages are created on first navigation
        self._page_classes = {}
        self._register_page_classes()

        # Update status bar in background
        self.after(100, self._update_status)

        # Handle window close properly
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Resize handler intentionally not bound. Keeping this hot path free
        # avoids extra jitter while users drag-resize the main window.

        # Zoom / scaling keybindings (Ctrl+Plus, Ctrl+Minus, Ctrl+0)
        saved_scale = float(getattr(settings, "ui_scale", self._DEFAULT_VISUAL_SCALE))
        # Migrate legacy default 1.0 to the new baseline 1.2.
        if abs(saved_scale - 1.0) < 1e-6:
            saved_scale = self._DEFAULT_VISUAL_SCALE
            settings.ui_scale = saved_scale
            self.config_manager.save(settings)
        self._current_scale = max(self._MIN_SCALE, min(self._MAX_SCALE, saved_scale))
        self._apply_scale(self._current_scale, save=False)
        self._apply_scaled_geometry(self._current_scale)
        # Bind reliable zoom shortcuts without low-level bind_all key spam.
        self.bind("<Control-plus>", lambda e: (self._zoom_in(), "break")[-1])
        self.bind("<Control-equal>", lambda e: (self._zoom_in(), "break")[-1])
        self.bind("<Control-minus>", lambda e: (self._zoom_out(), "break")[-1])
        self.bind("<Control-0>", lambda e: (self._zoom_reset(), "break")[-1])
        self.bind("<Control-KP_Add>", lambda e: (self._zoom_in(), "break")[-1])
        self.bind("<Control-KP_Subtract>", lambda e: (self._zoom_out(), "break")[-1])
        self.bind("<Control-KP_0>", lambda e: (self._zoom_reset(), "break")[-1])
        self.bind("<Configure>", self._on_window_activity, add="+")
        self.bind_all("<ButtonPress-1>", self._on_global_left_press, add="+")
        self.bind_all("<ButtonRelease-1>", self._on_global_left_release, add="+")

        _dbg("binding scroll...")
        # Global fast-scroll: intercept ALL MouseWheel events application-wide
        # and scroll the nearest scrollable ancestor 5x faster.
        # Do NOT use add="+" - we must be the sole bind_all handler so that
        # CTkScrollableFrame's Enter/Leave re-bind_all calls cannot silently
        # replace us with a no-op.
        self.bind_all("<MouseWheel>", self._global_fast_scroll)

        # Prevent CTkScrollableFrame from overriding our global scroll
        # handler.  CTkScrollableFrame's <Enter>/<Leave> handlers call
        # bind_all/unbind_all which replaces our handler.  Monkey-patch
        # the class to disable this behavior - our global handler
        # already handles all scroll events uniformly.
        try:
            self._neutralize_ctk_scroll_management()
        except Exception as e:
            logger.warn("App", f"Failed to neutralize CTk scroll management: {e}")

        # All UI is built and scaled - show the window now.
        # update_idletasks() forces Tk to process pending geometry
        # changes so the user never sees a half-built frame.
        # Install the global Tk error handler BEFORE deiconify so any
        # exceptions triggered by showing the window are captured.
        self.report_callback_exception = self._on_tk_error

        self.update_idletasks()
        # Build and settle the initial dashboard page while still hidden so
        # the first visible frame is fully rendered.
        try:
            self._complete_startup_navigation(pre_map=True)
        except Exception:
            pass
        # Prewarm common pages while still hidden so first tab switches do not
        # reveal half-built layouts.
        try:
            self._run_hidden_startup_prewarm()
        except Exception as e:
            logger.warn("App", f"Startup prewarm failed: {e}")
        self.update_idletasks()

        # Center before first show.
        self._center_window_on_screen()

        _dbg("update_idletasks done, showing window...")
        force_alpha_hidden = False
        try:
            self.attributes("-alpha", 0.0)
            force_alpha_hidden = True
        except Exception:
            pass
        if self._startup_hidden_withdraw:
            try:
                self.deiconify()
            except Exception:
                pass
        # Avoid forcing state("normal") after a withdrawn startup path
        # because that can reset window position on map.
        if not self._startup_hidden_withdraw:
            try:
                self.state("normal")
            except Exception:
                pass
        # Normalize geometry synchronously after map to avoid visible jumps.
        self.update_idletasks()
        self._center_window_on_screen()

        fade_in_supported = False
        if self._ENABLE_WINDOW_FADE and force_alpha_hidden:
            try:
                self.attributes("-alpha", 0.0)
                fade_in_supported = True
            except Exception:
                pass
        else:
            try:
                self.attributes("-alpha", 1.0)
            except Exception:
                pass
        # Avoid aggressive focus_force() during startup; it can trigger
        # unstable behavior on some Windows setups.
        try:
            self.lift()
        except Exception:
            pass
        if fade_in_supported and self._ENABLE_WINDOW_FADE:
            self.after(25, self._fade_in_window)
        _dbg(f"window shown, state={self.wm_state()}, mapped={self.winfo_ismapped()}")
        try:
            logger.debug("App", f"Startup geometry: {self.geometry()}")
        except Exception:
            pass

        logger.info("App", "Application startup complete")
        try:
            self.after(self._PAGE_WARMUP_INITIAL_DELAY_MS, self._start_background_page_warmup)
        except Exception:
            pass
        _dbg("startup complete")
        _dbg("__init__ complete")

    @staticmethod
    def _on_tk_error(exc_type, exc_value, exc_tb):
        """Log Tk callback exceptions instead of letting them crash the app.

        This handler MUST NOT raise - if it does, the error propagates
        back into Tk's C code and may cause a hard crash.
        """
        try:
            import traceback
            msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        except Exception:
            msg = f"{exc_type}: {exc_value}"
        # Write to stderr / crash.log first (most reliable)
        import sys
        try:
            sys.stderr.write(f"[TkCallback] {msg}\n")
            sys.stderr.flush()
        except Exception:
            pass
        # Then try the in-app logger (less critical)
        try:
            logger.error("TkCallback", msg)
        except Exception:
            pass

    def _complete_startup_navigation(self, pre_map: bool = False):
        """Finish initial page setup, optionally while startup window is still hidden."""
        self._startup_nav_after_id = None
        if self._shutting_down:
            return
        try:
            if pre_map:
                try:
                    if "dashboard" not in self.main_window.pages:
                        self._create_page("dashboard")
                    self.main_window.navigate_immediate("dashboard")
                except Exception:
                    self.navigate("dashboard")
                    try:
                        self.update()
                    except Exception:
                        pass
            else:
                self.navigate("dashboard")
            self.update_idletasks()
        except Exception:
            pass

    def _run_hidden_startup_prewarm(self):
        """Create and prime key pages while the window is still hidden."""
        if self._shutting_down or not hasattr(self, "main_window"):
            return
        warmed = []
        for page_id in self._STARTUP_PREWARM_PAGE_IDS:
            if self._shutting_down:
                break
            if page_id not in self._page_classes:
                continue
            try:
                self._create_page(page_id)
                run_on_show = page_id in self._STARTUP_PREWARM_ON_SHOW_PAGE_IDS
                self.main_window.prime_page_layout(page_id, run_on_show=run_on_show)
                warmed.append(page_id)
            except Exception as e:
                logger.warn("App", f"Startup prewarm step failed for {page_id}: {e}")
        if warmed:
            logger.info("App", f"Startup prewarmed pages: {', '.join(warmed)}")

    def _apply_scaled_geometry(self, scale: float):
        """Set window geometry and minsize proportional to scale factor."""
        # Get screen dimensions to cap window size
        screen_w, screen_h = self._get_primary_screen_size()

        # Scale the base dimensions
        scaled_w = int(self._BASE_WIDTH * scale)
        scaled_h = int(self._BASE_HEIGHT * scale)
        min_w = int(self._MIN_WIDTH * scale)
        min_h = int(self._MIN_HEIGHT * scale)

        # Cap to screen size (leave margin for taskbar)
        scaled_w = min(scaled_w, screen_w - 40)
        scaled_h = min(scaled_h, screen_h - 80)
        min_w = min(min_w, screen_w - 40)
        min_h = min(min_h, screen_h - 80)

        self.geometry(f"{scaled_w}x{scaled_h}")
        self.minsize(min_w, min_h)

    def _apply_scale(self, scale: float, save: bool = False):
        """Apply UI scaling factor and optionally persist it."""
        scale = max(self._MIN_SCALE, min(self._MAX_SCALE, float(scale)))
        overlay_shown = self._show_zoom_overlay(self._scale_to_display_percent(scale))
        try:
            self._current_scale = scale
            ctk.set_widget_scaling(scale)
            # Update minimum window size for new scale
            screen_w, screen_h = self._get_primary_screen_size()
            min_w = min(int(self._MIN_WIDTH * scale), screen_w - 40)
            min_h = min(int(self._MIN_HEIGHT * scale), screen_h - 80)
            self.minsize(min_w, min_h)
            if save:
                self._persist_scale(scale)
            zoom_percent = self._scale_to_display_percent(scale)
            logger.debug("App", f"UI scale set to {zoom_percent}%")
            # Keep zoom feedback lightweight to avoid stutter during key repeats.
            if hasattr(self, "main_window"):
                if hasattr(self.main_window, "status_bar"):
                    self.main_window.status_bar.set_zoom(zoom_percent)
        finally:
            if overlay_shown:
                try:
                    self.after(28, self._hide_zoom_overlay)
                except Exception:
                    self._hide_zoom_overlay()

    def _zoom_in(self):
        """Increase visual zoom by 10% (relative to the 100%=old120 baseline)."""
        base_scale = self._pending_scale_apply
        if base_scale is None:
            base_scale = self._current_scale
        pct = self._scale_to_display_percent(base_scale)
        self._queue_scale_change(self._display_percent_to_scale(pct + 10))

    def _zoom_out(self):
        """Decrease visual zoom by 10%."""
        base_scale = self._pending_scale_apply
        if base_scale is None:
            base_scale = self._current_scale
        pct = self._scale_to_display_percent(base_scale)
        self._queue_scale_change(self._display_percent_to_scale(pct - 10))

    def _zoom_reset(self):
        """Reset visual zoom to 100% (old 120% density)."""
        self._queue_scale_change(self._DEFAULT_VISUAL_SCALE)

    def _queue_scale_change(self, scale: float):
        """Throttle scale changes for responsiveness without reflow spam."""
        scale = max(self._MIN_SCALE, min(self._MAX_SCALE, float(scale)))
        effective = self._pending_scale_apply
        if effective is None:
            effective = self._current_scale
        if abs(scale - effective) < 1e-6:
            return
        self._note_user_activity()
        now = time.monotonic()
        previous_input = self._last_zoom_input_monotonic
        self._pending_scale_apply = scale
        self._last_zoom_input_monotonic = now
        if self._zoom_apply_after_id:
            try:
                self.after_cancel(self._zoom_apply_after_id)
            except Exception:
                pass
            self._zoom_apply_after_id = None
        # Coalesce rapid key repeats into one expensive scaling pass.
        delay_ms = int(self._ZOOM_APPLY_DEBOUNCE_MS)
        try:
            if previous_input <= 0.0 or (now - previous_input) >= 0.35:
                delay_ms = 60
        except Exception:
            delay_ms = int(self._ZOOM_APPLY_DEBOUNCE_MS)
        self._zoom_apply_after_id = self.after(delay_ms, self._flush_pending_scale)
        try:
            if hasattr(self, "main_window") and hasattr(self.main_window, "status_bar"):
                target_pct = self._scale_to_display_percent(scale)
                self.main_window.status_bar.set_zoom(target_pct)
        except Exception:
            pass

    def _show_zoom_overlay(self, target_percent: int) -> bool:
        """Cover content during scale churn to prevent transient misrender artifacts."""
        if self._shutting_down or not hasattr(self, "main_window"):
            return False
        try:
            if self._zoom_overlay is None or not bool(self._zoom_overlay.winfo_exists()):
                self._zoom_overlay = ctk.CTkFrame(
                    self.main_window.content,
                    fg_color="#12121e",
                    corner_radius=0,
                )
                self._zoom_overlay_label = ctk.CTkLabel(
                    self._zoom_overlay,
                    text="",
                    font=ctk.CTkFont(size=13),
                    text_color="#7a7a9a",
                )
                self._zoom_overlay_label.place(relx=0.5, rely=0.5, anchor="center")
            if self._zoom_overlay_label is not None and bool(self._zoom_overlay_label.winfo_exists()):
                self._zoom_overlay_label.configure(text=f"Applying zoom {int(target_percent)}%...")
            self._zoom_overlay.place(in_=self.main_window.content, x=0, y=0, relwidth=1, relheight=1)
            self._zoom_overlay.lift()
            self._zoom_overlay.update_idletasks()
            return True
        except Exception:
            return False

    def _hide_zoom_overlay(self):
        try:
            if self._zoom_overlay is not None and bool(self._zoom_overlay.winfo_exists()):
                self._zoom_overlay.place_forget()
        except Exception:
            pass

    def _flush_pending_scale(self):
        """Apply a debounced zoom request."""
        self._zoom_apply_after_id = None
        if self._pending_scale_apply is None:
            return
        pending = self._pending_scale_apply
        self._pending_scale_apply = None
        self._apply_scale(pending, save=False)
        self._last_scale_apply_monotonic = time.monotonic()
        self._schedule_scale_layout_settle()
        self._schedule_scale_persist(pending)

    def _schedule_scale_layout_settle(self):
        """Debounce expensive scale reflow until zoom input settles."""
        if self._scale_layout_settle_after_id:
            try:
                self.after_cancel(self._scale_layout_settle_after_id)
            except Exception:
                pass
            self._scale_layout_settle_after_id = None
        try:
            self._scale_layout_settle_after_id = self.after(
                self._ZOOM_LAYOUT_SETTLE_DEBOUNCE_MS, self._flush_scale_layout_settle
            )
        except Exception:
            self._scale_layout_settle_after_id = None

    def _flush_scale_layout_settle(self):
        self._scale_layout_settle_after_id = None
        if self._shutting_down or not hasattr(self, "main_window"):
            return
        if self._zoom_apply_after_id is not None or self._pending_scale_apply is not None:
            self._schedule_scale_layout_settle()
            return
        try:
            quiet_ms = (time.monotonic() - self._last_scale_apply_monotonic) * 1000.0
            input_quiet_ms = (time.monotonic() - self._last_zoom_input_monotonic) * 1000.0
            if quiet_ms < float(self._ZOOM_LAYOUT_SETTLE_DEBOUNCE_MS):
                remaining = max(12, int(float(self._ZOOM_LAYOUT_SETTLE_DEBOUNCE_MS) - quiet_ms))
                self._scale_layout_settle_after_id = self.after(remaining, self._flush_scale_layout_settle)
                return
            if input_quiet_ms < float(self._ZOOM_LAYOUT_SETTLE_DEBOUNCE_MS):
                remaining = max(12, int(float(self._ZOOM_LAYOUT_SETTLE_DEBOUNCE_MS) - input_quiet_ms))
                self._scale_layout_settle_after_id = self.after(remaining, self._flush_scale_layout_settle)
                return
        except Exception:
            pass
        try:
            self.main_window.update_idletasks()
        except Exception:
            pass
        try:
            page_id = getattr(self.main_window, "current_page", None)
            if page_id and page_id in self.main_window.pages:
                page = self.main_window.pages[page_id]
                page.update_idletasks()
                self.main_window.content.update_idletasks()
                try:
                    page.after_idle(page.update_idletasks)
                except Exception:
                    pass
                self._reset_all_canvas_xview(page)
        except Exception:
            pass

    def _reset_all_canvas_xview(self, widget):
        """Force horizontal canvas offset back to 0 after scale/layout churn."""
        import tkinter as tk
        try:
            if isinstance(widget, tk.Canvas):
                try:
                    widget.xview_moveto(0.0)
                except Exception:
                    pass
            for child in widget.winfo_children():
                self._reset_all_canvas_xview(child)
        except Exception:
            pass

    def _schedule_scale_persist(self, scale: float):
        """Persist zoom level lazily so key repeats don't hammer disk writes."""
        self._pending_scale_save = max(self._MIN_SCALE, min(self._MAX_SCALE, float(scale)))
        if self._zoom_persist_after_id:
            try:
                self.after_cancel(self._zoom_persist_after_id)
            except Exception:
                pass
        self._zoom_persist_after_id = self.after(self._ZOOM_PERSIST_DEBOUNCE_MS, self._flush_scale_persist)

    def _flush_scale_persist(self):
        self._zoom_persist_after_id = None
        scale = self._pending_scale_save
        if scale is None:
            scale = self._current_scale
        self._pending_scale_save = None
        self._persist_scale(scale)

    def _persist_scale(self, scale: float):
        """Write UI scale to config only when it actually changed."""
        try:
            settings = self.config_manager.settings
            if abs(float(getattr(settings, "ui_scale", self._DEFAULT_VISUAL_SCALE)) - float(scale)) < 1e-6:
                return
            settings.ui_scale = float(scale)
            self.config_manager.save(settings)
        except Exception:
            pass

    def _scale_to_display_percent(self, scale: float) -> int:
        """Map internal scale to UI-visible zoom percent."""
        return int(round((float(scale) / self._DEFAULT_VISUAL_SCALE) * 100))

    def _display_percent_to_scale(self, percent: int) -> float:
        """Map visible zoom percent back to internal scale."""
        min_pct = int(round((self._MIN_SCALE / self._DEFAULT_VISUAL_SCALE) * 100))
        max_pct = int(round((self._MAX_SCALE / self._DEFAULT_VISUAL_SCALE) * 100))
        pct = max(min_pct, min(max_pct, int(percent)))
        return max(self._MIN_SCALE, min(self._MAX_SCALE, (pct / 100.0) * self._DEFAULT_VISUAL_SCALE))

    def _on_keypress_zoom(self, event):
        """Low-level key handler for zoom shortcuts on Windows.

        This is a bind_all handler, so it MUST NOT raise.
        """
        try:
            return self._on_keypress_zoom_impl(event)
        except Exception:
            pass

    def _on_keypress_zoom_impl(self, event):
        """Inner zoom handler (may raise)."""
        # Check if Ctrl is held (state bit 0x4 on Windows)
        if not (event.state & 0x4):
            return
        # Skip zoom when focus is in a text input widget
        widget_class = event.widget.winfo_class()
        if widget_class in ("Entry", "Text", "TEntry", "Spinbox", "TSpinbox"):
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

    # --- Global fast scroll --------------------------------------------------

    _SCROLL_SPEED = 3                    # Listbox/Text scroll multiplier
    _CANVAS_SCROLL_PIXELS = 72           # Default canvas movement per wheel tick
    _MODS_CANVAS_SCROLL_PIXELS = 54      # Keep Mods aligned with Plugins pace
    _LONGFORM_SCROLL_SPEED = 4           # Long-form text/list widgets
    _LONGFORM_CANVAS_SCROLL_PIXELS = 78  # Online Guide/Migration boost

    def _on_global_left_press(self, event):
        try:
            self._note_user_activity()
            self._set_left_button_down(True, source_widget=getattr(event, "widget", None))
        except Exception:
            pass

    def _on_global_left_release(self, event):
        try:
            self._note_user_activity()
            self._set_left_button_down(False, source_widget=getattr(event, "widget", None))
        except Exception:
            pass

    @staticmethod
    def _widget_belongs_to_scrollbar(widget) -> bool:
        w = widget
        while w is not None:
            try:
                if isinstance(w, ctk.CTkScrollbar) or w.__class__.__name__ == "CTkScrollbar":
                    return True
                w = w.master
            except Exception:
                break
        return False

    @staticmethod
    def _resolve_scroll_target_from_scrollbar(widget):
        """Best-effort scroll target lookup from a CTk scrollbar widget tree."""
        w = widget
        while w is not None:
            try:
                if isinstance(w, ctk.CTkScrollbar) or w.__class__.__name__ == "CTkScrollbar":
                    cmd = getattr(w, "_command", None)
                    target = getattr(cmd, "__self__", None)
                    if target is not None:
                        return target
                    break
                w = w.master
            except Exception:
                break
        return None

    def _on_scrollbar_drag_start(self):
        self._scrollbar_drag_active = True
        self._drag_redraw_counter = 0
        self._last_drag_widget_refresh_monotonic = 0.0
        if self._active_drag_scroll_widget is None:
            try:
                pointed = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
                target = self._resolve_scroll_target_from_scrollbar(pointed)
                if target is not None:
                    self._active_drag_scroll_widget = target
            except Exception:
                pass
        try:
            if getattr(self.main_window, "current_page", None) == "conflicts":
                conflicts_page = self.main_window.pages.get("conflicts")
                if conflicts_page is not None and bool(
                    getattr(conflicts_page, "_top_anchor_guard_active", False)
                ):
                    conflicts_page.release_top_anchor_guard("scrollbar-drag")
        except Exception:
            pass
        self._suppress_scroll_refresh_until = max(
            self._suppress_scroll_refresh_until, time.monotonic() + 0.02
        )
        if self._active_drag_scroll_widget is not None:
            self._schedule_scroll_refresh(self._active_drag_scroll_widget)
        self._ensure_drag_redraw_loop()

    def _on_scrollbar_drag_end(self):
        target = self._active_drag_scroll_widget
        self._scrollbar_drag_active = False
        self._active_drag_scroll_widget = None
        if self._drag_refresh_after_id:
            try:
                self.after_cancel(self._drag_refresh_after_id)
            except Exception:
                pass
            self._drag_refresh_after_id = None
        try:
            self.after(8, lambda w=target: self._refresh_after_pointer_release(w))
        except Exception:
            pass
        if target is not None:
            self._schedule_scroll_refresh(target)

    def _on_scrollbar_drag_motion(self, scrollbar):
        """Force a targeted redraw while dragging a CTk scrollbar thumb."""
        if self._shutting_down:
            return
        target = None
        try:
            cmd = getattr(scrollbar, "_command", None)
            target = getattr(cmd, "__self__", None)
        except Exception:
            target = None
        if target is None:
            target = self._active_drag_scroll_widget
        if target is None:
            return
        self._active_drag_scroll_widget = target
        self._schedule_scroll_refresh(target)
        try:
            # During rapid thumb drags, force immediate paint each motion event.
            target.update()
            if hasattr(self, "main_window") and hasattr(self.main_window, "content"):
                self.main_window.content.update()
            else:
                self.update_idletasks()
            self._last_drag_widget_refresh_monotonic = time.monotonic()
        except Exception:
            pass

    def _set_left_button_down(self, pressed: bool, source_widget=None):
        self._pointer_left_down = bool(pressed)
        if pressed:
            self._scrollbar_drag_active = self._widget_belongs_to_scrollbar(source_widget)
            self._suppress_scroll_refresh_until = time.monotonic() + 0.05
            if self._scrollbar_drag_active:
                self._active_drag_scroll_widget = self._resolve_scroll_target_from_scrollbar(source_widget)
            # Drop pending refreshes before scrollbar dragging starts.
            if self._scroll_refresh_after_id:
                try:
                    self.after_cancel(self._scroll_refresh_after_id)
                except Exception:
                    pass
                self._scroll_refresh_after_id = None
            self._scroll_refresh_widgets.clear()
            if self._scrollbar_drag_active:
                self._on_scrollbar_drag_start()
        else:
            self._on_scrollbar_drag_end()

    def _ensure_drag_redraw_loop(self):
        if self._drag_refresh_after_id or not self._pointer_left_down or not self._scrollbar_drag_active:
            return
        try:
            self._drag_refresh_after_id = self.after(
                self._DRAG_REDRAW_INTERVAL_MS, self._drag_redraw_tick
            )
        except Exception:
            self._drag_refresh_after_id = None

    def _drag_redraw_tick(self):
        self._drag_refresh_after_id = None
        if not self._pointer_left_down or not self._scrollbar_drag_active or self._shutting_down:
            return
        target = self._active_drag_scroll_widget
        self._drag_redraw_counter = (self._drag_redraw_counter + 1) % max(
            1, int(self._DRAG_FORCE_UPDATE_EVERY_TICKS)
        )
        try:
            if target is not None and bool(target.winfo_exists()):
                target.update()
                self._schedule_scroll_refresh(target)
            else:
                self.update_idletasks()
        except Exception:
            pass
        try:
            if hasattr(self, "main_window") and hasattr(self.main_window, "content"):
                self.main_window.content.update_idletasks()
        except Exception:
            pass
        self._ensure_drag_redraw_loop()

    def _refresh_after_pointer_release(self, widget=None):
        if self._pointer_left_down or self._shutting_down:
            return
        try:
            if widget is not None and bool(widget.winfo_exists()):
                widget.update_idletasks()
                self.after(14, widget.update_idletasks)
                self.after(30, widget.update_idletasks)
            self.update_idletasks()
            self.after(14, self.update_idletasks)
            self.after(30, self.update_idletasks)
        except Exception:
            pass

    def _on_window_activity(self, event):
        """Throttle heavy redraw work during active resize/reflow."""
        try:
            if event.widget != self:
                return
            w = int(getattr(event, "width", 0) or 0)
            h = int(getattr(event, "height", 0) or 0)
            if w <= 1 or h <= 1:
                return
            size = (w, h)
            if size == self._last_window_activity_size:
                return
            self._last_window_activity_size = size
            self._suppress_scroll_refresh_until = max(
                self._suppress_scroll_refresh_until,
                time.monotonic() + 0.08,
            )
            if self._resize_after_id:
                try:
                    self.after_cancel(self._resize_after_id)
                except Exception:
                    pass
            self._resize_after_id = self.after(self._RESIZE_SETTLE_MS, self._finalize_resize)
        except Exception:
            pass

    @staticmethod
    def _widget_can_scroll_vertically(widget) -> bool:
        """Return True only for widgets that currently have vertical range."""
        try:
            y0, y1 = widget.yview()
            return (y1 - y0) < 0.999999
        except Exception:
            return False

    @staticmethod
    def _scroll_canvas_pixels(canvas, delta_pixels: float) -> bool:
        """Scroll a canvas by pixel distance for consistent speed across pages."""
        try:
            y0, y1 = canvas.yview()
            if (y1 - y0) >= 0.999999:
                return False
            scrollregion = canvas.cget("scrollregion")
            total_h = 0.0
            if scrollregion:
                parts = [float(p) for p in str(scrollregion).split()]
                if len(parts) == 4:
                    total_h = max(0.0, parts[3] - parts[1])
            if total_h <= 1.0:
                bbox = canvas.bbox("all")
                if bbox:
                    total_h = max(0.0, float(bbox[3] - bbox[1]))
            view_h = max(1.0, float(canvas.winfo_height()))
            scroll_h = max(1.0, total_h - view_h)
            current_px = float(y0) * scroll_h
            target_px = max(0.0, min(scroll_h, current_px + float(delta_pixels)))
            canvas.yview_moveto(target_px / scroll_h)
            return True
        except Exception:
            return False

    def _patch_ctk_scrollbar_drag_behavior(self):
        """Make CTk scrollbar thumb dragging preserve click offset.

        CustomTkinter's default behavior recenters the thumb under the mouse
        on click, which feels like a sudden jump when dragging from the top
        or bottom half of the thumb.
        """
        from customtkinter.windows.widgets import ctk_scrollbar as _ctk_scrollbar

        if getattr(_ctk_scrollbar.CTkScrollbar, "_ssbumm_drag_patch", False):
            return

        app = self
        original_clicked = _ctk_scrollbar.CTkScrollbar._clicked
        original_create_bindings = _ctk_scrollbar.CTkScrollbar._create_bindings

        def _clicked_preserve_offset(scrollbar, event):
            try:
                if scrollbar._orientation == "vertical":
                    denom = max(1e-6, (scrollbar._current_height - 2 * scrollbar._border_spacing))
                    value = scrollbar._reverse_widget_scaling(
                        (event.y - scrollbar._border_spacing) / denom
                    )
                else:
                    denom = max(1e-6, (scrollbar._current_width - 2 * scrollbar._border_spacing))
                    value = scrollbar._reverse_widget_scaling(
                        (event.x - scrollbar._border_spacing) / denom
                    )

                value = max(0.0, min(1.0, float(value)))
                raw_length = max(0.0, min(1.0, float(scrollbar._end_value - scrollbar._start_value)))
                corr_start, corr_end = scrollbar._get_scrollbar_values_for_minimum_pixel_size()
                corr_start = max(0.0, min(1.0, float(corr_start)))
                corr_end = max(0.0, min(1.0, float(corr_end)))
                corr_length = max(0.0, min(1.0, corr_end - corr_start))

                event_type = getattr(event, "type", None)
                event_type_s = str(event_type).lower()
                is_press = (
                    event_type == 4
                    or event_type_s == "4"
                    or "buttonpress" in event_type_s
                )
                is_motion = (
                    event_type == 6
                    or event_type_s == "6"
                    or "motion" in event_type_s
                )

                if is_press:
                    app._on_scrollbar_drag_start()
                    if corr_start <= value <= corr_end:
                        # Clicked inside thumb: preserve relative click offset.
                        scrollbar._drag_anchor_corrected = value - corr_start
                    else:
                        # Clicked outside thumb: keep prior "jump toward click" behavior.
                        scrollbar._drag_anchor_corrected = corr_length / 2.0
                elif is_motion and getattr(scrollbar, "_drag_anchor_corrected", None) is None:
                    # If the press event was missed (e.g. thumb tag hit), infer anchor
                    # from current visual thumb position before first drag step.
                    if corr_start <= value <= corr_end:
                        scrollbar._drag_anchor_corrected = value - corr_start
                    else:
                        scrollbar._drag_anchor_corrected = corr_length / 2.0

                anchor_corr = getattr(scrollbar, "_drag_anchor_corrected", None)
                if anchor_corr is None:
                    anchor_corr = corr_length / 2.0
                anchor_corr = max(0.0, min(float(anchor_corr), corr_length))
                target_corr_start = value - anchor_corr
                target_corr_start = max(0.0, min(target_corr_start, 1.0 - corr_length))

                denom_factor = max(1e-6, 1.0 - corr_length)
                raw_factor = (1.0 - raw_length) / denom_factor
                target_start = target_corr_start * raw_factor
                target_start = max(0.0, min(target_start, 1.0 - raw_length))
                target_end = target_start + raw_length

                scrollbar._start_value = target_start
                scrollbar._end_value = target_end
                scrollbar._draw()

                if scrollbar._command is not None:
                    scrollbar._command("moveto", scrollbar._start_value)
                    # Trigger a lightweight redraw pass for the actual scroll
                    # target to reduce transient text tearing during thumb drag.
                    try:
                        target_widget = getattr(scrollbar._command, "__self__", None)
                        if target_widget is not None:
                            app._active_drag_scroll_widget = target_widget
                            app._schedule_scroll_refresh(target_widget)
                            app._on_scrollbar_drag_motion(scrollbar)
                    except Exception:
                        pass
            except Exception:
                # Fall back to stock behavior if anything unexpected happens.
                return original_clicked(scrollbar, event)

        def _create_bindings_preserve_offset(scrollbar, sequence=None):
            original_create_bindings(scrollbar, sequence=sequence)
            try:
                if not getattr(scrollbar, "_ssbumm_drag_bindings", False):
                    scrollbar._canvas.bind("<Button-1>", scrollbar._clicked, add="+")
                    scrollbar._canvas.bind(
                        "<B1-Motion>",
                        lambda _e, sb=scrollbar: app._on_scrollbar_drag_motion(sb),
                        add="+",
                    )
                    scrollbar._canvas.bind(
                        "<ButtonRelease-1>",
                        lambda _e, sb=scrollbar: (
                            setattr(sb, "_drag_anchor_corrected", None),
                            app._on_scrollbar_drag_end(),
                        ),
                        add="+",
                    )
                    scrollbar._ssbumm_drag_bindings = True
            except Exception:
                pass

        _ctk_scrollbar.CTkScrollbar._clicked = _clicked_preserve_offset
        _ctk_scrollbar.CTkScrollbar._create_bindings = _create_bindings_preserve_offset
        _ctk_scrollbar.CTkScrollbar._ssbumm_drag_patch = True

    def _neutralize_ctk_scroll_management(self):
        """Prevent CTkScrollableFrame from overriding our global scroll handler.

        CTkScrollableFrame binds <Enter>/<Leave> on its canvas to call
        bind_all/unbind_all for <MouseWheel>, which replaces any existing
        global handler (including ours).  We monkey-patch ALL relevant
        class methods to be no-ops so only our global handler runs.
        Also unbind any existing <Enter>/<Leave> scroll bindings on all
        existing CTkScrollableFrame instances.
        """

        # Patch the class so new instances don't interfere.
        # _mouse_wheel_all: the handler CTk registers via bind_all
        # _mouse_wheel_bind: called on <Enter>, calls bind_all which
        #     REPLACES our global handler with the (no-op) _mouse_wheel_all
        # _mouse_wheel_unbind: called on <Leave>, calls unbind_all which
        #     REMOVES our global handler entirely
        def _noop(self_csf, *args, **kwargs):
            pass

        ctk.CTkScrollableFrame._mouse_wheel_all = _noop
        ctk.CTkScrollableFrame._mouse_wheel_bind = _noop
        ctk.CTkScrollableFrame._mouse_wheel_unbind = _noop

        # Also neutralize existing instances by unbinding their canvas
        # Enter/Leave handlers that were set before our class-level patch
        def _neutralize_existing(widget):
            if isinstance(widget, ctk.CTkScrollableFrame):
                try:
                    canvas = getattr(widget, '_parent_canvas', None)
                    if canvas is not None:
                        canvas.unbind("<Enter>")
                        canvas.unbind("<Leave>")
                        canvas.unbind("<MouseWheel>")
                except Exception:
                    pass
            try:
                for child in widget.winfo_children():
                    _neutralize_existing(child)
            except Exception:
                pass

        try:
            _neutralize_existing(self)
        except Exception:
            pass

        # Re-register our global handler in case a previous Enter/Leave
        # event already clobbered it.
        try:
            self.bind_all("<MouseWheel>", self._global_fast_scroll)
        except Exception:
            pass

    def _global_fast_scroll(self, event):
        """Intercept every MouseWheel event and scroll faster.

        Walks up the widget tree from the widget under the mouse cursor
        to find the nearest scrollable ancestor (Canvas inside a
        CTkScrollableFrame, Listbox, or Text) and scrolls it.

        This handler MUST NOT raise - it is called for every single
        mouse-wheel tick via bind_all, so an uncaught exception here
        would either kill the mainloop or cause a Tk/C-level crash.
        """
        try:
            return self._global_fast_scroll_impl(event)
        except Exception:
            pass

    def _global_fast_scroll_impl(self, event):
        """Inner implementation of fast scroll (may raise)."""
        import tkinter as tk
        self._note_user_activity()
        # Use event.widget as the primary source (reliable under scaling),
        # then optionally refine via winfo_containing when available.
        widget = getattr(event, "widget", None)
        try:
            pointed = event.widget.winfo_containing(event.x_root, event.y_root)
            if pointed is not None:
                widget = pointed
        except Exception:
            pass
        if widget is None:
            return

        # Walk up the hierarchy looking for a scrollable widget
        w = widget
        scrollable = None
        in_longform_page = False
        while w is not None:
            if w.__class__.__name__ in ("OnlineCompatPage", "MigrationPage"):
                in_longform_page = True
            if isinstance(w, tk.Listbox):
                if self._widget_can_scroll_vertically(w):
                    scrollable = w
                    break
            if isinstance(w, tk.Text):
                if self._widget_can_scroll_vertically(w):
                    scrollable = w
                    break
            # CTkScrollableFrame - its internal canvas is NOT in the
            # ancestor chain of child widgets, so we must detect the
            # frame itself and grab its _parent_canvas.
            if isinstance(w, ctk.CTkScrollableFrame):
                try:
                    parent_canvas = w._parent_canvas
                    if self._widget_can_scroll_vertically(parent_canvas):
                        scrollable = parent_canvas
                        break
                except AttributeError:
                    pass
            if isinstance(w, tk.Canvas):
                # Skip decorative CTk canvases (labels/buttons) and only use
                # canvases that actually have a vertical scroll range.
                if self._widget_can_scroll_vertically(w):
                    scrollable = w
                    break
            try:
                w = w.master
            except Exception:
                break

        if scrollable is None:
            return

        try:
            if event.delta == 0:
                return "break"
            if self._pointer_left_down:
                return "break"
            direction = -1 if event.delta > 0 else 1
            ticks = max(1, min(4, int(round(abs(event.delta) / 120))))
            page_id = None
            try:
                page_id = self.main_window.current_page
            except Exception:
                pass
            # Conflicts page is pinned to top after scan while the list
            # stabilizes. Hold wheel input briefly, then release guard on the
            # first explicit user wheel action.
            if page_id == "conflicts":
                try:
                    conflicts_page = self.main_window.pages.get("conflicts")
                    if conflicts_page is not None and bool(
                        getattr(conflicts_page, "_top_anchor_guard_active", False)
                    ):
                        can_release = True
                        try:
                            can_release = bool(conflicts_page._can_release_top_anchor_guard())
                        except Exception:
                            can_release = True
                        if not can_release:
                            return "break"
                        conflicts_page.release_top_anchor_guard("wheel")
                except Exception:
                    pass
            longform = in_longform_page or page_id in ("online_compat", "migration")
            if isinstance(scrollable, tk.Canvas):
                speed = self._CANVAS_SCROLL_PIXELS
                if longform:
                    speed = self._LONGFORM_CANVAS_SCROLL_PIXELS
                elif page_id == "mods":
                    speed = self._MODS_CANVAS_SCROLL_PIXELS
            else:
                speed = self._SCROLL_SPEED
                if longform:
                    speed = self._LONGFORM_SCROLL_SPEED
            if longform:
                key = f"{page_id or 'unknown'}:{type(scrollable).__name__}:{speed}"
                if key not in self._scroll_debug_keys:
                    self._scroll_debug_keys.add(key)
                    logger.debug("App", f"Long-form scroll boost active ({key})")
            delta = direction * speed * ticks
            if isinstance(scrollable, tk.Canvas):
                moved = self._scroll_canvas_pixels(scrollable, delta)
                if not moved:
                    scrollable.yview_scroll(int(delta), "units")
            else:
                scrollable.yview_scroll(int(delta), "units")
            self._schedule_scroll_refresh(scrollable)
        except tk.TclError:
            pass
        return "break"

    def _schedule_scroll_refresh(self, widget):
        """Throttle redraws while wheel-scrolling to avoid transient text artifacts."""
        if widget is None:
            return
        try:
            # Keep refreshes active while dragging a scrollbar thumb so text
            # in long-form pages does not smear during rapid movement.
            if (
                time.monotonic() < self._suppress_scroll_refresh_until
                and not self._scrollbar_drag_active
            ):
                return
            self._scroll_refresh_widgets.add(widget)
            if self._scroll_refresh_after_id:
                return
            self._scroll_refresh_after_id = self.after(
                self._SCROLL_REFRESH_INTERVAL_MS, self._flush_scroll_refresh
            )
        except Exception:
            pass

    def _flush_scroll_refresh(self):
        self._scroll_refresh_after_id = None
        widgets = list(self._scroll_refresh_widgets)
        self._scroll_refresh_widgets.clear()
        dragging = bool(self._pointer_left_down and self._scrollbar_drag_active)
        active_widget = self._active_drag_scroll_widget if dragging else None
        if dragging and active_widget is not None:
            widgets = [active_widget]
        if not widgets:
            return
        try:
            force_update = False
            if dragging:
                self._scroll_refresh_drag_counter = (
                    self._scroll_refresh_drag_counter + 1
                ) % max(1, int(self._DRAG_FORCE_UPDATE_EVERY_TICKS))
                force_update = self._scroll_refresh_drag_counter == 0
            for widget in widgets:
                try:
                    if not bool(widget.winfo_exists()) or not bool(widget.winfo_ismapped()):
                        continue
                    if dragging and force_update:
                        widget.update()
                    else:
                        widget.update_idletasks()
                except Exception:
                    continue
            if hasattr(self, "main_window") and hasattr(self.main_window, "content"):
                self.main_window.content.update_idletasks()
            elif not dragging:
                self.update_idletasks()
            if dragging and active_widget is not None:
                self._schedule_scroll_refresh(active_widget)
            else:
                self._scroll_refresh_full_counter = (self._scroll_refresh_full_counter + 1) % 6
                if self._scroll_refresh_full_counter == 0:
                    for widget in widgets:
                        try:
                            widget.after_idle(widget.update_idletasks)
                        except Exception:
                            pass
        except Exception:
            pass

    # --- Startup window recovery ---------------------------------------------

    def _get_primary_screen_size(self) -> tuple[int, int]:
        """Return primary monitor dimensions (Windows) with Tk fallback."""
        # Prefer Tk values so logical pixels match geometry values under DPI scaling.
        try:
            w = int(self.winfo_screenwidth())
            h = int(self.winfo_screenheight())
            if w > 200 and h > 200:
                return w, h
        except Exception:
            pass
        try:
            import ctypes
            user32 = ctypes.windll.user32
            # SM_CXSCREEN=0, SM_CYSCREEN=1 (primary monitor size)
            w = int(user32.GetSystemMetrics(0))
            h = int(user32.GetSystemMetrics(1))
            if w > 200 and h > 200:
                return w, h
        except Exception:
            pass
        return 1920, 1080

    def _get_current_geometry_size(self) -> tuple[int, int]:
        """Best-effort read of current geometry width/height."""
        try:
            g = self.geometry()
            m = re.match(r"(\d+)x(\d+)", g)
            if m:
                w = int(m.group(1))
                h = int(m.group(2))
                # Some Tk startup paths briefly report 1x1 while withdrawn.
                # Ignore that transient size so centering doesn't visibly jump.
                if w > 50 and h > 50:
                    return w, h
        except Exception:
            pass
        try:
            w = int(self.winfo_width())
            h = int(self.winfo_height())
            if w > 50 and h > 50:
                return w, h
        except Exception:
            pass
        # Fallback to expected scaled base size
        scale = getattr(self, "_current_scale", 1.0)
        sw, sh = self._get_primary_screen_size()
        w = min(int(self._BASE_WIDTH * scale), sw - 40)
        h = min(int(self._BASE_HEIGHT * scale), sh - 80)
        return max(600, w), max(450, h)

    def _center_window_on_screen(self):
        """Center the window using DPI-consistent Tk screen dimensions."""
        if self._shutting_down:
            return
        try:
            self.update_idletasks()
            sw, sh = self._get_primary_screen_size()
            ww, wh = self._get_current_geometry_size()
            x = max(0, (sw - ww) // 2)
            y = max(0, (sh - wh) // 2)
            self.geometry(f"{ww}x{wh}+{x}+{y}")
        except Exception:
            pass

    def _ensure_window_visible(self, attempt: int = 1):
        """Recover from startup cases where the window ends up hidden/minimized."""
        if self._shutting_down:
            return
        try:
            state = self.wm_state()
        except Exception:
            state = "unknown"
        try:
            mapped = bool(self.winfo_ismapped())
        except Exception:
            mapped = False
        try:
            viewable = bool(self.winfo_viewable())
        except Exception:
            viewable = mapped

        needs_recover = (state in ("withdrawn", "iconic")) or (not mapped) or (not viewable)
        if needs_recover:
            try:
                self.deiconify()
            except Exception:
                pass
            try:
                self.state("normal")
            except Exception:
                pass
            try:
                self.attributes("-alpha", 1.0)
            except Exception:
                pass
            try:
                self._center_window_on_screen()
            except Exception:
                pass
            try:
                self.lift()
            except Exception:
                pass
            logger.warn(
                "App",
                f"Startup visibility recovery attempt={attempt} state={state} mapped={int(mapped)} viewable={int(viewable)}",
            )

        if attempt < 12:
            try:
                self.after(250, lambda: self._ensure_window_visible(attempt + 1))
            except Exception:
                pass

    def _cancel_window_fade(self):
        if self._window_fade_after_id:
            try:
                self.after_cancel(self._window_fade_after_id)
            except Exception:
                pass
            self._window_fade_after_id = None

    def _fade_in_window(self):
        """Fade startup from transparent to fully visible."""
        self._cancel_window_fade()
        try:
            self.attributes("-alpha", 0.0)
        except Exception:
            return

        steps = max(1, int(self._WINDOW_FADE_IN_MS / self._WINDOW_FADE_STEP_MS))
        increment = 1.0 / float(steps)
        state = {"alpha": 0.0}

        def _tick():
            if self._shutting_down:
                return
            state["alpha"] = min(1.0, state["alpha"] + increment)
            try:
                self.attributes("-alpha", state["alpha"])
            except Exception:
                self._window_fade_after_id = None
                return
            if state["alpha"] >= 0.999:
                self._window_fade_after_id = None
                return
            try:
                self._window_fade_after_id = self.after(self._WINDOW_FADE_STEP_MS, _tick)
            except Exception:
                self._window_fade_after_id = None

        _tick()

    def _fade_out_then(self, on_complete):
        """Fade out before shutdown to avoid abrupt teardown flash."""
        self._cancel_window_fade()
        try:
            current = float(self.attributes("-alpha"))
        except Exception:
            current = 1.0
        if current <= 0.05:
            on_complete()
            return

        steps = max(1, int(self._WINDOW_FADE_OUT_MS / self._WINDOW_FADE_STEP_MS))
        decrement = max(0.02, current / float(steps))

        def _tick():
            try:
                value = max(0.0, float(self.attributes("-alpha")) - decrement)
                self.attributes("-alpha", value)
            except Exception:
                self._window_fade_after_id = None
                on_complete()
                return
            if value <= 0.01:
                self._window_fade_after_id = None
                on_complete()
                return
            try:
                self._window_fade_after_id = self.after(self._WINDOW_FADE_STEP_MS, _tick)
            except Exception:
                self._window_fade_after_id = None
                on_complete()

        _tick()

    # --- Window events -------------------------------------------------------

    def _on_configure(self, event):
        """Handle window resize events smoothly."""
        try:
            self._on_configure_impl(event)
        except Exception:
            pass

    def _on_configure_impl(self, event):
        if event.widget != self or self._shutting_down:
            return

        w, h = event.width, event.height
        if w == self._last_width and h == self._last_height:
            return

        self._last_width = w
        self._last_height = h
        # Keep resize handling lightweight to reduce drag stutter.

    def _finalize_resize(self):
        """Finalize layout after resize settles."""
        self._resize_after_id = None
        if self._shutting_down:
            return
        try:
            self.update_idletasks()
        except Exception:
            pass

    def _patch_ctk_toplevel_icon_behavior(self):
        """Apply app icon assets to every CTkToplevel automatically."""
        try:
            from customtkinter.windows import ctk_toplevel as _ctk_toplevel
        except Exception:
            return

        if getattr(_ctk_toplevel.CTkToplevel, "_ssbumm_icon_patch", False):
            return

        app = self
        original_init = _ctk_toplevel.CTkToplevel.__init__
        original_iconbitmap = _ctk_toplevel.CTkToplevel.iconbitmap
        original_wm_iconbitmap = getattr(
            _ctk_toplevel.CTkToplevel,
            "wm_iconbitmap",
            original_iconbitmap,
        )
        original_windows_set_titlebar_icon = getattr(
            _ctk_toplevel.CTkToplevel,
            "_windows_set_titlebar_icon",
            None,
        )

        def _windows_set_titlebar_color_noop(_toplevel, *_args, **_kwargs):
            return None

        def _windows_set_titlebar_icon_with_app(toplevel):
            # Prevent CTk's late default icon assignment from ever replacing
            # the app icon on transient dialogs.
            try:
                app.apply_window_icon(toplevel)
                return
            except Exception:
                pass
            if callable(original_windows_set_titlebar_icon):
                try:
                    return original_windows_set_titlebar_icon(toplevel)
                except Exception:
                    return None
            return None

        # Disable CTk header manipulation for transient dialogs. This avoids
        # withdraw/deiconify flashes while popup windows are being created.
        try:
            _ctk_toplevel.CTkToplevel._deactivate_windows_window_header_manipulation = True
        except Exception:
            pass

        def _override_ctk_default_icon(bitmap=None, default=None):
            candidate = default if default is not None else bitmap
            try:
                normalized = str(candidate).replace("\\", "/").lower()
            except Exception:
                normalized = ""
            if not normalized.endswith("customtkinter_icon_windows.ico"):
                return bitmap, default
            app_icon = getattr(app, "_icon_bitmap_path", None)
            if not app_icon or not Path(app_icon).exists():
                return bitmap, default
            if default is not None:
                return bitmap, app_icon
            return app_icon, default

        def _iconbitmap_with_override(toplevel, bitmap=None, default=None):
            bitmap, default = _override_ctk_default_icon(bitmap, default)
            try:
                return original_iconbitmap(toplevel, bitmap=bitmap, default=default)
            except TypeError:
                if default is not None:
                    return original_iconbitmap(toplevel, default=default)
                return original_iconbitmap(toplevel, bitmap)

        def _wm_iconbitmap_with_override(toplevel, bitmap=None, default=None):
            bitmap, default = _override_ctk_default_icon(bitmap, default)
            try:
                return original_wm_iconbitmap(toplevel, bitmap=bitmap, default=default)
            except TypeError:
                if default is not None:
                    return original_wm_iconbitmap(toplevel, default=default)
                return original_wm_iconbitmap(toplevel, bitmap)

        def _init_with_icon(toplevel, *args, **kwargs):
            original_init(toplevel, *args, **kwargs)

            def _apply_icon_once():
                try:
                    if bool(toplevel.winfo_exists()):
                        app.apply_window_icon(toplevel)
                except Exception:
                    pass

            _apply_icon_once()
            # CTk schedules delayed icon operations; apply ours again after
            # those callbacks so dialogs always keep the app icon.
            for delay_ms in (220, 420):
                try:
                    toplevel.after(delay_ms, _apply_icon_once)
                except Exception:
                    pass

        _ctk_toplevel.CTkToplevel.__init__ = _init_with_icon
        _ctk_toplevel.CTkToplevel.iconbitmap = _iconbitmap_with_override
        _ctk_toplevel.CTkToplevel.wm_iconbitmap = _wm_iconbitmap_with_override
        _ctk_toplevel.CTkToplevel._windows_set_titlebar_color = _windows_set_titlebar_color_noop
        _ctk_toplevel.CTkToplevel._windows_set_titlebar_icon = _windows_set_titlebar_icon_with_app
        _ctk_toplevel.CTkToplevel._ssbumm_icon_patch = True

    def apply_window_icon(self, window):
        """Apply current app icon assets to a child window."""
        if window is None:
            return
        try:
            icon_path = getattr(self, "_icon_bitmap_path", None)
            if icon_path and Path(icon_path).exists():
                try:
                    window.iconbitmap(default=icon_path)
                except TypeError:
                    window.iconbitmap(icon_path)
        except Exception:
            pass
        try:
            icon_photo = getattr(self, "_app_icon_photo", None)
            if icon_photo is not None:
                window.iconphoto(True, icon_photo)
                setattr(window, "_ssbumm_icon_ref", icon_photo)
        except Exception:
            pass

    def _on_close(self):
        """Clean shutdown - prompt for unsaved changes, stop threads and audio."""
        import sys as _sys
        try:
            _sys.stderr.write("[CLOSE] _on_close entered\n")
            _sys.stderr.flush()
        except Exception:
            pass

        if self._shutting_down:
            return

        if self._has_unsaved_changes:
            response = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes.\n\n"
                "Would you like to close anyway?\n\n"
                "- Yes - Close without saving\n"
                "- No / Cancel - Go back to the application"
            )
            if response is None or response is False:
                # User cancelled or said No - don't close
                return

        self._shutting_down = True
        logger.info("App", "Shutting down...")
        if self._ENABLE_WINDOW_FADE:
            self._fade_out_then(self._finalize_shutdown)
        else:
            self._finalize_shutdown()

    def _finalize_shutdown(self):
        """Final cleanup after optional close animation."""
        self._cancel_window_fade()

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
        try:
            if self._zoom_apply_after_id:
                self.after_cancel(self._zoom_apply_after_id)
        except Exception:
            pass
        try:
            if self._zoom_persist_after_id:
                self.after_cancel(self._zoom_persist_after_id)
        except Exception:
            pass
        try:
            if self._scale_layout_settle_after_id:
                self.after_cancel(self._scale_layout_settle_after_id)
        except Exception:
            pass
        try:
            if self._scroll_refresh_after_id:
                self.after_cancel(self._scroll_refresh_after_id)
        except Exception:
            pass
        try:
            if self._drag_refresh_after_id:
                self.after_cancel(self._drag_refresh_after_id)
        except Exception:
            pass
        try:
            if self._page_warmup_after_id:
                self.after_cancel(self._page_warmup_after_id)
        except Exception:
            pass
        try:
            if self._window_fade_after_id:
                self.after_cancel(self._window_fade_after_id)
        except Exception:
            pass
        try:
            if self._startup_nav_after_id:
                self.after_cancel(self._startup_nav_after_id)
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

    def mark_unsaved(self):
        """Mark that there are unsaved changes."""
        self._has_unsaved_changes = True
        if hasattr(self, 'main_window'):
            self.main_window.update_save_discard()

    def mark_saved(self):
        """Mark that all changes have been saved."""
        self._has_unsaved_changes = False
        if hasattr(self, 'main_window'):
            self.main_window.update_save_discard()

    def _register_page_classes(self):
        """Register page classes for lazy instantiation."""
        self._page_classes = {
            "dashboard": ("src.ui.pages.dashboard_page", "DashboardPage"),
            "mods": ("src.ui.pages.mods_page", "ModsPage"),
            "plugins": ("src.ui.pages.plugins_page", "PluginsPage"),
            "css": ("src.ui.pages.css_page", "CSSPage"),
            "music": ("src.ui.pages.music_page", "MusicPage"),
            "conflicts": ("src.ui.pages.conflicts_page", "ConflictsPage"),
            "share": ("src.ui.pages.share_page", "SharePage"),
            "migration": ("src.ui.pages.migration_page", "MigrationPage"),
            "online_compat": ("src.ui.pages.online_compat_page", "OnlineCompatPage"),
            "settings": ("src.ui.pages.settings_page", "SettingsPage"),
            "developer": ("src.ui.pages.developer_page", "DeveloperPage"),
        }

    def _create_page(self, page_id: str):
        """Create and register a page instance if it does not already exist."""
        if page_id in self.main_window.pages:
            return self.main_window.pages[page_id]
        if page_id not in self._page_classes:
            return None
        module_name, class_name = self._page_classes[page_id]
        module = importlib.import_module(module_name)
        page_class = getattr(module, class_name)
        page = page_class(self.main_window.content, self)
        self.main_window.register_page(page_id, page)
        logger.info("App", f"Created page: {page_id}")

        def _safe_neutralize():
            try:
                self._neutralize_ctk_scroll_management()
            except Exception as e:
                logger.warn("App", f"Failed to neutralize CTk scroll on page: {e}")

        self.after(80, _safe_neutralize)
        return page

    def _start_background_page_warmup(self):
        """Create selected lazy pages in the background to reduce first-navigation pop-in."""
        if self._shutting_down or not hasattr(self, "main_window"):
            return
        if self._page_warmup_after_id is not None:
            return
        current = getattr(self.main_window, "current_page", None)
        self._page_warmup_queue = [
            pid
            for pid in self._PAGE_WARMUP_PAGE_IDS
            if pid in self._page_classes and pid != current and pid not in self.main_window.pages
        ]
        if not self._page_warmup_queue:
            return
        self._page_warmup_after_id = self.after(40, self._run_page_warmup_step)

    def _run_page_warmup_step(self):
        self._page_warmup_after_id = None
        if self._shutting_down:
            self._page_warmup_queue = []
            return
        if not self._page_warmup_queue:
            return
        current = getattr(self.main_window, "current_page", None)
        # Warmup is strictly a startup optimization. Running hidden page
        # construction while users are actively using another page can cause
        # visible layout churn on some CTk scroll hosts (notably Conflicts).
        # Keep warmup work constrained to the dashboard startup window only.
        if current not in (None, "dashboard"):
            # User already moved past startup; stop warmup instead of retrying
            # indefinitely in the background.
            self._page_warmup_queue = []
            return
        if self.has_recent_user_activity(self._PAGE_WARMUP_IDLE_REQUIRED_MS / 1000.0):
            self._page_warmup_after_id = self.after(
                self._PAGE_WARMUP_RETRY_DELAY_MS,
                self._run_page_warmup_step,
            )
            return
        page_id = self._page_warmup_queue.pop(0)
        # Queue membership is computed once. By the time this step runs, the
        # user may already be on this page, so never prime the active page.
        current = getattr(self.main_window, "current_page", None)
        if page_id == current:
            if self._page_warmup_queue:
                self._page_warmup_after_id = self.after(
                    self._PAGE_WARMUP_STEP_DELAY_MS,
                    self._run_page_warmup_step,
                )
            return
        page = self._create_page(page_id)
        # Prime geometry while hidden but avoid page data loads (some pages kick
        # off heavy scans in on_show(), which causes startup jank).
        if page is not None:
            try:
                self.main_window.prime_page_layout(page_id)
            except Exception:
                pass
        if self._page_warmup_queue:
            self._page_warmup_after_id = self.after(
                self._PAGE_WARMUP_STEP_DELAY_MS,
                self._run_page_warmup_step,
            )

    def navigate(self, page_id: str):
        """Navigate to a page, creating it lazily if needed."""
        if self._shutting_down:
            return
        self._note_user_activity()
        # Lazy page creation
        if page_id not in self.main_window.pages:
            self._create_page(page_id)
        logger.info("App", f"Navigate to: {page_id}")
        self.main_window.navigate(page_id)

    def _note_user_activity(self):
        """Record latest user interaction timestamp for idle-sensitive work."""
        self._last_user_activity_monotonic = time.monotonic()

    def has_recent_user_activity(self, seconds: float = 1.0) -> bool:
        """True when users interacted with the app within the last N seconds."""
        try:
            return (time.monotonic() - self._last_user_activity_monotonic) < float(seconds)
        except Exception:
            return False

    @property
    def css_manager(self):
        if self._css_manager is None:
            from src.core.prc_handler import PRCHandler
            from src.core.msbt_handler import MSBTHandler
            from src.core.css_manager import CSSManager

            if self._prc_handler is None:
                self._prc_handler = PRCHandler()
            if self._msbt_handler is None:
                self._msbt_handler = MSBTHandler()
            self._css_manager = CSSManager(self._prc_handler, self._msbt_handler)
            logger.info("App", "CSS manager initialized lazily")
        return self._css_manager

    @property
    def music_manager(self):
        if self._music_manager is None:
            from src.core.music_manager import MusicManager

            self._music_manager = MusicManager()
            logger.info("App", "Music manager initialized lazily")
        return self._music_manager

    @property
    def conflict_detector(self):
        if self._conflict_detector is None:
            from src.core.conflict_detector import ConflictDetector

            self._conflict_detector = ConflictDetector()
            logger.info("App", "Conflict detector initialized lazily")
        return self._conflict_detector

    @property
    def share_manager(self):
        if self._share_manager is None:
            from src.core.share_code import ShareCodeManager

            self._share_manager = ShareCodeManager()
            logger.info("App", "Share manager initialized lazily")
        return self._share_manager

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
        """Update status text immediately and stats asynchronously."""
        settings = self.config_manager.settings
        try:
            emu_name = settings.emulator or "Emulator"
            if settings.eden_sdmc_path:
                self.main_window.update_status(f"{emu_name}: {settings.eden_sdmc_path}")
            else:
                self.main_window.update_status("Emulator not configured")
        except Exception as e:
            logger.warn("App", f"Status text update failed: {e}")

        self._status_refresh_generation += 1
        generation = self._status_refresh_generation
        if self._status_refresh_thread_active:
            self._status_refresh_pending = True
            return

        self._status_refresh_thread_active = True
        self._status_refresh_pending = False

        def collect():
            mods = 0
            plugins = 0
            try:
                local_settings = self.config_manager.settings
                if local_settings.mods_path and local_settings.mods_path.exists():
                    mod_list = self.mod_manager.list_mods()
                    mods = sum(1 for m in mod_list if m.status == ModStatus.ENABLED)
                if local_settings.plugins_path and local_settings.plugins_path.exists():
                    plugin_list = self.plugin_manager.list_plugins()
                    plugins = sum(1 for p in plugin_list if p.status == PluginStatus.ENABLED)
            except Exception as e:
                logger.warn("App", f"Status stats collection failed: {e}")

            def apply():
                self._status_refresh_thread_active = False
                if self._shutting_down:
                    return
                if generation == self._status_refresh_generation:
                    try:
                        self.main_window.update_stats(mods=mods, plugins=plugins)
                    except Exception as e:
                        logger.warn("App", f"Status stats apply failed: {e}")
                if self._status_refresh_pending:
                    self._status_refresh_pending = False
                    try:
                        self.after(20, self._update_status)
                    except Exception:
                        pass

            try:
                if not self._shutting_down:
                    self.after(0, apply)
                else:
                    self._status_refresh_thread_active = False
            except Exception:
                self._status_refresh_thread_active = False

        threading.Thread(target=collect, daemon=True).start()

