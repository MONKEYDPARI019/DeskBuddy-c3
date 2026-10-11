# `deskbuddy` command reference

`deskbuddy` downloads, flashes, erases, monitors and builds DeskBuddy C3 firmware. It works the same in Windows PowerShell, a Linux shell and the macOS Terminal.

## Install, update, remove

**With npm** (recommended, no Python needed; Node.js 18 or newer):

```bash
npm install -g deskbuddy-c3      # install
npm update -g deskbuddy-c3       # update to the newest version
npm uninstall -g deskbuddy-c3    # remove (then delete ~/.deskbuddy/app to free the space)
```

The npm package is a small launcher. On first use (or already during `npm install`), it downloads the ready-made `deskbuddy` program for your computer from the GitHub release of the same version, checks it against the release's `SHA256SUMS`, and keeps it in `~/.deskbuddy/app`. Ready-made programs exist for Windows x64 (and Windows on ARM), Linux x64 and arm64 (glibc 2.35+), and macOS (Apple silicon and Intel). Everything works the same as the Python version, except `deskbuddy build` and `flash --local`, which need Python.

**With pip** (Python 3.9 or newer):

```bash
# install
pip install "git+https://github.com/MONKEYDPARI019/DeskBuddy-C3#subdirectory=tool"

# update to the newest tool
pip install --upgrade --force-reinstall "git+https://github.com/MONKEYDPARI019/DeskBuddy-C3#subdirectory=tool"

# also install PlatformIO up front (only needed for `build` / `flash --local`)
pip install "deskbuddy-cli[build] @ git+https://github.com/MONKEYDPARI019/DeskBuddy-C3#subdirectory=tool"

# remove
pip uninstall deskbuddy-cli
```

On Python 3.10 and newer it uses esptool 5; on 3.9 it uses esptool 4. Both are tested. If `deskbuddy` isn't found after installing, run it as `python -m deskbuddy …`.

Use one or the other. If both are installed, whichever comes first on your PATH runs (`where deskbuddy` on Windows, `which -a deskbuddy` on Linux shows which).

## Overview

| Command | What it does |
|---|---|
| [`ports`](#ports) | List serial ports and spot DeskBuddy boards |
| [`doctor`](#doctor) | Check that everything is ready |
| [`versions`](#versions) | List firmware releases on GitHub |
| [`get`](#get) | Download firmware and source code |
| [`flash`](#flash) | Install firmware on the board |
| [`erase`](#erase) | Wipe the board completely |
| [`monitor`](#monitor) | Interactive serial monitor |
| [`cmd`](#cmd) | Send one command, print the reply |
| [`status`](#status-wifi-forget-reboot) | Show the board's status |
| [`link`](#link) | Switch Bluetooth ↔ WiFi |
| [`wifi-forget`](#status-wifi-forget-reboot) | Erase the saved WiFi network |
| [`reboot`](#status-wifi-forget-reboot) | Restart the board |
| [`build`](#build) | Compile firmware from source |
| [`ui`](#ui) | Open the installer window |

**Global options** (put them before the command):

| Option | Effect |
|---|---|
| `--version` | Print the tool version |
| `--verbose`, `-v` | Show esptool and PlatformIO output |
| `--debug` | Show full Python tracebacks on errors |

**Choosing the board.** Every command that talks to the board accepts `--port`/`-p` (e.g. `-p COM9` or `-p /dev/ttyACM0`). Without it, the tool picks the ESP32-C3 by itself. If several are plugged in, it asks; or, in a script, it fails with exit code 2.

**Builds.** `--env usb` is the normal USB-powered build (PlatformIO env `c3`). `--env battery` is the battery build (`c3-battery`).

---

### `ports`

```
> deskbuddy ports
* COM9 - ESP32-C3 (USB Serial Device (COM9))

* = ESP32-C3 (DeskBuddy)   ? = possible ESP32 (USB-UART chip)
```

`*` marks an ESP32-C3 (USB ID 303A). `?` marks USB-serial chips (CP210x, CH340) that might be another ESP32 board.

### `doctor`

Checks Python, esptool, pyserial, whether a board is connected, whether its port is free, whether GitHub is reachable, and (on Linux) whether you're in the `dialout` group. Every failed check comes with a fix.

```
> deskbuddy doctor
✓ Python: 3.13.15
✓ esptool: 5.5.0
✓ pyserial: 3.5
✓ Board: COM9 - ESP32-C3 (USB Serial Device (COM9))
✓ Port: COM9 is free
✓ GitHub: reachable
✓ Serial permissions: not needed on this OS

7 of 7 checks passed.
```

### `versions`

```
> deskbuddy versions
v2.0.0       2026-10-08  builds: battery, usb (latest)
    deskbuddy-c3-c3-battery-v2.0.0.bin  (1,685,408 bytes)
    deskbuddy-c3-c3-v2.0.0.bin  (1,673,952 bytes)
    manifest.json  (619 bytes)
    SHA256SUMS  (194 bytes)
```

### `get`

```
deskbuddy get [--version vX.Y.Z] [--dest DIR]
```

Downloads both firmware builds of a release (default: latest) into the cache, checks them, and extracts the release's **source code** into `DIR/DeskBuddy-C3-<tag>/` (default `DIR`: the current folder).

```
> deskbuddy get --dest projects
Release v2.0.0 (2026-10-08)
  ✓ usb firmware: ~/.deskbuddy/firmware/v2.0.0/deskbuddy-c3-c3-v2.0.0.bin
  ✓ battery firmware: ~/.deskbuddy/firmware/v2.0.0/deskbuddy-c3-c3-battery-v2.0.0.bin
  ✓ source code: projects/DeskBuddy-C3-v2.0.0
```

### `flash`

```
deskbuddy flash [--version vX.Y.Z | --file PATH | --local [--path DIR]]
                [--env usb|battery] [--port P] [--erase] [--baud N] [--no-monitor]
```

| Option | Default | Meaning |
|---|---|---|
| *(none of the three)* | latest release | Download the release image from GitHub (cached, SHA-256 checked) |
| `--version vX.Y.Z` | | A specific release |
| `--file PATH` | | A merged `.bin` you already have (e.g. from `build`, or downloaded by hand) |
| `--local` | | Build the source in `--path` (default: current folder) first, then flash it |
| `--env` | `usb` | `usb` or `battery` |
| `--erase` | off | Erase the whole flash first. This **resets saved settings and WiFi**. |
| `--baud` | `921600` | Start speed. Falls back to 460800, then 115200. |
| `--no-monitor` | off | Don't confirm the boot afterwards |

```
> deskbuddy flash
Looking up the firmware release on GitHub...
Downloading v2.0.0 (usb build)...
Keeping saved settings (WiFi, link mode); use --erase to reset them.
Writing firmware to COM9 at 921600 baud...
Waiting for the board to restart...
Installed DeskBuddy C3 v2.0.0 ✓
```

**Saved settings are kept.** Without `--erase`, the area where DeskBuddy stores its settings and WiFi network (NVS) is skipped, so updating doesn't make you set up WiFi again.

**If the board won't enter upload mode**, the tool prints **"Hold BOOT, tap RESET, release BOOT"**, waits for the port to come back, and retries up to 3 times.

**Only merged images can be flashed** (the `deskbuddy-c3-*.bin` files from releases or `build`). PlatformIO's own `firmware.bin` is refused, because it lacks the bootloader.

### `erase`

```
deskbuddy erase [--port P] [--yes]
```

Erases the **whole flash**: the firmware, the settings and the saved WiFi network. It asks first; `--yes` (`-y`) skips the question, for scripts.

```
> deskbuddy erase
Erase EVERYTHING on COM9 (firmware, settings and saved WiFi)? [y/N]: y
Erasing the whole flash on COM9...
Erased the whole flash on COM9 ✓
The board is empty now and waits in download mode, so the screen stays dark.
Put DeskBuddy back with: deskbuddy flash   (or INSTALL in deskbuddy ui)
```

- Takes a few seconds. Anything other than `y`/`yes` cancels, and nothing is erased (exit code 1).
- Afterwards, the chip **waits in download mode**, so its USB port stays steady. If you press RESET now, an empty chip restarts over and over and the port keeps dropping out. That's normal: install firmware, or hold BOOT, tap RESET and release BOOT to quiet it again.
- To erase and install in one go, use `deskbuddy flash --erase` instead.
- The installer window has the same thing as the **Erase chip** button.

### `monitor`

```
deskbuddy monitor [--port P] [--log FILE] [--raw]
```

Live serial output at 115200 baud. Type a command and press Enter to send it; **Ctrl+C** quits.

- Opens the port with DTR/RTS off, so the C3 doesn't reset or boot-loop.
- Colours: errors/`CRASH`/`assert` red, `[BLE]` blue, `[WiFi]` green, `[OLED]` yellow.
- When the board restarts or is unplugged, it shows "waiting for board…" and reconnects by itself.
- `--log FILE` also writes everything, including what you typed, to a file.
- `--raw` turns off colours and local echo, for piping into other programs.

### `cmd`

```
deskbuddy cmd "<command>" [--timeout S] [--port P]
```

Sends one serial command and prints the reply, until the board has been quiet for 0.8 s or `--timeout` (default 5 s) runs out.

```
> deskbuddy cmd i2c
  I2C device at 0x3C  <- OLED
  1 device(s) on SDA=GPIO6 SCL=GPIO7
```

Some commands (`face …`, `screen …`, `press …`) work but print nothing. `cmd` then reports "No reply" with exit code 8, even though it worked. See [Troubleshooting](troubleshooting.md#cmd-says-no-reply-but-it-worked).

### `status`, `wifi-forget`, `reboot`

| Command | Same as |
|---|---|
| `deskbuddy status` | `cmd status` |
| `deskbuddy wifi-forget` | `cmd "wifi forget"` |
| `deskbuddy reboot` | sends `reboot`, waits, and confirms the boot banner |

```
> deskbuddy status
DeskBuddy C3 c3-2.0.0 (USB build)
link     ble, bluetooth advertising, 0 app(s), 14:63:93:c6:68:9a
oled     OK at 0x3C
time     2026-10-08 20:33:43 UTC-5:30
screen   mochi, face idle/default
notifs   0, 0 unread
memory   137384 free, lowest 137252
uptime   43 s, last reset: other

> deskbuddy reboot
Waiting for the board to restart...
Board restarted: DeskBuddy C3 v2.0.0 (USB build) ✓
```

### `link`

```
deskbuddy link ble|wifi [--port P]
```

Switches the radio, waits for the restart, and checks the new mode from the boot messages. If the board is already in that mode, it returns at once.

```
> deskbuddy link wifi
Board is restarting with the new link...
Link is now WiFi ✓
```

### `build`

```
deskbuddy build [--env usb|battery] [--path DIR] [--out DIR]
```

Compiles the firmware in `--path` (default: the current folder, or its `firmware/` subfolder) and writes a merged, ready-to-flash image to `--out` (default `~/.deskbuddy/builds`).

```
> deskbuddy build --env usb --out dist
Building usb firmware in D:\ard\DeskBuddy-C3\firmware (first build downloads ~1 GB)...
✓ Built D:\ard\DeskBuddy-C3\dist\deskbuddy-c3-c3-v2.0.0.bin
  sha256 76d0307c…8c067b34  (1,673,952 bytes)
```

- The tool uses its **own private PlatformIO**, never your normal PlatformIO or VS Code setup.
- The first build downloads about **1 GB** and needs about **6 GB** of disk.
- Flash the result with `deskbuddy flash --file <path>`, or do both in one go with `deskbuddy flash --local`.

### `ui`

Opens the installer window. See [Installer window](installer-ui.md).

---

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | General error, a `doctor` check failed, or `erase` was cancelled |
| 2 | Usage error (bad option, several boards and no `--port`, unknown release) |
| 3 | No board / port not found / connection lost |
| 4 | Port busy |
| 5 | Network or GitHub problem |
| 6 | Integrity problem (checksum mismatch, unsafe archive) |
| 7 | Flashing or erasing failed |
| 8 | The board gave no reply |
| 9 | Build failed |
| 130 | Interrupted (Ctrl+C) |

## Files and environment variables

| Path | Contents |
|---|---|
| `~/.deskbuddy/app/<version>-<platform>/` | The ready-made program (npm install only). Older versions are removed after an update. |
| `~/.deskbuddy/firmware/<tag>/` | Downloaded, verified release images |
| `~/.deskbuddy/builds/` | Output of `deskbuddy build` |
| `~/.deskbuddy/platformio/venv/` | The tool's private PlatformIO (if the `[build]` extra isn't installed) |
| `~/.deskbuddy/platformio/core` | PlatformIO's downloads (~6 GB). On Windows with long paths disabled: `C:\.deskbuddy\platformio`. |

`~` is your home folder (`C:\Users\<you>` on Windows). Deleting `~/.deskbuddy` is safe; things are downloaded again when needed.

| Variable | Effect |
|---|---|
| `DESKBUDDY_HOME` | Move `~/.deskbuddy` somewhere else |
| `DESKBUDDY_PIO_CORE` | Move the 6 GB PlatformIO folder, e.g. to another drive. Keep the path short on Windows, e.g. `D:\.deskbuddy\platformio`. |
| `GITHUB_TOKEN` | Optional personal access token. Raises GitHub's limit of 60 requests per hour. |
| `DESKBUDDY_SKIP_DOWNLOAD` | npm only: don't download the program during `npm install` (the first run still does) |
| `DESKBUDDY_BINARY` | npm only: run this program instead of the downloaded one, e.g. a local build from `scripts/build_app.py` |

PowerShell example: `$env:DESKBUDDY_PIO_CORE = "D:\.deskbuddy\platformio"`. Linux: `export DESKBUDDY_PIO_CORE=~/data/pio`.
