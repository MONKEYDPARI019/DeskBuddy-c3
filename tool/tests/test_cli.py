from __future__ import annotations

import io
from types import SimpleNamespace

import pytest

from deskbuddy import __version__, cli, installer
from deskbuddy.errors import EXIT_NO_BOARD, EXIT_NO_REPLY, NoBoardError, NoReplyError
from tests.fakes import ScriptedSerial

COMMANDS = [
    "ports",
    "doctor",
    "versions",
    "get",
    "flash",
    "monitor",
    "cmd",
    "status",
    "link",
    "wifi-forget",
    "reboot",
    "build",
    "ui",
]


class Streams:
    def __init__(self):
        self.out = io.StringIO()
        self.err = io.StringIO()

    def run(self, *argv):
        return cli.main(list(argv), out=self.out, err=self.err)


def esp(device="COM9"):
    return SimpleNamespace(device=device, vid=0x303A, pid=0x1001, description="USB Serial Device", serial_number=None)


@pytest.fixture
def board(monkeypatch):
    monkeypatch.setattr(cli.ports, "comports", lambda: [esp()])


def test_help_lists_every_command():
    s = Streams()
    assert s.run() == 0
    for name in COMMANDS:
        assert name in s.out.getvalue()


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_ports_output(board):
    s = Streams()
    assert s.run("ports") == 0
    assert "* COM9 - ESP32-C3" in s.out.getvalue()


def test_ports_none(monkeypatch):
    monkeypatch.setattr(cli.ports, "comports", lambda: [])
    s = Streams()
    assert s.run("ports") == 0
    assert "No serial ports" in s.out.getvalue()


def test_cmd_prints_reply(board, monkeypatch):
    sent = {}

    def fake_run(port, text, timeout=5.0):
        sent.update(port=port, text=text, timeout=timeout)
        return "\nDeskBuddy C3 c3-2.0.0 (USB build)\n"

    monkeypatch.setattr(cli.serial_io, "run_command", fake_run)
    s = Streams()
    assert s.run("cmd", "status", "--timeout", "2") == 0
    assert sent == {"port": "COM9", "text": "status", "timeout": 2.0}
    assert "DeskBuddy C3" in s.out.getvalue()


@pytest.mark.parametrize(("command", "text"), [("status", "status"), ("wifi-forget", "wifi forget")])
def test_shortcuts(board, monkeypatch, command, text):
    seen = []
    monkeypatch.setattr(cli.serial_io, "run_command", lambda port, t, timeout=5.0: seen.append(t) or "ok")
    assert Streams().run(command) == 0
    assert seen == [text]


def test_no_reply_exit_code(board, monkeypatch):
    def silent(port, text, timeout=5.0):
        raise NoReplyError("No reply from the board on COM9 within 5 s", "Is the firmware installed?")

    monkeypatch.setattr(cli.serial_io, "run_command", silent)
    s = Streams()
    assert s.run("status") == EXIT_NO_REPLY
    err = s.err.getvalue()
    assert "No reply" in err and "-> Is the firmware installed?" in err
    assert "Traceback" not in err


def test_no_board_exit_code(monkeypatch):
    monkeypatch.setattr(cli.ports, "comports", lambda: [])
    s = Streams()
    assert s.run("status") == EXIT_NO_BOARD
    assert "No DeskBuddy board found" in s.err.getvalue()


def test_debug_shows_traceback(monkeypatch):
    monkeypatch.setattr(cli.ports, "comports", lambda: [])
    s = Streams()
    s.run("--debug", "status")
    assert "Traceback" in s.err.getvalue()


def test_unexpected_error_is_friendly(monkeypatch):
    def boom():
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cli.ports, "comports", boom)
    s = Streams()
    assert s.run("ports") == 1
    assert "Unexpected error: kaboom" in s.err.getvalue()
    assert "Traceback" not in s.err.getvalue()


def test_keyboard_interrupt(monkeypatch):
    def interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.ports, "comports", interrupt)
    assert Streams().run("ports") == 130


def test_link(board, monkeypatch):
    monkeypatch.setattr(cli.installer, "switch_link", lambda port, mode, status=None: "ble")
    s = Streams()
    assert s.run("link", "ble") == 0
    assert "Link is now Bluetooth (ble)" in s.out.getvalue()


def test_flash_reports_install(board, monkeypatch, tmp_path):
    captured = {}

    def fake_install(opts, callbacks=None, ask=None):
        captured["opts"] = opts
        callbacks.progress(50.0)
        callbacks.status("Writing...")
        img = installer.ResolvedImage(tmp_path / "x.bin", "v2.0.0")
        return installer.InstallResult("COM9", 921600, img, installer.BootInfo("2.0.0", "USB"))

    monkeypatch.setattr(cli.installer, "install", fake_install)
    s = Streams()
    assert s.run("flash", "--version", "v2.0.0", "--env", "battery", "--erase", "--no-monitor") == 0
    opts = captured["opts"]
    assert (opts.version, opts.env, opts.erase, opts.local) == ("v2.0.0", "battery", True, False)
    assert "Installed DeskBuddy C3 v2.0.0" in s.out.getvalue()


def test_flash_sources_are_exclusive(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["flash", "--local", "--file", "x.bin"])
    assert excinfo.value.code == 2


def test_versions(monkeypatch):
    rel = SimpleNamespace(
        tag="v2.0.0",
        date="2026-10-08",
        prerelease=False,
        assets=[
            SimpleNamespace(name="deskbuddy-c3-c3-v2.0.0.bin", size=1234),
            SimpleNamespace(name="SHA256SUMS", size=10),
        ],
    )
    monkeypatch.setattr(cli.github, "GitHubClient", lambda: SimpleNamespace(list_releases=lambda: [rel]))
    s = Streams()
    assert s.run("versions") == 0
    out = s.out.getvalue()
    assert "v2.0.0" in out and "builds: usb" in out and "(latest)" in out and "1,234 bytes" in out


def test_versions_none(monkeypatch):
    monkeypatch.setattr(cli.github, "GitHubClient", lambda: SimpleNamespace(list_releases=lambda: []))
    s = Streams()
    assert s.run("versions") == 0
    assert "No releases" in s.out.getvalue()


def test_get(monkeypatch, tmp_path):
    rel = SimpleNamespace(tag="v2.0.0", date="2026-10-08")
    monkeypatch.setattr(cli.github, "GitHubClient", lambda: SimpleNamespace(get_release=lambda v: rel))
    monkeypatch.setattr(cli.github, "fetch_firmware", lambda r, env, cache, client, progress=None: tmp_path / env)
    monkeypatch.setattr(cli.github, "get_source", lambda r, dest, client: dest / "DeskBuddy-C3-v2.0.0")
    s = Streams()
    assert s.run("get", "--dest", str(tmp_path)) == 0
    out = s.out.getvalue()
    assert "usb firmware" in out and "battery firmware" in out and "DeskBuddy-C3-v2.0.0" in out


def test_build(monkeypatch, tmp_path):
    merged = SimpleNamespace(path=tmp_path / "x.bin", sha256="ab" * 32, size=1000)
    seen = {}

    def fake_build(path, pio_env, out_dir=None, status=None, on_line=None):
        seen.update(path=path, env=pio_env, out=out_dir)
        return merged

    monkeypatch.setattr(cli.installer, "build_local", fake_build)
    s = Streams()
    assert s.run("build", "--env", "battery", "--path", str(tmp_path), "--out", str(tmp_path / "o")) == 0
    assert seen == {"path": tmp_path, "env": "c3-battery", "out": tmp_path / "o"}
    assert "sha256 " + "ab" * 32 in s.out.getvalue()


def test_doctor(monkeypatch):
    from deskbuddy import doctor

    monkeypatch.setattr(doctor, "default_deps", lambda: "deps")
    monkeypatch.setattr(doctor, "run_checks", lambda deps: [doctor.CheckResult("Python", True, "3.12")])
    s = Streams()
    assert s.run("doctor") == 0
    assert "1 of 1 checks passed" in s.out.getvalue()


def test_reboot(board, monkeypatch):
    port = ScriptedSerial()
    monkeypatch.setattr(cli.serial_io, "open_serial", lambda p: port)
    monkeypatch.setattr(cli.installer, "confirm_boot", lambda p, deps, status=None: installer.BootInfo("2.0.0", "USB"))
    s = Streams()
    assert s.run("reboot") == 0
    assert bytes(port.written) == b"reboot\n"
    assert "Board restarted: DeskBuddy C3 v2.0.0" in s.out.getvalue()


def test_run_monitor_prints_logs_and_sends(tmp_path):
    port = ScriptedSerial([b"[BLE] advertising\n", b"", b"", b""])
    con = cli.Console(io.StringIO(), io.StringIO())
    log = tmp_path / "m.log"
    stdin = io.StringIO("status\n\n")
    code = cli.run_monitor(
        "COM9", con, log=log, raw=False, follow_any=False, stdin=stdin, max_steps=6, opener=lambda p: port
    )
    assert code == 0
    out = con.out.getvalue()
    assert "[BLE] advertising" in out
    assert "> status" in out  # piped stdin is echoed locally
    assert b"status\n" in bytes(port.written)
    assert "[BLE] advertising" in log.read_text() and "> status" in log.read_text()


def test_console_ascii_fallback():
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    con = cli.Console(stream, stream)
    assert con.ok == "OK" and con.bad == "X"


def test_console_progress_only_on_tty():
    class Tty(io.StringIO):
        def isatty(self):
            return True

    con = cli.Console(Tty(), io.StringIO())
    con.progress(50, "Writing")
    con.print("done")
    assert "50.0%" in con.out.getvalue() and con.out.getvalue().endswith("done\n")


def test_ui_without_tkinter(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "tkinter":
            raise ImportError("no tk")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    s = Streams()
    assert s.run("ui") == 1
    assert "sudo apt install python3-tk" in s.err.getvalue()


def test_monitor_command_waits_without_board(monkeypatch):
    monkeypatch.setattr(cli.ports, "comports", lambda: [])
    seen = {}

    def fake_run_monitor(port, con, log, raw, follow_any):
        seen.update(port=port, raw=raw, follow=follow_any)
        return 0

    monkeypatch.setattr(cli, "run_monitor", fake_run_monitor)
    assert Streams().run("monitor", "--raw") == 0
    assert seen == {"port": None, "raw": True, "follow": True}


def test_errors_raise_from_choose_port_are_reported(monkeypatch):
    def none(*a, **k):
        raise NoBoardError("No DeskBuddy board found", "plug it in")

    monkeypatch.setattr(cli.ports, "choose_port", none)
    s = Streams()
    assert s.run("link", "wifi") == EXIT_NO_BOARD
