"""Where the tool keeps its cache and data: ~/.deskbuddy (override with DESKBUDDY_HOME)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


def data_dir() -> Path:
    override = os.environ.get("DESKBUDDY_HOME")
    return Path(override).expanduser() if override else Path.home() / ".deskbuddy"


def firmware_cache_dir() -> Path:
    return data_dir() / "firmware"


def platformio_dir() -> Path:
    return data_dir() / "platformio"


def logs_dir() -> Path:
    return data_dir() / "logs"


def platformio_venv_dir() -> Path:
    """Private venv holding PlatformIO when the [build] extra is not installed."""
    return platformio_dir() / "venv"


def windows_long_paths_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem")
        with key:
            value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
        return bool(value)
    except OSError:
        return False


def platformio_core_dir(is_windows: bool = os.name == "nt", long_paths: Optional[bool] = None) -> Path:
    """Isolated PLATFORMIO_CORE_DIR (never the user's own ~/.platformio).

    The pioarduino framework package contains paths of ~190 characters. With Windows long
    paths disabled (the default) a core dir under the user profile exceeds MAX_PATH, so a
    short folder at the drive root is used instead, as PlatformIO's own docs recommend.
    DESKBUDDY_PIO_CORE overrides everything (e.g. to put the ~6 GB on another drive).
    """
    override = os.environ.get("DESKBUDDY_PIO_CORE")
    if override:
        return Path(override).expanduser()
    if is_windows and not (windows_long_paths_enabled() if long_paths is None else long_paths):
        drive = os.environ.get("SYSTEMDRIVE", "C:")
        return Path(drive + "\\") / ".deskbuddy" / "platformio"
    return platformio_dir() / "core"
