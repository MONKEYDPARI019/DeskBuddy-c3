from __future__ import annotations

import sys

import pytest

from deskbuddy import builder
from deskbuddy.errors import BuildError, UsageError


def make_repo(root):
    fw = root / "firmware"
    (fw / "src").mkdir(parents=True)
    (fw / "platformio.ini").write_text("[platformio]\n")
    (fw / "src" / "config.h").write_text('#define FW_VERSION "c3-2.0.0"\n')
    return fw


def test_find_project_from_repo_root(tmp_path):
    fw = make_repo(tmp_path)
    assert builder.find_project(tmp_path) == fw


def test_find_project_from_firmware_dir(tmp_path):
    fw = make_repo(tmp_path)
    assert builder.find_project(fw) == fw


def test_find_project_missing(tmp_path):
    with pytest.raises(UsageError, match="No DeskBuddy firmware project"):
        builder.find_project(tmp_path)


def test_find_project_defaults_to_cwd(tmp_path, monkeypatch):
    fw = make_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert builder.find_project(None) == fw


def test_child_env_isolates_core_and_drops_msys(monkeypatch, tmp_path):
    monkeypatch.setenv("MSYSTEM", "MINGW64")
    monkeypatch.setenv("PLATFORMIO_CORE_DIR", "C:/Users/me/.platformio")
    env = builder.child_env(tmp_path / "core")
    assert env["PLATFORMIO_CORE_DIR"] == str(tmp_path / "core")
    assert "MSYSTEM" not in env
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_platformio_command_uses_installed_module(tmp_path):
    cmd = builder.platformio_command(tmp_path / "venv", has_module=lambda: True, runner=None)
    assert cmd == [sys.executable, "-m", "platformio"]


def test_platformio_command_creates_private_venv(tmp_path):
    calls = []

    def runner(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1:3] == ["-m", "venv"]:
            py = builder.venv_python(tmp_path / "venv")
            py.parent.mkdir(parents=True)
            py.write_text("")
        return 0

    statuses = []
    cmd = builder.platformio_command(tmp_path / "venv", has_module=lambda: False, runner=runner, status=statuses.append)
    py = builder.venv_python(tmp_path / "venv")
    assert cmd == [str(py), "-m", "platformio"]
    assert calls[0] == [sys.executable, "-m", "venv", str(tmp_path / "venv")]
    assert calls[1][:5] == [str(py), "-m", "pip", "install", "--disable-pip-version-check"]
    assert calls[1][-1] == builder.PIO_SPEC
    assert any("first use" in s for s in statuses)


def test_platformio_command_reuses_existing_venv(tmp_path):
    py = builder.venv_python(tmp_path / "venv")
    py.parent.mkdir(parents=True)
    py.write_text("")
    calls = []
    marker = tmp_path / "venv" / builder.READY_MARKER
    marker.write_text(builder.PIO_SPEC)
    cmd = builder.platformio_command(tmp_path / "venv", has_module=lambda: False, runner=lambda c, **k: calls.append(c))
    assert cmd == [str(py), "-m", "platformio"]
    assert calls == []


def test_platformio_command_venv_failure(tmp_path):
    with pytest.raises(BuildError, match="Could not set up PlatformIO") as excinfo:
        builder.platformio_command(tmp_path / "venv", has_module=lambda: False, runner=lambda c, **k: 1)
    assert "python3-venv" in excinfo.value.hint


def test_venv_python_layout(tmp_path):
    py = builder.venv_python(tmp_path)
    assert py.name in ("python.exe", "python")


def test_stream_command_collects_lines(tmp_path):
    seen = []
    code = builder.stream_command(
        [sys.executable, "-c", "print('a'); print('b')"], cwd=tmp_path, env=None, on_line=seen.append
    )
    assert code == 0
    assert seen == ["a", "b"]


def test_stream_command_missing_program(tmp_path):
    with pytest.raises(BuildError, match="Could not run"):
        builder.stream_command([str(tmp_path / "nope.exe")], cwd=tmp_path, env=None)


def test_stream_command_kills_child_when_callback_fails(tmp_path):
    def explode(line):
        raise RuntimeError("stop")

    script = "import time\nprint('x', flush=True)\ntime.sleep(30)"
    with pytest.raises(RuntimeError):
        builder.stream_command([sys.executable, "-c", script], cwd=tmp_path, env=None, on_line=explode)


def test_child_env_drops_tokens(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setenv("GH_TOKEN", "secret")
    env = builder.child_env(tmp_path)
    assert "GITHUB_TOKEN" not in env and "GH_TOKEN" not in env


def test_reap_kills_stubborn_process():
    import subprocess

    calls = []

    class Stubborn:
        stdout = None

        def poll(self):
            return None

        def terminate(self):
            calls.append("terminate")

        def wait(self, timeout=None):
            calls.append(("wait", timeout))
            if timeout is not None:
                raise subprocess.TimeoutExpired("x", timeout)
            return -9

        def kill(self):
            calls.append("kill")

    builder.reap(Stubborn())
    assert calls == ["terminate", ("wait", 5), "kill", ("wait", None)]
