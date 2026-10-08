"""Build firmware with PlatformIO and merge it into one flashable image (+ SHA256SUMS, manifest.json).

Shared by `deskbuddy build` / `flash --local` and by scripts/merge_firmware.py (CI releases).
Flash offsets come from `pio project metadata`, never hard-coded; for the ESP32-C3 the
bootloader must sit at 0x0 and the app at 0x10000, which is asserted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from deskbuddy import __version__
from deskbuddy.builder import stream_command
from deskbuddy.checksums import format_sha256sums, sha256_file
from deskbuddy.envs import CHIP, image_filename, parse_image_filename, to_friendly
from deskbuddy.errors import BuildError
from deskbuddy.esptool_compat import Syntax, current_syntax, run_esptool
from deskbuddy.versions import read_fw_version

BOOTLOADER_OFFSET = 0x0
APP_OFFSET = 0x10000
FLASH_MODE = "dio"
FLASH_SIZE = "4MB"
SUMS_FILE = "SHA256SUMS"
MANIFEST_FILE = "manifest.json"

LineCallback = Callable[[str], None]


@dataclass(frozen=True)
class FlashImage:
    offset: int
    path: Path


@dataclass(frozen=True)
class MergedImage:
    env: str
    path: Path
    sha256: str
    size: int
    version: str


def parse_metadata_output(text: str) -> Any:
    """`pio project metadata --json-output` may print warnings first; parse from the first '{'."""
    start = text.find("{")
    if start < 0:
        raise BuildError("PlatformIO did not return project metadata", "Run with --verbose to see its output.")
    try:
        return json.loads(text[start:])
    except ValueError as exc:
        raise BuildError("PlatformIO returned unreadable project metadata", "Run with --verbose.") from exc


def flash_images(meta: Any, env: str) -> list[FlashImage]:
    """bootloader, partitions, boot_app0 and app images with their offsets, sorted by offset."""
    data = meta.get(env) if isinstance(meta, dict) else None
    if not isinstance(data, dict):
        raise BuildError(f"PlatformIO returned no metadata for env '{env}'", "Check platformio.ini.")
    try:
        extra = data["extra"]
        images = [FlashImage(int(str(i["offset"]), 16), Path(i["path"])) for i in extra["flash_images"]]
        app_offset = int(str(extra.get("application_offset", hex(APP_OFFSET))), 16)
        images.append(FlashImage(app_offset, Path(data["prog_path"]).with_suffix(".bin")))
    except (KeyError, TypeError, ValueError) as exc:
        raise BuildError(f"Unexpected PlatformIO metadata format ({exc})", "Update PlatformIO or report this.") from exc
    images.sort(key=lambda i: i.offset)
    boot = next((i for i in images if "bootloader" in i.path.name), None)
    if boot is None or boot.offset != BOOTLOADER_OFFSET:
        raise BuildError("The ESP32-C3 bootloader must be flashed at 0x0", f"PlatformIO reported: {boot}")
    if app_offset != APP_OFFSET:
        raise BuildError(f"The app must start at 0x10000 (got {hex(app_offset)})", "Check partitions.csv.")
    missing = [str(i.path) for i in images if not i.path.is_file()]
    if missing:
        raise BuildError(f"Build output missing: {', '.join(missing)}", "Run the build again.")
    return images


def merge_args(syntax: Syntax, images: list[FlashImage], out: Path) -> list[str]:
    args = ["--chip", CHIP, syntax.merge_bin, "-o", str(out), "-fm", FLASH_MODE, "-fs", FLASH_SIZE]
    for image in images:
        args += [hex(image.offset), str(image.path)]
    return args


def _tail(lines: list[str], count: int = 15) -> str:
    return "\n".join(line for line in lines[-count:] if line.strip())


def build_and_merge(
    project: Path,
    pio_env: str,
    out_dir: Path,
    pio_cmd: list[str],
    env: Optional[dict[str, str]],
    on_line: Optional[LineCallback] = None,
    runner: Callable[..., int] = stream_command,
    esptool_runner: Optional[Callable[..., Any]] = None,
    syntax: Optional[Syntax] = None,
) -> MergedImage:
    """`pio run -e <env>`, read the flash layout, merge into out_dir/deskbuddy-c3-<env>-v<semver>.bin."""
    version = read_fw_version(project / "src" / "config.h")
    log: list[str] = []

    def collect(line: str) -> None:
        log.append(line)
        if on_line:
            on_line(line)

    if runner([*pio_cmd, "run", "-e", pio_env], cwd=project, env=env, on_line=collect) != 0:
        raise BuildError(f"Firmware build failed ({pio_env})", _tail(log))
    meta_lines: list[str] = []
    if (
        runner(
            [*pio_cmd, "project", "metadata", "-e", pio_env, "--json-output"],
            cwd=project,
            env=env,
            on_line=meta_lines.append,
        )
        != 0
    ):
        raise BuildError("Could not read the PlatformIO project metadata", _tail(meta_lines))
    images = flash_images(parse_metadata_output("\n".join(meta_lines)), pio_env)

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / image_filename(pio_env, version)
    result = (esptool_runner or run_esptool)(merge_args(syntax or current_syntax(), images, out), on_line=on_line)
    if result.returncode != 0:
        raise BuildError("esptool could not merge the firmware images", _tail(result.output.splitlines()))
    return MergedImage(pio_env, out, sha256_file(out), out.stat().st_size, version)


def write_release_files(out_dir: Path, version: str, tool_min_version: str = __version__) -> tuple[Path, Path]:
    """Write SHA256SUMS and manifest.json for every deskbuddy-c3-*-v<version>.bin in out_dir."""
    found: list[tuple[str, Path]] = []
    for path in sorted(out_dir.glob(f"deskbuddy-c3-*-v{version}.bin")):
        parsed = parse_image_filename(path.name)
        if parsed and parsed[1] == version:
            found.append((parsed[0], path))
    if not found:
        raise BuildError(f"No firmware images for v{version} in {out_dir}", "Build the firmware first.")
    found.sort(key=lambda item: (item[0] != "c3", item[0]))
    hashes = {path.name: sha256_file(path) for _, path in found}
    sums = out_dir / SUMS_FILE
    sums.write_text(format_sha256sums(hashes), encoding="utf-8", newline="\n")
    manifest = {
        "version": version,
        "tool_min_version": tool_min_version,
        "chip": CHIP,
        "images": [
            {
                "env": env,
                "build": to_friendly(env),
                "file": path.name,
                "sha256": hashes[path.name],
                "size": path.stat().st_size,
                "chip": CHIP,
                "offset": "0x0",
            }
            for env, path in found
        ],
    }
    manifest_path = out_dir / MANIFEST_FILE
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return sums, manifest_path
