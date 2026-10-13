# Phone app

The DeskBuddy Android app (in [`app/`](../app)) forwards your notifications, sets the clock, and lets you control Mochi, screens and settings. The same app drives DeskBuddy v2 (the desk version) and DeskBuddy C3; you choose the device type in Setup.

## Build and install

The app isn't in the releases yet, so you build it yourself once with Android Studio.

1. Install [Android Studio](https://developer.android.com/studio).
2. **File → Open**, and choose the `app` folder of this repo. Let Gradle sync finish; the first sync downloads a lot.
3. On your phone, enable **Developer options → USB debugging**, and connect it with USB.
4. Choose your phone in the device list and click **Run ▶**. The app installs and opens.

**Updating:** get the new code (`git pull`, or the files you were sent), open the `app` folder in Android Studio again, connect the phone and click **Run ▶**. It installs over the old version and keeps your settings. Build it on the same PC each time: an app built on another PC has a different signature, and Android then asks you to uninstall the old one first.

## Permissions

| Permission | Why |
|---|---|
| **Nearby devices** (Android 12+) or **Location** (older) | Scanning for and connecting to DeskBuddy over Bluetooth |
| **Notification access** | Reading your notifications to forward them. Turn it on when the app asks, or via Android Settings → Notifications → Device & app notifications. |
| **Notifications** | Showing the "DeskBuddy linked" notification that keeps the connection alive in the background |

Keep the phone's **Bluetooth** and **Location** switched on for Bluetooth mode. If your phone aggressively kills background apps, set the DeskBuddy app's battery usage to **Unrestricted**.

## Connect

Open **Setup**, then:

1. **Device type: C3 Pocket.** The app also switches to it by itself the first time a C3 answers.
2. **Link**: choose to match DeskBuddy's current mode (shown top-left on its clock screen):
   - **Bluetooth**: nothing else to fill in.
   - **WiFi**: **Host** `deskbuddy-c3.local` and **Port** `81`. Or tap **FIND** to search the network; it fills in DeskBuddy's IP.
3. Tap **LINK**. The app reconnects by itself from now on, also after the phone restarts. **STOP** disconnects.

When you change **Link** while connected, the app tells DeskBuddy to switch radios, and follows it after the restart. When not connected, it only changes how the app searches, so DeskBuddy must already be in that mode.

**Don't** pair DeskBuddy in Android's Bluetooth settings. The app connects directly. If it's listed under paired devices, tap it and choose **Forget**.

## Background connection

While LINK is on, the app keeps a small **"DeskBuddy"** notification. That's what keeps the connection alive in the background, so notifications are forwarded even when the app is closed.

- **Stop** on that notification (or **STOP** in Setup) disconnects and removes it. It stays off until you tap **LINK** again.
- **Searching stops by itself** after 10 minutes without finding DeskBuddy, to save battery. You then get a normal notification, "DeskBuddy not found", that you can swipe away. Tap **Search again** on it, or just open the app.
- **Stay connected when app is closed** (Setup, on by default):
  - **Off:** swiping the app away from the recent apps list disconnects it, and opening the app reconnects. Notifications are then only forwarded while the app is open.

## What you can do

| Screen | On a DeskBuddy C3 |
|---|---|
| **Home** | Live copy of Mochi, the screen buttons (CLOCK / MOCHI / INBOX), link and battery status, **ZZZ** (put Mochi to sleep) |
| **Moods** | Tap one of the 15 moods to show it on DeskBuddy |
| **Inbox** | Notifications sent so far, and which apps to forward (block noisy apps here) |
| **Setup** | Device type, link, host/port, notification forwarding on/off, silent mode, volume, brightness, sleep time, power off (battery build), theme |

The voice features of DeskBuddy v2 are hidden for the C3, which has no microphone or speaker.

## Tips

- **Notifications don't arrive:** check that notification access is on and forwarding is enabled in Setup, and that the app isn't blocked in Inbox. Test with `deskbuddy cmd "notify test"` to confirm the board side works.
- **The clock shows `--:--` in Bluetooth mode:** the app sets the time when it connects. Make sure it's connected (filled dot next to `BT`).
- **WiFi says "can't find host":** the phone must be on the same WiFi as DeskBuddy. Tap **FIND**, or type the IP from `deskbuddy status` into Host.

More in [Troubleshooting](troubleshooting.md).
