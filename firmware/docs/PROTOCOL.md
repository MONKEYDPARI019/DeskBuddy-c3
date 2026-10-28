# DeskBuddy C3 protocol

JSON messages between DeskBuddy C3 and the Android app. They travel over one of two links:

- **Bluetooth LE** (default): Nordic UART Service. Each message is one JSON object followed by `\n`, sent in pieces of (MTU − 3) bytes. Enable notifications on TX before sending `hello`.
- **WiFi**: WebSocket text frames at `ws://deskbuddy-c3.local:81/`, one message per frame. The device announces `_deskbuddy._tcp` over mDNS.

| | UUID |
|---|---|
| Service | `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` |
| RX (app writes) | `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` |
| TX (device notifies) | `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` |

Lines longer than 1536 bytes are dropped.

## App → device

| type | fields | effect |
|---|---|---|
| `hello` | `name` | replies `hello`, then `state` |
| `ping` | | replies `pong` |
| `get` | | replies `state` |
| `time` | `epoch` (UTC s), `tz_min` (e.g. 330) or `tz` (POSIX) | sets the clock (the app sends it on every connect) |
| `notify` | `app`, `title`, `body` (UTF-8; shown as ASCII) | stores + shows a notification |
| `face` | `name`: a mood, a state, or `sleep` | changes Mochi |
| `screen` | `name`: `clock`, `mochi`, `notify`, `next` | changes screen |
| `sound` | `name` | plays a chirp |
| `set` | `key`, `value`, `save` (default true) | changes a setting; `link` = `wifi`/`ble` switches radio and restarts |
| `clear` | | 2.3.1+: clears all notifications, exactly like a long BTN2 press ("Cleared" message and sound, also while Mochi sleeps); replies `state` (`notifs: 0`, `unread: 0`) |
| `wifi_setup` | | 2.3.0+: replies `wifi_setup` (`ap`, `restart_ms`), then restarts in WiFi mode with the setup portal open |
| `power_off` | | deep sleep (battery build only, otherwise `error`) |
| `call` | `state`: `ringing`, `active`, `ended`; `name`, `app`, `id` | 2.5.0+: shows a phone call. While ringing: BTN1 answers, BTN2 declines (sent back as `call_action`). Active: BTN1 hides the call screen, BTN2 hangs up. |
| `ota_nonce` | | 2.5.0+: replies `ota_challenge` |
| `ota_begin` | `size`, `sha256` (hex), `version`, `proof` | 2.5.0+: asks to update; see [Updates from the app](#updates-from-the-app) |
| `ota_data` | `seq` (0, 1, 2...), `data` (base64, up to `chunk` bytes) | one piece of the image; replies `ota_ack` |
| `ota_end` | | all sent: replies `ota_done` and restarts into the new firmware, or `ota_error` |
| `ota_abort` | | stops an update; the old firmware keeps running |
| `ota_pass` | `key` (hex), `proof` (only when changing) | sets or changes the update password |

`ptt`, `think`, `say_*` reply `error` (no mic or speaker on the C3). `set owm_city` is ignored quietly.

**Compatibility:** firmware older than the version in the table replies `{"type":"error","msg":"unknown type"}` to a message it doesn't know. The app reads `fw` from `hello`/`state` and only sends `clear` to `c3-2.3.1` or newer; older apps never send it.

## Device → app

| type | fields |
|---|---|
| `hello` | `device`, `model: "c3"`, `fw`, `build` (`usb`/`battery`, 2.5.0+), `ota_pass` (2.5.0+), `link`, `mic: false`, `screens` |
| `state` | `face`, `mood`, `shown`, `screen`, `unread`, `notifs`, `silent`, `volume`, `bright`, `sleep`, `auto_off`, `leds`, `link`, `bat` (−1 = none), `bat_mv`, `mic`, `rssi`, `ip`, `time_ok`, `uptime`, `fw`, `model`, `build`, `ota_pass` |
| `call_action` | `action`: `answer`, `decline`, `hangup`; `id` of the call (2.5.0+) |
| `ota_challenge` | `nonce` (32 hex), `pass_set`, `locked` (seconds), `build`, `fw` |
| `ota_confirm` | `timeout` (s): DeskBuddy is asking for BTN1 |
| `ota_ready` | `chunk` (bytes per `ota_data`): BTN1 pressed, send the image |
| `ota_ack` | `seq`, `got` (bytes so far) |
| `ota_done` | `restart_ms` |
| `ota_pass_ok` | the password was saved |
| `ota_error` | `code`, `msg`, `left` (tries, for `bad_password`), `wait` (s, while locked) |
| `button` | `btn` (1/2), `action`: `click`, `long`, `power` |
| `link_switch` | `link`, `restart_ms` |
| `wifi_setup` | `ap`, `restart_ms` |
| `error` | `msg` |

`state` is sent shortly after every change and every 15 s while an app is connected. `notifs` is the number of notifications DeskBuddy holds; when it drops to 0 (long BTN2, or `clear`) the app clears its own list too.

## Settings (`set` keys)

`tz`, `link`, `silent`, `brightness` (0–255), `volume` (0–100), `leds`, `sleep_sec` (0 = never), `auto_off` (minutes, battery build), `bat_off` (mV calibration), `http_en`, `http_port`, `ws_port`.

## HTTP (WiFi mode)

`GET /notify?app=WhatsApp&title=Mom&msg=Dinner` shows a notification. `GET /` returns a small status JSON.

## Updates from the app

2.5.0+. The firmware arrives as normal messages over the same link (Bluetooth or WiFi); ArduinoOTA and the
`pio run -e ota` upload are gone. The rules are in `firmware/src/logic/ota_core.h` (unit-tested), the app side in
`OtaUpdater.kt` / `OtaLogic.kt`.

**Password.** DeskBuddy stores only `K = SHA-256("deskbuddy-ota:" + password)` (NVS namespace `dbc3ota`). The
password itself never travels: every request carries `proof = HMAC-SHA256(K, nonce ‖ purpose ‖ detail)` in hex,
where `nonce` is the 16 random bytes from the last `ota_challenge` (used once, valid 60 s).

| Request | purpose | detail |
|---|---|---|
| `ota_begin` | `update:` | the image's `sha256` as sent (so the proof also vouches for the image) |
| `ota_pass` (change) | `pass:` | the `key` as sent |

- **First password:** `ota_pass` with `key` = K in hex and no proof. DeskBuddy asks for BTN1 (`ota_confirm`), then
  replies `ota_pass_ok`. Over USB: `otapass set <password>`.
- **Change:** `key` = new K xor `HMAC-SHA256(old K, nonce ‖ "mask")` in hex, `proof` made with the old K. No button.
- **Forgot it:** `otapass clear` over USB (physical access), then set a new one.
- 3 wrong proofs in a row lock updates for 60 s (`locked`).

**An update:**
1. `ota_nonce` → `ota_challenge`.
2. `ota_begin` (`size` ≤ the update slot, 1.9 MB) → `ota_confirm`. DeskBuddy shows "Update DeskBuddy?": BTN1 yes,
   BTN2 no, 30 s.
3. BTN1 → `ota_ready {chunk: 1024}`.
4. `ota_data` with `seq` 0, 1, 2... in order; each is answered by `ota_ack`. The app keeps at most 2 unanswered
   (the inbox holds 4 messages). Over Bluetooth the app uses writes without response for these, and both sides ask for
   a 7.5–15 ms connection interval.
5. `ota_end` → DeskBuddy checks the size and the SHA-256, lets the IDF check the image, replies `ota_done` and
   restarts 1.5 s later.

Any `ota_error`, `ota_abort`, a long BTN2, the phone disconnecting or 20 s without a chunk throw the partial image
away; the old firmware keeps running. Images for this are published with each release as
`deskbuddy-c3-ota-<usb|battery>-vX.Y.Z.bin` (the app-only image, listed in `SHA256SUMS` and in `manifest.json` under
`ota_images`). The app picks the one for the `build` DeskBuddy reports.
