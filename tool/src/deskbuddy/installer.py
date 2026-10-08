"""High-level flows shared by the CLI and the installer window: pick an image, flash it,
confirm the board booted, and switch the radio link."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from deskbuddy import envs, flasher, github, paths, ports, serial_io
from deskbuddy.errors import DeskBuddyError, NoReplyError, UsageError
from deskbuddy.esptool_compat import Syntax, current_syntax, run_esptool

_BOOT_RE = re.compile(r"DeskBuddy C3 (\S+) \((USB|battery) build\)")
_LINK_RE = re.compile(r"^link\s+(ble|wifi)\b", re.MULTILINE)
BANNER_WAIT = 4.0
REBOOT_TIMEOUT = 25.0
LINK_NAMES = {"ble": "ble", "bt": "ble", "bluetooth": "ble", "wifi": "wifi"}


@dataclass(frozen=True)
class BootInfo:
    version: str
    build: str


@dataclass
class InstallOptions:
    version: Optional[str] = None
    file: Optional[Path] = None
    local: bool = False
    path: Optional[Path] = None
    env: str = "usb"
    port: Optional[str] = None
    erase: bool = False
    baud: Optional[int] = None


@dataclass(frozen=True)
class ResolvedImage:
    path: Path
    label: str


@dataclass(frozen=True)
class InstallResult:
    port: str
    baud: int
    image: ResolvedImage
    boot: Optional[BootInfo]

    @property
    def message(self) -> str:
        if self.boot is None:
            return f"Flashed {self.image.label}, but could not confirm the boot message (try 'deskbuddy monitor')"
        return f"Installed DeskBuddy C3 v{self.boot.version}"


def _default_syntax() -> Syntax:
    return current_syntax()


@dataclass
class Deps:
    """Everything that touches hardware/processes, injectable for tests."""

    lister: Optional[ports.Lister] = None
    run_esptool: Callable[..., Any] = run_esptool
    wait_for_board: Callable[..., Optional[str]] = serial_io.wait_for_board
    open_serial: Callable[[str], Any] = serial_io.open_serial
    run_command: Callable[..., str] = serial_io.run_command
    syntax: Optional[Syntax] = None
    sleep: Callable[[float], None] = time.sleep
    extra: dict[str, Any] = field(default_factory=dict)


def parse_boot_info(text: str) -> Optional[BootInfo]:
    match = _BOOT_RE.search(text)
    if not match:
        return None
    try:
        from deskbuddy.versions import parse_fw_version

        version = parse_fw_version(match.group(1))
    except DeskBuddyError:
        version = match.group(1)
    return BootInfo(version, match.group(2))


def parse_link(text: str) -> Optional[str]:
    match = _LINK_RE.search(text)
    return match.group(1) if match else None


def pick_port(requested: Optional[str], deps: Deps, ask: Optional[ports.Asker] = None) -> str:
    return ports.choose_port(requested, ports.list_ports(deps.lister), ask=ask)


def build_local(
    path: Optional[Path],
    pio_env: str,
    out_dir: Optional[Path] = None,
    status: Optional[Callable[[str], None]] = None,
    on_line: Optional[Callable[[str], None]] = None,
) -> Any:
    """Build the firmware at `path` with the isolated PlatformIO and return the merged image."""
    from deskbuddy import builder, firmware

    project = builder.find_project(path)
    pio_cmd = builder.platformio_command(paths.platformio_venv_dir(), status=status)
    env = builder.child_env(paths.platformio_core_dir())
    target = out_dir or (paths.data_dir() / "builds")
    if status:
        status(f"Building {envs.to_friendly(pio_env)} firmware in {project} (first build downloads ~1 GB)...")
    return firmware.build_and_merge(project, pio_env, target, pio_cmd=pio_cmd, env=env, on_line=on_line)


def resolve_image(
    opts: InstallOptions,
    client: Optional[github.GitHubClient] = None,
    callbacks: Optional[flasher.FlashCallbacks] = None,
) -> ResolvedImage:
    cb = callbacks or flasher.FlashCallbacks()
    sources = sum(bool(x) for x in (opts.version, opts.file, opts.local))
    if sources > 1:
        raise UsageError("Choose only one of --version, --file and --local")
    pio_env = envs.to_pio_env(opts.env)
    if opts.file:
        flasher.check_image(opts.file)
        return ResolvedImage(opts.file, opts.file.name)
    if opts.local:
        merged = build_local(opts.path, pio_env, status=cb.status, on_line=cb.output)
        return ResolvedImage(merged.path, f"local build v{merged.version}")
    cli = client or github.GitHubClient()
    cb.status("Looking up the firmware release on GitHub...")
    release = cli.get_release(opts.version)
    cb.status(f"Downloading {release.tag} ({envs.to_friendly(pio_env)} build)...")
    image = github.fetch_firmware(release, pio_env, paths.firmware_cache_dir(), cli, progress=cb.progress)
    flasher.check_image(image)
    return ResolvedImage(image, release.tag)


def confirm_boot(port: str, deps: Deps, status: Optional[Callable[[str], None]] = None) -> Optional[BootInfo]:
    """Wait for the board to come back after a reset and read its version (banner or 'status')."""
    if status:
        status("Waiting for the board to restart...")
    current = deps.wait_for_board(port, timeout=REBOOT_TIMEOUT, gone_first=True)
    if current is None:
        return None
    try:
        ser = deps.open_serial(current)
    except DeskBuddyError:
        deps.sleep(1.0)
        ser = None
    if ser is not None:
        try:
            info = parse_boot_info(
                serial_io.read_until_idle(ser, idle=1.5, timeout=BANNER_WAIT).decode("utf-8", "replace")
            )
        finally:
            ser.close()
        if info:
            return info
    try:
        return parse_boot_info(deps.run_command(current, "status", timeout=5.0))
    except DeskBuddyError:
        return None


def install(
    opts: InstallOptions,
    deps: Optional[Deps] = None,
    callbacks: Optional[flasher.FlashCallbacks] = None,
    ask: Optional[ports.Asker] = None,
    client: Optional[github.GitHubClient] = None,
    image: Optional[ResolvedImage] = None,
) -> InstallResult:
    d = deps or Deps()
    cb = callbacks or flasher.FlashCallbacks()
    resolved = image or resolve_image(opts, client=client, callbacks=cb)
    port = pick_port(opts.port, d, ask)
    cb.progress(0.0)
    outcome = flasher.flash_image(
        resolved.path,
        port,
        runner=d.run_esptool,
        waiter=lambda p: d.wait_for_board(p, timeout=60.0, gone_first=True),
        syntax=d.syntax or _default_syntax(),
        callbacks=cb,
        erase=opts.erase,
        bauds=flasher.baud_ladder(opts.baud),
    )
    boot = confirm_boot(outcome.port, d, cb.status)
    return InstallResult(outcome.port, outcome.baud, resolved, boot)


def switch_link(
    port: str, mode: str, deps: Optional[Deps] = None, status: Optional[Callable[[str], None]] = None
) -> str:
    """Send 'link <mode>', wait for the restart and confirm the new mode from 'status'."""
    d = deps or Deps()
    wanted = LINK_NAMES.get(mode.strip().lower())
    if wanted is None:
        raise UsageError(f"Unknown link '{mode}'", "Use: deskbuddy link ble   or   deskbuddy link wifi")
    reply = d.run_command(port, f"link {wanted}", timeout=5.0)
    if "already" in reply:
        return wanted
    if "switching" not in reply.lower():
        raise DeskBuddyError(
            f"The board did not accept 'link {wanted}': {reply.strip()[:80]}",
            "Update the firmware with 'deskbuddy flash'.",
        )
    if status:
        status("Board is restarting with the new link...")
    current = d.wait_for_board(port, timeout=REBOOT_TIMEOUT, gone_first=True) or port
    for _ in range(5):
        try:
            found = parse_link(d.run_command(current, "status", timeout=5.0))
        except NoReplyError:
            d.sleep(1.0)
            continue
        except DeskBuddyError:
            d.sleep(1.0)
            current = d.wait_for_board(current, timeout=10.0) or current
            continue
        if found == wanted:
            return wanted
        raise DeskBuddyError(
            f"The board restarted but is still in {found} mode", "Run 'deskbuddy monitor' to see what happened."
        )
    raise NoReplyError("The board did not answer after the restart", "Run 'deskbuddy monitor' to watch it boot.")
