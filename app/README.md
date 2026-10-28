# DeskBuddy C3 Android app

A small Kotlin + Jetpack Compose app that talks to DeskBuddy C3 over Bluetooth LE or WiFi, with the JSON messages in
[`../firmware/docs/PROTOCOL.md`](../firmware/docs/PROTOCOL.md). How to use it: [`../docs/phone-app.md`](../docs/phone-app.md).

> **0.6.0 (release 2.5.0):** DeskBuddy C3 only (the DeskBuddy v2 voice, weather and device-type parts are gone),
> **Update DeskBuddy** over the air with a password + BTN1, **calls** on DeskBuddy (BTN1 answers, BTN2 declines),
> and release APKs signed with one fixed key so updates install over the old app.
> The kawaii look (0.5) comes from the Figma design https://www.figma.com/design/qS3xjTV6SfNbELhLHzSix4; colours are
> in `ui/Theme.kt`, icons and Mochi's faces are vector drawables (`res/drawable/ic_*`, `face_*`), fonts Fredoka +
> Nunito (SIL OFL, see `FONTS-OFL.txt`).

## What it does

| Feature | Where |
|---|---|
| Bluetooth LE link (Nordic UART Service), or WebSocket over WiFi; reconnects with backoff | `BleLink.kt`, `DeskBuddyClient.kt` |
| Finds DeskBuddy on the LAN via mDNS (`_deskbuddy._tcp`) with **Find** | `Discovery.kt` |
| Keeps the link alive in the background as a foreground service | `LinkService.kt` |
| Forwards phone notifications | `NotifListener.kt` |
| Calls: shows them on DeskBuddy, answers / declines / hangs up from BTN1 / BTN2 | `CallBridge.kt` |
| Update DeskBuddy: GitHub release, SHA256SUMS check, password proof, chunked transfer | `OtaUpdater.kt`, `OtaLogic.kt` |
| Screens (Home, Moods, Inbox, Setup) | `ui/` |

## Build and run

1. In Android Studio, choose **File → Open**, select this `app/` folder and let Gradle sync. From a terminal:
   `./gradlew assembleDebug` (Windows: `gradlew.bat assembleDebug`) with JDK 17+, and `./gradlew testDebugUnitTest`
   for the unit tests.
2. Run it on your phone, then in the app: **Setup → Link**, and grant notification access when asked.

A build from your PC is signed with your own debug key, so it can't install over a release APK without an uninstall
(and the other way round). Release signing: [`../docs/development.md`](../docs/development.md#the-apps-signing-key).
