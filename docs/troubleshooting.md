# Troubleshooting

Start with `deskbuddy doctor`. It checks the common problems and tells you the fix. If that's all green, find your symptom below.

When asking for help, attach a log: `deskbuddy monitor --log log.txt` (or **Save log** in the installer window), reproduce the problem, then press Ctrl+C.

---

## DeskBuddy.exe (Windows app)

### "Windows protected your PC"
SmartScreen warns about apps that aren't code-signed. DeskBuddy.exe isn't (a certificate costs money every year). Click **More info → Run anyway**; Windows remembers it for that file.

### It opens slowly, or the antivirus quarantines it
The single file unpacks itself each time it starts, which takes a few seconds. Some antivirus tools flag one-file Python apps by mistake. Compare the file with `SHA256SUMS` from the same release (`Get-FileHash DeskBuddy.exe` in PowerShell); if it matches, allow it in the antivirus.

### The window never appears
Look in `%USERPROFILE%\.deskbuddy\logs\app.log`. You can always use the command-line tool instead: `npm install -g deskbuddy-c3`, then `deskbuddy ui`.

---

## Installing the tool (npm)

### PowerShell: "running scripts is disabled on this system"
Windows blocks npm's PowerShell launchers until you allow local scripts. Run once:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
Or use `deskbuddy.cmd …` instead of `deskbuddy …`.

### "deskbuddy is not recognized" / "command not found" after `npm install -g`
Open a new terminal first. If it's still missing, npm's global folder isn't on your PATH: `npm prefix -g` shows it (on Windows, add that folder to PATH; on Linux/macOS, add its `bin` subfolder).

### "Could not download …" or "HTTP 404" on the first run
The first `deskbuddy` command downloads the ready-made program from GitHub (about 20 MB). Check your internet connection and run it again. A 404 means that release has no program for your computer: use the pip version (see [the command reference](cli.md#install-update-remove)).

### "There is no ready-made DeskBuddy program for …"
Ready-made programs exist for Windows, Linux x64/arm64 and macOS. On anything else, install the pip version instead.

### Linux: "GLIBC_2.35 not found"
The ready-made Linux program needs glibc 2.35 or newer (Ubuntu 22.04+, Debian 12, Raspberry Pi OS Bookworm). On older systems, use the pip version.

### I have both the npm and the pip version
Whichever comes first on your PATH runs. `where deskbuddy` (Windows) or `which -a deskbuddy` (Linux/macOS) shows which. Remove the one you don't use: `npm uninstall -g deskbuddy-c3` or `pip uninstall deskbuddy-cli`.

### `deskbuddy build` says it needs the Python version
Compiling the firmware needs PlatformIO, which needs a real Python. Installing release firmware (`deskbuddy flash`) works in the npm version; for `build` and `flash --local`, install the pip version.

---

## Connecting and flashing

### The board isn't found
- **Cable:** use a **data** cable. Many USB-C cables only charge. If `deskbuddy ports` shows nothing, try another cable and another USB port (not a hub).
- **Windows:** the C3 needs no driver, and shows up as "USB Serial Device (COMx)" in Device Manager.
- **Linux:** check `ls /dev/ttyACM*`. If you get "permission denied", run `sudo usermod -aG dialout $USER`, then log out and back in.

### "COMx is busy" / "Access is denied" / "Device or resource busy"
Another program has the port: the PlatformIO or Arduino serial monitor, a second `deskbuddy monitor`, or the installer window. Close it and try again. Only one program can use a serial port at a time.

### "Hold BOOT, tap RESET, release BOOT"
The chip didn't enter upload mode by itself. Press and hold **BOOT** on the Super Mini, tap **RESET**, release BOOT. The tool retries by itself. If it keeps happening, try another cable or port.

### The COM port disappears for a moment after reset, `link` or flashing
That's normal. The C3's USB restarts with the chip. The tool and the monitor wait and reconnect. If a port never comes back, unplug and replug the board.

### The board keeps connecting and disconnecting after an erase
An empty chip has no program to run, so it restarts over and over, and its USB port drops out each time. Hold **BOOT**, tap **RESET**, release **BOOT**: the chip then waits quietly in download mode. Install the firmware (`deskbuddy flash`, or **INSTALL** in the window). `deskbuddy erase` and **Erase chip** already leave the chip in download mode, so this only happens if you press RESET before installing.

In the installer window (2.2.1 and newer) the status line then says **"Board is empty: click INSTALL."**, and the monitor shows the repeated `invalid header: 0xffffffff` line once with a count. Older versions of the window could stop responding while an empty chip was printing; update to the latest DeskBuddy.exe or `npm install -g deskbuddy-c3`.

If it keeps doing this **after** a successful install, the firmware itself is restarting: save the monitor output (`deskbuddy monitor --log boot.txt`, or **Save log** in the window) and look for `rst:`, `assert`, `Guru Meditation` or `Brownout`.

### The board keeps resetting as soon as a serial monitor opens
Some monitors (for example VS Code's built-in "Serial Monitor" tab) toggle the DTR/RTS lines, which resets the C3 over and over. Use `deskbuddy monitor` or the installer window, which keep them off. In PlatformIO, use its own monitor; the project already sets `monitor_rts = 0` and `monitor_dtr = 0`.

### My WiFi and settings were gone after flashing
Only `--erase` / **Erase settings** does that. Normal flashing keeps them. If you erased, set WiFi up again (see [Using DeskBuddy](using-deskbuddy.md#bluetooth-or-wifi)).

---

## Screen, buttons, LEDs

### The OLED stays black
1. Run `deskbuddy cmd i2c`. It should list **0x3C** (or 0x3D).
2. **Nothing found:** check the wiring: VCC → **3V3** (not 5V), GND → G, SDA → **GPIO6**, SCL → **GPIO7**. Make sure SDA and SCL aren't swapped, and press each jumper in firmly.
3. **Found, but black:** run `oled reinit` in the monitor, or press RESET.

The firmware checks the OLED every 3 seconds and restarts it on its own when it answers again, so a loose wire recovers without a reset once it's fixed.

### Mochi changes face by himself / the screen jumps back to Mochi / the radio switches at every reset
DeskBuddy is seeing **button presses you didn't make**. Each BTN1 click changes the mood and jumps to Mochi. Both buttons "held" at start-up switch the radio.

Firmware 2.3.0 and later ignore short spikes: a press must last 30 ms **and** be read the same at least 3 times in a row. A phantom press that still gets through is a wiring problem:

1. In `deskbuddy monitor`, type `test buttons` and **don't touch anything** for 10 s. Any `BTN1 down` or `BTN2 down` means a wiring problem.
2. Use **diagonally opposite legs** of each button (see [Hardware](hardware.md#buttons-use-diagonal-legs)), and check for loose jumpers, a bad breadboard hole, or solder touching a neighbouring pin.

### The screen freezes after a few button presses (firmware 2.2.1 and older)
On USB power from a PC with sound on, firmware 2.2.1 and older could freeze after a few presses when no program was
reading the USB serial port: the board waited for its log output to be read. Update to 2.3.0 or newer
(`deskbuddy flash`). On 2.2.1, `set silent 1` makes it less likely, and opening `deskbuddy monitor` unfreezes it.
To check a board: `python scripts/board_stress_test.py` (needs 2.3.0+).

### The first button press does nothing
Mochi was asleep. The screen dims after `sleep_sec` (default 120 s), and the first press only wakes him up. Change the delay with `set sleep_sec 600`, or `set sleep_sec 0` to never sleep.

### The LEDs never light
That's usually normal: red is only for silent mode or a low battery, and yellow only for unread notifications. Check them with `test leds`. If nothing lights:
- the **long leg** goes to the GPIO (through 330 Ω), and the short leg to G;
- red → GPIO3, yellow → GPIO4;
- `get` shows `leds 1`.

### No sound
- Check `get` for `silent 0` and a `volume` above 0.
- The buzzer must be **passive**. An active buzzer only clicks or beeps once.
- Run `test buzzer`.

### The buzzer sounds while flashing
During an upload the chip runs its ROM bootloader, not DeskBuddy, so nothing drives the buzzer pin. Firmware 2.2.1 and
later park the pin LOW before every restart, so uploads are quiet, but only once 2.2.1 is on the board: the upload that
installs it may still beep, and a board with no firmware at all (just erased, then unplugged) can too. If yours still
beeps after that, put a 10 kΩ resistor from GPIO10 to GND.

---

## Phone app and radios

### The app can't find DeskBuddy over Bluetooth
1. Check that DeskBuddy is actually in Bluetooth mode: `deskbuddy status` should show `link ble, bluetooth advertising`. If it says `wifi`, switch with `deskbuddy link ble`, or hold BTN1 + BTN2 while pressing RESET.
2. On the phone, turn on Bluetooth **and Location**, and allow the app's Nearby devices permission.
3. Don't pair DeskBuddy in Android's Bluetooth settings. If it's listed there, choose **Forget**.
4. Turn the phone's Bluetooth off and on, then reopen the app.
5. Test with **nRF Connect** (free on the Play Store). If "DeskBuddy-C3" shows up in its scan, the board is fine and the problem is in the app settings.

### The app says "can't find host" (WiFi)
- **Same network:** the phone must be on the **same WiFi** as DeskBuddy, not mobile data and not the setup network.
- **Host and port:** tap **Find** in Setup, or type DeskBuddy's IP (from `deskbuddy status`) instead of `deskbuddy-c3.local`. Many Android phones can't resolve `.local` names. Port **81**.
- **Board online:** check that DeskBuddy is online: `deskbuddy status` should show `link wifi, online, …, 192.168.x.x`.

### "DeskBuddy_C3_Setup" doesn't appear on my phone
- **Mode:** check it's in WiFi mode: `deskbuddy status` should show `wifi setup portal`.
- **Distance:** hold the phone within 1–2 m, and refresh the WiFi list. The Super Mini's antenna is weak, and firmware 2.0.0 lowers the transmit power to work around it. Update older firmware with `deskbuddy flash`.
- **Another device:** check with a laptop too.

### The setup portal comes back after I saved my WiFi
The password was wrong, or the network is **5 GHz**. The ESP32-C3 only does 2.4 GHz. Join the setup network again and pick the 2.4 GHz one. Phone hotspots work if set to 2.4 GHz ("maximise compatibility" on iPhone).

### The clock shows `--:--`
- **Bluetooth:** connect the app; it sets the time.
- **WiFi:** wait for the "getting the time..." hint to go away. If it says "join DeskBuddy_C3_Setup", WiFi isn't set up yet.

### Notifications don't arrive
1. Test the board: `deskbuddy cmd "notify hello"` should pop up.
2. In the app: notification access on, forwarding on, the app not blocked in Inbox, and the link connected.
3. Some phones kill background apps. Set DeskBuddy's battery usage to **Unrestricted**.

---

## Battery build

### It switches off right away, or shows a strange battery level
- **Divider:** the divider must be fitted: battery+ → 220 kΩ → GPIO0 → 220 kΩ → G. Without it, GPIO0 floats; fit at least a 100 kΩ resistor from GPIO0 to G, or use the USB build.
- **Calibration:** compare `test battery` with a multimeter reading, and correct it with `set bat_off <mV>`.

### It won't switch on
Hold **BTN1 for a full 3 seconds**; a short press sends it back to sleep. Check the slide switch, and charge the battery through the TP4056's USB port.

### Runtime is short
Use Bluetooth mode. WiFi uses roughly twice the power. Lower `brightness`, set a shorter `sleep_sec`, or set `auto_off` (minutes).

---

## Building from source

### The first `deskbuddy build` takes forever
It downloads about 1 GB (the ESP32 toolchain) once. Later builds take a minute or two.

### "FileNotFoundError" or path errors during the build on Windows
These come from Windows' 260-character path limit. The tool already uses a short folder (`C:\.deskbuddy\platformio`). If C: is full or the error persists, set a short folder on another drive:

```powershell
$env:DESKBUDDY_PIO_CORE = "D:\.deskbuddy\platformio"
deskbuddy build
```

### PlatformIO in VS Code: "Failed to install Python dependencies into penv"
This only affects your own VS Code PlatformIO, not `deskbuddy build`. Close VS Code, then in PowerShell:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\uv.exe" pip install --reinstall --python "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" platformio==6.1.18 "littlefs-python>=0.16.0" "fatfs-ng>=0.1.14" "pyyaml>=6.0.2" "rich-click>=1.8.6" "zopfli>=0.2.2" "intelhex>=2.3.0" "rich>=14.0.0" "urllib3<2" "cryptography>=45.0.3" "certifi>=2025.8.3" "ecdsa>=0.19.1" "bitstring>=4.3.1" "reedsolo>=1.5.3,<1.8" "esp-idf-size>=2.0.0" "esp-coredump>=1.14.0"
```

If that fails too, delete `%USERPROFILE%\.platformio\penv`, open VS Code, let PlatformIO reinstall itself, and run the command again.

---

## `cmd` says "No reply" but it worked
Tool versions before 2.3.0 reported "No reply" (exit code 8) for commands that succeed silently, like `face happy` or `screen clock`. Update the tool (`npm install -g deskbuddy-c3`, or the latest DeskBuddy.exe): silent commands now return at once with exit code 0. If 2.3.0 still says "No reply", the board printed nothing at all: check that DeskBuddy firmware is installed (`deskbuddy monitor`).

---

## Error messages

| Message | What to do |
|---|---|
| No DeskBuddy board found | Plug the board in with a data USB cable (not charge-only), then run `deskbuddy ports`. |
| Several boards found (COMx, COMy) | Choose one with `--port`, e.g. `--port COMx`. |
| COMx not found | Check the USB cable, then run `deskbuddy ports`. |
| Cannot open COMx | Unplug and re-plug the board, then try again. |
| COMx is busy | Close the other serial monitor or program using the port. |
| Lost the connection to COMx | The board restarted or was unplugged; try again. |
| No reply from the board on COMx within N s | Check that DeskBuddy firmware is installed: try `deskbuddy monitor`, or reflash with `deskbuddy flash`. (Also see "`cmd` says No reply" above.) |
| The board would not enter download mode | Hold BOOT, tap RESET, release BOOT, then run the command again. Try another cable. |
| Flashing failed at every speed | Try a different USB cable or port, and avoid hubs. |
| esptool is not installed in this Python environment | Reinstall the tool with the `pip install` command. |
| Firmware file X not found | Check the path, or leave out `--file` to use the latest release. |
| X is too small / does not look like a merged ESP32 image | Use a `deskbuddy-c3-*.bin` from a release or from `deskbuddy build`, not PlatformIO's `firmware.bin`. |
| Choose only one of --version, --file and --local | Use just one of them. |
| Unknown build 'X' | Use `--env usb` or `--env battery`. |
| Unknown link 'X' | Use `deskbuddy link ble` or `deskbuddy link wifi`. |
| The board did not accept 'link X' | The firmware is too old; update it with `deskbuddy flash`. |
| The board restarted but is still in X mode | Watch it with `deskbuddy monitor`. A button may be read as held at start-up (see above). |
| The board did not answer after the restart | Watch it boot with `deskbuddy monitor`. |
| Cannot reach GitHub | Check your internet connection, proxy and firewall. |
| GitHub refused the request (API rate limit reached?) | Wait an hour, or set `GITHUB_TOKEN` to a personal access token. |
| GitHub answered HTTP N | Try again in a minute. |
| No firmware release has been published yet | Build from source: `deskbuddy flash --local`. |
| Release vX not found | List the releases with `deskbuddy versions`. |
| Release vX has no usb/battery firmware | See what each release contains with `deskbuddy versions`. |
| Download failed | Check your connection and free disk space, and try again. |
| X failed the checksum test | The download is damaged or was tampered with. Run the command again; if it keeps failing, report it on GitHub. |
| Checksums for X disagree | The release may have been tampered with. **Don't flash it**; report it on GitHub. |
| Release vX has no checksum for X | The tool refuses unverified images. Use `--file` with an image you trust, or `--local`. |
| Archive contains an unsafe path / a link | The source archive was rejected and nothing was extracted. Report it. |
| DIR already exists and is not empty | Delete it, or choose another `--dest`. |
| No DeskBuddy firmware project found in DIR | Run inside the DeskBuddy-C3 folder, pass `--path`, or download the source with `deskbuddy get`. |
| Could not set up PlatformIO for building | Check your internet connection. Debian/Ubuntu: `sudo apt install python3-venv`. Or install with the `[build]` extra. |
| Firmware build failed (env) | Read the last build lines shown. Run with `-v` for the full output. |
| The ESP32-C3 bootloader must be flashed at 0x0 / The app must start at 0x10000 | `partitions.csv` was changed; restore it. |
| Tkinter is not installed | `sudo apt install python3-tk` (Fedora: `sudo dnf install python3-tkinter`). |
| Unexpected error | Run the command again with `--debug`, and report the output on GitHub. |
