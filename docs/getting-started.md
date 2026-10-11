# Getting started

This tutorial takes you from a wired-up DeskBuddy C3 to Mochi showing your phone's notifications. It takes about 20 minutes. Every step is the same on Windows (PowerShell) and Linux, except where marked.

**Before you start**, you need:

- a DeskBuddy C3 with at least the OLED connected (see [Hardware](hardware.md)). Buttons, LEDs and buzzer can come later.
- a **USB-C data cable**. Some cables only charge; if the board never shows up, try another one.
- a PC with internet.
- an Android phone, if you want the app.

---

## Step 1: Install Node.js

The easiest way to get the `deskbuddy` tool is through **npm**, which comes with Node.js.

**Windows:** run `winget install OpenJS.NodeJS.LTS` (or download the LTS installer from [nodejs.org](https://nodejs.org)), then open a **new** PowerShell window and check:

```powershell
node --version
```

Any version from 18 up works.

**Linux (Debian/Ubuntu):**
1. Install Node.js 18 or newer from [nodejs.org](https://nodejs.org/en/download) (the distribution's own package is often too old).
2. Give yourself access to serial ports, then **log out and back in**:

   ```bash
   sudo usermod -aG dialout $USER
   ```

## Step 2: Install the `deskbuddy` tool

```bash
npm install -g deskbuddy-c3
```

This also downloads the ready-made `deskbuddy` program for your computer (about 20 MB, once). Check it worked:

```bash
deskbuddy --version
```

It should print `deskbuddy 2.1.0` (or newer).

> **PowerShell says "running scripts is disabled on this system"?** Windows blocks npm's PowerShell launchers by default. Run this once, then try again:
>
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```
>
> **"deskbuddy is not recognized"?** Open a new terminal. If it still isn't found, npm's folder isn't on your PATH: run `npm prefix -g` and add that folder to PATH.

**Prefer Python?** The same tool installs with pip, and also has `deskbuddy build` for compiling the firmware yourself. You need Python 3.9 or newer (on Windows, tick "Add python.exe to PATH" in its installer) and Git:

```bash
pip install "git+https://github.com/MONKEYDPARI019/DeskBuddy-C3#subdirectory=tool"
```

If `deskbuddy` isn't found afterwards, use `python -m deskbuddy` instead. Linux may say "externally-managed-environment": install it with pipx instead (`sudo apt install pipx python3-tk`, then `pipx install "git+…"`). Install it one way or the other, not both, so you always know which `deskbuddy` runs.

## Step 3: Plug in the board and run the checks

1. Plug the DeskBuddy into the PC with the USB-C cable.
2. **Close any other serial monitor** (PlatformIO, Arduino IDE), because only one program can use the port at a time.
3. Run the checks:

   ```bash
   deskbuddy doctor
   ```

   You should see something like:

   ```
   ✓ Python: 3.12.4
   ✓ esptool: 5.5.0
   ✓ pyserial: 3.5
   ✓ Board: COM9 - ESP32-C3 (USB Serial Device (COM9))
   ✓ Port: COM9 is free
   ✓ GitHub: reachable
   ✓ Serial permissions: not needed on this OS

   7 of 7 checks passed.
   ```

Each ✗ comes with a hint. The usual ones are a charge-only cable, a busy port, or (on Linux) the `dialout` group. See [Troubleshooting](troubleshooting.md) for more.

## Step 4: Install the firmware

```bash
deskbuddy flash
```

The tool:
1. looks up the latest release on GitHub;
2. downloads the **USB build**;
3. checks its SHA-256;
4. writes it to the board;
5. waits for the board to restart and confirms it booted.

```
Looking up the firmware release on GitHub...
Downloading v2.0.0 (usb build)...
Keeping saved settings (WiFi, link mode); use --erase to reset them.
Writing firmware to COM9 at 921600 baud...
Waiting for the board to restart...
Installed DeskBuddy C3 v2.0.0 ✓
```

The OLED shows "DeskBuddy C3" for a moment, then **Mochi** opens his eyes, and the buzzer plays a little hello tune.

> **It says "Hold BOOT, tap RESET, release BOOT"?** Some boards don't enter upload mode on their own. Press and hold the **BOOT** button on the Super Mini, tap **RESET**, release BOOT. The tool notices and carries on.
>
> **Using a battery?** Install the battery build instead: `deskbuddy flash --env battery`. Read [the battery section](hardware.md#battery-build) first.

## Step 5: Say hello over the serial monitor

```bash
deskbuddy monitor
```

Type `status` and press Enter:

```
> status
DeskBuddy C3 c3-2.0.0 (USB build)
link     ble, bluetooth advertising, 0 app(s), 14:63:93:c6:68:9a
oled     OK at 0x3C
time     not set UTC-5:30
screen   mochi, face idle/default
notifs   0, 0 unread
memory   137384 free, lowest 137252
uptime   43 s, last reset: other
```

Try a few more commands:

| Type | What happens |
|---|---|
| `face happy` | Mochi smiles |
| `notify Hello from my PC!` | a notification pops up, and the yellow LED lights |
| `test leds` | the LEDs light one by one |
| `test buzzer` | rising beeps |
| `help` | lists every command |

Press **Ctrl+C** to leave the monitor. (You can also do all of this in the installer window: `deskbuddy ui`.)

## Step 6: Connect the phone app (Bluetooth)

DeskBuddy starts in **Bluetooth** mode, which needs no setup.

1. Install the DeskBuddy app on your phone (see [Phone app](phone-app.md)).
2. Turn on the phone's **Bluetooth** and **Location**. Android needs Location for Bluetooth scanning.
3. In the app, open **Setup** and set **Device type: C3 Pocket** and **Link: Bluetooth**. Tap **LINK**. Allow the **Nearby devices** permission when asked.
4. Give the app **notification access** when it asks. That's how it can forward your messages.

**Don't** pair DeskBuddy in Android's Bluetooth settings. The app connects to it directly.

When it connects:
- DeskBuddy chirps and Mochi smiles.
- The clock gets the phone's time.
- On the clock screen (press **BTN2**), the dot next to "BT" is filled in.

Now send yourself a message on WhatsApp or by SMS. It pops up on DeskBuddy.

## Step 7: (Optional) Use WiFi instead

Use WiFi if you want internet time, the browser notification link, or wireless firmware updates. Bluetooth is better for battery life and works anywhere.

1. **Switch DeskBuddy to WiFi.** Use any one of these:
   - In the app: Setup → Link → **WiFi** (while connected over Bluetooth)
   - On the PC: `deskbuddy link wifi`
   - On the device: hold **BTN1 + BTN2**, tap **RESET**, and keep holding until the screen says "WiFi mode"
2. **Give it your WiFi (first time only).**
   1. On your phone, join the WiFi network **DeskBuddy_C3_Setup** (no password). If the phone says "no internet", tap **Stay connected**.
   2. A setup page opens. If it doesn't, open **192.168.4.1** in Chrome.
   3. Tap **Configure WiFi**, pick your home network, type the password and tap **Save**.

   Use a **2.4 GHz** network. The ESP32-C3 can't see 5 GHz ones (names often ending in "5G").
3. **Connect the app.**
   1. Put the phone back on your home WiFi.
   2. In the app's Setup, set **Link: WiFi**, **Host: `deskbuddy-c3.local`** (or tap **FIND**) and **Port: 81**.
   3. Tap **LINK**.

DeskBuddy remembers the network. To go back to Bluetooth, use the app, `deskbuddy link ble`, or the both-buttons trick again.

## What next?

- **Controls:** learn the buttons, LEDs and settings in [Using DeskBuddy](using-deskbuddy.md).
- **Battery:** make it pocket-sized with the [battery build](hardware.md#battery-build).
- **Changing the code:** see [Development](development.md).
- **Something not working?** See [Troubleshooting](troubleshooting.md).
