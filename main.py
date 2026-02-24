"""SSBU Mod Manager - Entry Point"""
import sys
import os
import traceback
import atexit
import threading

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Determine base directory (next to .exe or script)
_log_dir = os.path.dirname(os.path.abspath(sys.argv[0] if sys.argv else __file__))
_crash_path = os.path.join(_log_dir, "crash.log")

# Open a persistent crash log file that captures ALL output.
# Keep a reference so it's never garbage-collected.
try:
    _crash_fh = open(_crash_path, "w", encoding="utf-8")
    sys.stderr = _crash_fh
    sys.stdout = _crash_fh          # also capture print() calls
except OSError:
    _crash_fh = None

# Enable faulthandler so C-level crashes (SIGSEGV, SIGABRT, etc.)
# dump a Python traceback to crash.log instead of dying silently.
try:
    import faulthandler
    if _crash_fh:
        faulthandler.enable(file=_crash_fh, all_threads=True)
    else:
        faulthandler.enable(all_threads=True)
except Exception:
    pass

# Catch unhandled exceptions in background threads
def _thread_excepthook(args):
    _write_debug(f"UNCAUGHT THREAD EXCEPTION in {args.thread}:")
    _write_debug("".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))

try:
    threading.excepthook = _thread_excepthook
except AttributeError:
    pass  # Python < 3.8

# Register an atexit handler — this fires during normal interpreter
# shutdown.  If the process is killed externally (e.g. TerminateProcess
# by antivirus) this will NOT run, which is itself diagnostic.
def _at_exit():
    try:
        if _crash_fh and not _crash_fh.closed:
            _crash_fh.write("[atexit] interpreter shutting down\n")
            _crash_fh.flush()
    except Exception:
        pass

atexit.register(_at_exit)

# Trap SIGTERM so we can log it if the OS asks us to terminate.
import signal
def _on_sigterm(signum, frame):
    try:
        if _crash_fh and not _crash_fh.closed:
            _crash_fh.write(f"[SIGNAL] Received signal {signum} — process being terminated\n")
            _crash_fh.flush()
    except Exception:
        pass
    raise SystemExit(128 + signum)

try:
    signal.signal(signal.SIGTERM, _on_sigterm)
except (OSError, ValueError):
    pass


def _write_debug(msg):
    """Write a debug line to crash.log and flush immediately."""
    try:
        if _crash_fh:
            _crash_fh.write(msg + "\n")
            _crash_fh.flush()
    except Exception:
        pass


def main():
    _write_debug("main() entered")
    try:
        _write_debug("importing ModManagerApp...")
        from src.app import ModManagerApp
        _write_debug("import OK, creating app...")
        app = ModManagerApp()
        _write_debug("app created, entering mainloop...")

        app.mainloop()
        _write_debug("mainloop exited normally")
    except SystemExit as e:
        _write_debug(f"SystemExit raised (code={e.code})")
        _write_debug(traceback.format_exc())
    except KeyboardInterrupt:
        _write_debug("KeyboardInterrupt")
    except BaseException:
        _write_debug("EXCEPTION in main():")
        _write_debug(traceback.format_exc())
    except SystemExit as e:
        _write_debug(f"SystemExit raised (code={e.code})")
        _write_debug(traceback.format_exc())
    except KeyboardInterrupt:
        _write_debug("KeyboardInterrupt")
    except BaseException:
        _write_debug("EXCEPTION in main():")
        _write_debug(traceback.format_exc())

        # Show a messagebox so the user sees the error
        try:
            import tkinter as tk
            from tkinter import messagebox as mb
            root = tk.Tk()
            root.withdraw()
            mb.showerror(
                "SSBU Mod Manager - Crash",
                f"The application crashed on startup.\n\n"
                f"{traceback.format_exc()}\n\n"
                f"A crash log has been saved to:\n{_crash_path}",
            )
            root.destroy()
        except Exception:
            pass
    finally:
        _write_debug("main() exiting")


if __name__ == "__main__":
    main()
