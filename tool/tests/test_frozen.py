from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from deskbuddy import cli, esptool_compat, frozen, installer
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
