from __future__ import annotations

from types import SimpleNamespace

import pytest

from deskbuddy import esptool_compat, installer
from deskbuddy.errors import DeskBuddyError, NoReplyError, UsageError
from deskbuddy.esptool_compat import EsptoolResult
from tests.fakes import ScriptedSerial

GOOD_IMAGE = b"\xe9" + b"\x00" * 70000


def esp_port(device="COM9"):
    return SimpleNamespace(device=device, vid=0x303A, pid=0x1001, description="USB", serial_number=None)


def test_parse_banner_and_status():
    assert installer.parse_boot_info("\n\n=== DeskBuddy C3 c3-2.0.0 (USB build) ===\n") == installer.BootInfo(
        "2.0.0", "USB"
    )
    assert installer.parse_boot_info("DeskBuddy C3 c3-2.1.0 (battery build)\nlink ...") == installer.BootInfo(
        "2.1.0", "battery"
    )
    assert installer.parse_boot_info("garbage") is None


def test_parse_link():
    assert installer.parse_link("DeskBuddy C3 ...\nlink     ble, bluetooth advertising, 0 app(s), \n") == "ble"
    assert installer.parse_link("link     wifi, online, 1 app(s), 192.168.1.5") == "wifi"
    assert installer.parse_link("nothing") is None


class Deps:
    """Builds an installer.Deps with scripted pieces."""

    def __init__(self, esptool_results=None, serials=None, replies=None, ports=None):
        self.esptool_results = list(esptool_results or [])
        self.serials = list(serials or [])
        self.replies = list(replies or [])
        self.esptool_calls = []
        self.commands = []
        self.waits = []
        self.deps = installer.Deps(
            lister=lambda: ports if ports is not None else [esp_port()],
            run_esptool=self._esptool,
            wait_for_board=self._wait,
            open_serial=self._open,
            run_command=self._cmd,
            syntax=esptool_compat.syntax_for(5),
            sleep=lambda s: None,
        )

    def _esptool(self, args, on_line=None):
        self.esptool_calls.append(args)
        rc, out = self.esptool_results.pop(0)
        for line in out.splitlines():
            if on_line:
                on_line(line)
        return EsptoolResult(rc, out)

    def _wait(self, port, timeout=20.0, gone_first=False):
        self.waits.append((port, gone_first))
        return port

    def _open(self, port):
        item = self.serials.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def _cmd(self, port, text, timeout=5.0):
        self.commands.append((port, text))
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "deskbuddy-c3-c3-v2.0.0.bin"
    path.write_bytes(GOOD_IMAGE)
    return path


def test_install_from_file_confirms_banner(image):
    d = Deps(
        esptool_results=[(0, "Writing at 0x00010000... (100 %)\n")],
        serials=[ScriptedSerial([b"\n\n=== DeskBuddy C3 c3-2.0.0 (USB build) ===\n"])],
    )
    events = []
    result = installer.install(
        installer.InstallOptions(file=image, erase=True),
        deps=d.deps,
        callbacks=installer.flasher.FlashCallbacks(status=events.append),
    )
    assert result.port == "COM9"
    assert result.boot == installer.BootInfo("2.0.0", "USB")
    assert result.message == "Installed DeskBuddy C3 v2.0.0"
    assert "-e" in d.esptool_calls[0]
    assert d.waits == [("COM9", True)]


def test_install_falls_back_to_status_command(image):
    d = Deps(
        esptool_results=[(0, "")],
        serials=[ScriptedSerial([b"[Boot] ready\n"])],
        replies=["\nDeskBuddy C3 c3-2.0.0 (USB build)\nlink     ble, ...\n"],
    )
    result = installer.install(installer.InstallOptions(file=image), deps=d.deps)
    assert result.boot == installer.BootInfo("2.0.0", "USB")
    assert d.commands == [("COM9", "status")]


def test_install_without_confirmation(image):
    d = Deps(esptool_results=[(0, "")], serials=[ScriptedSerial([])], replies=[NoReplyError("silent")])
    result = installer.install(installer.InstallOptions(file=image), deps=d.deps)
    assert result.boot is None
    assert "could not confirm" in result.message


def test_install_board_never_comes_back(image):
    d = Deps(esptool_results=[(0, "")])
    d.deps.wait_for_board = lambda port, timeout=20.0, gone_first=False: None
    result = installer.install(installer.InstallOptions(file=image), deps=d.deps)
    assert result.boot is None


def test_install_resolves_release(tmp_path, monkeypatch):
    calls = {}

    class FakeClient:
        def get_release(self, tag):
            calls["tag"] = tag
            return SimpleNamespace(tag="v2.0.0")

    def fake_fetch(release, env, cache_dir, client, progress=None):
        calls["env"] = env
        path = tmp_path / "img.bin"
        path.write_bytes(GOOD_IMAGE)
        return path

    monkeypatch.setattr(installer.github, "fetch_firmware", fake_fetch)
    resolved = installer.resolve_image(installer.InstallOptions(version="2.0.0", env="battery"), client=FakeClient())
    assert calls == {"tag": "2.0.0", "env": "c3-battery"}
    assert resolved.label == "v2.0.0"


def test_resolve_image_rejects_conflicting_sources(image):
    with pytest.raises(UsageError, match="only one"):
        installer.resolve_image(installer.InstallOptions(file=image, local=True))


def test_resolve_image_local_build(monkeypatch, tmp_path):
    built = tmp_path / "local.bin"
    built.write_bytes(GOOD_IMAGE)
    seen = {}

    def fake_build(path, pio_env, out_dir=None, status=None, on_line=None):
        seen["args"] = (path, pio_env)
        return SimpleNamespace(path=built, version="2.0.0")

    monkeypatch.setattr(installer, "build_local", fake_build)
    resolved = installer.resolve_image(installer.InstallOptions(local=True, path=tmp_path))
    assert seen["args"] == (tmp_path, "c3")
    assert resolved.path == built and resolved.label == "local build v2.0.0"


def test_switch_link_already():
    d = Deps(replies=["already ble\n"])
    assert installer.switch_link("COM9", "ble", deps=d.deps) == "ble"


def test_switch_link_confirms_after_restart():
    d = Deps(
        replies=["[App] switching to Bluetooth\n", NoReplyError("booting"), "link     ble, bluetooth advertising\n"]
    )
    assert installer.switch_link("COM9", "bluetooth", deps=d.deps) == "ble"
    assert d.waits[0] == ("COM9", True)
    assert [c[1] for c in d.commands] == ["link ble", "status", "status"]


def test_switch_link_wrong_mode_after_restart():
    d = Deps(replies=["[App] switching to WiFi\n", "link     ble, bluetooth advertising\n"])
    with pytest.raises(DeskBuddyError, match="still in ble"):
        installer.switch_link("COM9", "wifi", deps=d.deps)


def test_switch_link_unexpected_reply():
    d = Deps(replies=["unknown command 'link' (type help)\n"])
    with pytest.raises(DeskBuddyError, match="did not accept"):
        installer.switch_link("COM9", "wifi", deps=d.deps)


def test_switch_link_bad_mode():
    with pytest.raises(UsageError):
        installer.switch_link("COM9", "zigbee", deps=Deps().deps)


def test_pick_port_uses_lister():
    d = Deps(ports=[esp_port("COM4")])
    assert installer.pick_port(None, d.deps) == "COM4"
