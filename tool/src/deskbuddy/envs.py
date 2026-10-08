"""Build variants: the user-facing names (usb/battery) and the PlatformIO env names."""

from __future__ import annotations

import re

from deskbuddy.errors import UsageError

ENV_MAP = {"usb": "c3", "battery": "c3-battery"}
PIO_ENVS = tuple(ENV_MAP.values())
CHIP = "esp32c3"

_IMAGE_RE = re.compile(r"^deskbuddy-c3-(?P<env>c3(?:-battery)?)-v(?P<version>\d+\.\d+\.\d+[-+0-9A-Za-z.]*)\.bin$")


def to_pio_env(name: str) -> str:
    """'usb' -> 'c3', 'battery' -> 'c3-battery'. PIO names are accepted as-is."""
    key = name.strip().lower()
    if key in ENV_MAP:
        return ENV_MAP[key]
    if key in PIO_ENVS:
        return key
    raise UsageError(f"Unknown build '{name}'", "Use --env usb or --env battery.")


def to_friendly(pio_env: str) -> str:
    for friendly, env in ENV_MAP.items():
        if env == pio_env:
            return friendly
    return pio_env


def image_filename(pio_env: str, semver: str) -> str:
    return f"deskbuddy-c3-{pio_env}-v{semver}.bin"


def parse_image_filename(name: str) -> tuple[str, str] | None:
    """'deskbuddy-c3-c3-battery-v2.0.0.bin' -> ('c3-battery', '2.0.0')."""
    match = _IMAGE_RE.fullmatch(name)
    return (match.group("env"), match.group("version")) if match else None
