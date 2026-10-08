from __future__ import annotations

from types import SimpleNamespace

import pytest

from deskbuddy import ports
from deskbuddy.errors import NoBoardError, UsageError


def info(device, vid=None, pid=None, desc="n/a", serial_number=None):
    return SimpleNamespace(device=device, vid=vid, pid=pid, description=desc, serial_number=serial_number)


RAW = [
    info("COM3", desc="Bluetooth link"),
    info("COM7", 0x1A86, 0x7523, "USB-SERIAL CH340"),
    info("COM9", 0x303A, 0x1001, "USB Serial Device", "14:63:93"),
    info("COM5", 0x10C4, 0xEA60, "CP210x UART"),
]


def test_classify():
    assert ports.classify(0x303A, 0x1001) == ports.KIND_ESP32C3
    assert ports.classify(0x10C4, 0xEA60) == ports.KIND_POSSIBLE
    assert ports.classify(0x1A86, 0x7523) == ports.KIND_POSSIBLE
    assert ports.classify(None, None) == ports.KIND_OTHER


def test_list_ports_ranks_esp32c3_first():
    result = ports.list_ports(lambda: RAW)
    assert [p.device for p in result] == ["COM9", "COM5", "COM7", "COM3"]
    assert result[0].label == "ESP32-C3"
    assert result[1].label == "possible ESP32 (CP210x)"
    assert result[2].label == "possible ESP32 (CH340)"
    assert result[3].label == ""


def test_board_candidates_prefers_esp32c3():
    assert [p.device for p in ports.board_candidates(ports.list_ports(lambda: RAW))] == ["COM9"]


def test_board_candidates_falls_back_to_possible():
    raw = [r for r in RAW if r.device != "COM9"]
    assert [p.device for p in ports.board_candidates(ports.list_ports(lambda: raw))] == ["COM5", "COM7"]


def test_choose_port_explicit_wins():
    assert ports.choose_port("COM42", []) == "COM42"


def test_choose_port_single_board():
    assert ports.choose_port(None, ports.list_ports(lambda: RAW)) == "COM9"


def test_choose_port_none_found():
    with pytest.raises(NoBoardError, match="No DeskBuddy"):
        ports.choose_port(None, ports.list_ports(lambda: [info("COM3")]))


def test_choose_port_several_non_interactive_fails():
    raw = [*RAW, info("COM11", 0x303A, 0x1001)]
    with pytest.raises(UsageError, match="Several boards") as excinfo:
        ports.choose_port(None, ports.list_ports(lambda: raw))
    assert "--port" in excinfo.value.hint


def test_choose_port_several_asks():
    raw = [*RAW, info("COM11", 0x303A, 0x1001)]
    seen = []

    def ask(candidates):
        seen.extend(c.device for c in candidates)
        return candidates[1]

    assert ports.choose_port(None, ports.list_ports(lambda: raw), ask=ask) == "COM9"
    assert seen == ["COM11", "COM9"]


def test_describe():
    port = ports.list_ports(lambda: RAW)[0]
    assert port.describe() == "COM9 - ESP32-C3 (USB Serial Device)"


def test_default_lister_uses_pyserial(monkeypatch):
    monkeypatch.setattr(ports, "comports", lambda: [info("X", 0x303A, 1)])
    assert ports.list_ports()[0].device == "X"
