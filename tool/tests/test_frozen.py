from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from deskbuddy import __version__, cli, esptool_compat, frozen, installer
from deskbuddy.errors import BuildError


@pytest.fixture
def as_program(monkeypatch):
    """Pretend to run as the ready-made (PyInstaller) program."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/opt/deskbuddy/deskbuddy")


def test_esptool_command_pip_version():
    assert esptool_compat.esptool_command() == [sys.executable, "-m", "esptool"]
    assert not frozen.is_frozen()


def test_esptool_command_program_runs_itself(as_program):
    assert frozen.is_frozen()
    assert esptool_compat.esptool_command() == ["/opt/deskbuddy/deskbuddy", "--run-esptool"]


class FakeEsptool:
    def __init__(self, outcome=None):
        self.outcome = outcome
        self.argv = None

    def _main(self):
        self.argv = list(sys.argv)
        if self.outcome is not None:
            raise self.outcome


@pytest.fixture
def fake_esptool(monkeypatch):
    def install(outcome=None):
        fake = FakeEsptool(outcome)
        monkeypatch.setitem(sys.modules, "esptool", fake)
        monkeypatch.setattr(sys, "argv", ["deskbuddy"])
        monkeypatch.setattr(frozen, "_unbuffered_stdio", lambda: None)
        return fake

    return install


@pytest.mark.parametrize(
    ("outcome", "code"),
    [(None, 0), (SystemExit(None), 0), (SystemExit(0), 0), (SystemExit(2), 2), (SystemExit("bad"), 1)],
)
def test_run_esptool_exit_codes(fake_esptool, outcome, code):
    fake = fake_esptool(outcome)
    assert frozen.run_esptool_main(["--chip", "esp32c3", "erase-flash"]) == code
    assert fake.argv == ["esptool", "--chip", "esp32c3", "erase-flash"]


def test_run_esptool_uncaught_error_is_one_line(fake_esptool, capsys):
    fake_esptool(ValueError("invalid URL, protocol 'socket' not known"))
    assert frozen.run_esptool_main(["version"]) == 2
    assert "A fatal error occurred: invalid URL" in capsys.readouterr().out


def test_entry_dispatches_hidden_esptool_flag(fake_esptool):
    fake = fake_esptool()
    assert frozen.entry(["--run-esptool", "version"]) == 0
    assert fake.argv == ["esptool", "version"]


def test_entry_answers_version_without_loading_the_command_line(monkeypatch, capsys):
    monkeypatch.setattr(cli, "main", lambda args: pytest.fail("the command line was loaded"))
    assert frozen.entry(["--version"]) == 0
    assert capsys.readouterr().out == f"deskbuddy {__version__}\n"  # same text as argparse prints


def test_entry_runs_the_command_line(monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "main", lambda args: seen.append(args) or 0)
    assert frozen.entry(["ports"]) == 0
    assert seen == [["ports"]]


def test_unbuffered_stdio_writes_straight_through(tmp_path, monkeypatch):
    target = tmp_path / "out.txt"
    with target.open("w", encoding="utf-8") as handle:
        monkeypatch.setattr(sys, "stdout", handle)
        monkeypatch.setattr(sys, "stderr", SimpleNamespace())  # no fileno(): left alone
        frozen._unbuffered_stdio()
        sys.stdout.write("50 %\r")  # no newline and no flush: must still arrive
        assert target.read_bytes() == b"50 %\r"
        assert isinstance(sys.stderr, SimpleNamespace)


def test_building_needs_the_pip_version(as_program):
    with pytest.raises(BuildError, match="Python version") as excinfo:
        installer.build_local(None, "c3")
    assert "pip install" in excinfo.value.hint


# --- the double-click app (DeskBuddy.exe) ------------------------------------------------


@pytest.fixture
def fake_ui(monkeypatch):
    """A stand-in for deskbuddy.ui (Tkinter is not needed to test the entry point)."""
    import deskbuddy

    calls = []
    fake = SimpleNamespace(main=lambda quit_after_ms=None: calls.append(quit_after_ms))
    monkeypatch.setitem(sys.modules, "deskbuddy.ui", fake)
    monkeypatch.setattr(deskbuddy, "ui", fake, raising=False)
    return calls


def test_gui_entry_dispatches_hidden_esptool_flag(fake_esptool):
    fake = fake_esptool()
    assert frozen.gui_entry(["--run-esptool", "version"]) == 0
    assert fake.argv == ["esptool", "version"]


def test_gui_entry_reports_version(capsys):
    from deskbuddy import __version__

    assert frozen.gui_entry(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"DeskBuddy {__version__}"


def test_gui_entry_opens_the_window(fake_ui):
    assert frozen.gui_entry([]) == 0
    assert fake_ui == [None]


def test_gui_entry_self_test_runs_esptool_then_opens_briefly(fake_ui, monkeypatch, capsys):
    from deskbuddy import esptool_compat

    monkeypatch.setattr(esptool_compat, "run_esptool", lambda args: esptool_compat.EsptoolResult(0, "esptool v5.5.0\n"))
    assert frozen.gui_entry(["--self-test"]) == 0
    assert fake_ui == [frozen.SELF_TEST_MS]
    out = capsys.readouterr().out
    assert "esptool child: esptool v5.5.0" in out
    assert "self-test ok" in out


def test_gui_entry_self_test_fails_when_esptool_child_fails(fake_ui, monkeypatch, capsys):
    from deskbuddy import esptool_compat

    monkeypatch.setattr(esptool_compat, "run_esptool", lambda args: esptool_compat.EsptoolResult(1, "boom\n"))
    assert frozen.gui_entry(["--self-test"]) == 1
    assert fake_ui == []
    assert "self-test failed" in capsys.readouterr().out


def test_gui_entry_explains_a_startup_failure(monkeypatch):
    import deskbuddy

    def broken(quit_after_ms=None):
        raise RuntimeError("no display")

    fake = SimpleNamespace(main=broken)
    monkeypatch.setitem(sys.modules, "deskbuddy.ui", fake)
    monkeypatch.setattr(deskbuddy, "ui", fake, raising=False)
    shown = []
    monkeypatch.setattr(frozen, "_fatal", shown.append)
    assert frozen.gui_entry([]) == 1
    assert "DeskBuddy could not start" in shown[0]
    assert "no display" in shown[0]


def test_windowed_program_logs_to_a_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DESKBUDDY_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    path = frozen._log_to_file()
    assert path == tmp_path / "logs" / "app.log"
    print("hello from the window")
    sys.stdout.flush()
    assert "hello from the window" in path.read_text(encoding="utf-8")
    sys.stdout.close()


def test_console_program_does_not_log_to_a_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DESKBUDDY_HOME", str(tmp_path))
    assert frozen._log_to_file() is None
    assert not (tmp_path / "logs").exists()


def test_esptool_child_without_a_pipe_prints_nowhere(fake_esptool, monkeypatch):
    fake_esptool()
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    assert frozen.run_esptool_main(["version"]) == 0
    assert sys.stdout is not None
    sys.stdout.close()


def test_attach_std_streams_is_windows_only(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "stdout", None)
    frozen._attach_std_streams()
    assert sys.stdout is None
