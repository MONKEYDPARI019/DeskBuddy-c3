from __future__ import annotations

import io
import sys

import pytest

from deskbuddy import esptool_compat, flasher
from deskbuddy.errors import FlashError, PortBusyError
from deskbuddy.esptool_compat import EsptoolResult

V4 = esptool_compat.syntax_for(4)
V5 = esptool_compat.syntax_for(5)


# --- esptool version handling -------------------------------------------------


def test_major_version_parsing():
    assert esptool_compat.major_of("4.10.0") == 4
    assert esptool_compat.major_of("5.5.0") == 5
    assert esptool_compat.major_of("garbage") == 5


def test_installed_version_uses_metadata():
    assert esptool_compat.installed_version(lambda name: "4.8.1") == "4.8.1"


def test_installed_version_missing():
    def missing(name):
        raise esptool_compat.PackageNotFoundError(name)

    with pytest.raises(FlashError, match="esptool is not installed"):
        esptool_compat.installed_version(missing)


def test_syntax_v4_and_v5_differ():
    assert (V4.write_flash, V4.merge_bin, V4.default_reset, V4.hard_reset) == (
        "write_flash",
        "merge_bin",
        "default_reset",
        "hard_reset",
    )
    assert (V5.write_flash, V5.merge_bin, V5.default_reset, V5.hard_reset) == (
        "write-flash",
        "merge-bin",
        "default-reset",
        "hard-reset",
    )


def test_current_syntax(monkeypatch):
    monkeypatch.setattr(esptool_compat, "installed_version", lambda getter=None: "4.9.0")
    assert esptool_compat.current_syntax() == V4


class FakePopen:
    def __init__(self, cmd, **kwargs):
        self.cmd = cmd
        self.kwargs = kwargs
        self.stdout = io.StringIO("line one\nWriting at 0x00010000... (50 %)\n")
        self.returncode = 0

    def wait(self):
        return self.returncode

    def poll(self):
        return self.returncode


def test_run_esptool_streams_lines():
    seen = []
    created = []

    def popen(cmd, **kwargs):
        proc = FakePopen(cmd, **kwargs)
        created.append(proc)
        return proc

    result = esptool_compat.run_esptool(["version"], on_line=seen.append, popen=popen)
    assert result == EsptoolResult(0, "line one\nWriting at 0x00010000... (50 %)\n")
    assert seen == ["line one", "Writing at 0x00010000... (50 %)"]
    proc = created[0]
    assert proc.cmd[:3] == [sys.executable, "-m", "esptool"]
    assert proc.kwargs["env"]["NO_COLOR"] == "1"
    assert proc.kwargs["shell"] is False


def test_run_esptool_launch_failure():
    def popen(cmd, **kwargs):
        raise OSError("boom")

    with pytest.raises(FlashError, match="Could not start esptool"):
        esptool_compat.run_esptool(["version"], popen=popen)


# --- progress parsing ---------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Writing at 0x00010000... (5 %)", 5.0),
        ("Writing at 0x0002c3a1... (100 %)", 100.0),
        # captured from esptool 5.5.0 on real hardware (non-TTY output)
        ("Writing at 0x0001c9ab >                                1.7% 16.00kB/936.29kB [0s] ", 1.7),
        ("Writing at 0x00010000 [====>                         ]  14.6% 65536/447776 bytes...", 14.6),
        ("\x1b[2KWriting at 0x00010000 [=>   ]   3.0% 1/2", 3.0),
        ("Writing at 0x00010000 [━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━] 100.0% 447776/447776 bytes...", 100.0),
        ("Wrote 447776 bytes (300000 compressed) at 0x00000000 in 4.1 seconds", None),
        ("Erasing flash (this may take a while)...", None),
    ],
)
def test_parse_progress(line, expected):
    assert flasher.parse_progress(line) == expected


# --- failure classification ---------------------------------------------------


@pytest.mark.parametrize(
    ("output", "kind"),
    [
        (
            "A fatal error occurred: Could not open COM9, the port is busy or doesn't exist.\n"
            "(could not open port 'COM9': PermissionError(13, 'Access is denied.', None, 5))",
            flasher.Failure.PORT_BUSY,
        ),
        ("could not open port /dev/ttyACM0: [Errno 16] Device or resource busy", flasher.Failure.PORT_BUSY),
        (
            "could not open port 'COM9': FileNotFoundError(2, 'The system cannot find the file specified.')",
            flasher.Failure.PORT_MISSING,
        ),
        (
            "A fatal error occurred: Failed to connect to ESP32-C3: No serial data received.",
            flasher.Failure.NO_DOWNLOAD_MODE,
        ),
        ("Wrong boot mode detected (0x8)! The chip needs to be in download mode.", flasher.Failure.NO_DOWNLOAD_MODE),
        ("A fatal error occurred: Timed out waiting for packet header", flasher.Failure.COMM_ERROR),
        ("A fatal error occurred: Packet content transfer stopped (received 8 bytes)", flasher.Failure.COMM_ERROR),
        ("A serial exception error occurred: Write timeout", flasher.Failure.COMM_ERROR),
        ("A fatal error occurred: File firmware.bin does not exist", flasher.Failure.OTHER),
    ],
)
def test_classify_failure(output, kind):
    assert flasher.classify_failure(output) is kind


# --- argument building --------------------------------------------------------


def test_write_flash_args_v5():
    args = flasher.write_flash_args(V5, "COM9", 921600, "fw.bin", erase=False)
    assert args == [
        "--chip",
        "esp32c3",
        "--port",
        "COM9",
        "--baud",
        "921600",
        "--before",
        "default-reset",
        "--after",
        "hard-reset",
        "write-flash",
        "0x0",
        "fw.bin",
    ]


def test_write_flash_args_v4_with_erase():
    args = flasher.write_flash_args(V4, "/dev/ttyACM0", 115200, "fw.bin", erase=True)
    assert args[6:] == ["--before", "default_reset", "--after", "hard_reset", "write_flash", "-e", "0x0", "fw.bin"]


# --- retry / fallback state machine ----------------------------------------------


class ScriptedRunner:
    """Returns pre-baked esptool results in order and records the baud/port of each call."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, args, on_line=None):
        port = args[args.index("--port") + 1]
        baud = int(args[args.index("--baud") + 1])
        self.calls.append((port, baud))
        rc, output = self.results.pop(0)
        if on_line:
            for line in output.splitlines():
                on_line(line)
        return EsptoolResult(rc, output)


OK = (0, "Writing at 0x00010000... (50 %)\nWriting at 0x00020000... (100 %)\nHash of data verified.")
COMM = (2, "A fatal error occurred: Timed out waiting for packet header")
NO_DL = (2, "A fatal error occurred: Failed to connect to ESP32-C3: No serial data received.")
BUSY = (2, "could not open port 'COM9': PermissionError(13, 'Access is denied.', None, 5)")
WEIRD = (2, "A fatal error occurred: something unexpected\nmore detail")


class Recorder(flasher.FlashCallbacks):
    def __init__(self):
        self.events = []
        super().__init__(
            progress=lambda p: self.events.append(("progress", p)),
            status=lambda s: self.events.append(("status", s)),
            boot_hint=lambda h: self.events.append(("hint", h)),
            output=lambda line: None,
        )


def run_flash(runner, waiter=lambda port: port, **kwargs):
    callbacks = Recorder()
    outcome = flasher.flash_image(
        "fw.bin", "COM9", runner=runner, waiter=waiter, syntax=V5, callbacks=callbacks, **kwargs
    )
    return outcome, callbacks.events


def test_flash_succeeds_first_try_and_reports_progress():
    runner = ScriptedRunner(OK)
    outcome, events = run_flash(runner)
    assert outcome == flasher.FlashOutcome(port="COM9", baud=921600)
    assert ("progress", 50.0) in events and ("progress", 100.0) in events
    assert not [e for e in events if e[0] == "hint"]


def test_flash_falls_back_through_baud_rates():
    runner = ScriptedRunner(COMM, COMM, OK)
    outcome, _ = run_flash(runner)
    assert [b for _, b in runner.calls] == [921600, 460800, 115200]
    assert outcome.baud == 115200


def test_flash_respects_requested_baud():
    runner = ScriptedRunner(COMM, OK)
    outcome, _ = run_flash(runner, bauds=flasher.baud_ladder(460800))
    assert [b for _, b in runner.calls] == [460800, 115200]
    assert outcome.baud == 115200


def test_baud_ladder():
    assert flasher.baud_ladder(None) == (921600, 460800, 115200)
    assert flasher.baud_ladder(230400) == (230400, 115200)
    assert flasher.baud_ladder(115200) == (115200,)


def test_flash_all_bauds_fail():
    runner = ScriptedRunner(COMM, COMM, COMM)
    with pytest.raises(FlashError, match="every speed"):
        run_flash(runner)


def test_flash_port_busy_stops_immediately():
    runner = ScriptedRunner(BUSY)
    with pytest.raises(PortBusyError):
        run_flash(runner)
    assert len(runner.calls) == 1


def test_flash_other_error_shows_esptool_detail():
    runner = ScriptedRunner(WEIRD)
    with pytest.raises(FlashError, match="esptool failed") as excinfo:
        run_flash(runner)
    assert "something unexpected" in excinfo.value.hint


def test_flash_boot_hint_then_success_on_new_port():
    runner = ScriptedRunner(NO_DL, OK)
    waited = []

    def waiter(port):
        waited.append(port)
        return "COM12"

    outcome, events = run_flash(runner, waiter=waiter)
    assert ("hint", flasher.BOOT_HINT) in events
    assert waited == ["COM9"]
    assert runner.calls == [("COM9", 921600), ("COM12", 921600)]
    assert outcome == flasher.FlashOutcome(port="COM12", baud=921600)


def test_flash_boot_hint_retries_three_times_then_gives_up():
    runner = ScriptedRunner(NO_DL, NO_DL, NO_DL, NO_DL)
    with pytest.raises(FlashError, match="download mode") as excinfo:
        run_flash(runner)
    assert len(runner.calls) == 4
    assert "BOOT" in excinfo.value.hint


def test_flash_port_missing_is_treated_like_reenumeration():
    missing = (2, "could not open port 'COM9': FileNotFoundError(2, 'The system cannot find the file specified.')")
    runner = ScriptedRunner(missing, OK)
    outcome, events = run_flash(runner)
    assert outcome.baud == 921600
    assert any(e[0] == "hint" for e in events)


def test_flash_waiter_timeout_keeps_old_port():
    runner = ScriptedRunner(NO_DL, OK)
    outcome, _ = run_flash(runner, waiter=lambda port: None)
    assert outcome.port == "COM9"


def test_flash_missing_image(tmp_path):
    with pytest.raises(FlashError, match="not found"):
        flasher.check_image(tmp_path / "nope.bin")


def test_check_image_rejects_tiny_file(tmp_path):
    image = tmp_path / "x.bin"
    image.write_bytes(b"\x00" * 10)
    with pytest.raises(FlashError, match="too small"):
        flasher.check_image(image)


def test_check_image_rejects_non_esp_image(tmp_path):
    image = tmp_path / "x.bin"
    image.write_bytes(b"\x00" * 70000)
    with pytest.raises(FlashError, match="does not look like"):
        flasher.check_image(image)


def test_check_image_accepts_merged_image(tmp_path):
    image = tmp_path / "x.bin"
    image.write_bytes(b"\xe9" + b"\x00" * 70000)
    flasher.check_image(image)


def make_merged(tmp_path, nvs_fill=0xFF, size=0x20000):
    data = bytearray(b"\xe9" + b"\x11" * (size - 1))
    data[flasher.NVS_START : flasher.NVS_END] = bytes([nvs_fill]) * (flasher.NVS_END - flasher.NVS_START)
    path = tmp_path / "merged.bin"
    path.write_bytes(bytes(data))
    return path, bytes(data)


def test_flash_segments_skip_empty_nvs(tmp_path):
    image, data = make_merged(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    segments = flasher.flash_segments(image, erase=False, workdir=work)
    assert [s[0] for s in segments] == ["0x0", "0xe000"]
    assert segments[0][1].read_bytes() == data[: flasher.NVS_START]
    assert segments[1][1].read_bytes() == data[flasher.NVS_END :]


def test_flash_segments_whole_image_when_erasing_or_nvs_has_data(tmp_path):
    image, _ = make_merged(tmp_path)
    assert flasher.flash_segments(image, erase=True, workdir=tmp_path) == [("0x0", image)]
    image2, _ = make_merged(tmp_path, nvs_fill=0x00)
    assert flasher.flash_segments(image2, erase=False, workdir=tmp_path) == [("0x0", image2)]


def test_write_flash_args_with_segments(tmp_path):
    args = flasher.write_flash_args(V5, "COM9", 921600, [("0x0", tmp_path / "a"), ("0xe000", tmp_path / "b")], False)
    assert args[-4:] == ["0x0", str(tmp_path / "a"), "0xe000", str(tmp_path / "b")]


def test_flash_image_preserves_nvs_by_default(tmp_path):
    image, _ = make_merged(tmp_path)
    seen = []

    def runner(args, on_line=None):
        seen.append(args)
        return EsptoolResult(0, "")

    statuses = []
    flasher.flash_image(
        image,
        "COM9",
        runner=runner,
        waiter=lambda p: p,
        syntax=V5,
        callbacks=flasher.FlashCallbacks(status=statuses.append),
    )
    assert "0xe000" in seen[0] and "-e" not in seen[0]
    assert any("Keeping saved settings" in s for s in statuses)
