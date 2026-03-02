"""Application entry point with crash logging and startup diagnostics."""

from __future__ import annotations

import atexit
import os
import signal
import sys
import threading
import traceback

# ── Per-Monitor V1 DPI awareness ──────────────────────────────────────
# Must be set BEFORE any tkinter/CustomTkinter import so the process
# tells Windows it will manage DPI itself.
#
# Per-Monitor **V2** (SetProcessDpiAwarenessContext(-4)) is intentionally
# NOT used here.  Tk has a known compatibility issue where V2's
# automatic WM_DPICHANGED handling fights with CustomTkinter's own
# scaling callback system, causing the window to grow uncontrollably
# when dragged between monitors of different DPI.  The CTk author
# documented this exact problem and deliberately chose V1.
#
# Per-Monitor V1 lets CTk handle all client-area scaling through its
# ScalingTracker polling loop while Windows bitmap-scales the non-client
# area (titlebar).  This avoids the double-scaling conflict.
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor V1
    except Exception:
        pass

CRASH_LOG_FILENAME = "crash.log"
HEARTBEAT_ENV_VAR = "SSBUMM_HEARTBEAT"
HEARTBEAT_ENABLED_VALUE = "1"
HEARTBEAT_INTERVAL_MS = 1000
HEARTBEAT_MAX_TICKS = 15
UNKNOWN_TEXT = "unknown"
NOT_AVAILABLE_TEXT = "n/a"
NOT_AVAILABLE_NUMERIC = -1
SIGTERM_EXIT_CODE_BASE = 128
WINDOWS_APP_USER_MODEL_ID = "SSBUModManager.Desktop"
CRASH_DIALOG_TITLE = "SSBU Mod Manager - Crash"
PYTHON_PATH_INSERT_INDEX = 0
NEWLINE = "\n"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(PYTHON_PATH_INSERT_INDEX, PROJECT_ROOT)

LOG_DIR = os.path.dirname(os.path.abspath(sys.argv[0] if sys.argv else __file__))
CRASH_LOG_PATH = os.path.join(LOG_DIR, CRASH_LOG_FILENAME)

try:
    _crash_fh = open(CRASH_LOG_PATH, "w", encoding="utf-8")
    sys.stderr = _crash_fh
    sys.stdout = _crash_fh
except OSError:
    _crash_fh = None


def _write_debug(message: str) -> None:
    try:
        if _crash_fh:
            _crash_fh.write(message + NEWLINE)
            _crash_fh.flush()
    except Exception:
        pass


try:
    import faulthandler

    if _crash_fh:
        faulthandler.enable(file=_crash_fh, all_threads=True)
    else:
        faulthandler.enable(all_threads=True)
except Exception:
    pass


def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
    _write_debug(f"UNCAUGHT THREAD EXCEPTION in {args.thread}:")
    _write_debug(
        "".join(
            traceback.format_exception(
                args.exc_type,
                args.exc_value,
                args.exc_traceback,
            )
        )
    )


try:
    threading.excepthook = _thread_excepthook
except AttributeError:
    pass


def _on_exit() -> None:
    try:
        if _crash_fh and not _crash_fh.closed:
            _crash_fh.write("[atexit] interpreter shutting down" + NEWLINE)
            _crash_fh.flush()
    except Exception:
        pass


atexit.register(_on_exit)


def _on_sigterm(signum: int, _frame) -> None:
    try:
        if _crash_fh and not _crash_fh.closed:
            _crash_fh.write(
                f"[SIGNAL] Received signal {signum}; process being terminated"
                + NEWLINE
            )
            _crash_fh.flush()
    except Exception:
        pass
    raise SystemExit(SIGTERM_EXIT_CODE_BASE + signum)


try:
    signal.signal(signal.SIGTERM, _on_sigterm)
except (OSError, ValueError):
    pass


def _set_windows_app_id() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            WINDOWS_APP_USER_MODEL_ID
        )
        _write_debug(f"Set AppUserModelID: {WINDOWS_APP_USER_MODEL_ID}")
    except Exception as exc:
        _write_debug(f"Failed to set AppUserModelID: {exc}")


def _heartbeat_tick(app, tick: int = 1) -> None:
    try:
        state = app.wm_state()
    except Exception:
        state = UNKNOWN_TEXT

    try:
        mapped = int(bool(app.winfo_ismapped()))
    except Exception:
        mapped = NOT_AVAILABLE_NUMERIC

    try:
        viewable = int(bool(app.winfo_viewable()))
    except Exception:
        viewable = NOT_AVAILABLE_NUMERIC

    try:
        geometry = app.geometry()
    except Exception:
        geometry = NOT_AVAILABLE_TEXT

    _write_debug(
        f"[HEARTBEAT] +{tick}s state={state} mapped={mapped} "
        f"viewable={viewable} geom={geometry}"
    )

    if tick >= HEARTBEAT_MAX_TICKS:
        return

    try:
        app.after(
            HEARTBEAT_INTERVAL_MS,
            lambda: _heartbeat_tick(app, tick + 1),
        )
    except Exception as exc:
        _write_debug(f"[HEARTBEAT] scheduling failed: {exc}")


def _try_enable_heartbeat(app) -> None:
    enabled = os.environ.get(HEARTBEAT_ENV_VAR, "").strip() == HEARTBEAT_ENABLED_VALUE
    if not enabled:
        return
    try:
        app.after(HEARTBEAT_INTERVAL_MS, lambda: _heartbeat_tick(app))
    except Exception as exc:
        _write_debug(f"[HEARTBEAT] init failed: {exc}")


def _show_crash_dialog(stack_trace: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox as messagebox_dialog

        root = tk.Tk()
        root.withdraw()
        messagebox_dialog.showerror(
            CRASH_DIALOG_TITLE,
            "The application crashed on startup.\n\n"
            f"{stack_trace}\n\n"
            "A crash log has been saved to:\n"
            f"{CRASH_LOG_PATH}",
        )
        root.destroy()
    except Exception:
        pass


def main() -> None:
    _write_debug("main() entered")
    _set_windows_app_id()
    try:
        _write_debug("importing ModManagerApp...")
        from src.app import ModManagerApp

        _write_debug("import OK, creating app...")
        app = ModManagerApp()
        _write_debug("app created, entering mainloop...")
        _try_enable_heartbeat(app)
        app.mainloop()
        _write_debug("mainloop exited normally")
    except SystemExit as exc:
        _write_debug(f"SystemExit raised (code={exc.code})")
        _write_debug(traceback.format_exc())
    except KeyboardInterrupt:
        _write_debug("KeyboardInterrupt")
    except BaseException:
        stack_trace = traceback.format_exc()
        _write_debug("EXCEPTION in main():")
        _write_debug(stack_trace)
        _show_crash_dialog(stack_trace)
    finally:
        _write_debug("main() exiting")


if __name__ == "__main__":
    main()
