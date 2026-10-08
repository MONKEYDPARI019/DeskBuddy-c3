#!/usr/bin/env python3
"""Build DeskBuddy C3 firmware and produce ready-to-flash images.

    python scripts/merge_firmware.py <env> [<env> ...] <out_dir>

For each PlatformIO env (c3, c3-battery): runs `pio run -e <env>`, reads the flash layout from
`pio project metadata`, merges bootloader + partitions + boot_app0 + app with esptool into
<out_dir>/deskbuddy-c3-<env>-v<semver>.bin, then (re)writes <out_dir>/SHA256SUMS and manifest.json.

The logic lives in the deskbuddy tool (tool/src/deskbuddy/firmware.py) so the CLI's
`deskbuddy build` and this script share one implementation. Needs: platformio, esptool.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tool" / "src"))

from deskbuddy import envs, firmware  # noqa: E402
from deskbuddy.errors import DeskBuddyError  # noqa: E402


def pio_command() -> list[str]:
    if importlib.util.find_spec("platformio") is not None:
        return [sys.executable, "-m", "platformio"]
    return ["pio"]


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    *env_names, out = argv
    out_dir = Path(out).resolve()
    project = ROOT / "firmware"
    try:
        pio_envs = [envs.to_pio_env(name) for name in env_names]
        version = None
        for pio_env in pio_envs:
            print(f"==> building {pio_env}", flush=True)
            merged = firmware.build_and_merge(
                project,
                pio_env,
                out_dir,
                pio_cmd=pio_command(),
                env=None,
                on_line=lambda line: print(line, flush=True),
            )
            version = merged.version
            print(f"==> {merged.path.name}  {merged.size} bytes  sha256 {merged.sha256}", flush=True)
        assert version is not None
        sums, manifest = firmware.write_release_files(out_dir, version)
        print(f"==> wrote {sums} and {manifest}")
    except DeskBuddyError as exc:
        print(f"error: {exc.message}\n{exc.hint}", file=sys.stderr)
        return exc.exit_code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
