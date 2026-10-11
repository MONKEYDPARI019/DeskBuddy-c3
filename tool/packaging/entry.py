"""PyInstaller entry point for the ready-made `deskbuddy` program (see scripts/build_app.py)."""

import sys

from deskbuddy.frozen import entry

if __name__ == "__main__":
    sys.exit(entry())
