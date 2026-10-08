"""Run esptool as a subprocess, hiding the v4/v5 command-line differences.

esptool 5.x (Python >= 3.10) renamed commands and choice values to kebab-case
(`write-flash`, `merge-bin`, `default-reset`); 4.x uses snake_case. Short options
(-e, -o, -fm, -fs) are identical in both. Running `python -m esptool` in a
subprocess with NO_COLOR=1 gives stable, line-based output for both majors, which
the progress parser relies on.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import Any, Callable, Optional

from deskbuddy.errors import FlashError

LineCallback = Callable[[str], None]


@dataclass(frozen=True)
class Syntax:
    major: int
    write_flash: str
    merge_bin: str
    default_reset: str
    hard_reset: str


@dataclass(frozen=True)
class EsptoolResult:
    returncode: int
    output: str


def syntax_for(major: int) -> Syntax:
    if major >= 5:
        return Syntax(major, "write-flash", "merge-bin", "default-reset", "hard-reset")
    return Syntax(major, "write_flash", "merge_bin", "default_reset", "hard_reset")


def major_of(version: str) -> int:
    head = version.split(".", 1)[0]
    return int(head) if head.isdigit() else 5


def installed_version(getter: Optional[Callable[[str], str]] = None) -> str:
    try:
        return (getter or _pkg_version)("esptool")
    except PackageNotFoundError as exc:
        raise FlashError(
            "esptool is not installed in this Python environment",
            'Reinstall the tool: pip install "git+https://github.com/MONKEYDPARI019/DeskBuddy-C3#subdirectory=tool"',
        ) from exc


def current_syntax() -> Syntax:
    return syntax_for(major_of(installed_version()))


def esptool_command() -> list[str]:
    return [sys.executable, "-m", "esptool"]


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    for secret in ("GITHUB_TOKEN", "GH_TOKEN", "GH_ENTERPRISE_TOKEN"):
        env.pop(secret, None)
    env.update({"NO_COLOR": "1", "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "TERM": "dumb"})
    return env


def run_esptool(
    args: list[str],
    on_line: Optional[LineCallback] = None,
    popen: Callable[..., Any] = subprocess.Popen,
) -> EsptoolResult:
    """Run esptool with `args`, streaming each output line to `on_line`. Never uses a shell."""
    try:
        proc = popen(
            [*esptool_command(), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=_child_env(),
            shell=False,
        )
    except OSError as exc:
        raise FlashError(f"Could not start esptool: {exc}", "Reinstall the deskbuddy tool and try again.") from exc
    from deskbuddy.builder import reap

    lines: list[str] = []
    # text mode uses universal newlines, so '\r'-only progress updates also arrive as lines
    try:
        for raw in proc.stdout:
            line = raw.rstrip("\r\n")
            lines.append(line)
            if on_line:
                on_line(line)
        returncode = proc.wait()
    finally:
        reap(proc)
    return EsptoolResult(returncode, "".join(f"{line}\n" for line in lines))
