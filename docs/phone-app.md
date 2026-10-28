# Phone app

The DeskBuddy Android app (in [`app/`](../app)) forwards your notifications and calls, sets the clock, updates DeskBuddy's firmware, and lets you control Mochi, screens and settings. Since app 0.6.0 (release 2.5.0) it is for DeskBuddy C3 only; the DeskBuddy v2 parts (voice, weather, device type) are gone.

## Install

**Ready-made:** every release has the app as `deskbuddy-app-vX.Y.Z.apk` (`...-debug.apk` before 2.5.0). Download it on the phone from the [latest release](https://github.com/MONKEYDPARI019/DeskBuddy-C3/releases/latest), open it, and allow "Install unknown apps" for your browser when Android asks.

- **From 2.5.0 on**, every release APK is signed with the same key, so a new one installs over the old one and keeps your settings.
- **Once, when going to 2.5.0:** uninstall the old app first. The older APKs were signed with a different key, so Android refuses to install over them ("App not installed" / "conflicts with an existing package").

**Build it yourself** with Android Studio:

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
| **Answer phone calls** (optional, Inbox → Calls → Allow) | Letting BTN1 / BTN2 on DeskBuddy answer, decline and hang up SIM calls |

Keep the phone's **Bluetooth** and **Location** switched on for Bluetooth mode. If your phone aggressively kills background apps, set the DeskBuddy app's battery usage to **Unrestricted**.

## Connect

Open **Setup**, then:

1. **Link**: choose to match DeskBuddy's current mode (shown top-left on its clock screen):
   - **Bluetooth**: nothing else to fill in.
   - **WiFi**: **Host** `deskbuddy-c3.local` and **Port** `81`. Or tap **Find** to search the network; it fills in DeskBuddy's IP.
2. Tap **Link**. The app reconnects by itself from now on, also after the phone restarts. **Stop** disconnects.

When you change **Link** while connected, the app tells DeskBuddy to switch radios, and follows it after the restart. When not connected, it only changes how the app searches, so DeskBuddy must already be in that mode.

**Don't** pair DeskBuddy in Android's Bluetooth settings. The app connects directly. If it's listed under paired devices, tap it and choose **Forget**.

## Background connection

While LINK is on, the app keeps a small **"DeskBuddy"** notification. That's what keeps the connection alive in the background, so notifications are forwarded even when the app is closed.

- **Stop** on that notification (or **Stop** in Setup) disconnects and removes it. It stays off until you tap **Link** again.
- **Reconnecting** is quick: the app tries again as soon as the screen comes on, Bluetooth is switched back on or a WiFi network appears, instead of waiting for its retry timer. Notifications that arrive while it's reconnecting are kept for 2 minutes and sent once it's back.
- **Searching stops by itself** after 10 minutes without finding DeskBuddy, to save battery. You then get a normal notification, "DeskBuddy not found", that you can swipe away. Tap **Search again** on it, or just open the app.
- **Stay connected when app is closed** (Setup, on by default):
  - **Off:** swiping the app away from the recent apps list disconnects it, and opening the app reconnects. Notifications are then only forwarded while the app is open.

## What you can do

The app has a kawaii pastel look, in light or dark: Setup → Theme, or the moon / sun button at the top.

| Screen | On a DeskBuddy C3 |
|---|---|
| **Home** | Live copy of Mochi, the screen buttons (Clock / Mochi / Inbox), link and battery status, **Zzz** (put Mochi to sleep) |
| **Moods** | Tap one of the 15 moods to show it on DeskBuddy |
| **Inbox** | Notifications sent so far, and which apps to forward (block noisy apps here). **Clear all** clears the list here **and on DeskBuddy** (firmware 2.3.1+; older firmware: only the app's list, and the app says so). Clearing on DeskBuddy (long BTN2) clears the app's list too. **Calls**: show calls on DeskBuddy. |
| **Setup** | Link, **Change WiFi** (move DeskBuddy to another network), host/port, **Update DeskBuddy**, the update password, notification forwarding on/off, silent mode, buzzer, brightness, sleep time, power off (battery build), theme |

## Calls on DeskBuddy

Firmware 2.5.0+. When a call rings (the phone app's, WhatsApp's, ...), DeskBuddy shows the caller, blinks yellow and rings:

- **BTN1** answers, **BTN2** declines. You then talk on the phone: DeskBuddy C3 has no microphone or speaker.
- During the call DeskBuddy shows "On call" and the time: **BTN1** hides that screen, **BTN2** hangs up.

It works through the call notification, so **notification access** must be on. For normal SIM calls also tap **Allow** under Inbox → Calls (Android's "answer phone calls" permission). Other apps' calls are answered by pressing their notification's button; on some Android versions an app that opens its own call screen can't do that from the background, and you answer on the phone. Turn the whole thing off with **Show calls on DeskBuddy**.

## Update DeskBuddy

Firmware 2.5.0+: no PC needed for updates any more. Install 2.5.0 **once** over USB (DeskBuddy.exe or `deskbuddy flash`); after that:

1. **Setup → Set update password** (first time only). DeskBuddy asks you to press **BTN1** to save it. Only someone who knows it *and* has DeskBuddy in hand can update it.
2. **Setup → Update DeskBuddy → Check for updates.** The app looks for the newest release on GitHub.
3. Type the password and tap **Update to vX.Y.Z** (or **Reinstall vX.Y.Z over the air** when it's already up to date, handy to test).
4. DeskBuddy shows "Update DeskBuddy?": press **BTN1** (BTN2 = no). The app sends the new firmware with a progress bar (about a minute over Bluetooth, less over WiFi); keep the phone close. DeskBuddy checks it, restarts, and the app reconnects by itself.

If anything goes wrong (wrong password, link lost, Cancel, a damaged download) DeskBuddy keeps its old firmware. Three wrong passwords lock updates for a minute. **Forgot the password?** Plug DeskBuddy into a PC, open DeskBuddy.exe and send `otapass clear`, then set a new one. The password itself never leaves the phone (see [PROTOCOL.md](../firmware/docs/PROTOCOL.md#updates-from-the-app)).

## Tips

- **Notifications don't arrive:** check that notification access is on and forwarding is enabled in Setup, and that the app isn't blocked in Inbox. Test with `deskbuddy cmd "notify test"` to confirm the board side works.
- **The clock shows `--:--` in Bluetooth mode:** the app sets the time when it connects. Make sure it's connected (filled dot next to `BT`).
- **WiFi says "can't find host":** the phone must be on the same WiFi as DeskBuddy. Tap **Find**, or type the IP from `deskbuddy status` into Host.

More in [Troubleshooting](troubleshooting.md).
