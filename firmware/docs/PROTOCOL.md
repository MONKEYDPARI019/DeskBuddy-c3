# DeskBuddy C3 protocol

The same JSON messages as DeskBuddy v2, so one Android app drives both. They travel over one of two links:

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
| `power_off` | | deep sleep (battery build only, otherwise `error`) |

`ptt`, `think`, `say_*` reply `error` (no mic or speaker on the C3). `set owm_city` is ignored quietly.

## Device → app

| type | fields |
|---|---|
| `hello` | `device`, `model: "c3"`, `fw`, `link`, `mic: false`, `screens` |
| `state` | `face`, `mood`, `shown`, `screen`, `unread`, `notifs`, `silent`, `volume`, `bright`, `sleep`, `auto_off`, `leds`, `link`, `bat` (−1 = none), `bat_mv`, `mic`, `rssi`, `ip`, `time_ok`, `uptime`, `fw`, `model` |
| `button` | `btn` (1/2), `action`: `click`, `long`, `power` |
| `link_switch` | `link`, `restart_ms` |
| `error` | `msg` |

`state` is sent shortly after every change and every 15 s while an app is connected.

## Settings (`set` keys)

`tz`, `link`, `silent`, `brightness` (0–255), `volume` (0–100), `leds`, `sleep_sec` (0 = never), `auto_off` (minutes, battery build), `bat_off` (mV calibration), `http_en`, `http_port`, `ws_port`.

## HTTP (WiFi mode)

`GET /notify?app=WhatsApp&title=Mom&msg=Dinner` shows a notification. `GET /` returns a small status JSON.
