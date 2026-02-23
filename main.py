"""SSBU Mod Manager - Entry Point"""
import sys
import os
import traceback

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Redirect stderr to a file so we capture errors even in --windowed mode
_log_dir = os.path.dirname(os.path.abspath(sys.argv[0] if sys.argv else __file__))
try:
    sys.stderr = open(os.path.join(_log_dir, "crash.log"), "w", encoding="utf-8")
except OSError:
    pass


def main():
    try:
        from src.app import ModManagerApp
        app = ModManagerApp()
        app.mainloop()
    except Exception:
        # Write crash log next to the executable / script so the user can
        # report issues even when running the --windowed PyInstaller build
        # (which has no console).
        crash_path = os.path.join(
            os.path.dirname(os.path.abspath(sys.argv[0] if sys.argv else __file__)),
            "crash.log",
        )
        try:
            with open(crash_path, "w", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except OSError:
            pass

        # Also try a tkinter messagebox so the user sees the error
        try:
            import tkinter as tk
            from tkinter import messagebox as mb
            root = tk.Tk()
            root.withdraw()
            mb.showerror(
                "SSBU Mod Manager - Crash",
                f"The application crashed on startup.\n\n"
                f"{traceback.format_exc()}\n\n"
                f"A crash log has been saved to:\n{crash_path}",
            )
            root.destroy()
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
