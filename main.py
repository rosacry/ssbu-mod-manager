"""SSBU Mod Manager - Entry Point"""
import sys
import os
import traceback

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
    except Exception:
        _write_debug("EXCEPTION in main():")
        _write_debug(traceback.format_exc())

        # Also write a dedicated crash log
        try:
            with open(_crash_path, "a", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except OSError:
            pass

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
        raise


if __name__ == "__main__":
    main()
