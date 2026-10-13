# Changelog

All notable changes to DeskBuddy C3 are listed here. Versions follow the firmware `FW_VERSION`
(`c3-X.Y.Z` → tag `vX.Y.Z`).

## [2.2.0] - 2026-10-13

### Double-click app for Windows
- New release file **`DeskBuddy.exe`**: download it, double-click it and the installer window opens (INSTALL, Erase chip,
  serial monitor). No Node.js, Python or install step. It is one windowed file with the DeskBuddy icon, built and tested
  on Windows by `app.yml` and listed in `SHA256SUMS`.
- `https://github.com/MONKEYDPARI019/DeskBuddy-C3/releases/latest/download/DeskBuddy.exe` always points to the newest one.
- Not code-signed: the first time, Windows SmartScreen asks; click **More info → Run anyway**.

### Android app 0.3.0
- The "DeskBuddy" link notification now has a **Stop** button (same as STOP in the app).
- Searching stops by itself after 10 minutes without finding DeskBuddy. A swipe-away "DeskBuddy not found" notification
  offers **Search again**.
- New Setup option **Stay connected when app is closed** (on by default). Off: swiping the app away disconnects, and
  opening it reconnects.
- Opening the app reconnects automatically while LINK is on.
- Fixed: a late status update could bring the link notification back after STOP.

### `deskbuddy` tool 2.2.0
- Windows app: DeskBuddy icon on the window and taskbar, and sharp text on scaled (125 %, 150 %) screens.
- `scripts/build_app.py --gui` builds the double-click app.

### Firmware (c3-2.2.0)
- No functional changes; the version follows the project version.

## [2.1.0] - 2026-10-11

### Install with npm
- New npm package **`deskbuddy-c3`**: `npm install -g deskbuddy-c3` gives the same `deskbuddy` command with no Python
  needed. It downloads a ready-made program for the computer (Windows x64, Linux x64/arm64, macOS arm64/x64) from this
  release, checks it against `SHA256SUMS` and keeps it in `~/.deskbuddy/app`.
- Each release now also carries `deskbuddy-<version>-<platform>.tar.gz`, built with PyInstaller by the new `app.yml`
  workflow, which also tests the npm package end to end on every OS.

### `deskbuddy` tool 2.1.0
- New command `deskbuddy erase`: erases the whole flash (firmware, settings, saved WiFi) after a confirmation
  (`--yes` skips it, `--port` picks the board). The chip is left waiting in download mode, so its USB port stays
  steady instead of dropping out over and over while it has no firmware.
- Installer window: new **Erase chip** button next to INSTALL, with a confirmation dialog. It only erases detected
  ESP32 boards.
- Runs as a ready-made program too: esptool runs inside it (`--run-esptool`), `doctor` reports the built-in Python,
  and `build` / `flash --local` point to the pip version.

### Firmware (c3-2.1.0)
- No functional changes; the version follows the project version.

## [2.0.0] - 2026-10-08

First release from this repository.

### Firmware (c3-2.0.0)
- ESP32-C3 Super Mini firmware: animated face "Mochi", clock and phone notifications on a 0.96" SSD1306 OLED.
- Bluetooth LE (Nordic UART Service) or WiFi (WebSocket :81, HTTP :80, mDNS `deskbuddy-c3.local`) link to the Android app.
- Two builds: `usb` (env `c3`) and `battery` (env `c3-battery`, LiPo + TP4056 with battery sensing).
- Serial command line at 115200 baud (`help`, `status`, `link wifi|ble`, `test ...`, ...).
- Built on pioarduino 55.03.36 (Arduino-ESP32 3.3.6), NimBLE-Arduino 2.5.1, U8g2 2.36.19, ArduinoJson 7.4.3,
  arduinoWebSockets 2.7.2, WiFiManager 2.0.17.

### Release assets
- `deskbuddy-c3-c3-v2.0.0.bin` and `deskbuddy-c3-c3-battery-v2.0.0.bin`: merged images, flash at `0x0`.
- `SHA256SUMS` and `manifest.json`.

### `deskbuddy` tool 2.0.0
- New command-line tool: `pip install "git+https://github.com/MONKEYDPARI019/DeskBuddy-C3#subdirectory=tool"`.
- Commands: `ports`, `doctor`, `versions`, `get`, `flash`, `monitor`, `cmd`, `status`, `link`, `wifi-forget`,
  `reboot`, `build`, `ui`.
- Verified (sha256) downloads, automatic port detection, baud fallback, BOOT-button guidance, a monitor that
  survives board resets, isolated PlatformIO builds, and a Tkinter installer window.
