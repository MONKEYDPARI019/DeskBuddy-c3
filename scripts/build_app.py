#!/usr/bin/env python3
"""Build the ready-made DeskBuddy programs (no Python needed).

    python scripts/build_app.py [<out_dir>]          the `deskbuddy` command for the npm package
    python scripts/build_app.py --gui [<out_dir>]    the double-click app, DeskBuddy.exe

Default out_dir: dist. Both run PyInstaller on this machine's OS and check the result before
writing it to out_dir:

- `deskbuddy` (console, one folder): must start and run esptool from inside itself, then it is
  packed as deskbuddy-<version>-<platform>.tar.gz with one top-level folder, `deskbuddy/`.
  <platform> is win32-x64, linux-x64, linux-arm64, darwin-arm64 or darwin-x64, the same names
  the npm launcher (npm/lib/launcher.js) asks for.
- `DeskBuddy.exe` (windowed, one file, DeskBuddy icon): must report its version through a pipe,
  run esptool from inside itself, start itself as esptool and read its output the way INSTALL
  does, and open the installer window for a few seconds (`--self-test`). On Linux the same
  build is written as DeskBuddy-<platform> (for testing; needs a display, e.g. xvfb-run).

Needs: the tool installed (pip install ./tool) and pyinstaller.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tool"
PACKAGING = TOOL / "packaging"
ICON = PACKAGING / "deskbuddy.ico"
BUILD = ROOT / "build" / "app"
GUI_NAME = "DeskBuddy"

# esptool loads its flasher stubs from data files and finds commands by module; pyserial opens
# rfc2217:// / socket:// ports through modules it imports by name
BUNDLE_ARGS = [
    "--collect-data",
    "esptool",
    "--collect-submodules",
    "esptool",
    "--copy-metadata",
    "esptool",
    "--copy-metadata",
    "pyserial",
    "--collect-submodules",
    "serial",
]
_ARCH = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}

# Tcl/Tk data the installer window never uses: time zones (609 files), translations and demo
# images. A one-file program unpacks every bundled file at each start (and Windows Defender
# scans each one), so leaving these ~770 files out makes DeskBuddy.exe open much faster.
UNUSED_DATA = ("_tcl_data/tzdata/", "_tcl_data/msgs/", "_tk_data/msgs/", "_tk_data/images/")
_SPEC_FILTER = (
    "# build_app.py: leave out Tcl/Tk data the installer window never uses (faster start)\n"
    "a.datas = [d for d in a.datas if not d[0].replace('\\\\', '/').startswith({prefixes!r})]\n"
)


def build_with_filtered_data(name: str, options: list[str], entry: Path, dist: Path, work: Path) -> None:
    """PyInstaller with the same options as on its command line, minus UNUSED_DATA.

    pyi-makespec writes the spec, the filter goes in right after the analysis, then the spec is built.
    """
    BUILD.mkdir(parents=True, exist_ok=True)
    makespec = [sys.executable, "-m", "PyInstaller.utils.cliutils.makespec", "--name", name, "--specpath", str(BUILD)]
    subprocess.run([*makespec, *options, str(entry)], check=True)
    spec = BUILD / f"{name}.spec"
    text = spec.read_text(encoding="utf-8")
    marker = "pyz = PYZ("
    if marker not in text:
        raise SystemExit(f"error: unexpected spec layout in {spec}")
    text = text.replace(marker, _SPEC_FILTER.format(prefixes=UNUSED_DATA) + marker, 1)
    spec.write_text(text, encoding="utf-8")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(dist)]
    cmd += ["--workpath", str(work), str(spec)]
    print("==> " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


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
    options = ["--onedir", "--console", *BUNDLE_ARGS]
    build_with_filtered_data("deskbuddy", options, PACKAGING / "entry.py", BUILD / "dist", BUILD / "work")
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


def version_file(version: str) -> Path:
    """Windows file properties (Details tab) for DeskBuddy.exe."""
    numbers = [int(part) for part in re.findall(r"\d+", version)[:3]]
    numbers += [0] * (4 - len(numbers))
    fixed = tuple(numbers)
    strings = {
        "CompanyName": "DeskBuddy",
        "FileDescription": "DeskBuddy Installer",
        "FileVersion": version,
        "InternalName": GUI_NAME,
        "LegalCopyright": "MIT License",
        "OriginalFilename": f"{GUI_NAME}.exe",
        "ProductName": "DeskBuddy",
        "ProductVersion": version,
    }
    table = ", ".join(f"StringStruct({key!r}, {value!r})" for key, value in strings.items())
    text = (
        "VSVersionInfo(\n"
        f"  ffi=FixedFileInfo(filevers={fixed}, prodvers={fixed}, mask=0x3f, flags=0x0, OS=0x40004,\n"
        "                    fileType=0x1, subtype=0x0, date=(0, 0)),\n"
        f"  kids=[StringFileInfo([StringTable('040904B0', [{table}])]),\n"
        "        VarFileInfo([VarStruct('Translation', [1033, 1200])])]\n"
        ")\n"
    )
    BUILD.mkdir(parents=True, exist_ok=True)
    path = BUILD / "version_info.txt"
    path.write_text(text, encoding="utf-8")
    return path


def run_pyinstaller_gui(version: str) -> Path:
    """One windowed file with the installer window; esptool runs inside it like in the console build."""
    options = [
        "--onefile",
        "--windowed",
        "--icon",
        str(ICON),
        "--add-data",
        f"{ICON}{os.pathsep}.",  # window and taskbar icon, see deskbuddy.ui._set_icon
    ]
    if sys.platform == "win32":
        options += ["--version-file", str(version_file(version))]
    options += BUNDLE_ARGS
    build_with_filtered_data(GUI_NAME, options, PACKAGING / "gui_entry.py", BUILD / "dist-gui", BUILD / "work-gui")
    exe = BUILD / "dist-gui" / (f"{GUI_NAME}.exe" if sys.platform == "win32" else GUI_NAME)
    if not exe.is_file():
        raise SystemExit(f"error: PyInstaller did not produce {exe}")
    return exe


def smoke_test_gui(exe: Path, version: str) -> None:
    """Version through a pipe (the same path esptool output takes), esptool inside it, the window."""
    checks = [
        (["--version"], lambda text: f"DeskBuddy {version}" in text),
        (["--run-esptool", "version"], lambda text: re.search(r"\d+\.\d+", text) is not None),
        (["--self-test"], lambda text: "esptool child:" in text and "self-test ok" in text),
    ]
    for args, ok in checks:
        out = subprocess.run([str(exe), *args], capture_output=True, text=True, timeout=300)
        text = out.stdout + out.stderr
        if out.returncode != 0 or not ok(text):
            raise SystemExit(f"error: '{exe.name} {' '.join(args)}' failed (exit {out.returncode}):\n{text}")
        print(f"==> {exe.name} {' '.join(args)}: {text.strip().splitlines()[-1]}", flush=True)


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
    gui = "--gui" in argv
    rest = [arg for arg in argv if arg != "--gui"]
    out_dir = Path(rest[0] if rest else "dist").resolve()
    version = tool_version()
    if gui:
        exe = run_pyinstaller_gui(version)
        smoke_test_gui(exe, version)
        out_dir.mkdir(parents=True, exist_ok=True)
        name = exe.name if sys.platform == "win32" else f"{GUI_NAME}-{platform_key()}"
        target = out_dir / name
        shutil.copy2(exe, target)
        print(f"==> {target}  ({target.stat().st_size:,} bytes)", flush=True)
        return 0
    exe = run_pyinstaller()
    smoke_test(exe, version)
    archive = pack(exe.parent, out_dir, version)
    print(f"==> {archive}  ({archive.stat().st_size:,} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
