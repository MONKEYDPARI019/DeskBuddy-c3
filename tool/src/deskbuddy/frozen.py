"""Support for running as a ready-made program (PyInstaller).

Two programs are built from the same code:

- `deskbuddy` (console), shipped by the npm package: the full command line (`entry`).
- `DeskBuddy.exe` (windowed, one file), the double-click app: opens the installer window
  (`gui_entry`).

A frozen program has no `python -m esptool`, so esptool runs inside the program itself:
`<program> --run-esptool <esptool args>`. The tool still starts it as a separate process,
exactly like in the pip version, so the output parsing and progress bars stay the same.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Optional

ESPTOOL_FLAG = "--run-esptool"  # hidden: not shown in --help


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def esptool_command() -> list[str]:
    """Command prefix that runs esptool: `python -m esptool`, or this program when frozen."""
    if is_frozen():
        return [sys.executable, ESPTOOL_FLAG]
    return [sys.executable, "-m", "esptool"]


def _unbuffered_stdio() -> None:
    """Like `python -u`: every write reaches the parent at once, including '\\r' progress updates."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        try:
            raw = open(stream.fileno(), "wb", buffering=0, closefd=False)  # noqa: SIM115
        except (AttributeError, OSError, ValueError):
            continue  # no real file behind it (tests, windowed builds): leave it as it is
        wrapped = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", write_through=True)
        setattr(sys, name, wrapped)


def run_esptool_main(args: Sequence[str]) -> int:
    """Run esptool in this process with `args` and return its exit code."""
    import esptool

    if sys.stdout is None:  # windowed program started without a pipe: nowhere to print
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = sys.stdout
    _unbuffered_stdio()
    sys.argv = ["esptool", *args]
    try:
        esptool._main()
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return code if isinstance(code, int) else 1
    except Exception as exc:  # what esptool leaves uncaught: one line instead of a traceback
        print(f"\nA fatal error occurred: {exc}", flush=True)
        return 2
    return 0


def entry(argv: Optional[Sequence[str]] = None) -> int:
    """Program entry point: esptool mode for the hidden flag, the deskbuddy command line otherwise."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == [ESPTOOL_FLAG]:
        return run_esptool_main(args[1:])
    from deskbuddy.cli import main

    return main(args)


# --- the double-click app (DeskBuddy.exe) ------------------------------------------------

SELF_TEST_MS = 3000


def _say(text: str) -> None:
    """Print for a parent that reads our output (CI checks); silent when nobody listens."""
    if sys.stdout is not None:
        print(text, flush=True)


def _attach_std_streams() -> None:
    """A windowed program starts with sys.stdout/stderr = None, even when its parent gave it pipes.

    The installer window runs esptool as a child (`--run-esptool`) and reads its output through
    a pipe, so re-open any handle the parent passed us. Without a parent pipe nothing changes.
    """
    if sys.platform != "win32":
        return
    import ctypes
    import msvcrt

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.GetStdHandle.restype = ctypes.c_void_p
    invalid = ctypes.c_void_p(-1).value
    for name, std_id in (("stdout", -11), ("stderr", -12)):
        if getattr(sys, name) is not None:
            continue
        handle = kernel32.GetStdHandle(std_id)
        if not handle or handle == invalid:
            continue
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_WRONLY)  # type: ignore[attr-defined]
            raw = open(fd, "wb", buffering=0)  # noqa: SIM115
        except OSError:
            continue
        setattr(sys, name, io.TextIOWrapper(raw, encoding="utf-8", errors="replace", write_through=True))


def _log_to_file() -> Optional[Path]:
    """No console: send stray output and Tk callback errors to ~/.deskbuddy/logs/app.log."""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    from deskbuddy.paths import logs_dir

    log_path = logs_dir() / "app.log"
    path: Optional[Path] = log_path
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stream = open(log_path, "w", encoding="utf-8", errors="replace", buffering=1)  # noqa: SIM115
    except OSError:
        path = None
        stream = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    return path


def _enable_dpi_awareness() -> None:
    """Sharp text on scaled (125 %, 150 %) Windows screens instead of a blurry stretched window."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        with contextlib.suppress(AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]


def _fatal(message: str) -> None:
    """Tell the user when the window cannot open at all (there is no console to read)."""
    if sys.platform == "win32":
        import ctypes

        try:
            ctypes.windll.user32.MessageBoxW(None, message, "DeskBuddy", 0x10)  # type: ignore[attr-defined]
            return
        except (AttributeError, OSError):
            pass
    if sys.stderr is not None:
        print(message, file=sys.stderr, flush=True)


def _self_test_esptool() -> bool:
    """Run esptool the way INSTALL does: this program starts itself and reads the child's pipe."""
    from deskbuddy.esptool_compat import run_esptool

    result = run_esptool(["version"])
    lines = [line for line in result.output.splitlines() if line.strip()]
    if result.returncode != 0 or not lines:
        _say(f"self-test failed: esptool child exited {result.returncode}:\n{result.output}")
        return False
    _say(f"esptool child: {lines[-1]}")
    return True


def gui_entry(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point of the double-click app: opens the installer window.

    The same program is also esptool for its own flashing (`--run-esptool`, started by the
    window) and answers `--version` and `--self-test` (open the window briefly) for CI.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    _attach_std_streams()
    if args[:1] == [ESPTOOL_FLAG]:
        return run_esptool_main(args[1:])
    if args[:1] == ["--version"]:
        from deskbuddy import __version__

        _say(f"DeskBuddy {__version__}")
        return 0
    self_test = args[:1] == ["--self-test"]
    if self_test and not _self_test_esptool():
        return 1
    log = _log_to_file()
    try:
        _enable_dpi_awareness()
        from deskbuddy import ui

        ui.main(quit_after_ms=SELF_TEST_MS if self_test else None)
    except Exception as exc:  # the window could not open: say why instead of vanishing
        import traceback

        traceback.print_exc()
        where = f"\n\nDetails: {log}" if log else ""
        _fatal(f"DeskBuddy could not start:\n\n{exc}{where}")
        return 1
    if self_test:
        _say("self-test ok")
    return 0
