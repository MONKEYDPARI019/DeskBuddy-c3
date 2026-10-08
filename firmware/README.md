# DeskBuddy C3 firmware (v2.0, rewritten)

Pocket DeskBuddy on an **ESP32-C3 Super Mini**: Mochi's face, a clock, and phone notifications on a 0.96" OLED, with 2 buttons, 3 LEDs and a buzzer. It works with the DeskBuddy Android app over **Bluetooth** (default) or **WiFi**. The protocol hasn't changed, so the app needs no update.

Built with **PlatformIO** only. Every version is pinned in `platformio.ini`.

## Wiring

| Part | Pin on the Super Mini |
|---|---|
| OLED VCC / GND | 3.3 / G |
| OLED SDA / SCL | GPIO 6 / GPIO 7 |
| BTN1 (mood / power) | GPIO 1 → button → GND |
| BTN2 (screen) | GPIO 20 → button → GND |
| LED red / yellow / green | GPIO 3 / 4 / 5 → 330 Ω → LED → GND |
| Passive buzzer | GPIO 10 → 220 Ω → buzzer → GND |
| Battery sense (battery build only) | battery + → 220 kΩ → GPIO 0 → 220 kΩ → GND |

Leave GPIO 2, 8 and 9 free (boot pins), and GPIO 18/19 (USB).

## Build and flash

1. Open **this folder** (`firmware`) in VS Code with the PlatformIO extension.
2. Plug the Super Mini in with USB-C and click **Upload** (→). The first build downloads the ESP32 core and libraries, which takes a few minutes. After that it's fast.
3. Click **Serial Monitor** (the plug icon in the PlatformIO toolbar) and type `help`.

If the upload can't find the board, hold **BOOT**, tap **RESET**, release BOOT, and upload again. Press RESET once afterwards.

Use the PlatformIO monitor, not VS Code's own "Serial Monitor" tab. That tab toggles DTR/RTS, which keeps resetting the C3.

| Environment | Use |
|---|---|
| `c3` (default) | USB powered. Battery code is compiled out, so GPIO 0 is never read. |
| `c3-battery` | Once the LiPo, TP4056, slide switch and GPIO 0 divider are fitted: battery icon, low-battery warning, auto power-off, hold BTN1 3 s for on/off. |
| `ota` | Later updates over WiFi (WiFi mode only). |

In VS Code, pick the environment in the bottom status bar ("env:c3"). From a terminal: `pio run -e c3-battery -t upload`.

## Controls

| | Click | Hold |
|---|---|---|
| **BTN1** | next mood (on the inbox: next notification) | 1 s: silent on/off. Battery build: 3 s = power off; let go between 1.5 and 3 s to cancel. |
| **BTN2** | next screen: clock → Mochi → inbox | 1 s: clear notifications |

- When nobody touches it for `sleep_sec` (120 s by default), Mochi falls asleep and the screen dims. The next press only wakes Mochi.
- **Switch Bluetooth <-> WiFi without a PC:** hold **both buttons** and tap **RESET** (or switch on), keep holding ~1 s until the screen says "Bluetooth mode" / "WiFi mode", then let go.
- In the battery build, after power-off, hold BTN1 for 3 s to switch it on. A shorter press goes back to sleep.

**LEDs:** red solid = silent, red fast blink = battery low; yellow = unread notifications; green solid = app connected, a short flash every 2 s = waiting for the app, fast blink = WiFi setup portal.

## Bluetooth or WiFi

Only one radio runs at a time. To switch, use **Setup → Link** in the app, or type `link wifi` / `link ble` in the monitor. The board saves the choice and restarts.

- **Bluetooth:** works anywhere within ~10 m of the phone, and the phone sets the clock.
- **WiFi:** the first time, join `DeskBuddy_C3_Setup` and pick your network. After that you get NTP time, `http://deskbuddy-c3.local/notify?app=..&title=..&msg=..` and OTA updates. If the saved network is missing for 30 s, the setup portal opens for 3 minutes, then it tries the network again, and so on.

## Serial commands (115200)

`status`, `get`, `set <key> <value>`, `defaults`, `link wifi|ble`, `screen <name>`, `face <name>`, `notify <text>`, `sound <name>`, `time <unix>`, `test oled|leds|buzzer|buttons|battery`, `i2c`, `oled reinit`, `press 1|2 [ms]`, `state`, `app <json>`, `wifi forget`, `off`, `reboot`.

`app {"type":"notify","app":"Test","title":"Hi","body":"hello"}` acts exactly like the phone sending that message.

## How the code is organised

```
src/
  main.cpp        setup() + the one main loop
  config.h        pins, timings, FEATURE_BATTERY
  settings.*      settings in flash (written only when something changed)
  oled.*          OLED: slow probe at boot, retries, hot-plug recovery
  ui.*            screens, popups, overlays (draws only)
  face.*          Mochi (same face as v2 and the app)
  app.*           behaviour: screens, notifications, sleep, LEDs, timers
  protocol.*      JSON messages to/from the app
  link.*          one interface for both radios + the inbox queue
  link_ble.cpp    Bluetooth LE (NimBLE 2.x, Nordic UART Service)
  link_wifi.cpp   WebSocket, HTTP, mDNS, OTA, NTP, setup portal
  buttons.* leds.* buzzer.* battery.* power.* cli.*
  logic/          pure C++ (framing, text, notifications, time zone, battery curve)
test/host/        unit tests for src/logic, run on a PC: sh test/host/run_tests.sh
```

## What changed from the first C3 firmware, and why

| Problem we hit | What this version does |
|---|---|
| OLED stayed black: it was probed once, at 400 kHz, right after power-on | Waits for the OLED, probes at 100 kHz with retries, re-checks every 3 s, and re-initialises it when it comes back (loose wire or power blip) |
| Arduino core 2.0.x couldn't drive I2C on this board | Pinned to core 3.3.6 (pioarduino 55.03.36) |
| NimBLE 1.x vs 2.x mismatch broke the build | Every library pinned to an exact release, written for NimBLE 2.x |
| A floating GPIO 0 read as "battery empty" and switched the board off | Battery code compiled out in the USB build. In the battery build, 3 s of real-cell readings are needed before it's trusted. |
| VS Code Serial Monitor reset loop, commands ignored | `monitor_rts/dtr = 0`, LF line ending, echo on |
| Slow Arduino IDE builds (it scanned the Android folder) | PlatformIO project in its own folder |
| Seven tasks + mutexes, hard to reason about | One main loop. The Bluetooth task only queues complete messages, so there are no races. |
| WiFiManager blocked boot for up to 20 s | Saved network connects in the background, and the portal is non-blocking with timeouts |
| Emoji and curly quotes showed as garbage | Text folded to ASCII (`’` → `'`, `é` → `e`, emoji → `*`) |
| Notification body cut every 25 characters, mid-word | Word wrap, with slow auto-scroll for long messages |
| "No core dump partition" error at boot | Partition table includes a coredump partition |
