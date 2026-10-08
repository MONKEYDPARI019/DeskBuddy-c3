from __future__ import annotations

from types import SimpleNamespace

from deskbuddy import doctor
from deskbuddy.errors import NetworkError, PortBusyError
from tests.fakes import ScriptedSerial


def board(device="COM9", vid=0x303A):
    return SimpleNamespace(device=device, vid=vid, pid=0x1001, description="USB Serial Device", serial_number=None)


def deps(**overrides):
    base = dict(
        python_version=(3, 12, 1),
        package_version=lambda name: {"esptool": "5.4.0", "pyserial": "3.5"}[name],
        lister=lambda: [board()],
        opener=lambda port: ScriptedSerial(),
        github_ping=lambda: None,
        platform="win32",
        user_groups=lambda: [],
    )
    base.update(overrides)
    return doctor.DoctorDeps(**base)


def by_name(results):
    return {r.name: r for r in results}


def test_all_good_on_windows():
    results = doctor.run_checks(deps())
    assert all(r.ok for r in results)
    names = [r.name for r in results]
    assert names == ["Python", "esptool", "pyserial", "Board", "Port", "GitHub", "Serial permissions"]
    assert "not needed" in by_name(results)["Serial permissions"].detail


def test_old_python_fails():
    r = by_name(doctor.run_checks(deps(python_version=(3, 8, 10))))["Python"]
    assert not r.ok and "3.9" in r.hint


def test_missing_packages():
    def missing(name):
        raise doctor.PackageNotFoundError(name)

    results = by_name(doctor.run_checks(deps(package_version=missing)))
    assert not results["esptool"].ok and "pip install" in results["esptool"].hint
    assert not results["pyserial"].ok


def test_no_board_skips_port_check():
    results = by_name(doctor.run_checks(deps(lister=lambda: [])))
    assert not results["Board"].ok
    assert "data USB cable" in results["Board"].hint
    assert not results["Port"].ok
    assert "no board" in results["Port"].detail


def test_possible_esp32_is_reported():
    results = by_name(doctor.run_checks(deps(lister=lambda: [board("COM5", 0x10C4)])))
    assert results["Board"].ok
    assert "possible ESP32" in results["Board"].detail


def test_busy_port():
    def busy(port):
        raise PortBusyError(f"{port} is busy", "close the monitor")

    r = by_name(doctor.run_checks(deps(opener=busy)))["Port"]
    assert not r.ok and r.detail == "COM9 is busy" and r.hint == "close the monitor"


def test_github_unreachable():
    def offline():
        raise NetworkError("Cannot reach GitHub", "check internet")

    r = by_name(doctor.run_checks(deps(github_ping=offline)))["GitHub"]
    assert not r.ok and r.hint == "check internet"


def test_linux_dialout_missing():
    r = by_name(doctor.run_checks(deps(platform="linux", user_groups=lambda: ["users"])))["Serial permissions"]
    assert not r.ok
    assert "sudo usermod -aG dialout $USER" in r.hint


def test_linux_dialout_present():
    r = by_name(doctor.run_checks(deps(platform="linux", user_groups=lambda: ["users", "dialout"])))[
        "Serial permissions"
    ]
    assert r.ok


def test_format_results_marks_and_hints():
    results = [doctor.CheckResult("A", True, "fine"), doctor.CheckResult("B", False, "bad", "fix it")]
    text = doctor.format_results(results, ascii_only=False)
    assert "✓ A: fine" in text
    assert "✗ B: bad" in text
    assert "fix it" in text
    assert "[ok] A" in doctor.format_results(results, ascii_only=True)


def test_current_user_groups_does_not_crash():
    assert isinstance(doctor.current_user_groups(), list)
