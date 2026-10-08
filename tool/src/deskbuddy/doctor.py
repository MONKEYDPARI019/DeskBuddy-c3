"""`deskbuddy doctor`: environment checks, each with a fix hint."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import Any, Callable, Optional

from deskbuddy import ports, serial_io
from deskbuddy.errors import DeskBuddyError

MIN_PYTHON = (3, 9)
_REINSTALL = 'pip install --upgrade "git+https://github.com/MONKEYDPARI019/DeskBuddy-C3#subdirectory=tool"'


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    hint: str = ""


@dataclass
class DoctorDeps:
    python_version: tuple[int, ...]
    package_version: Callable[[str], str]
    lister: Optional[ports.Lister]
    opener: Callable[[str], Any]
    github_ping: Callable[[], None]
    platform: str
    user_groups: Callable[[], list[str]]


def current_user_groups() -> list[str]:
    """Group names of the current user (POSIX only; empty list elsewhere)."""
    try:
        import grp

        return [grp.getgrgid(gid).gr_name for gid in os.getgroups()]
    except (ImportError, KeyError, OSError, AttributeError):
        return []


def default_deps() -> DoctorDeps:
    from deskbuddy.github import GitHubClient

    def ping() -> None:
        GitHubClient(timeout=8).get_json("")

    return DoctorDeps(
        python_version=tuple(sys.version_info[:3]),
        package_version=_pkg_version,
        lister=None,
        opener=serial_io.open_serial,
        github_ping=ping,
        platform=sys.platform,
        user_groups=current_user_groups,
    )


def _check_python(version: tuple[int, ...]) -> CheckResult:
    text = ".".join(str(v) for v in version)
    if tuple(version[:2]) >= MIN_PYTHON:
        return CheckResult("Python", True, text)
    return CheckResult("Python", False, f"{text} is too old", "Install Python 3.9 or newer from python.org.")


def _check_package(name: str, getter: Callable[[str], str]) -> CheckResult:
    try:
        return CheckResult(name, True, getter(name))
    except PackageNotFoundError:
        return CheckResult(name, False, "not installed", f"Reinstall the tool: {_REINSTALL}")


def _check_board(found: list[ports.BoardPort]) -> tuple[CheckResult, Optional[str]]:
    candidates = ports.board_candidates(found)
    if not candidates:
        return (
            CheckResult(
                "Board",
                False,
                "no ESP32-C3 found",
                "Plug the board in with a data USB cable (not charge-only); try another USB port.",
            ),
            None,
        )
    names = ", ".join(c.describe() for c in candidates)
    return CheckResult("Board", True, names), candidates[0].device


def _check_port(port: Optional[str], opener: Callable[[str], Any]) -> CheckResult:
    if port is None:
        return CheckResult("Port", False, "skipped (no board)", "Fix the board check first.")
    try:
        opener(port).close()
    except DeskBuddyError as exc:
        return CheckResult("Port", False, exc.message, exc.hint)
    return CheckResult("Port", True, f"{port} is free")


def _check_github(ping: Callable[[], None]) -> CheckResult:
    try:
        ping()
    except DeskBuddyError as exc:
        return CheckResult("GitHub", False, exc.message, exc.hint)
    return CheckResult("GitHub", True, "reachable")


def _check_permissions(platform: str, groups: Callable[[], list[str]]) -> CheckResult:
    if not platform.startswith("linux"):
        return CheckResult("Serial permissions", True, "not needed on this OS")
    if {"dialout", "uucp"} & set(groups()):
        return CheckResult("Serial permissions", True, "user is in the dialout group")
    return CheckResult(
        "Serial permissions",
        False,
        "user is not in the dialout group",
        "Run: sudo usermod -aG dialout $USER   then log out and back in.",
    )


def run_checks(deps: DoctorDeps) -> list[CheckResult]:
    board_result, port = _check_board(ports.list_ports(deps.lister))
    return [
        _check_python(deps.python_version),
        _check_package("esptool", deps.package_version),
        _check_package("pyserial", deps.package_version),
        board_result,
        _check_port(port, deps.opener),
        _check_github(deps.github_ping),
        _check_permissions(deps.platform, deps.user_groups),
    ]


def format_results(results: list[CheckResult], ascii_only: bool = False) -> str:
    ok_mark, bad_mark = ("[ok]", "[!!]") if ascii_only else ("✓", "✗")
    lines = []
    for r in results:
        lines.append(f"{ok_mark if r.ok else bad_mark} {r.name}: {r.detail}")
        if not r.ok and r.hint:
            lines.append(f"    -> {r.hint}")
    return "\n".join(lines)
