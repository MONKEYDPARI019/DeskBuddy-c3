"""Support for running as a ready-made program (PyInstaller), as shipped by the npm package.

A frozen program has no `python -m esptool`, so esptool runs inside the program itself:
`deskbuddy --run-esptool <esptool args>`. The tool still starts it as a separate process,
exactly like in the pip version, so the output parsing and progress bars stay the same.
"""

from __future__ import annotations

import io
import sys
from collections.abc import Sequence
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
