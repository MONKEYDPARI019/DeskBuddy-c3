# PLAN — DeskBuddy C3 repo + `deskbuddy` tool

Source of truth: `MASTER_PROMPT_DeskBuddy-C3.md` (in `D:\ard\c3bud`). This file tracks progress.

## Research findings (2026-10-08)

- esptool **5.x requires Python ≥ 3.10**; 4.x (last 4.10.0) still supports 3.7+. The tool depends on
  `esptool>=4.8,<6` so Python 3.9 gets v4 and newer Pythons get v5.
- v5 renamed commands/options to kebab-case (`merge-bin`, `write-flash`, `--flash-mode`, `default-reset`);
  it still accepts the v4 snake_case names but prints deprecation warnings. The tool picks the spelling for the
  installed major version.
- Progress: v4 prints `Writing at 0x00010000... (5 %)`; v5 (non-TTY) prints one line per update,
  `Writing at 0x00010000 [====>   ]  30.5% …`. One regex covers both. esptool runs as a subprocess
  (`python -m esptool`) with `NO_COLOR=1`, which is stable across both majors (the v5 Python API differs from v4).
- pyserial 3.5 is current. PlatformIO Core 6.2.0 (Python ≥ 3.9).
- `gh` CLI is **not installed** → G2 gives the exact git/web commands instead.
- `app/` has `gradle-wrapper.properties` but no `gradlew` or wrapper jar → CI skips the Android build with a notice.

## Milestones

### A — repository setup
- [x] A1 git init `D:\ard\DeskBuddy-C3` (main), LICENSE, .gitignore, .gitattributes
- [x] A2 copy firmware (no `.pio/`)
- [x] A3 copy Android app (no build/.gradle/.idea/local.properties/keystores)
- [x] A4 README stub

### B — firmware build + images
- [ ] B1 `scripts/merge_firmware.py` (pio run → pio project metadata → esptool merge-bin → versioned .bin + SHA256SUMS), logic in `deskbuddy.firmware`
- [ ] B2 `manifest.json`
- [x] B3 host tests green (537 checks)
- [ ] B4 local build of `c3` + `c3-battery` with isolated `PLATFORMIO_CORE_DIR`

### C — CI/CD
- [ ] `ci.yml`: firmware builds + host tests, ruff + pytest matrix (ubuntu/windows × 3.9/3.12), Android skip notice
- [ ] `release.yml`: tag ↔ FW_VERSION check, build + merge, GitHub Release with assets + CHANGELOG notes

### D — `deskbuddy` CLI (`tool/`)
- [ ] package skeleton (pyproject, hatchling, console script)
- [ ] core modules: ports, serial_io, monitor, github, flasher, firmware(merge), builder, doctor
- [ ] commands: ports, doctor, versions, get, flash, monitor, cmd, status, link, wifi-forget, reboot, build, ui, --version

### E — installer window
- [ ] Tkinter UI over the shared core (worker thread + queue)

### F — tests and quality
- [ ] pytest suite covering the listed areas, coverage ≥ 80 %
- [ ] ruff clean, mypy on core
- [ ] code review + python-reviewer + security-reviewer findings resolved/documented

### G — hardware test + release
- [ ] G1 end-to-end on the board (doctor, flash --local, status, link ble)
- [ ] G2 ask before repo creation / push / tag; verify release assets; fresh-venv pip install test
- [ ] CHANGELOG, HANDOFF.md
