# HANDOFF — DeskBuddy C3 (for the documentation writer)

Everything here was verified on 2026-10-08 on Windows 10 (PowerShell + Git Bash) with a real
DeskBuddy C3 (ESP32-C3 Super Mini, USB-Serial/JTAG on COM9), unless marked otherwise.

## 1. Summary

This repo contains the DeskBuddy C3 firmware, the Android app and `deskbuddy`, a Python
command-line tool plus a small Tkinter installer window. It downloads, flashes, builds and
monitors the firmware.

| Item | Version |
|---|---|
| Firmware | `c3-2.0.0` (`FW_VERSION` in `firmware/src/config.h`) |
| Tool (`deskbuddy-cli`) | 2.0.0 |
| esptool | `>=4.8,<6`; tested with 5.5.0 (Python ≥ 3.10) and 4.12.0 (Python 3.9) |
| pyserial | 3.5 |
| PlatformIO Core | 6.2.0 (`platformio>=6.1,<7`) |
| Platform | pioarduino 55.03.36 (Arduino-ESP32 3.3.6) |
| Release | https://github.com/MONKEYDPARI019/DeskBuddy-c3/releases/tag/v2.0.0 |

Repository: https://github.com/MONKEYDPARI019/DeskBuddy-C3 (GitHub shows it as `DeskBuddy-c3`;
URLs are case-insensitive).

## 2. Repo map

```
DeskBuddy-C3/
├─ firmware/                     PlatformIO project (copied unchanged from c3bud/deskbuddy-c3/firmware)
│  ├─ platformio.ini             envs: c3 (USB), c3-battery (-DFEATURE_BATTERY=1), ota (espota)
│  ├─ partitions.csv             4 MB layout: nvs 0x9000, otadata 0xe000, app0 0x10000, app1, spiffs, coredump
│  ├─ src/                       firmware sources (config.h holds FW_VERSION)
│  ├─ docs/PROTOCOL.md           app <-> board protocol (existing)
│  └─ test/host/run_tests.sh     host unit tests (g++), 537 checks
├─ app/                          Android app sources (no build output, no local.properties/keystores)
├─ tool/                         Python package "deskbuddy-cli" -> command `deskbuddy`
│  ├─ pyproject.toml             hatchling, Python >= 3.9, deps esptool + pyserial, extras [build] [dev]
│  ├─ src/deskbuddy/
│  │  ├─ cli.py                  argparse commands and human-friendly output (thin)
│  │  ├─ ui.py                   Tkinter installer window (thin; uses installer/monitor)
│  │  ├─ installer.py            shared flows: pick image, flash, confirm boot, switch link
│  │  ├─ flasher.py              esptool write with baud fallback, BOOT-hint retries, NVS-preserving segments
│  │  ├─ esptool_compat.py       runs `python -m esptool`, hides v4/v5 differences
│  │  ├─ firmware.py             pio run + pio project metadata + esptool merge-bin, SHA256SUMS, manifest.json
│  │  ├─ builder.py              isolated PlatformIO (private venv + own core dir), subprocess streaming
│  │  ├─ github.py               GitHub Releases API, verified downloads, safe zip extraction
│  │  ├─ checksums.py            sha256 + SHA256SUMS format
│  │  ├─ serial_io.py            open port with DTR/RTS off, send command, read until idle, wait for board
│  │  ├─ monitor.py              line buffer, colours, reconnecting monitor state machine, log file
│  │  ├─ ports.py                list/rank serial ports (VID 0x303A, CP210x, CH340)
│  │  ├─ doctor.py               environment checks
│  │  ├─ envs.py / versions.py   usb/battery <-> c3/c3-battery, version strings
│  │  ├─ paths.py                ~/.deskbuddy layout, isolated PlatformIO core location
│  │  └─ errors.py               error classes and exit codes
│  └─ tests/                     pytest suite (fakes for serial, subprocess and HTTP)
├─ scripts/merge_firmware.py     CI/release build: <env>... <out_dir> -> merged .bin + SHA256SUMS + manifest.json
├─ .github/workflows/ci.yml      firmware builds, host tests, tool lint/type/test matrix, Android check
├─ .github/workflows/release.yml on tag vX.Y.Z: tag check, build, GitHub Release with assets
├─ PLAN.md  HANDOFF.md  CHANGELOG.md  LICENSE (MIT)  README.md (stub)
└─ .gitignore  .gitattributes
```

Data folders the tool creates:

| Path | Purpose |
|---|---|
| `~/.deskbuddy/firmware/<tag>/` | downloaded, sha256-verified release images |
| `~/.deskbuddy/platformio/venv/` | private PlatformIO install (when the `[build]` extra is not installed) |
| `~/.deskbuddy/builds/` | default output of `deskbuddy build` |
| PlatformIO core | `~/.deskbuddy/platformio/core` — **on Windows with long paths disabled: `C:\.deskbuddy\platformio`** (see decisions) |

Environment variables: `DESKBUDDY_HOME` (moves `~/.deskbuddy`), `DESKBUDDY_PIO_CORE` (moves the
~6 GB PlatformIO core, e.g. to another drive), `GITHUB_TOKEN` (optional, raises the API rate limit).

## 3. Commands

Global options: `--version`, `--debug` (tracebacks), `--verbose`/`-v` (esptool/PlatformIO output).
`--port`/`-p` on every board command; default: auto-detect. With several boards: asks
(interactive) or fails with exit 2 (non-interactive).

| Command | Options (defaults) |
|---|---|
| `deskbuddy ports` | — |
| `deskbuddy doctor` | — |
| `deskbuddy versions` | — |
| `deskbuddy get` | `--version vX.Y.Z` (latest), `--dest DIR` (current folder) |
| `deskbuddy flash` | one of `--version vX.Y.Z` (latest) / `--file PATH` / `--local`; `--path DIR` (cwd, for --local); `--env usb\|battery` (usb); `--port`; `--erase`; `--baud N` (921600 → 460800 → 115200); `--no-monitor` |
| `deskbuddy monitor` | `--port`, `--log FILE`, `--raw` (no colours, no local echo) |
| `deskbuddy cmd "<text>"` | `--timeout S` (5), `--port` |
| `deskbuddy status` | `--timeout`, `--port` (= `cmd status`) |
| `deskbuddy wifi-forget` | `--timeout`, `--port` (= `cmd "wifi forget"`) |
| `deskbuddy link ble\|wifi` | `--port` |
| `deskbuddy reboot` | `--port` |
| `deskbuddy build` | `--env usb\|battery` (usb), `--path DIR` (cwd), `--out DIR` (`~/.deskbuddy/builds`) |
| `deskbuddy ui` | — |

`--env usb` = PlatformIO env `c3`; `--env battery` = `c3-battery`.

### Real output (copied from the test runs)

```
> deskbuddy --version
deskbuddy 2.0.0

> deskbuddy ports
* COM9 - ESP32-C3 (USB Serial Device (COM9))

* = ESP32-C3 (DeskBuddy)   ? = possible ESP32 (USB-UART chip)

> deskbuddy doctor
✓ Python: 3.13.15
✓ esptool: 5.5.0
✓ pyserial: 3.5
✓ Board: COM9 - ESP32-C3 (USB Serial Device (COM9))
✓ Port: COM9 is free
✓ GitHub: reachable
✓ Serial permissions: not needed on this OS

7 of 7 checks passed.

> deskbuddy flash --local --env usb --no-monitor
Building usb firmware in D:\ard\DeskBuddy-C3\firmware (first build downloads ~1 GB)...
Keeping saved settings (WiFi, link mode); use --erase to reset them.
Writing firmware to COM9 at 921600 baud...
Waiting for the board to restart...
Installed DeskBuddy C3 v2.0.0 ✓

> deskbuddy status
DeskBuddy C3 c3-2.0.0 (USB build)
link     ble, bluetooth advertising, 0 app(s), 14:63:93:c6:68:9a
oled     OK at 0x3C
time     2026-10-08 20:33:43 UTC-5:30
screen   mochi, face idle/default
notifs   0, 0 unread
memory   137384 free, lowest 137252
uptime   43 s, last reset: other

> deskbuddy link ble
Link is now Bluetooth (ble) ✓          (when already in BLE mode it returns at once)

> deskbuddy link wifi
Board is restarting with the new link...
Link is now WiFi ✓

> deskbuddy reboot
Waiting for the board to restart...
Board restarted: DeskBuddy C3 v2.0.0 (USB build) ✓

> deskbuddy build --env usb --out dist
Building usb firmware in D:\ard\DeskBuddy-C3\firmware (first build downloads ~1 GB)...
✓ Built D:\ard\DeskBuddy-C3\dist\deskbuddy-c3-c3-v2.0.0.bin
  sha256 76d0307c2e654657db4971f2d4a2834197596cb257504da67ae59a588c067b34  (1,673,952 bytes)

> deskbuddy monitor --log m.log        (typed: status, reboot)
[connected to COM9]
> status
DeskBuddy C3 c3-2.0.0 (USB build)
...
> reboot
ESP-ROM:esp32c3-api1-20210207
...
=== DeskBuddy C3 c3-2.0.0 (USB build) ===
[Settings] loaded
[OLED] found at 0x3C
[WiFi] setup portal: join 'DeskBuddy_C3_Setup' and open 192.168.4.1
[Boot] ready in 1442 ms. Type 'help'.

> deskbuddy cmd "face happy"
✗ No reply from the board on COM9 within 5 s
  -> Is DeskBuddy firmware installed? Try 'deskbuddy monitor' or reflash with 'deskbuddy flash'.
(exit 8 — this firmware command succeeds silently; see Known issues)

> deskbuddy status --port COM42
✗ COM42 not found
  -> Check the USB cable, then run 'deskbuddy ports' to see the boards.
```

```
> deskbuddy versions                    (fresh venv, after the release)
v2.0.0       2026-10-08  builds: battery, usb (latest)
    deskbuddy-c3-c3-battery-v2.0.0.bin  (1,685,408 bytes)
    deskbuddy-c3-c3-v2.0.0.bin  (1,673,952 bytes)
    manifest.json  (619 bytes)
    SHA256SUMS  (194 bytes)

> deskbuddy get --dest %TEMP%\get-test
Release v2.0.0 (2026-10-08)
  ✓ usb firmware: ...\.deskbuddyirmware2.0.0\deskbuddy-c3-c3-v2.0.0.bin
  ✓ battery firmware: ...\.deskbuddyirmware2.0.0\deskbuddy-c3-c3-battery-v2.0.0.bin
  ✓ source code: ...\get-test\DeskBuddy-C3-v2.0.0

> deskbuddy flash --no-monitor          (latest release from GitHub)
Looking up the firmware release on GitHub...
Downloading v2.0.0 (usb build)...
Keeping saved settings (WiFi, link mode); use --erase to reset them.
Writing firmware to COM9 at 921600 baud...
Waiting for the board to restart...
Installed DeskBuddy C3 v2.0.0 ✓
```

With a console that cannot print Unicode (e.g. Git Bash on cp1252), `✓`/`✗` become `OK`/`X`
and the progress bar uses `#`/`-`. On a TTY `flash` shows a live progress bar; the monitor
colours errors/`CRASH`/`assert` red, `[BLE]` blue, `[WiFi]` green, `[OLED]` yellow.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | general error / a `doctor` check failed / unexpected error |
| 2 | usage error (bad option, several boards and no `--port`, unknown release) |
| 3 | no board / port not found / connection lost |
| 4 | port busy |
| 5 | network / GitHub problem |
| 6 | integrity (checksum mismatch, unsafe archive) |
| 7 | flashing failed |
| 8 | board gave no reply |
| 9 | build failed |
| 130 | interrupted (Ctrl+C) |

## 4. The installer window (`deskbuddy ui`)

Controls (top to bottom):
- **Board** dropdown + **Refresh**: boards found (ESP32-C3 marked "(found)"); choosing one also points the monitor at it.
- **Firmware** dropdown: releases from GitHub (newest first, "(latest)"); **Choose .bin…** adds a local merged image. Offline: shows "(offline: …) – use Choose .bin…".
- **Build**: USB / Battery radio buttons; **Erase settings** check box (asks for confirmation).
- **INSTALL**: flashes on a worker thread; button disabled while busy.
- **Progress bar + status text**: download, then esptool write progress (0-100 % per flash segment).
- **Serial monitor** frame with "● on/off" indicator, live output (auto-scroll, error lines red, BLE blue, WiFi green, OLED yellow, max 5000 lines), command entry + **Send**, and buttons **status**, **help**, **Bluetooth** (`link ble`), **WiFi** (`link wifi`), **Reboot**, **Clear**, **Save log** (.txt).

States:
- **Idle**: "Ready.", monitor connected (● on) or "[waiting for board...]".
- **Flashing**: monitor shows "[paused while flashing]" and releases the port; progress bar moves; status shows each step.
- **BOOT hint**: a red banner "Hold BOOT, tap RESET, release BOOT" appears under the progress bar when the chip does not enter download mode; the tool waits for the port to re-appear and retries (3 times).
- **Success**: progress 100 %, status "Installed DeskBuddy C3 vX.Y.Z"; the monitor resumes on the (possibly new) port.
- **Error**: status "Failed: …" and a message box with the error and the fix hint; the monitor resumes.

A screenshot of the idle state was taken on the dev PC (`~/.deskbuddy/logs/ui.png`).
If Tkinter is missing (Linux): `deskbuddy ui` prints "Tkinter … is not installed" with
`sudo apt install python3-tk` (Fedora: `sudo dnf install python3-tkinter`).

## 5. Install paths tested

| OS / shell | Command | Result |
|---|---|---|
| Windows 10, Git Bash, Python 3.13 (fresh uv venv) | `pip install "git+https://github.com/MONKEYDPARI019/DeskBuddy-C3#subdirectory=tool"` | OK — esptool 5.5.0; `deskbuddy --help` lists all 13 commands |
| Windows 10, Python 3.9.25 (fresh uv venv) | same | OK — esptool 4.12.0; flashed the board successfully (v4 code path) |
| Windows 10, PowerShell | `deskbuddy doctor/flash/status/link/reboot/monitor/ui` | OK on real hardware |
| Linux (ubuntu-latest, CI) | `pip install -e tool[dev]`, ruff/mypy/pytest on Python 3.9 and 3.12 | see CI links in §9 |
| Linux, real hardware | — | **not tested** (no Linux PC with the board) |

OS-specific gotchas:
- **Windows drivers**: the C3's USB-Serial/JTAG needs no driver on Windows 10/11 (shows as "USB Serial Device (COMx)").
- **Port busy** ("Access is denied" on Windows, "Device or resource busy" on Linux): another program (PlatformIO/Arduino monitor, a second `deskbuddy monitor`, the UI) holds the port. Close it.
- **Linux permissions**: user must be in `dialout` (`sudo usermod -aG dialout $USER`, then log out/in). `doctor` checks this.
- **Tkinter on Linux**: `sudo apt install python3-tk`.
- **Windows long paths / disk space** (for `build` and `flash --local` only): the PlatformIO core needs ~6 GB; on Windows with long paths disabled it goes to `C:\.deskbuddy\platformio`. Set `DESKBUDDY_PIO_CORE` (short path, e.g. `D:\.deskbuddy\platformio`) to put it elsewhere.
- **Git Bash/MSYS**: builds strip `MSYSTEM` from the environment because pioarduino's `idf_tools.py` refuses to run under MSYS.

## 6. Release process

1. Change the firmware; bump `FW_VERSION` in `firmware/src/config.h` (e.g. `"c3-2.1.0"`).
2. Add a `## [2.1.0] - YYYY-MM-DD` section at the top of `CHANGELOG.md` (it becomes the release notes).
3. If the tool changed, bump `__version__` in `tool/src/deskbuddy/__init__.py`.
4. Commit, push `main`, wait for `ci` to be green.
5. Tag and push: `git tag v2.1.0 && git push origin v2.1.0`.
6. `release.yml` then: checks the tag equals `v` + FW_VERSION (fails with a clear message otherwise);
   builds `c3` and `c3-battery` with `scripts/merge_firmware.py`; builds a debug APK only if
   `app/gradlew` + wrapper jar exist; writes notes from CHANGELOG; creates the GitHub Release with
   `deskbuddy-c3-c3-vX.Y.Z.bin`, `deskbuddy-c3-c3-battery-vX.Y.Z.bin`, `SHA256SUMS`, `manifest.json`.
7. Check: `deskbuddy versions` lists it; `deskbuddy flash` installs it.

`manifest.json` format: `{"version", "tool_min_version", "chip", "images": [{"env", "build", "file", "sha256", "size", "chip", "offset"}]}`.

## 7. Decisions log

| Decision | Why |
|---|---|
| esptool runs as a subprocess (`python -m esptool`), CLI spelling chosen per major version | v5 needs Python ≥ 3.10 and renamed commands/values (`write-flash`, `default-reset`); v4 is the only option on 3.9. The CLI is stable across both; short options (`-e -o -fm -fs`) are identical. |
| Progress parsed from esptool output with one regex | v4 prints `Writing at 0x… (5 %)`, v5 (non-TTY, `NO_COLOR=1`) prints `Writing at 0x… ===>  14.6% …`; both verified on hardware. |
| Release images are merged at 0x0, but flashed as two segments around NVS | The merged image's 0xFF padding covers NVS (0x9000-0xE000) and wiped saved WiFi/link settings (found in the hardware test). Unless `--erase`, the tool writes 0x0-0x9000 and 0xE000-end. |
| Release downloads must have a checksum | `SHA256SUMS` is required (or GitHub's asset digest); both are cross-checked when present. No "skip verify" option exists. |
| Tool version 2.0.0 = firmware version | One release number for users; `manifest.json` carries `tool_min_version` so they can diverge later. |
| Isolated PlatformIO: own venv + own core dir | Lesson 7. The user's `~/.platformio` is never touched. |
| Core dir at `C:\.deskbuddy\platformio` on Windows with long paths disabled | pioarduino's framework package has ~190-char paths; under `C:\Users\<name>\.deskbuddy\platformio\core\.cache\tmp\…` they exceed MAX_PATH (build failed with FileNotFoundError). PlatformIO's docs recommend a short root folder. `DESKBUDDY_PIO_CORE` overrides. On the dev PC it was set to `D:\.deskbuddy\platformio` because C: was full. |
| `MSYSTEM` removed from the build environment | pioarduino's `idf_tools.py` aborts with "MSys/Mingw is not supported" when started from Git Bash. |
| Tokens never reach child processes | PlatformIO runs project Python code; `GITHUB_TOKEN`/`GH_TOKEN` are stripped. The token is only sent to api.github.com, never on redirects; redirects to non-https are refused. |
| Releases are created with the runner's `gh` CLI | Avoids a third-party release action; `contents: write` only on the publish job. |
| No Android build in CI | `app/` has `gradle-wrapper.properties` but no `gradlew`/wrapper jar; per instructions no wrapper was invented. CI prints a notice. |
| `monitor --raw` = no colours and no local echo | The monitor is line-based; raw mode is for piping/logging. |
| Typed lines echoed locally only when stdin is not a terminal | A terminal already shows what you type; piped input is echoed as `> text`. The log file always records `> text`. |
| Commits use the GitHub no-reply e-mail (repo-local git config) | GitHub rejected the push because the account's e-mail is private. |
| CI actions on major tags (`@v7`), `persist-credentials: false` | Current majors verified 2026-10-08. Pinning to commit SHAs is a recommended follow-up. |

## 8. Firmware/app changes

None. `firmware/` and `app/` are byte-for-byte copies of the sources (minus build output,
`.pio/`, `.gradle/`, `.idea/`, `local.properties`, an empty `.vscode/`).

## 9. Test results

- Python tool: **257 tests passed**, coverage **93.7 %** (`ui.py`/`__main__.py` excluded), on Python 3.13 and 3.9 (Windows). ruff clean, ruff format clean, mypy clean (`--platform win32` and `linux`).
- Firmware host tests: `537 checks, 0 failed`.
- Local builds (isolated PlatformIO): `c3` and `c3-battery` both SUCCESS; merged images reproducible (same sha256 on rebuild).
- CI (all jobs green — firmware c3 + c3-battery, host tests, Android check, tool on ubuntu/windows × Python 3.9/3.12):
  https://github.com/MONKEYDPARI019/DeskBuddy-c3/actions/runs/37800260164
- Release workflow (build + publish green): https://github.com/MONKEYDPARI019/DeskBuddy-c3/actions/runs/37800735477
- Release assets (sha256 from GitHub): `deskbuddy-c3-c3-v2.0.0.bin` 65013ff2…9da4c, `deskbuddy-c3-c3-battery-v2.0.0.bin` 27dc4494…0d2d,
  `SHA256SUMS`, `manifest.json`. (CI-built images differ from local builds because build paths are embedded.)
- End-to-end after release (fresh venv, Windows): `pip install git+…#subdirectory=tool` ✓, `versions` ✓, `get` ✓, `flash` (latest release) ✓.
- Reviews: python-reviewer and security-reviewer agents; all MEDIUM/LOW findings fixed except those listed in §10.
- Hardware test log (COM9, ESP32-C3 Super Mini):
  - `doctor` 7/7 ✓; `flash --local --env usb` ✓ (921600 baud, banner confirmed);
  - `status` ✓; `link ble` ✓; `link wifi` ✓ (restart + confirmation); `reboot` ✓; `monitor` ✓ (survived a reboot, log written); `wifi-forget` ✓;
  - `flash --file` with esptool 5.5.0 (Python 3.13) and 4.12.0 (Python 3.9) ✓, saved settings kept;
  - `ui` opened, found COM9, monitor connected;
  - BOOT-hint path not triggered on hardware (the C3 always entered download mode by itself); covered by unit tests.
  - Note: the very first test flash (before the NVS fix) erased the board's saved WiFi network.

## 10. Known issues / TODO

- `cmd` treats "no output" as failure (exit 8, per spec), but some firmware commands (`face …`, `screen …`, `press …`) succeed silently. Consider a "silent OK" list or a firmware `ok` reply.
- OTA flashing from the tool (the `ota` env exists in platformio.ini) is not implemented.
- Not published to PyPI (by instruction); install is from git.
- Android app is not built in CI/releases (no Gradle wrapper in `app/`).
- Source archives from `deskbuddy get` are only protected by HTTPS (GitHub publishes no hash); building them runs their PlatformIO scripts.
- Recommended repo hardening: tag protection rule for `v*`, protected environment for the release job, pin actions to SHAs.
- Linux was tested only in CI (no hardware).
- PlatformIO first build downloads ~1 GB and needs ~6 GB disk.

## 11. Error messages catalogue

| Message | Fix hint shown |
|---|---|
| No DeskBuddy board found | Plug the board in with a data USB cable (not charge-only), then run 'deskbuddy ports'. |
| Several boards found (COMx, COMy) | Choose one with --port, e.g. --port COMx |
| COMx not found | Check the USB cable, then run 'deskbuddy ports' to see the boards. |
| Cannot open COMx: … | Unplug and re-plug the board, then try again. |
| COMx is busy | Close the PlatformIO/Arduino serial monitor (or any other program using the port) and try again. |
| Lost the connection to COMx | The board restarted or was unplugged; try again. |
| No reply from the board on COMx within N s | Is DeskBuddy firmware installed? Try 'deskbuddy monitor' or reflash with 'deskbuddy flash'. |
| The board would not enter download mode | Hold BOOT, tap RESET, release BOOT, then run the command again. Also try another USB cable. |
| Flashing failed at every speed | Try a different USB cable or port (avoid hubs). (+ last esptool lines) |
| esptool failed | (last esptool lines) |
| esptool is not installed in this Python environment | Reinstall the tool: pip install "git+…#subdirectory=tool" |
| Firmware file X not found | Check the path, or omit --file to use the latest release. |
| X is too small to be a DeskBuddy firmware image | Use a merged .bin from a release. |
| X does not look like a merged ESP32 image | Use the deskbuddy-c3-*.bin file from a release, not firmware.bin from the build folder. |
| Choose only one of --version, --file and --local | — |
| Unknown build 'X' | Use --env usb or --env battery. |
| Unknown link 'X' | Use: deskbuddy link ble   or   deskbuddy link wifi |
| The board did not accept 'link X' | Update the firmware with 'deskbuddy flash'. |
| The board restarted but is still in X mode | Run 'deskbuddy monitor' to see what happened. |
| The board did not answer after the restart | Run 'deskbuddy monitor' to watch it boot. |
| Cannot reach GitHub | Check your internet connection (and proxy/firewall), then try again. |
| GitHub refused the request (API rate limit reached?) | Wait an hour, or set the GITHUB_TOKEN environment variable to a personal access token. |
| GitHub answered HTTP N / GitHub sent an unexpected answer (…) | Try again in a minute. |
| No firmware release has been published yet | Build from source instead: deskbuddy flash --local |
| Release vX not found | Run 'deskbuddy versions' to list the releases. |
| Release vX has no usb/battery firmware | Run 'deskbuddy versions' to see what each release contains. |
| Download failed: … | Try again later / Check your connection and free disk space. |
| X failed the checksum test | The download is damaged or was tampered with. Run the command again; if it keeps failing, report it on GitHub. |
| Checksums for X disagree (SHA256SUMS vs GitHub) | The release may have been tampered with. Do not flash it; report this on GitHub. |
| Release vX has no checksum for X | Refusing to flash an unverified image. Use --file with an image you trust, or --local. |
| Archive contains an unsafe path / a link | The archive was rejected; nothing was extracted. |
| DIR already exists and is not empty | Delete it or choose another --dest folder. |
| No DeskBuddy firmware project found in DIR | Run inside the DeskBuddy-C3 folder, pass --path, or download the source with 'deskbuddy get'. |
| Could not set up PlatformIO for building | Check your internet connection. On Debian/Ubuntu: sudo apt install python3-venv. Or: pip install "deskbuddy-cli[build]". |
| Firmware build failed (env) | (last build lines) |
| The ESP32-C3 bootloader must be flashed at 0x0 / The app must start at 0x10000 | Check partitions.csv. |
| esptool could not merge the firmware images | (last esptool lines) |
| Tkinter (the Python GUI toolkit) is not installed | On Debian/Ubuntu: sudo apt install python3-tk (Fedora: sudo dnf install python3-tkinter) |
| Unexpected error: … | Run the command again with --debug and report the output on GitHub. |
