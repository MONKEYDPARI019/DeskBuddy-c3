"""Isolated PlatformIO: find the firmware project, provision PlatformIO, run commands.

The user's own PlatformIO install is never used or modified: builds run with their own
PLATFORMIO_CORE_DIR (see paths.platformio_core_dir) and, unless the [build] extra is installed,
a private venv in ~/.deskbuddy/platformio/venv.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from deskbuddy.errors import BuildError, UsageError

PIO_SPEC = "platformio>=6.1,<7"
READY_MARKER = ".deskbuddy-ready"
# idf_tools.py (used by pioarduino to install toolchains) refuses to run when it sees MSYS.
_DROP_ENV = (
    "MSYSTEM",
    "MSYSTEM_CARCH",
    "MSYSTEM_CHOST",
    "MSYSTEM_PREFIX",
    "MINGW_PREFIX",
    "PLATFORMIO_CORE_DIR",
    # never hand tokens to build scripts (PlatformIO runs the project's own Python code)
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GH_ENTERPRISE_TOKEN",
)

LineCallback = Callable[[str], None]
CommandRunner = Callable[..., int]


def find_project(path: Optional[Path]) -> Path:
    """Return the PlatformIO project folder: `path` itself, or `path`/firmware (repo root)."""
    base = (path or Path.cwd()).expanduser()
    for candidate in (base, base / "firmware"):
        if (candidate / "platformio.ini").is_file() and (candidate / "src" / "config.h").is_file():
            return candidate
    raise UsageError(
        f"No DeskBuddy firmware project found in {base}",
        "Run inside the DeskBuddy-C3 folder, pass --path, or download the source with 'deskbuddy get'.",
    )


def child_env(core_dir: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _DROP_ENV}
    env["PLATFORMIO_CORE_DIR"] = str(core_dir)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def stream_command(
    cmd: list[str], cwd: Optional[Path], env: Optional[dict[str, str]], on_line: Optional[LineCallback] = None
) -> int:
    """Run `cmd` (no shell), stream merged stdout/stderr lines, return the exit code."""
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,
        )
    except OSError as exc:
        raise BuildError(f"Could not run {Path(cmd[0]).name}: {exc}", "Check your Python installation.") from exc
    assert proc.stdout is not None
    try:
        for raw in proc.stdout:
            if on_line:
                on_line(raw.rstrip("\r\n"))
        return proc.wait()
    finally:
        reap(proc)


def reap(proc: Any) -> None:
    """Make sure a child process is gone (e.g. after Ctrl+C or an exception in a callback)."""
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    if proc.stdout is not None:
        proc.stdout.close()


def _has_platformio_module() -> bool:
    return importlib.util.find_spec("platformio") is not None


def platformio_command(
    venv: Path,
    has_module: Callable[[], bool] = _has_platformio_module,
    runner: Optional[CommandRunner] = None,
    status: Optional[LineCallback] = None,
) -> list[str]:
    """Command prefix that runs PlatformIO, installing it into a private venv on first use."""
    if has_module():
        return [sys.executable, "-m", "platformio"]
    run = runner or (lambda cmd, **kw: stream_command(cmd, cwd=None, env=None, on_line=kw.get("on_line")))
    py = venv_python(venv)
    marker = venv / READY_MARKER
    if not (py.is_file() and marker.is_file() and marker.read_text().strip() == PIO_SPEC):
        if status:
            status(f"Installing PlatformIO into {venv} (first use, takes a few minutes)...")
        steps = [
            [sys.executable, "-m", "venv", str(venv)],
            [str(py), "-m", "pip", "install", "--disable-pip-version-check", "--quiet", PIO_SPEC],
        ]
        for step in steps:
            if (step[0] != sys.executable and not py.is_file()) or run(step, on_line=status) != 0:
                raise BuildError(
                    "Could not set up PlatformIO for building",
                    "Check your internet connection. On Debian/Ubuntu install venv support: "
                    'sudo apt install python3-venv. Or: pip install "deskbuddy-cli[build]".',
                )
        marker.write_text(PIO_SPEC)
    return [str(py), "-m", "platformio"]
