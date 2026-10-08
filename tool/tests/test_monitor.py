from __future__ import annotations

import pytest
import serial

from deskbuddy import monitor
from deskbuddy.errors import NoBoardError, PortBusyError
from tests.fakes import ScriptedSerial


@pytest.mark.parametrize(
    ("line", "colour"),
    [
        ("[BLE] advertising as 'DeskBuddy-C3'", "blue"),
        ("[WiFi] online: 192.168.1.7", "green"),
        ("[OLED] retrying every 5 s", "yellow"),
        ("uptime 12 s, last reset: CRASH (panic)", "red"),
        ("assert failed: foo.cpp:12", "red"),
        ("[WiFi] mDNS failed: error 3", "red"),
        ("[BLE] FAILED to advertise", "red"),
        ("Guru Meditation Error: Core 0 panic'ed", "red"),
        ("link     ble, bluetooth advertising, 0 app(s)", None),
    ],
)
def test_line_colour(line, colour):
    assert monitor.line_colour(line) == colour


def test_colourise_only_when_enabled():
    assert monitor.colourise("[BLE] hi", enabled=False) == "[BLE] hi"
    coloured = monitor.colourise("[BLE] hi", enabled=True)
    assert coloured.startswith("\x1b[34m") and coloured.endswith("\x1b[0m")
    assert monitor.colourise("plain", enabled=True) == "plain"


def test_line_buffer_splits_and_keeps_partial():
    buf = monitor.LineBuffer()
    assert buf.feed(b"hello\r\nwor") == ["hello"]
    assert buf.feed(b"ld\n\n") == ["world", ""]
    assert buf.feed(b"tail") == []
    assert buf.flush() == ["tail"]
    assert buf.flush() == []


def test_line_buffer_handles_utf8_split_across_chunks():
    buf = monitor.LineBuffer()
    data = "café\n".encode()
    assert buf.feed(data[:4]) == []
    assert buf.feed(data[4:]) == ["café"]


def test_line_buffer_caps_runaway_lines():
    buf = monitor.LineBuffer(max_len=8)
    assert buf.feed(b"0123456789") == ["0123456789"]


class Harness:
    """Drives a ReconnectingMonitor with scripted port opens."""

    def __init__(self, opens, resolve=lambda: "COM9"):
        self.opens = list(opens)
        self.lines = []
        self.statuses = []
        self.slept = 0.0
        self.mon = monitor.ReconnectingMonitor(
            resolve_port=resolve,
            opener=self._open,
            on_line=self.lines.append,
            on_status=self.statuses.append,
            sleep=self._sleep,
        )

    def _open(self, port):
        item = self.opens.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def _sleep(self, seconds):
        self.slept += seconds


def test_monitor_connects_and_reads_lines():
    h = Harness([ScriptedSerial([b"=== DeskBuddy C3 c3-2.0.0 (USB build) ===\n"])])
    assert h.mon.step() is monitor.State.CONNECTED
    assert h.statuses == ["connected to COM9"]
    h.mon.step()
    assert h.lines == ["=== DeskBuddy C3 c3-2.0.0 (USB build) ==="]


def test_monitor_first_open_busy_is_fatal():
    h = Harness([PortBusyError("COM9 is busy")])
    with pytest.raises(PortBusyError):
        h.mon.step()


def test_monitor_first_open_missing_board_waits():
    h = Harness([NoBoardError("COM9 not found"), ScriptedSerial()])
    assert h.mon.step() is monitor.State.WAITING
    assert h.statuses == ["waiting for board..."]
    assert h.mon.step() is monitor.State.CONNECTED


def test_monitor_no_port_at_all_waits():
    h = Harness([], resolve=lambda: None)
    assert h.mon.step() is monitor.State.WAITING
    assert h.mon.step() is monitor.State.WAITING
    assert h.statuses == ["waiting for board..."]  # said once, not every poll
    assert h.slept > 0


def test_monitor_reconnects_after_reset():
    first = ScriptedSerial([b"before\n", serial.SerialException("ClearCommError failed")])
    second = ScriptedSerial([b"after\n"])
    h = Harness([first, NoBoardError("gone"), PortBusyError("still busy"), second])
    h.mon.step()  # connect
    h.mon.step()  # 'before'
    assert h.mon.step() is monitor.State.WAITING  # read error -> board reset
    assert not first.is_open
    assert h.mon.step() is monitor.State.WAITING  # port missing
    assert h.mon.step() is monitor.State.WAITING  # busy while re-enumerating is not fatal later
    assert h.mon.step() is monitor.State.CONNECTED
    h.mon.step()
    assert h.lines == ["before", "after"]
    assert h.statuses == ["connected to COM9", "board disconnected - waiting for board...", "connected to COM9"]


def test_monitor_flushes_partial_line_on_disconnect():
    h = Harness([ScriptedSerial([b"no newline", OSError("gone")])])
    h.mon.step()
    h.mon.step()
    h.mon.step()
    assert h.lines == ["no newline"]


def test_monitor_send_when_connected():
    port = ScriptedSerial()
    h = Harness([port])
    h.mon.step()
    assert h.mon.send("status") is True
    assert bytes(port.written) == b"status\n"


def test_monitor_send_when_disconnected():
    h = Harness([], resolve=lambda: None)
    assert h.mon.send("status") is False
    assert h.statuses[-1] == "not connected - command not sent"


def test_monitor_send_failure_marks_disconnected():
    port = ScriptedSerial()
    h = Harness([port])
    h.mon.step()
    port.close()
    assert h.mon.send("status") is False
    assert h.mon.state is monitor.State.WAITING


def test_monitor_pause_releases_port_and_resume_reconnects():
    port = ScriptedSerial()
    h = Harness([port, ScriptedSerial()])
    h.mon.step()
    h.mon.pause()
    assert not port.is_open
    assert h.mon.step() is monitor.State.PAUSED
    h.mon.resume()
    assert h.mon.step() is monitor.State.CONNECTED


def test_monitor_close():
    port = ScriptedSerial()
    h = Harness([port])
    h.mon.step()
    h.mon.close()
    assert not port.is_open
    assert h.mon.state is monitor.State.CLOSED


def test_log_writer(tmp_path):
    log = tmp_path / "logs" / "serial.log"
    with monitor.LogWriter(log) as writer:
        writer.write("hello")
        writer.write("> status")
    assert log.read_text(encoding="utf-8") == "hello\n> status\n"


def test_log_writer_disabled():
    with monitor.LogWriter(None) as writer:
        writer.write("ignored")
