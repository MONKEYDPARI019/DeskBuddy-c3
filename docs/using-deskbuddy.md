# Using DeskBuddy

Everything DeskBuddy C3 does, and how to control it with the buttons, the app and the serial command line.

## Screens

Press **BTN2** to move through the screens. DeskBuddy always starts on Mochi.

| Screen | What it shows |
|---|---|
| **Clock** | Date, time (12 h with AM/PM) and a seconds bar along the bottom. Top-left: the link (`BT` or `WIFI`) with a dot, filled = app connected, hollow = waiting. Top-right: a crossed-out speaker in silent mode, and the battery level in the battery build. |
| **Mochi** | The face. A small badge in the top-right corner shows unread notifications. |
| **Inbox** | The last 8 notifications, newest first: app, title, and the message word-wrapped. Long messages scroll by themselves. `2/5` in the corner shows which one you're reading. |

**Before the clock knows the time**, it shows `--:--` and a hint underneath:

| Hint | Meaning |
|---|---|
| `connect the app` | Bluetooth mode: the phone sets the time when it connects |
| `connecting to WiFi...` | WiFi mode, joining your network |
| `getting the time...` | Online, fetching the time from the internet |
| `join DeskBuddy_C3_Setup` | WiFi setup needed (see [Bluetooth or WiFi](#bluetooth-or-wifi)) |

**When a notification arrives** on another screen, a popup shows the app, title and the start of the message for 4 seconds. Mochi looks surprised, the buzzer chirps, and the yellow LED lights until you open the inbox.

## Buttons

| | Click | Hold |
|---|---|---|
| **BTN1** | Next mood. On the inbox: next notification. | ~1 s: silent mode on/off. *Battery build:* hold 3 s to power off. "Power off..." appears after 1.5 s; let go before 3 s to cancel. |
| **BTN2** | Next screen | ~1 s: clear all notifications |
| **BTN1 + BTN2 while pressing RESET** (or switching on) | Switch radio: Bluetooth ↔ WiFi. Keep holding until the screen says "Bluetooth mode" or "WiFi mode". | |

- **Sleep:** after 2 minutes without a press or a notification, Mochi falls asleep and the screen dims. **The first press only wakes him up**, and the next press does its normal job.
- **Battery build, switched off:** hold **BTN1 for 3 s** to switch on.

## LEDs

| LED | Meaning |
|---|---|
| **Red** solid | Silent mode is on |
| **Red** fast blink | Battery low (battery build) |
| **Yellow** on | Unread notifications. Goes off when you open the inbox. |
| **Green** solid (optional LED) | The app is connected |
| **Green** short flash every 2 s | Waiting for the app |
| **Green** fast blink | WiFi setup portal is open |

All LEDs are off while Mochi sleeps. They can be turned off completely with `set leds 0`. With no notifications and sound on, it's normal for red and yellow to be dark.

## Mochi's moods

`default` · `happy` · `love` · `star` · `wink` · `dizzy` · `angry` · `sad` · `sleepy` · `surprised` · `smug` · `nervous` · `cat` · `sleeping` · `cute`

BTN1 cycles through them in this order. The app's **Moods** screen picks one directly. The app's **ZZZ** button (or `face sleep`) puts Mochi to sleep.

## Bluetooth or WiFi

Only one radio runs at a time. Switching saves the choice and restarts DeskBuddy (it takes about 2 seconds).

| | Bluetooth (default) | WiFi |
|---|---|---|
| Works | anywhere within ~10 m of your phone | when phone and DeskBuddy are on the same WiFi |
| Clock | set by the phone on connect | from the internet (NTP) |
| Battery | best | shorter (about half) |
| Extras | — | browser notification link, OTA updates |
| Setup | none | once, through the setup portal |

**To switch**, use any one of these:
- the app (Setup → Link, while connected)
- the command line: `deskbuddy link ble` / `deskbuddy link wifi`
- the serial command `link ble` / `link wifi`
- the buttons: BTN1 + BTN2 held while pressing RESET (BTN2 alone opens the WiFi setup portal, see [Change WiFi](#change-wifi))

**WiFi setup (first time):**
1. In WiFi mode, DeskBuddy opens its own network, **DeskBuddy_C3_Setup**.
2. Join it from your phone and open **192.168.4.1** (it usually opens by itself).
3. Tap **Configure WiFi**, pick a **2.4 GHz** network, enter the password and tap **Save**.

It remembers the network from then on. If the saved network can't be reached for 30 s (router off, moved house), the setup portal opens again for 3 minutes, then DeskBuddy retries the saved network, and keeps alternating. To forget the network: `deskbuddy wifi-forget`.

### Change WiFi

To move DeskBuddy to a different network while the old one is still in range (firmware 2.3.0+), use any one of these:
- the app: Setup → Link → **CHANGE WIFI** (while connected, over Bluetooth or WiFi)
- the buttons: hold **BTN2 alone** while pressing RESET, for about 1 s (the screen says "Change WiFi")
- the command line: `deskbuddy wifi-setup`, or the serial command `wifi setup`

DeskBuddy switches to WiFi mode and opens **DeskBuddy_C3_Setup** straight away. Join it and pick the new network as in the first-time setup. The old network stays saved: if nothing is set up within 3 minutes, DeskBuddy goes back to it.

**In WiFi mode** DeskBuddy is reachable at:

| Address | What |
|---|---|
| `deskbuddy-c3.local` or its IP, port **81** | WebSocket for the app |
| `http://<ip>/` | small status JSON |
| `http://<ip>/notify?app=Test&title=Hi&msg=Hello` | shows a notification (GET or POST). Handy for scripts and automations. |

The IP appears in the serial log as `[WiFi] online: 192.168.x.x …`, and in `deskbuddy status`.

## Notifications

- Up to **8** are kept; the oldest drops off. They're cleared on restart.
- Text is shown in plain ASCII: curly quotes become straight, `é` becomes `e`, `₹` becomes `Rs`, emoji become `*`.
- Other scripts: the app (Android 10+) turns Hindi, Kannada, Cyrillic, ... into Latin letters before sending, e.g. `नमस्ते` → `namaste`. Text that still can't be drawn shows as one `?` per word.
- The app sends up to 127 characters of each message (title 31), never cutting an emoji in half. The HTTP link and `app` command accept up to 127.
- Notifications that arrive while DeskBuddy is not connected are kept for 2 minutes and sent as soon as the link is back.
- The app decides which apps are forwarded. Each app can be blocked in the app's Inbox screen.

## Sounds

`hello` (start-up), `bye` (power off), `screen`, `notify`, `mood`, `happy`, `sad`, `surprised`, `purr`, `link` (app connected), `error`, `silent_on`, `silent_off`, `low_battery`.

Play one with the serial command `sound <name>`. Silent mode mutes everything except important warnings.

## Serial commands

Use them with `deskbuddy monitor` (interactive) or `deskbuddy cmd "<command>"` (one-shot). See the [command reference](cli.md).

| Command | What it does |
|---|---|
| `help` | List all commands |
| `status` | Link, OLED, time, screen, notifications, memory, timing (longest loop, frame and OLED transfer since the last `status`), uptime, last reset reason |
| `get` | Show all settings |
| `set <key> <value>` | Change and save a setting (see below) |
| `defaults` | Factory settings (keeps the radio choice) |
| `link wifi` / `link ble` | Switch radio (restarts) |
| `screen clock\|mochi\|notify\|next` | Change screen |
| `face <mood>` | Change Mochi's mood (`face sleep` = sleep) |
| `notify <text>` | Fake a notification |
| `sound <name>` | Play a sound |
| `time <unix seconds>` | Set the clock by hand |
| `test oled\|leds\|buzzer\|buttons\|battery` | Hardware tests |
| `i2c` | Scan the I2C bus (OLED = 0x3C) |
| `oled reinit` | Restart the OLED |
| `press 1\|2 [ms]` | Press a button in software |
| `state` | The JSON status the app receives |
| `app <json>` | Handle one app message, e.g. `app {"type":"notify","app":"Test","title":"Hi","body":"hello"}` |
| `wifi setup` | Change WiFi: restart into the setup portal, keeping the old network as a fallback |
| `wifi forget` | Erase the saved WiFi network |
| `echo <text>` | Print `<text>` (the PC tool uses it to see where a reply ends) |
| `off` | Power off (battery build) |
| `reboot` | Restart |

## Settings

Change with `set <key> <value>` (saved immediately), or from the app.

| Key | Default | Meaning |
|---|---|---|
| `link` | `ble` | `ble` or `wifi`. Use `link …` to switch. |
| `silent` | `0` | `1` = no sounds |
| `brightness` | `200` | Screen contrast, 0–255 |
| `volume` | `70` | Buzzer loudness, 0–100 |
| `leds` | `1` | `0` = all LEDs off |
| `sleep_sec` | `120` | Seconds before Mochi sleeps (0 = never) |
| `tz` | `UTC-5:30` | Time zone (POSIX format). The app sets it from your phone. |
| `auto_off` | `0` | Battery build: minutes idle before powering off (0 = never) |
| `bat_off` | `0` | Battery build: reading correction in mV |
| `http_en` | `1` | WiFi mode: enable `/notify` |
| `http_port` | `80` | WiFi mode: HTTP port |
| `ws_port` | `81` | WiFi mode: WebSocket port (the app expects 81) |

Settings and the WiFi network survive firmware updates. Only `deskbuddy flash --erase` resets them.
