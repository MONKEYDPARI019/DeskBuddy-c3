from __future__ import annotations

import pytest

from deskbuddy import envs, paths
from deskbuddy.errors import DeskBuddyError, UsageError
from deskbuddy.versions import parse_fw_version, read_fw_version, to_tag, version_key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("c3-2.0.0", "2.0.0"),
        ("2.0.0", "2.0.0"),
        ("v2.1.3", "2.1.3"),
        (" c3-10.20.30 ", "10.20.30"),
        ("c3-2.0.0-rc1", "2.0.0-rc1"),
    ],
)
def test_parse_fw_version_accepts_known_forms(raw, expected):
    assert parse_fw_version(raw) == expected


@pytest.mark.parametrize("raw", ["", "c3-2.0", "esp-2.0.0", "two"])
def test_parse_fw_version_rejects_garbage(raw):
    with pytest.raises(DeskBuddyError):
        parse_fw_version(raw)


def test_to_tag():
    assert to_tag("c3-2.0.0") == "v2.0.0"
    assert to_tag("v2.0.0") == "v2.0.0"


def test_version_key_orders_releases():
    tags = ["v1.9.9", "v2.0.0-rc1", "v2.0.0", "garbage", "v10.0.0"]
    assert sorted(tags, key=version_key) == ["garbage", "v1.9.9", "v2.0.0-rc1", "v2.0.0", "v10.0.0"]


def test_read_fw_version(tmp_path):
    config = tmp_path / "config.h"
    config.write_text('#define FW_NAME "DeskBuddy C3"\n#define FW_VERSION  "c3-2.0.0"\n')
    assert read_fw_version(config) == "2.0.0"


def test_read_fw_version_missing_define(tmp_path):
    config = tmp_path / "config.h"
    config.write_text("// nothing here\n")
    with pytest.raises(DeskBuddyError, match="No FW_VERSION"):
        read_fw_version(config)


def test_read_fw_version_missing_file(tmp_path):
    with pytest.raises(DeskBuddyError, match="Cannot read"):
        read_fw_version(tmp_path / "nope.h")


@pytest.mark.parametrize(
    ("name", "pio"),
    [("usb", "c3"), ("USB", "c3"), ("battery", "c3-battery"), ("c3", "c3"), ("c3-battery", "c3-battery")],
)
def test_env_mapping(name, pio):
    assert envs.to_pio_env(name) == pio


def test_env_mapping_rejects_unknown():
    with pytest.raises(UsageError, match="Unknown build") as excinfo:
        envs.to_pio_env("ota")
    assert "--env usb" in excinfo.value.hint


def test_friendly_names():
    assert envs.to_friendly("c3") == "usb"
    assert envs.to_friendly("c3-battery") == "battery"
    assert envs.to_friendly("other") == "other"


def test_image_filename_round_trip():
    name = envs.image_filename("c3-battery", "2.0.0")
    assert name == "deskbuddy-c3-c3-battery-v2.0.0.bin"
    assert envs.parse_image_filename(name) == ("c3-battery", "2.0.0")
    assert envs.parse_image_filename("deskbuddy-c3-c3-v2.0.0.bin") == ("c3", "2.0.0")
    assert envs.parse_image_filename("SHA256SUMS") is None


def test_paths_follow_override(isolated_home):
    assert paths.data_dir() == isolated_home
    assert paths.firmware_cache_dir() == isolated_home / "firmware"
    assert paths.platformio_dir() == isolated_home / "platformio"
    assert paths.logs_dir() == isolated_home / "logs"


def test_pio_core_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("DESKBUDDY_PIO_CORE", str(tmp_path / "pio"))
    assert paths.platformio_core_dir() == tmp_path / "pio"


def test_pio_core_dir_short_on_windows_without_long_paths(monkeypatch):
    monkeypatch.delenv("DESKBUDDY_PIO_CORE", raising=False)
    monkeypatch.setenv("SYSTEMDRIVE", "E:")
    result = str(paths.platformio_core_dir(is_windows=True, long_paths=False))
    assert result.startswith("E:")
    assert result.replace("\\", "/").endswith(".deskbuddy/platformio")
    assert len(result) < 30  # short enough for the pioarduino package paths


def test_pio_core_dir_default(monkeypatch, isolated_home):
    monkeypatch.delenv("DESKBUDDY_PIO_CORE", raising=False)
    assert paths.platformio_core_dir(is_windows=False) == isolated_home / "platformio" / "core"
    assert paths.platformio_core_dir(is_windows=True, long_paths=True) == isolated_home / "platformio" / "core"
    assert paths.platformio_venv_dir() == isolated_home / "platformio" / "venv"


def test_long_paths_probe_returns_bool():
    assert isinstance(paths.windows_long_paths_enabled(), bool)


def test_paths_default_home(monkeypatch, tmp_path):
    monkeypatch.delenv("DESKBUDDY_HOME")
    monkeypatch.setattr(paths.Path, "home", lambda: tmp_path)
    assert paths.data_dir() == tmp_path / ".deskbuddy"
