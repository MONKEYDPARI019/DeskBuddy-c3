# Installer window

`deskbuddy ui` opens a small window for installing firmware and watching the serial output, for when you'd rather click than type. It does exactly what `deskbuddy flash` and `deskbuddy monitor` do.

```bash
deskbuddy ui
```

```
┌ DeskBuddy Installer ──────────────────────────────────────────────┐
│ Board:    [ COM9 – ESP32-C3 (found) ▾ ]  [Refresh]                │
│ Firmware: [ v2.0.0 (latest)        ▾ ]  [Choose .bin…]            │
│ Build:    (•) USB   ( ) Battery     [ ] Erase settings            │
│ [               INSTALL                ]   [ Erase chip ]         │
│ ██████████████░░░░░░  70%  Writing firmware...                    │
├ Serial monitor ──────────────────────────────────────────── ● on ─┤
│ === DeskBuddy C3 c3-2.0.0 (USB build) ===                         │
│ [OLED] found at 0x3C                                              │
│ [BLE] advertising as 'DeskBuddy-C3' (14:63:93:c6:68:9a)           │
│ > ____________________________________________________ [Send]     │
│ [status] [help] [Bluetooth] [WiFi] [Reboot] [Clear] [Save log]    │
└───────────────────────────────────────────────────────────────────┘
```

## Installing firmware

1. **Board**: plug DeskBuddy in. It appears as "(found)". Click **Refresh** if you plugged it in after opening the window. With several boards, pick one here (the monitor follows your choice).
2. **Firmware**: the releases from GitHub, newest first. To use a file you built or downloaded, click **Choose .bin…**. Pick a `deskbuddy-c3-*.bin` merged image. Offline, the list says so; use Choose .bin….
3. **Build**: **USB** for USB power, **Battery** if you fitted the battery circuit.
4. **Erase settings** (optional): wipes saved settings and the WiFi network, and asks you to confirm. Leave it off for normal updates.
5. Click **INSTALL**. The window:
   1. downloads and checks the firmware;
   2. pauses the monitor (it needs the port);
   3. writes the firmware while the bar shows progress;
   4. waits for DeskBuddy to restart.

When it's finished, the status line says **"Installed DeskBuddy C3 vX.Y.Z"**, and the monitor continues with the boot messages.

**If a red "Hold BOOT, tap RESET, release BOOT" banner appears**, the chip didn't enter upload mode on its own. Do exactly that on the Super Mini's two buttons. The window notices the board coming back and tries again, up to 3 times.

## Erasing the chip

**Erase chip** wipes the board completely: the firmware, the settings and the saved WiFi. Use it to start testing from zero.

1. Pick the board under **Board**.
2. Click **Erase chip**, and confirm with **Yes**.
3. The status line says **"Chip erased (empty)."** after a few seconds. The screen stays dark, because there's no firmware on the chip.
4. Click **INSTALL** to put DeskBuddy back. It starts like a new board: Bluetooth mode, default settings, no WiFi saved.

After erasing, the chip waits in download mode, so its USB port stays steady. If you press RESET before installing, the empty chip restarts over and over and the port keeps dropping out. That's normal; just install, or hold BOOT, tap RESET and release BOOT first.

**Erase chip or Erase settings?** **Erase chip** only erases. **Erase settings** + **INSTALL** erases the whole chip and then installs the firmware in one go.

## Serial monitor

- **Output:** live output with auto-scroll. Errors are red, `[BLE]` blue, `[WiFi]` green, `[OLED]` yellow. The last 5000 lines are kept.
- **Sending commands:** type any [serial command](using-deskbuddy.md#serial-commands) and press Enter or **Send**.
- **Quick buttons:**

  | Button | Sends |
  |---|---|
  | **status** | `status` |
  | **help** | `help` |
  | **Bluetooth** | `link ble` |
  | **WiFi** | `link wifi` |
  | **Reboot** | `reboot` |
- **Clear** empties the view. **Save log** writes it to a `.txt` file, which is handy when asking for help.
- **The ● on/off indicator** shows whether the monitor holds the port. It's off while flashing, and shows "[waiting for board…]" when the board restarts or is unplugged. It reconnects by itself.

## What you might see

| State | Looks like |
|---|---|
| Idle | "Ready.", monitor ● on |
| Flashing | Progress bar moving, monitor "[paused while flashing]" |
| BOOT needed | Red banner under the progress bar |
| Success | 100 %, "Installed DeskBuddy C3 vX.Y.Z", monitor resumes |
| Erasing | Moving bar, "Erasing the whole flash on COMx...", then "Chip erased (empty)." |
| Error | "Failed: …" plus a message box saying what to do. The monitor resumes. |

Close other serial monitors (PlatformIO, Arduino IDE, a `deskbuddy monitor` in a terminal) before using the window, because only one program can use the port at a time.

**On Linux**, if `deskbuddy ui` says Tkinter is missing: `sudo apt install python3-tk` (Fedora: `sudo dnf install python3-tkinter`).
