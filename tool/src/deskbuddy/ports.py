"""Find serial ports and rank the ones that look like a DeskBuddy (ESP32-C3)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Callable, Optional

from serial.tools.list_ports import comports

from deskbuddy.errors import NoBoardError, UsageError

ESPRESSIF_VID = 0x303A
USB_UART_CHIPS = {0x10C4: "CP210x", 0x1A86: "CH340"}

KIND_ESP32C3 = "esp32c3"
KIND_POSSIBLE = "possible"
KIND_OTHER = "other"
_RANK = {KIND_ESP32C3: 0, KIND_POSSIBLE: 1, KIND_OTHER: 2}

Lister = Callable[[], Iterable[Any]]
Asker = Callable[[Sequence["BoardPort"]], "BoardPort"]


@dataclass(frozen=True)
class BoardPort:
    device: str
    description: str
    vid: Optional[int]
    pid: Optional[int]
    serial_number: Optional[str]
    kind: str

    @property
    def label(self) -> str:
        if self.kind == KIND_ESP32C3:
            return "ESP32-C3"
        if self.kind == KIND_POSSIBLE:
            return f"possible ESP32 ({USB_UART_CHIPS.get(self.vid or 0, 'USB-UART')})"
        return ""

    def describe(self) -> str:
        label = f" - {self.label}" if self.label else ""
        return f"{self.device}{label} ({self.description})"


def classify(vid: Optional[int], pid: Optional[int]) -> str:
    if vid == ESPRESSIF_VID:
        return KIND_ESP32C3
    if vid in USB_UART_CHIPS:
        return KIND_POSSIBLE
    return KIND_OTHER


def list_ports(lister: Optional[Lister] = None) -> list[BoardPort]:
    """All serial ports, ESP32-C3 boards first, then possible ESP32s, then the rest."""
    raw = (lister or comports)()
    found = [
        BoardPort(
            device=p.device,
            description=p.description or "",
            vid=p.vid,
            pid=p.pid,
            serial_number=getattr(p, "serial_number", None),
            kind=classify(p.vid, p.pid),
        )
        for p in raw
    ]
    return sorted(found, key=lambda p: (_RANK[p.kind], p.device))


def board_candidates(found: Sequence[BoardPort]) -> list[BoardPort]:
    """ESP32-C3 boards if any are plugged in, otherwise the possible ESP32s."""
    exact = [p for p in found if p.kind == KIND_ESP32C3]
    return exact or [p for p in found if p.kind == KIND_POSSIBLE]


def choose_port(requested: Optional[str], found: Sequence[BoardPort], ask: Optional[Asker] = None) -> str:
    """Pick the port to use. Asks via `ask` when several boards match, or fails if non-interactive."""
    if requested:
        return requested
    candidates = board_candidates(found)
    if not candidates:
        raise NoBoardError(
            "No DeskBuddy board found",
            "Plug the board in with a data USB cable (not charge-only), then run 'deskbuddy ports'.",
        )
    if len(candidates) == 1:
        return candidates[0].device
    if ask is None:
        names = ", ".join(c.device for c in candidates)
        raise UsageError(
            f"Several boards found ({names})", "Choose one with --port, e.g. --port " + candidates[0].device
        )
    return ask(candidates).device
