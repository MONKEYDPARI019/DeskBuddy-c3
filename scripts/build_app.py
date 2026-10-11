#!/usr/bin/env python3
"""Build the ready-made `deskbuddy` program (no Python needed) for the npm package.

    python scripts/build_app.py [<out_dir>]          (default out_dir: dist)

Runs PyInstaller on this machine's OS, checks that the program starts and can run esptool,
then packs it as <out_dir>/deskbuddy-<version>-<platform>.tar.gz with one top-level folder,
`deskbuddy/`. <platform> is win32-x64, linux-x64, linux-arm64, darwin-arm64 or darwin-x64, the
same names the npm launcher (npm/lib/launcher.js) asks for.

Needs: the tool installed (pip install ./tool) and pyinstaller.
"""

from __future__ import annotations

import platform
import re
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tool"
BUILD = ROOT / "build" / "app"
_ARCH = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}


def platform_key() -> str:
    arch = _ARCH.get(platform.machine().lower())
    system = {"win32": "win32", "linux": "linux", "darwin": "darwin"}.get(sys.platform)
    if not arch or not system:
        raise SystemExit(f"error: unsupported platform {sys.platform}/{platform.machine()}")
    return f"{system}-{arch}"


def tool_version() -> str:
    text = (TOOL / "src" / "deskbuddy" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"', text, re.M)
    if not match:
        raise SystemExit("error: __version__ not found in tool/src/deskbuddy/__init__.py")
    return match.group(1)


def run_pyinstaller() -> Path:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--name",
        "deskbuddy",
        "--distpath",
        str(BUILD / "dist"),
        "--workpath",
        str(BUILD / "work"),
        "--specpath",
        str(BUILD),
        # esptool loads its flasher stubs from data files and finds commands by module
        "--collect-data",
        "esptool",
        "--collect-submodules",
        "esptool",
        "--copy-metadata",
        "esptool",
        "--copy-metadata",
        "pyserial",
        # pyserial opens rfc2217:// / socket:// ports through modules it imports by name
        "--collect-submodules",
        "serial",
        str(TOOL / "packaging" / "entry.py"),
    ]
    print("==> " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)
    exe = BUILD / "dist" / "deskbuddy" / ("deskbuddy.exe" if sys.platform == "win32" else "deskbuddy")
    if not exe.is_file():
        raise SystemExit(f"error: PyInstaller did not produce {exe}")
    return exe


def smoke_test(exe: Path, version: str) -> None:
    """The program must start, report the right version and run esptool from inside itself."""
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=120)
    if out.returncode != 0 or version not in out.stdout:
        raise SystemExit(f"error: '{exe.name} --version' failed:\n{out.stdout}{out.stderr}")
    print(f"==> {out.stdout.strip()}", flush=True)
    out = subprocess.run([str(exe), "--run-esptool", "version"], capture_output=True, text=True, timeout=120)
    text = out.stdout + out.stderr
    if out.returncode != 0 or not re.search(r"\d+\.\d+", text):
        raise SystemExit(f"error: esptool inside the program failed:\n{text}")
    print(f"==> bundled esptool: {text.strip().splitlines()[-1]}", flush=True)


def pack(folder: Path, out_dir: Path, version: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f"deskbuddy-{version}-{platform_key()}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(folder, arcname="deskbuddy")
    return archive


def main(argv: list[str]) -> int:
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    out_dir = Path(argv[0] if argv else "dist").resolve()
    version = tool_version()
    exe = run_pyinstaller()
    smoke_test(exe, version)
    archive = pack(exe.parent, out_dir, version)
    print(f"==> {archive}  ({archive.stat().st_size:,} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
