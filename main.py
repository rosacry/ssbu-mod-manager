"""SSBU Mod Manager - Entry Point"""
import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.app import ModManagerApp


def main():
    app = ModManagerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
