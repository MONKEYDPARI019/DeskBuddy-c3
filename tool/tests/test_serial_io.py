from __future__ import annotations

from types import SimpleNamespace

import pytest
import serial

from deskbuddy import serial_io
from deskbuddy.errors import NoBoardError, NoReplyError, PortBusyError
from tests.fakes import ScriptedSerial


class RecordingPort:
    """Unopened-port stand-in that records the line states at open() time."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.dtr = True
        self.rts = True
        self.opened_with = None
        self.port = self.baudrate = self.timeout = None

    def open(self):
        if self.error:
            raise self.error
        self.opened_with = (self.dtr, self.rts)


def test_open_serial_turns_dtr_rts_off_before_opening():
    fake = RecordingPort()
    ser = serial_io.open_serial("COM9", factory=lambda port: fake)
    assert ser is fake
    assert fake.opened_with == (False, False)
    assert fake.baudrate == 115200
    assert fake.port == "COM9"


def test_open_serial_works_with_loop_url():
    ser = serial_io.open_serial("loop://")
    try:
        serial_io.send_line(ser, "status")
        assert ser.read(7) == b"status\n"
    finally:
        ser.close()


@pytest.mark.parametrize(
    "message",
    [
        "could not open port 'COM9': PermissionError(13, 'Access is denied.', None, 5)",
        "[Errno 16] could not open port /dev/ttyACM0: [Errno 16] Device or resource busy",
        "Could not exclusively lock port /dev/ttyACM0: [Errno 11] Resource temporarily unavailable",
    ],
)
def test_open_serial_maps_busy(message):
    with pytest.raises(PortBusyError) as excinfo:
        serial_io.open_serial("COM9", factory=lambda p: RecordingPort(serial.SerialException(message)))
    assert "COM9 is busy" in excinfo.value.message
    assert "serial monitor" in excinfo.value.hint


@pytest.mark.parametrize(
    "message",
    [
        "could not open port 'COM9': FileNotFoundError(2, 'The system cannot find the file specified.')",
        "[Errno 2] could not open port /dev/ttyACM0: [Errno 2] No such file or directory",
    ],
)
def test_open_serial_maps_missing(message):
    with pytest.raises(NoBoardError, match="COM9 not found"):
        serial_io.open_serial("COM9", factory=lambda p: RecordingPort(serial.SerialException(message)))


def test_open_serial_other_errors_are_wrapped():
    with pytest.raises(NoBoardError, match="Cannot open COM9"):
        serial_io.open_serial("COM9", factory=lambda p: RecordingPort(OSError("weird")))


def test_send_line_uses_lf():
    ser = ScriptedSerial()
    serial_io.send_line(ser, "  link ble \r\n")
    assert bytes(ser.written) == b"link ble\n"


def test_read_until_idle_stops_after_idle_gap(clock):
    ser = ScriptedSerial([b"hello ", b"world\n", *([b""] * 10), b"late"], clock=clock)
    data = serial_io.read_until_idle(ser, idle=0.8, timeout=10, clock=clock)
    assert data == b"hello world\n"
    assert ser.chunks  # 'late' was never read


def test_read_until_idle_honours_timeout_with_constant_output(clock):
    ser = ScriptedSerial([b"x"] * 1000, clock=clock)
    data = serial_io.read_until_idle(ser, idle=0.8, timeout=2.0, clock=clock)
    assert 15 <= len(data) <= 21


def test_read_until_idle_no_data_waits_for_timeout(clock):
    ser = ScriptedSerial([], clock=clock)
    assert serial_io.read_until_idle(ser, idle=0.8, timeout=3.0, clock=clock) == b""
    assert clock.now == pytest.approx(3.0, abs=0.11)


def test_read_until_idle_reports_chunks(clock):
    seen = []
    ser = ScriptedSerial([b"a", b"b"], clock=clock)
    serial_io.read_until_idle(ser, idle=0.3, timeout=5, clock=clock, on_data=seen.append)
    assert seen == [b"a", b"b"]


def test_run_command_returns_reply(clock):
    ser = ScriptedSerial([b"\nDeskBuddy C3 c3-2.0.0 (USB build)\n", b"link ble\n"], clock=clock)
    reply = serial_io.run_command("COM9", "status", opener=lambda port: ser, clock=clock)
    assert "DeskBuddy C3" in reply
    assert bytes(ser.written) == b"status\n"
    assert ser.reset_calls == 1
    assert not ser.is_open


def test_run_command_no_reply(clock):
    ser = ScriptedSerial([], clock=clock)
    with pytest.raises(NoReplyError, match="No reply"):
        serial_io.run_command("COM9", "status", timeout=1, opener=lambda port: ser, clock=clock)


def test_run_command_whitespace_only_is_no_reply(clock):
    ser = ScriptedSerial([b"\r\n"], clock=clock)
    with pytest.raises(NoReplyError):
        serial_io.run_command("COM9", "status", timeout=1, opener=lambda port: ser, clock=clock)


def _lister(*snapshots):
    """Each call returns the next list of (device, vid) pairs; the last one repeats."""
    seq = list(snapshots)

    def lister():
        snap = seq.pop(0) if len(seq) > 1 else seq[0]
        return [SimpleNamespace(device=d, vid=v, pid=0x1001, description="", serial_number=None) for d, v in snap]

    return lister


def test_wait_for_board_returns_preferred_when_present(clock):
    lister = _lister([], [], [("COM9", 0x303A)])
    assert serial_io.wait_for_board("COM9", timeout=5, lister=lister, clock=clock, sleep=clock.sleep) == "COM9"


def test_wait_for_board_follows_new_name(clock):
    lister = _lister([], [("COM12", 0x303A)])
    assert serial_io.wait_for_board("COM9", timeout=5, lister=lister, clock=clock, sleep=clock.sleep) == "COM12"


def test_wait_for_board_times_out(clock):
    lister = _lister([])
    assert serial_io.wait_for_board(None, timeout=2, lister=lister, clock=clock, sleep=clock.sleep) is None
    assert clock.now >= 2


def test_wait_for_board_can_require_disappearance(clock):
    lister = _lister([("COM9", 0x303A)], [("COM9", 0x303A)], [], [("COM9", 0x303A)])
    port = serial_io.wait_for_board("COM9", timeout=10, lister=lister, clock=clock, sleep=clock.sleep, gone_first=True)
    assert port == "COM9"
    assert clock.now == pytest.approx(3 * serial_io.POLL_INTERVAL)


def test_wait_for_board_gone_first_falls_back_when_never_gone(clock):
    lister = _lister([("COM9", 0x303A)])
    port = serial_io.wait_for_board("COM9", timeout=2, lister=lister, clock=clock, sleep=clock.sleep, gone_first=True)
    assert port == "COM9"


def test_wait_for_board_cancel(clock):
    lister = _lister([])
    assert (
        serial_io.wait_for_board(None, timeout=60, lister=lister, clock=clock, sleep=clock.sleep, cancel=lambda: True)
        is None
    )
    assert clock.now < 1


def test_run_command_lost_connection_is_a_friendly_error(clock):
    ser = ScriptedSerial([b"[App] switching", serial.SerialException("ClearCommError failed")], clock=clock)
    with pytest.raises(NoBoardError, match="Lost the connection"):
        serial_io.run_command("COM9", "link ble", opener=lambda port: ser, clock=clock)
    assert not ser.is_open


def test_wait_for_board_gone_first_without_preferred_returns_present_board(clock):
    lister = _lister([("COM9", 0x303A)])
    port = serial_io.wait_for_board(None, timeout=1, lister=lister, clock=clock, sleep=clock.sleep, gone_first=True)
    assert port == "COM9"
