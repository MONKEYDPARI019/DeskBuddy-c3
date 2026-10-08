"""Firmware version strings: FW_VERSION "c3-2.0.0" <-> semver "2.0.0" <-> tag "v2.0.0"."""

from __future__ import annotations

import re
from pathlib import Path

from deskbuddy.errors import DeskBuddyError

_SEMVER = r"(\d+)\.(\d+)\.(\d+)([-+][0-9A-Za-z.\-+]*)?"
_FW_RE = re.compile(rf"^(?:c3-)?v?(?P<semver>{_SEMVER})$")
_DEFINE_RE = re.compile(r'^\s*#define\s+FW_VERSION\s+"([^"]+)"', re.MULTILINE)


def parse_fw_version(value: str) -> str:
    """'c3-2.0.0' -> '2.0.0'. Also accepts '2.0.0' and 'v2.0.0'."""
    match = _FW_RE.match(value.strip())
    if not match:
        raise DeskBuddyError(
            f"'{value}' is not a valid firmware version",
            "Use the form c3-MAJOR.MINOR.PATCH (e.g. c3-2.0.0) or vMAJOR.MINOR.PATCH.",
        )
    return match.group("semver")


def to_tag(value: str) -> str:
    """'2.0.0' / 'v2.0.0' / 'c3-2.0.0' -> 'v2.0.0'."""
    return "v" + parse_fw_version(value)


def version_key(value: str) -> tuple[int, int, int, int]:
    """Sort key: releases before pre-releases of the same number; invalid strings sort first."""
    try:
        semver = parse_fw_version(value)
    except DeskBuddyError:
        return (-1, -1, -1, -1)
    match = re.match(_SEMVER, semver)
    assert match is not None
    major, minor, patch, suffix = match.groups()
    return (int(major), int(minor), int(patch), 0 if suffix else 1)


def read_fw_version(config_h: Path) -> str:
    """Read FW_VERSION from firmware/src/config.h and return the semver part."""
    try:
        text = config_h.read_text(encoding="utf-8")
    except OSError as exc:
        raise DeskBuddyError(f"Cannot read {config_h}: {exc.strerror}", "Check the firmware path.") from exc
    match = _DEFINE_RE.search(text)
    if not match:
        raise DeskBuddyError(f"No FW_VERSION define found in {config_h}", 'Expected: #define FW_VERSION "c3-X.Y.Z"')
    return parse_fw_version(match.group(1))
