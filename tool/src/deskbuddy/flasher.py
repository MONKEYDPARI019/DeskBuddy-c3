"""Write a merged firmware image to an ESP32-C3 with baud fallback and BOOT-button retries."""

from __future__ import annotations

import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Union

from deskbuddy.envs import CHIP
from deskbuddy.errors import FlashError, port_busy
from deskbuddy.esptool_compat import EsptoolResult, Syntax

BAUD_RATES = (921600, 460800, 115200)
BOOT_RETRIES = 3
BOOT_HINT = "Hold BOOT, tap RESET, release BOOT"
MERGED_IMAGE_OFFSET = "0x0"
NVS_START = 0x9000  # nvs partition (firmware/partitions.csv): 0x9000, size 0x5000
NVS_END = 0xE000
MIN_IMAGE_SIZE = 64 * 1024  # bootloader + partition table + app: always larger than this
ESP_IMAGE_MAGIC = 0xE9

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_PROGRESS_RE = re.compile(r"Writing at 0x[0-9a-fA-F]+.*?(\d{1,3}(?:\.\d+)?)\s*%")

Runner = Callable[..., EsptoolResult]
Segments = list[tuple[str, Path]]
Waiter = Callable[[str], Optional[str]]


class Failure(Enum):
    PORT_BUSY = "port busy"
    PORT_MISSING = "port missing"
    NO_DOWNLOAD_MODE = "no download mode"
    COMM_ERROR = "communication error"
    OTHER = "other"


_FAILURE_PATTERNS: tuple[tuple[Failure, tuple[str, ...]], ...] = (
    (Failure.PORT_BUSY, ("access is denied", "permissionerror", "resource busy", "could not exclusively lock")),
    (Failure.PORT_MISSING, ("filenotfounderror", "cannot find the file", "no such file or directory")),
    (Failure.NO_DOWNLOAD_MODE, ("failed to connect", "wrong boot mode", "no serial data received", "download mode")),
    (
        Failure.COMM_ERROR,
        (
            "timed out",
            "packet content transfer stopped",
            "invalid head of packet",
            "serial exception",
            "write timeout",
            "chip stopped responding",
            "md5 of file does not match",
            "corrupt",
        ),
    ),
)


@dataclass(frozen=True)
class FlashOutcome:
    port: str
    baud: int


def _noop(_: object) -> None:
    return None


@dataclass
class FlashCallbacks:
    progress: Callable[[float], None] = field(default=_noop)
    status: Callable[[str], None] = field(default=_noop)
    boot_hint: Callable[[str], None] = field(default=_noop)
    output: Callable[[str], None] = field(default=_noop)


def parse_progress(line: str) -> Optional[float]:
    """Percentage from an esptool v4 ('... (5 %)') or v5 ('... 14.6% ...') progress line."""
    match = _PROGRESS_RE.search(_ANSI_RE.sub("", line))
    return float(match.group(1)) if match else None


def classify_failure(output: str) -> Failure:
    text = output.lower()
    for kind, markers in _FAILURE_PATTERNS:
        if any(marker in text for marker in markers):
            return kind
    return Failure.OTHER


def baud_ladder(requested: Optional[int]) -> tuple[int, ...]:
    """921600 -> 460800 -> 115200, or the requested rate followed by the safe 115200."""
    if requested is None:
        return BAUD_RATES
    return (requested,) if requested == 115200 else (requested, 115200)


def write_flash_args(syntax: Syntax, port: str, baud: int, image: Union[str, Path, Segments], erase: bool) -> list[str]:
    args = [
        "--chip",
        CHIP,
        "--port",
        port,
        "--baud",
        str(baud),
        "--before",
        syntax.default_reset,
        "--after",
        syntax.hard_reset,
        syntax.write_flash,
    ]
    if erase:
        args.append("-e")
    segments = image if isinstance(image, list) else [(MERGED_IMAGE_OFFSET, Path(image))]
    for offset, path in segments:
        args += [offset, str(path)]
    return args


def flash_segments(image: Path, erase: bool, workdir: Path) -> Segments:
    """Split the merged image around the NVS partition so saved settings survive a flash.

    The merged image is padded with 0xFF from the partition table up to boot_app0, which covers
    NVS (0x9000-0xE000 in firmware/partitions.csv). Writing it whole would wipe WiFi credentials
    and the link mode. Unless --erase was asked for, write [0x0, NVS) and [NVS end, ...) instead.
    The split only happens if that region of the image really is empty (all 0xFF).
    """
    whole: Segments = [(MERGED_IMAGE_OFFSET, image)]
    if erase or not image.is_file():
        return whole
    data = image.read_bytes()
    if len(data) <= NVS_END or data[NVS_START:NVS_END].count(0xFF) != NVS_END - NVS_START:
        return whole
    head, tail = workdir / "part-0x0.bin", workdir / f"part-{NVS_END:#x}.bin"
    head.write_bytes(data[:NVS_START])
    tail.write_bytes(data[NVS_END:])
    return [(MERGED_IMAGE_OFFSET, head), (hex(NVS_END), tail)]


def check_image(image: Path) -> None:
    """Basic sanity check that `image` is a merged ESP image starting with the bootloader."""
    if not image.is_file():
        raise FlashError(
            f"Firmware file {image} not found", "Check the path, or omit --file to use the latest release."
        )
    if image.stat().st_size < MIN_IMAGE_SIZE:
        raise FlashError(
            f"{image.name} is too small to be a DeskBuddy firmware image", "Use a merged .bin from a release."
        )
    with image.open("rb") as handle:
        first = handle.read(1)
    if not first or first[0] != ESP_IMAGE_MAGIC:
        raise FlashError(
            f"{image.name} does not look like a merged ESP32 image (it must start at offset 0x0)",
            "Use the deskbuddy-c3-*.bin file from a release, not firmware.bin from the build folder.",
        )


def _last_lines(output: str, count: int = 6) -> str:
    lines = [line for line in output.splitlines() if line.strip()]
    return "\n".join(lines[-count:])


def _attempt_all_bauds(
    image: Segments, port: str, erase: bool, runner: Runner, syntax: Syntax, bauds: Sequence[int], cb: FlashCallbacks
) -> Optional[int]:
    """Try each baud rate. Returns the baud that worked, or None if the chip is not in download mode."""

    def on_line(line: str) -> None:
        cb.output(line)
        pct = parse_progress(line)
        if pct is not None:
            cb.progress(pct)

    last_output = ""
    for baud in bauds:
        cb.status(f"Writing firmware to {port} at {baud} baud...")
        result = runner(write_flash_args(syntax, port, baud, image, erase), on_line=on_line)
        if result.returncode == 0:
            return baud
        last_output = result.output
        kind = classify_failure(result.output)
        if kind is Failure.PORT_BUSY:
            raise port_busy(port)
        if kind in (Failure.NO_DOWNLOAD_MODE, Failure.PORT_MISSING):
            return None
        if kind is Failure.OTHER:
            raise FlashError("esptool failed", _last_lines(result.output))
        cb.status(f"Connection unstable at {baud} baud, trying slower...")
    raise FlashError(
        "Flashing failed at every speed",
        "Try a different USB cable or port (avoid hubs).\n" + _last_lines(last_output, 3),
    )


def flash_image(
    image: Union[str, Path],
    port: str,
    *,
    runner: Runner,
    waiter: Waiter,
    syntax: Syntax,
    callbacks: Optional[FlashCallbacks] = None,
    erase: bool = False,
    bauds: Sequence[int] = BAUD_RATES,
    boot_retries: int = BOOT_RETRIES,
) -> FlashOutcome:
    """Flash the merged image at 0x0. Falls back to slower bauds on communication errors; if the
    chip will not enter download mode, shows the BOOT hint, waits for re-enumeration and retries."""
    cb = callbacks or FlashCallbacks()
    with tempfile.TemporaryDirectory(prefix="deskbuddy-") as tmp:
        segments = flash_segments(Path(image), erase, Path(tmp))
        if len(segments) > 1:
            cb.status("Keeping saved settings (WiFi, link mode); use --erase to reset them.")
        return _flash_with_retries(segments, port, runner, waiter, syntax, cb, erase, bauds, boot_retries)


def _flash_with_retries(
    segments: Segments,
    port: str,
    runner: Runner,
    waiter: Waiter,
    syntax: Syntax,
    cb: FlashCallbacks,
    erase: bool,
    bauds: Sequence[int],
    boot_retries: int,
) -> FlashOutcome:
    current_port = port
    for attempt in range(boot_retries + 1):
        baud = _attempt_all_bauds(segments, current_port, erase, runner, syntax, bauds, cb)
        if baud is not None:
            cb.progress(100.0)
            return FlashOutcome(port=current_port, baud=baud)
        if attempt == boot_retries:
            break
        cb.boot_hint(BOOT_HINT)
        cb.status(f"Waiting for the board to reconnect (attempt {attempt + 2} of {boot_retries + 1})...")
        current_port = waiter(current_port) or current_port
    raise FlashError(
        "The board would not enter download mode",
        f"{BOOT_HINT}, then run the command again. Also try another USB cable.",
    )
