# Development

How the project is put together, how to build and test it, and how to cut a release.

## Repository layout

```
DeskBuddy-C3/
├─ firmware/                    PlatformIO project
│  ├─ platformio.ini            envs: c3 (USB), c3-battery, ota
│  ├─ partitions.csv            4 MB: nvs, otadata, app0/app1 (1.875 MB each), spiffs, coredump
│  ├─ src/                      firmware sources
│  │  └─ logic/                 pure C++ (no Arduino), unit-tested on a PC
│  ├─ docs/PROTOCOL.md          app ↔ board messages
│  └─ test/host/                host unit tests (g++)
├─ app/                         Android app (Kotlin, Jetpack Compose)
├─ tool/                        deskbuddy-cli (Python)
│  ├─ pyproject.toml
│  ├─ src/deskbuddy/            cli.py, ui.py, installer.py, flasher.py, firmware.py, builder.py,
│  │                            github.py, serial_io.py, monitor.py, ports.py, doctor.py, frozen.py, …
│  ├─ packaging/entry.py        entry point of the ready-made program (PyInstaller)
│  └─ tests/                    pytest suite
├─ npm/                         deskbuddy-c3 npm package: launcher that downloads the ready-made program
│  ├─ bin/deskbuddy.js, lib/launcher.js
│  └─ test/launcher.test.js     node --test suite
├─ scripts/merge_firmware.py    release builds: merged image + SHA256SUMS + manifest.json
├─ scripts/build_app.py         builds + smoke-tests the ready-made program for this OS
└─ .github/workflows/           ci.yml, app.yml, release.yml
```

## Firmware

### Building

Pick whichever you like:

- **Command line, no setup:** from the repo root, run `deskbuddy build --env usb`, or `deskbuddy flash --local` to build and flash in one go. This uses the tool's own private PlatformIO.
- **VS Code + PlatformIO:**
  1. Open the **`firmware`** folder itself, not the repo root.
  2. Pick the environment in the status bar (`env:c3` or `env:c3-battery`).
  3. Click **Upload**, then use PlatformIO's **Serial Monitor** (plug icon).
- **PlatformIO CLI:** `cd firmware`, then `pio run -e c3 -t upload` and `pio device monitor`.

**Over WiFi (OTA):** with the board in WiFi mode on the same network, run `cd firmware` then `pio run -e ota -t upload`. It uploads to `deskbuddy-c3.local`; the board shows a progress bar while it updates.

### Architecture

One main loop does everything, in a fixed order: serial commands → radio → incoming app messages → buttons → app logic → sound → LEDs → display. Only the Bluetooth stack runs in its own task, and its callbacks just put complete JSON lines into a queue (`link.cpp`). Nothing else is shared, so there are no locks and no race conditions.

| Module | Job |
|---|---|
| `main.cpp` | `setup()` and the main loop. Boot sequence, and the both-buttons radio switch. |
| `config.h` | Pins, timings, `FW_VERSION`, `FEATURE_BATTERY` |
| `settings.*` | Settings in flash (NVS namespace `dbc3`), written only when something changed |
| `oled.*` | OLED probe at 100 kHz with retries; re-check every 3 s, re-init after a blip |
| `ui.*` | Draws the screens, popups and overlays (reads state, changes nothing) |
| `face.*` | Mochi: moods, states, blinking, gaze, animations |
| `app.*` | Behaviour: screens, notifications, sleep, LEDs, state pushes, link switching, power-off |
| `protocol.*` | JSON messages with the app (ArduinoJson 7) |
| `link.*`, `link_ble.cpp`, `link_wifi.cpp` | One interface over both radios, plus the inbox queue |
| `buttons.*`, `leds.*`, `buzzer.*` | Debounced buttons, LED patterns, non-blocking melodies (LEDC) |
| `battery.*`, `power.*` | Battery reading and deep-sleep power switch (compiled out in the USB build) |
| `cli.*` | Serial command line |
| `logic/` | `framing.h` (BLE line framing), `text.h` (UTF-8 → ASCII, word wrap), `notif_store.h`, `tz.h`, `battery_curve.h` |

### Pinned versions

Everything is pinned in `platformio.ini` so builds are identical everywhere:

| Component | Version |
|---|---|
| Platform | pioarduino 55.03.36 (Arduino-ESP32 3.3.6) |
| U8g2 | 2.36.19 |
| ArduinoJson | 7.4.3 |
| NimBLE-Arduino | 2.5.1 |
| arduinoWebSockets | 2.7.2 |
| WiFiManager | 2.0.17 |

### Lessons learned: don't undo these

| Rule | Why |
|---|---|
| Stay on **pioarduino / Arduino core 3.x** | Core 2.0.x couldn't drive I2C on the Super Mini; the OLED stayed black. |
| Write for **NimBLE 2.x** and call `setCallbacks(&cb, false)` | 1.x and 2.x have different callback signatures. With `true`, NimBLE deletes static callback objects, which crashed on the Bluetooth → WiFi switch. |
| Keep **WiFi TX power at 8.5 dBm** | At full power, the Super Mini's antenna distorts the signal, and phones couldn't see the setup network. |
| Keep **WiFi modem sleep off** | With it on, mDNS/FIND and `deskbuddy-c3.local` were unreliable. |
| Keep the **slow, retried OLED probe** and the hot-plug check | Probing once at 400 kHz right after power-on missed the OLED. |
| Never read GPIO0 unless the battery build is selected, and require plausible readings first | A floating GPIO0 read as "battery empty" and switched the board off. |
| Keep `monitor_rts = 0` / `monitor_dtr = 0` | DTR/RTS toggling resets the C3's native USB serial. |
| Flash release images **around NVS** unless erasing | The merged image's padding covers NVS and wiped the saved WiFi network. |

### Tests

```bash
sh firmware/test/host/run_tests.sh
```

This runs 537 checks of the pure logic in `src/logic` on a PC with g++: framing, text folding and wrapping, the notification store, time zones and the battery curve. On Windows, run it in Git Bash or WSL.

## The `deskbuddy` tool

### Setting up

```bash
cd tool
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

### Checks (the same as CI)

```bash
ruff check . && ruff format --check .
mypy src
pytest --cov
```

The suite has 257 tests and about 94 % coverage. It uses fakes for serial ports, subprocesses and HTTP, so it needs no board or network.

### How it works

- **Flashing:** `python -m esptool` runs as a subprocess, with the right command spelling for esptool 4 or 5. Progress is parsed from esptool's output. Images are written at 921600 baud, falling back to 460800 and 115200. When the chip doesn't sync, the BOOT/RESET hint is shown and the tool retries.
- **Release images:** each is one merged binary (bootloader, partitions, boot_app0, app) meant for `0x0`. Unless `--erase` is given, it's written as two pieces that skip NVS (`0x9000–0xE000`), so settings and WiFi survive.
- **Downloads:** from the GitHub Releases API. They must match `SHA256SUMS` (and GitHub's own digest, when present), and are cached in `~/.deskbuddy/firmware`. Source archives are extracted with path checks.
- **Serial:** ports are opened with DTR/RTS off. The monitor is a reconnecting state machine, so it survives resets.
- **Building:** a private PlatformIO (its own venv and core folder) is used. `GITHUB_TOKEN` is kept away from build processes, and `MSYSTEM` is removed so pioarduino's tools run from Git Bash too.
- **The CLI and the UI** are thin layers over the same `installer.py` / `serial_io.py` / `monitor.py`.

### The npm package and the ready-made program

`npm install -g deskbuddy-c3` installs a small Node.js launcher, not a JavaScript rewrite. The real tool is the same Python code, packed by **PyInstaller** into a folder with its own Python, esptool, pyserial and Tk:

1. `scripts/build_app.py` runs PyInstaller (`--onedir`, with esptool's flasher stubs and pyserial's URL handlers included), checks that the program starts and that its built-in esptool runs, and packs it as `deskbuddy-<version>-<platform>.tar.gz` (`win32-x64`, `linux-x64`, `linux-arm64`, `darwin-arm64`, `darwin-x64`).
2. Each release carries one archive per platform, listed in `SHA256SUMS`.
3. The launcher (`npm/lib/launcher.js`) picks the archive for the computer it runs on, downloads it from the release whose version equals the npm package's version, checks the SHA-256, unpacks it with the system `tar` into `~/.deskbuddy/app/<version>-<platform>/` and runs it with the same arguments, passing stdin/stdout and the exit code straight through. There is deliberately no `postinstall` script: npm 11 and newer no longer run install scripts of global packages unless the user allows them, so the download happens on the first run instead. `DESKBUDDY_DOWNLOAD_BASE` can point at a local folder with the release files, which CI uses and which also allows offline installs.

A frozen program has no `python -m esptool`, so the tool starts **itself** with a hidden flag, `deskbuddy --run-esptool <args>` (`frozen.py`). esptool still runs as a separate process, so progress parsing and error handling are identical in both versions. `deskbuddy build` and `flash --local` need a real Python for PlatformIO, so the program says to use the pip version for those.

Try a local build without publishing anything:

```bash
pip install ./tool "pyinstaller>=6.10,<7"
python scripts/build_app.py dist
# run it through the launcher
DESKBUDDY_BINARY=build/app/dist/deskbuddy/deskbuddy node npm/bin/deskbuddy.js --version
cd npm && npm test
```

On Windows the program is `build\app\dist\deskbuddy\deskbuddy.exe`; in PowerShell set the variable with `$env:DESKBUDDY_BINARY = "..."`.

## CI and releases

**`ci.yml`** (every push and pull request):
- builds both firmware envs;
- runs the host tests;
- runs ruff, mypy and pytest for the tool on Ubuntu and Windows, with Python 3.9 and 3.12;
- checks the Android app. It's skipped while `app/` has no Gradle wrapper.

**`app.yml`** (pushes that touch `tool/`, `npm/` or `scripts/build_app.py`, and every release):
- runs the npm launcher's tests on Windows, Linux and macOS with Node 18 and 24, including a check that `npm/package.json`, the tool's `__version__` and `FW_VERSION` agree;
- builds the ready-made program on Windows x64, Linux x64 and arm64 (Ubuntu 22.04, so it runs on glibc 2.35+) and macOS arm64 and Intel;
- installs each one end to end through `npm install -g`, with the release files taken from the local `dist/` folder, and runs `deskbuddy --version`;
- keeps the archives as downloadable workflow artifacts (`program-<platform>`) for 14 days, so you can try a build before releasing it.

**`release.yml`** (on a `vX.Y.Z` tag):
1. Checks that the tag matches `FW_VERSION`, the tool's `__version__` **and** `npm/package.json`.
2. Builds both firmware envs with `scripts/merge_firmware.py`, and the ready-made programs with `app.yml`.
3. Takes the release notes from `CHANGELOG.md`.
4. Publishes the GitHub Release with the firmware images, the program archives, `SHA256SUMS` (covering all of them) and `manifest.json`.
5. Publishes the npm package, if you switched that on (below).

### Cutting a release

The whole project shares one version number.

1. Change what you need, then bump the version in **three** places:
   - `FW_VERSION` in `firmware/src/config.h` (e.g. `"c3-2.2.0"`);
   - `__version__` in `tool/src/deskbuddy/__init__.py` (`"2.2.0"`);
   - `"version"` in `npm/package.json` (`"2.2.0"`).
2. Add a `## [2.2.0] - YYYY-MM-DD` section at the top of `CHANGELOG.md`. It becomes the release notes.
3. Commit, push to `main`, and wait for CI to go green.
4. Tag and push:
   ```bash
   git tag v2.2.0
   git push origin v2.2.0
   ```
5. When the release workflow finishes, check that `deskbuddy versions` lists it, `deskbuddy flash` installs it, and, if npm publishing is on, `npm view deskbuddy-c3 version` shows it.

`manifest.json` lists, for each firmware build, `env`, `build`, `file`, `sha256`, `size`, `chip` and `offset`, plus the release `version` and `tool_min_version`.

### Publishing to npm

The npm package must only be published **after** its GitHub release exists, because it downloads the program from there.

**The first time, by hand** (npm doesn't let you set up automatic publishing for a package that doesn't exist yet):

1. Create an account on [npmjs.com](https://www.npmjs.com/signup) and turn on two-factor authentication.
2. After the `v2.1.0` release has finished on GitHub:
   ```bash
   cd npm
   npm login
   npm publish --access public
   ```

**From then on, automatically, with trusted publishing** (no token to store or renew):

1. On npmjs.com, open the `deskbuddy-c3` package → **Settings** → **Trusted publishing** → **GitHub Actions**, and enter your GitHub user, the repository name exactly as GitHub shows it, and the workflow file `release.yml`.
2. In the GitHub repository: **Settings → Secrets and variables → Actions → Variables → New repository variable**: name `NPM_PUBLISH`, value `true`.

The next tag then publishes to npm by itself, after the GitHub release. The job uses Node 24 with the newest npm (trusted publishing needs npm 11.5.1 or newer), sets `repository.url` to the exact GitHub spelling (npm checks it), runs the tests and publishes. npm adds a provenance statement linking the package to the workflow run.

## Known limitations / ideas

- `deskbuddy cmd` treats silent commands (`face`, `screen`, `press`) as "no reply". A firmware `ok` reply, or a list of silent commands, would fix that.
- OTA flashing isn't in the tool yet; use `pio run -e ota -t upload`.
- The Python tool isn't on PyPI yet; install it from GitHub (or use the npm package).
- The ready-made programs aren't code-signed. Downloads through npm don't trigger Windows SmartScreen or macOS Gatekeeper (those only check files downloaded by a browser), but an antivirus may scan them on first run.
- The Android app isn't built in CI. Add a Gradle wrapper (`gradle wrapper` in `app/`) to enable it.
- Linux has only been tested in CI, not with a real board.
- Hardening: protect `v*` tags, add a protected environment for the release job, and pin GitHub Actions to commit SHAs.
