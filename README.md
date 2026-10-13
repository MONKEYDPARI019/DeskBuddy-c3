# DeskBuddy C3

**A pocket-sized desk companion.** An ESP32-C3 Super Mini drives a 0.96" OLED with an animated face called **Mochi**, a clock, and your phone's notifications. It has two buttons, two or three status LEDs and a buzzer, and runs from USB or a small LiPo battery. It talks to the DeskBuddy Android app over **Bluetooth** or **WiFi**.

This repo has everything: the firmware, the Android app, and **`deskbuddy`**, a command-line tool and installer window that downloads, flashes and monitors the board. On Windows the installer window is also a double-click app, **DeskBuddy.exe**. You don't need PlatformIO or the Arduino IDE.

> DeskBuddy C3 is the pocket sibling of [DeskBuddy v2](https://github.com/MONKEYDPARI019/DeskBuddy-v2), the desk version on a full ESP32 with a microphone and speaker. The same app drives both.

<!-- Add a photo or GIF of your DeskBuddy here, e.g. ![DeskBuddy C3](docs/images/deskbuddy-c3.jpg) -->

## Features

- **Mochi:** 15 animated moods that blink, look around, bounce and sleep. Change them with a button or from the app.
- **Clock:** the time is set by your phone (Bluetooth) or from the internet (WiFi).
- **Notifications:** forwarded from your phone, with a popup, an inbox of the last 8, word-wrapped and auto-scrolling.
- **Bluetooth or WiFi:** switch between them from the app, the command line, or the buttons.
- **Battery build:** LiPo charging, battery icon, low-battery warning, auto power-off, and hold-to-switch-on/off.
- **Double-click app (Windows):** download `DeskBuddy.exe`, open it, click INSTALL. Nothing to install first.
- **One-command install:** `npm install -g deskbuddy-c3`, then `deskbuddy flash` downloads the latest release, checks it and flashes it.
- **Installer window:** `deskbuddy ui` gives you install and erase buttons and a live serial monitor.

## Quick start

**Easiest, on Windows:** download **[DeskBuddy.exe](https://github.com/MONKEYDPARI019/DeskBuddy-C3/releases/latest/download/DeskBuddy.exe)**, plug the board in, double-click the file and click **INSTALL**. Nothing else to install.

> The first time, Windows may say **"Windows protected your PC"**, because the app isn't code-signed. Click **More info → Run anyway**.

**On any computer, from the command line:** you need a DeskBuddy C3 wired up (see [Hardware](docs/hardware.md)), a USB-C data cable and [Node.js](https://nodejs.org) 18 or newer.

```bash
# 1. Install the tool (once)
npm install -g deskbuddy-c3

# 2. Plug the board in and check everything
deskbuddy doctor

# 3. Install the latest firmware
deskbuddy flash

# 4. Watch it talk (type "help", Ctrl+C to quit)
deskbuddy monitor
```

No Python needed. If you prefer Python, `pip install "git+https://github.com/MONKEYDPARI019/DeskBuddy-C3#subdirectory=tool"` gives you the same `deskbuddy` command (see [the command reference](docs/cli.md#install-update-remove)).

If you'd rather click than type, run `deskbuddy ui`.

New to all of this? The **[Getting started tutorial](docs/getting-started.md)** walks you from an empty desk to Mochi showing your WhatsApp messages.

## Documentation

| Guide | What's inside |
|---|---|
| [Getting started](docs/getting-started.md) | Step-by-step tutorial: install, flash, connect the app, set up WiFi |
| [Hardware](docs/hardware.md) | Parts list, pinout, wiring, and the battery build |
| [Using DeskBuddy](docs/using-deskbuddy.md) | Screens, buttons, LEDs, moods, sleep, Bluetooth vs WiFi, settings |
| [Phone app](docs/phone-app.md) | Building, installing and setting up the Android app |
| [`deskbuddy` command reference](docs/cli.md) | Every command, option, exit code and environment variable |
| [Installer window](docs/installer-ui.md) | How `deskbuddy ui` and DeskBuddy.exe work |
| [Troubleshooting](docs/troubleshooting.md) | Symptoms, causes and fixes, plus every error message |
| [Development](docs/development.md) | Building from source, code layout, tests, releases |
| [Protocol](firmware/docs/PROTOCOL.md) | The JSON messages between the app and the board |

## Hardware at a glance

| Part | Super Mini pin |
|---|---|
| OLED SSD1306 128×64 (I2C) | SDA **GPIO6**, SCL **GPIO7**, VCC **3.3V**, GND **G** |
| BTN1 (mood / silent / power) | **GPIO1** → button → G |
| BTN2 (screen / clear) | **GPIO20** → button → G |
| LEDs red / yellow / (green, optional) | **GPIO3 / GPIO4 / GPIO5**, each through 330 Ω |
| Passive buzzer | **GPIO10** through 220 Ω |
| Battery sense (battery build only) | **GPIO0**, via a 2 × 220 kΩ divider |

Full wiring and the battery circuit are in [docs/hardware.md](docs/hardware.md).

## Controls

| | Click | Hold |
|---|---|---|
| **BTN1** | next mood (on the inbox: next notification) | 1 s: silent on/off · *battery build:* 3 s = power off |
| **BTN2** | next screen: clock → Mochi → inbox | 1 s: clear notifications |
| **Both, while pressing RESET** | switch Bluetooth ↔ WiFi | |

## Repository layout

```
firmware/   ESP32-C3 firmware (PlatformIO, Arduino core 3.3.6)
app/        Android app (Kotlin, Jetpack Compose), shared with DeskBuddy v2
tool/       the `deskbuddy` command-line tool + installer window (Python)
scripts/    release build helper (merged firmware images)
docs/       these guides
.github/    CI and release workflows
```

## Releases

Each [release](https://github.com/MONKEYDPARI019/DeskBuddy-C3/releases) contains ready-to-flash firmware for both builds (`deskbuddy-c3-c3-vX.Y.Z.bin` for USB, `deskbuddy-c3-c3-battery-vX.Y.Z.bin` for battery), plus `SHA256SUMS` and `manifest.json`. `deskbuddy flash` picks the right file and checks it for you. The changes are listed in [CHANGELOG.md](CHANGELOG.md).

## Related projects

- [DeskBuddy](https://github.com/MONKEYDPARI019/DeskBuddy): the original v1 on an ESP8266
- [DeskBuddy v2](https://github.com/MONKEYDPARI019/DeskBuddy-v2): the desk version on an ESP32 (voice, weather, Pomodoro)

## License

[MIT](LICENSE) © Parinith ([@MONKEYDPARI019](https://github.com/MONKEYDPARI019))
