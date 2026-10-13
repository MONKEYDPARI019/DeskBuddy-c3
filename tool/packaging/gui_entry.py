"""PyInstaller entry point for the double-click app, DeskBuddy.exe (see scripts/build_app.py --gui)."""

import sys

from deskbuddy.frozen import gui_entry

if __name__ == "__main__":
    sys.exit(gui_entry())
