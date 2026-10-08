"""`deskbuddy` command line: argument parsing and human-friendly output.

All serial/flash/download logic lives in the core modules; this file only wires options to
them and prints results. Errors are shown as "what happened" + "what to do"; tracebacks only
with --debug.
"""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable, Optional, TextIO

from deskbuddy import REPO, __version__, envs, flasher, github, installer, monitor, paths, ports, serial_io
from deskbuddy.errors import EXIT_ERROR, EXIT_INTERRUPTED, EXIT_OK, DeskBuddyError, UsageError


class Console:
    """Printing helpers that degrade gracefully on non-UTF-8 / non-TTY outputs."""

    def __init__(self, out: TextIO, err: TextIO) -> None:
        self.out = out
        self.err = err
        self.tty = bool(getattr(out, "isatty", lambda: False)())
        encoding = getattr(out, "encoding", None) or "ascii"
        try:
            "✓✗█░".encode(encoding)
            self.unicode = True
        except (UnicodeEncodeError, LookupError):
            self.unicode = False
        self._progress_shown = False

    @property
    def ok(self) -> str:
        return "✓" if self.unicode else "OK"

    @property
    def bad(self) -> str:
        return "✗" if self.unicode else "X"

    def print(self, text: str = "") -> None:
        self.end_progress()
        print(text, file=self.out, flush=True)

    def note(self, text: str) -> None:
        self.end_progress()
        print(text, file=self.err, flush=True)

    def progress(self, pct: float, label: str = "") -> None:
        if not self.tty:
            return
        width = 30
        filled = int(width * pct / 100)
        fill, empty = ("█", "░") if self.unicode else ("#", "-")
        self.out.write(f"\r{fill * filled}{empty * (width - filled)} {pct:5.1f}%  {label}"[:100])
        self.out.flush()
        self._progress_shown = True

    def end_progress(self) -> None:
        if self._progress_shown:
            self.out.write("\n")
            self._progress_shown = False


# --- commands -----------------------------------------------------------------------


def cmd_ports(args: argparse.Namespace, con: Console) -> int:
    found = ports.list_ports()
    if not found:
        con.print("No serial ports found.")
        return EXIT_OK
    for p in found:
        marker = "*" if p.kind == ports.KIND_ESP32C3 else ("?" if p.kind == ports.KIND_POSSIBLE else " ")
        con.print(f"{marker} {p.describe()}")
    con.print("\n* = ESP32-C3 (DeskBuddy)   ? = possible ESP32 (USB-UART chip)")
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace, con: Console) -> int:
    from deskbuddy import doctor

    results = doctor.run_checks(doctor.default_deps())
    con.print(doctor.format_results(results, ascii_only=not con.unicode))
    failed = [r for r in results if not r.ok]
    con.print()
    con.print(f"{len(results) - len(failed)} of {len(results)} checks passed.")
    return EXIT_OK if not failed else EXIT_ERROR


def _release_builds(rel: github.Release) -> list[str]:
    builds = []
    for asset in rel.assets:
        parsed = envs.parse_image_filename(asset.name)
        if parsed:
            builds.append(envs.to_friendly(parsed[0]))
    return builds


def cmd_versions(args: argparse.Namespace, con: Console) -> int:
    releases = github.GitHubClient().list_releases()
    if not releases:
        con.print(f"No releases published yet on github.com/{REPO}.")
        return EXIT_OK
    latest = next((r.tag for r in releases if not r.prerelease), None)
    for rel in releases:
        tags = [t for t in ("latest" if rel.tag == latest else "", "pre-release" if rel.prerelease else "") if t]
        extra = f" ({', '.join(tags)})" if tags else ""
        con.print(f"{rel.tag:<12} {rel.date}  builds: {', '.join(_release_builds(rel)) or '-'}{extra}")
        for asset in rel.assets:
            con.print(f"    {asset.name}  ({asset.size:,} bytes)")
    return EXIT_OK


def cmd_get(args: argparse.Namespace, con: Console) -> int:
    client = github.GitHubClient()
    release = client.get_release(args.version)
    con.print(f"Release {release.tag} ({release.date})")
    for pio_env in envs.PIO_ENVS:
        try:
            path = github.fetch_firmware(
                release, pio_env, paths.firmware_cache_dir(), client, progress=lambda p: con.progress(p, "downloading")
            )
        except UsageError as exc:
            con.print(f"  - {exc.message}")
            continue
        con.print(f"  {con.ok} {envs.to_friendly(pio_env)} firmware: {path}")
    dest = Path(args.dest).expanduser() if args.dest else Path.cwd()
    source = github.get_source(release, dest, client)
    con.print(f"  {con.ok} source code: {source}")
    return EXIT_OK


def _ask_port(con: Console) -> Optional[ports.Asker]:
    if not (sys.stdin and sys.stdin.isatty()):
        return None

    def ask(candidates: Sequence[ports.BoardPort]) -> ports.BoardPort:
        con.print("Several boards found:")
        for i, c in enumerate(candidates, 1):
            con.print(f"  {i}) {c.describe()}")
        while True:
            answer = input(f"Which one? [1-{len(candidates)}]: ").strip()
            if answer.isdigit() and 1 <= int(answer) <= len(candidates):
                return candidates[int(answer) - 1]

    return ask


def _flash_callbacks(con: Console, verbose: bool) -> flasher.FlashCallbacks:
    def hint(text: str) -> None:
        con.note("")
        con.note(f"  >>> {text} <<<")
        con.note("  (the board did not enter download mode by itself)")

    def output(line: str) -> None:
        if verbose:
            con.note(f"  | {line}")

    return flasher.FlashCallbacks(
        progress=lambda p: con.progress(p, "Writing firmware..."), status=con.note, boot_hint=hint, output=output
    )


def cmd_flash(args: argparse.Namespace, con: Console) -> int:
    opts = installer.InstallOptions(
        version=args.version,
        file=Path(args.file).expanduser() if args.file else None,
        local=args.local,
        path=Path(args.path).expanduser() if args.path else None,
        env=args.env,
        port=args.port,
        erase=args.erase,
        baud=args.baud,
    )
    result = installer.install(opts, callbacks=_flash_callbacks(con, args.verbose), ask=_ask_port(con))
    con.end_progress()
    con.print(f"{result.message} {con.ok if result.boot else ''}".rstrip())
    if args.no_monitor:
        return EXIT_OK
    con.note("Opening the serial monitor (Ctrl+C to quit)...")
    return run_monitor(result.port, con, log=None, raw=False, follow_any=args.port is None)


def run_monitor(
    port: Optional[str],
    con: Console,
    log: Optional[Path],
    raw: bool,
    follow_any: bool,
    stdin: Optional[TextIO] = None,
    max_steps: Optional[int] = None,
    opener: Optional[Callable[[str], Any]] = None,
) -> int:
    """Interactive monitor loop: board output to stdout, typed lines to the board."""
    source = stdin if stdin is not None else sys.stdin
    typed_lines: queue.Queue[str] = queue.Queue()
    echo = not (source is not None and source.isatty())

    def reader() -> None:
        assert source is not None
        for line in source:
            typed_lines.put(line.rstrip("\r\n"))

    if source is not None:
        threading.Thread(target=reader, daemon=True).start()

    def resolve() -> Optional[str]:
        if not follow_any:
            return port
        names = [p.device for p in ports.board_candidates(ports.list_ports())]
        return port if port in names else (names[0] if names else None)

    with monitor.LogWriter(log) as logger:

        def on_line(text: str) -> None:
            logger.write(text)
            con.print(monitor.colourise(text, enabled=con.tty and not raw))

        mon = monitor.ReconnectingMonitor(
            resolve_port=resolve, on_line=on_line, on_status=lambda s: con.note(f"[{s}]"), opener=opener
        )
        steps = 0
        try:
            while max_steps is None or steps < max_steps:
                steps += 1
                mon.step()
                while not typed_lines.empty():
                    typed = typed_lines.get_nowait()
                    if not typed.strip():
                        continue
                    logger.write(f"> {typed}")
                    if echo and not raw:
                        con.print(f"> {typed}")
                    mon.send(typed)
        except KeyboardInterrupt:
            con.note("\n[monitor closed]")
        finally:
            mon.close()
    return EXIT_OK


def cmd_monitor(args: argparse.Namespace, con: Console) -> int:
    port = args.port
    if port is None:
        candidates = ports.board_candidates(ports.list_ports())
        port = candidates[0].device if candidates else None
    log = Path(args.log).expanduser() if args.log else None
    return run_monitor(port, con, log=log, raw=args.raw, follow_any=args.port is None)


def _port_for(args: argparse.Namespace, con: Console) -> str:
    return ports.choose_port(args.port, ports.list_ports(), ask=_ask_port(con))


def cmd_cmd(args: argparse.Namespace, con: Console) -> int:
    port = _port_for(args, con)
    reply = serial_io.run_command(port, args.text, timeout=args.timeout)
    con.print(reply.strip("\r\n"))
    return EXIT_OK


def _shortcut(text: str) -> Callable[[argparse.Namespace, Console], int]:
    def run(args: argparse.Namespace, con: Console) -> int:
        args.text = text
        return cmd_cmd(args, con)

    return run


def cmd_link(args: argparse.Namespace, con: Console) -> int:
    port = _port_for(args, con)
    mode = installer.switch_link(port, args.mode, status=con.note)
    con.print(f"Link is now {'Bluetooth (ble)' if mode == 'ble' else 'WiFi'} {con.ok}")
    return EXIT_OK


def cmd_reboot(args: argparse.Namespace, con: Console) -> int:
    port = _port_for(args, con)
    ser = serial_io.open_serial(port)
    try:
        serial_io.send_line(ser, "reboot")
    finally:
        ser.close()
    info = installer.confirm_boot(port, installer.Deps(), status=con.note)
    if info is None:
        con.print("Reboot command sent; the board did not report back yet (try 'deskbuddy monitor').")
    else:
        con.print(f"Board restarted: DeskBuddy C3 v{info.version} ({info.build} build) {con.ok}")
    return EXIT_OK


def cmd_build(args: argparse.Namespace, con: Console) -> int:
    pio_env = envs.to_pio_env(args.env)
    out_dir = Path(args.out).expanduser() if args.out else None
    path = Path(args.path).expanduser() if args.path else None
    on_line = (lambda line: con.note(f"  | {line}")) if args.verbose else None
    merged = installer.build_local(path, pio_env, out_dir=out_dir, status=con.note, on_line=on_line)
    con.print(f"{con.ok} Built {merged.path}")
    con.print(f"  sha256 {merged.sha256}  ({merged.size:,} bytes)")
    return EXIT_OK


def cmd_ui(args: argparse.Namespace, con: Console) -> int:
    try:
        import tkinter  # noqa: F401
    except ImportError as exc:
        raise DeskBuddyError(
            "Tkinter (the Python GUI toolkit) is not installed",
            "On Debian/Ubuntu: sudo apt install python3-tk   (Fedora: sudo dnf install python3-tkinter)",
        ) from exc
    from deskbuddy import ui

    ui.main()
    return EXIT_OK


# --- parser -------------------------------------------------------------------------


def _add_port(p: argparse.ArgumentParser) -> None:
    p.add_argument("--port", "-p", help="serial port (default: auto-detect the DeskBuddy)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deskbuddy",
        description="Install firmware on and talk to a DeskBuddy C3 (ESP32-C3) board.",
        epilog="Run 'deskbuddy <command> --help' for the options of a command.",
    )
    parser.add_argument("--version", action="version", version=f"deskbuddy {__version__}")
    parser.add_argument("--debug", action="store_true", help="show full tracebacks on errors")
    parser.add_argument("--verbose", "-v", action="store_true", help="show esptool/PlatformIO output")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    def add(name: str, func: Callable[..., int], help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.set_defaults(func=func)
        return p

    add("ports", cmd_ports, "list serial ports and mark ESP32-C3 boards")
    add("doctor", cmd_doctor, "check Python, packages, board, port, GitHub access and permissions")
    add("versions", cmd_versions, "list firmware releases available on GitHub")

    p = add("get", cmd_get, "download release firmware images and the release source code")
    p.add_argument("--version", dest="version", metavar="vX.Y.Z", help="release to get (default: latest)")
    p.add_argument("--dest", metavar="DIR", help="where to extract the source code (default: current folder)")

    p = add("flash", cmd_flash, "install DeskBuddy firmware on the board")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--version", dest="version", metavar="vX.Y.Z", help="release to install (default: latest)")
    src.add_argument("--file", metavar="PATH", help="install a local merged .bin image")
    src.add_argument("--local", action="store_true", help="build the source in --path (or here) and install it")
    p.add_argument("--path", metavar="DIR", help="source folder for --local (default: current folder)")
    p.add_argument("--env", choices=sorted(envs.ENV_MAP), default="usb", help="build variant (default: usb)")
    _add_port(p)
    p.add_argument("--erase", action="store_true", help="erase the whole flash first (resets saved settings)")
    p.add_argument("--baud", type=int, metavar="N", help="flash speed (default: 921600, falls back to slower)")
    p.add_argument("--no-monitor", action="store_true", help="exit after flashing instead of opening the monitor")

    p = add("monitor", cmd_monitor, "interactive serial monitor (survives board resets)")
    _add_port(p)
    p.add_argument("--log", metavar="FILE", help="also append everything to FILE")
    p.add_argument("--raw", action="store_true", help="no colours and no local echo")

    p = add("cmd", cmd_cmd, "send one command to the board and print the reply")
    p.add_argument("text", help='the command, e.g. "status" or "face happy"')
    p.add_argument("--timeout", type=float, default=5.0, metavar="S", help="max seconds to wait (default: 5)")
    _add_port(p)

    for name, text, help_text in (
        ("status", "status", "show the board status (shortcut for: cmd status)"),
        ("wifi-forget", "wifi forget", 'erase the saved WiFi network (shortcut for: cmd "wifi forget")'),
    ):
        p = add(name, _shortcut(text), help_text)
        p.add_argument("--timeout", type=float, default=5.0, metavar="S", help="max seconds to wait (default: 5)")
        _add_port(p)

    p = add("link", cmd_link, "switch the radio to Bluetooth (ble) or WiFi and confirm after the restart")
    p.add_argument("mode", choices=["ble", "wifi"], help="ble or wifi")
    _add_port(p)

    p = add("reboot", cmd_reboot, "restart the board and wait for it to come back")
    _add_port(p)

    p = add("build", cmd_build, "build the firmware from source with an isolated PlatformIO")
    p.add_argument("--env", choices=sorted(envs.ENV_MAP), default="usb", help="build variant (default: usb)")
    p.add_argument("--path", metavar="DIR", help="source folder (default: current folder)")
    p.add_argument("--out", metavar="DIR", help="where to put the merged image (default: ~/.deskbuddy/builds)")

    add("ui", cmd_ui, "open the installer window")
    return parser


def _report(exc: DeskBuddyError, con: Console) -> None:
    con.end_progress()
    con.note(f"{con.bad} {exc.message}")
    for line in exc.hint.splitlines():
        con.note(f"  -> {line}")


def main(argv: Optional[Sequence[str]] = None, out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure: Any = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(errors="replace")
    con = Console(out or sys.stdout, err or sys.stderr)
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help(con.out)
        return EXIT_OK
    try:
        return int(args.func(args, con))
    except DeskBuddyError as exc:
        if args.debug:
            traceback.print_exc(file=con.err)
        _report(exc, con)
        return exc.exit_code
    except KeyboardInterrupt:
        con.note("\nInterrupted.")
        return EXIT_INTERRUPTED
    except Exception as exc:  # last-resort friendly message; details only with --debug
        if args.debug:
            traceback.print_exc(file=con.err)
        con.note(f"{con.bad} Unexpected error: {exc}")
        con.note("  -> Run the command again with --debug and report the output on GitHub.")
        return EXIT_ERROR
