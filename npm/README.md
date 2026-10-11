# deskbuddy-c3

Install, erase and monitor the firmware of a **DeskBuddy C3**: the pocket desk companion on an ESP32-C3 Super Mini, with an animated face called Mochi, a clock and your phone's notifications.

```bash
npm install -g deskbuddy-c3
deskbuddy flash
```

No Python, PlatformIO or Arduino IDE needed. The first run downloads a ready-made program for your computer (about 20 MB) from the project's GitHub release, checks its SHA-256 checksum, and keeps it in `~/.deskbuddy/app`. After that, `deskbuddy` starts at once.

## Commands

| Command | What it does |
|---|---|
| `deskbuddy flash` | Install the latest firmware (keeps your settings and WiFi) |
| `deskbuddy flash --env battery` | Install the battery build |
| `deskbuddy erase` | Wipe the board completely (asks first) |
| `deskbuddy monitor` | Serial monitor; type commands, Ctrl+C quits |
| `deskbuddy status` | Show link mode, screen, time and memory |
| `deskbuddy link ble` / `link wifi` | Switch Bluetooth ↔ WiFi |
| `deskbuddy wifi-forget` | Forget the saved WiFi (in WiFi mode, the setup network opens) |
| `deskbuddy ui` | Installer window with a live serial monitor |
| `deskbuddy doctor` | Check that everything is ready |

`deskbuddy --help` lists them all. The full guide is in the [repository](https://github.com/MONKEYDPARI019/DeskBuddy-C3#readme).

## Supported computers

Windows 10/11 (x64, and ARM through emulation), Linux (x64 and arm64, glibc 2.35 or newer, e.g. Ubuntu 22.04+ or Raspberry Pi OS Bookworm) and macOS (Apple silicon and Intel). Node.js 18 or newer.

On anything else, use the Python version, which has the same commands plus `deskbuddy build`:

```bash
pip install "git+https://github.com/MONKEYDPARI019/DeskBuddy-C3#subdirectory=tool"
```

## Update or remove

```bash
npm update -g deskbuddy-c3      # newest version; its program is downloaded on the next run
npm uninstall -g deskbuddy-c3   # then delete ~/.deskbuddy/app to free the space
```

## Environment variables

| Variable | Effect |
|---|---|
| `DESKBUDDY_HOME` | Keep the program and downloads somewhere other than `~/.deskbuddy` |
| `DESKBUDDY_SKIP_DOWNLOAD` | Don't download during `npm install` (the first run still does) |
| `DESKBUDDY_BINARY` | Run this program instead of the downloaded one (for testing a local build) |

## License

MIT
