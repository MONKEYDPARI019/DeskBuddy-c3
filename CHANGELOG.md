# Changelog

All notable changes to DeskBuddy C3 are listed here. Versions follow the firmware `FW_VERSION`
(`c3-X.Y.Z` → tag `vX.Y.Z`).

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
