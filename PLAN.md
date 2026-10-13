# PLAN — DeskBuddy C3 hardening (2.2.1 → next release)

Started 2026-10-13. The earlier plan (repo setup → v2.0.0) is complete and lives in git history
(`git show cb63588:PLAN.md`). This file tracks the current work; checkboxes are kept current.

## Environment facts (checked 2026-10-13)

- Windows 10, Python 3.13, Node 24, PlatformIO in Python 3.13 Scripts, npm user `optimus_19` (logged in).
- `gh` CLI not installed → GitHub Actions/Releases are polled through the REST API with the token
  from Git Credential Manager (`git credential fill`), never printed.
- No `java` on PATH; JDK 21 at `%USERPROFILE%\.jdks\jbr-21.0.11-1`, JDK 25 at `D:\ANDROID_STUDIO\jbr`.
  Android SDK at `%LOCALAPPDATA%\Android\Sdk` (platforms 34, build-tools 34). Gradle 8.7 dist cached.
- C: has ~16 GB free — PlatformIO core stays where it is; big caches go to D:.
- Board: not plugged in at start (`deskbuddy ports` → none). Hardware tests run only if it appears.
- 2.2.1 zip already applied (config.h says `c3-2.2.1`, 14 modified files). No stray
  `deskbuddy-2.2.0-update/` folder. `deskbuddy-windows-fix.zip` in repo root is git-ignored (left alone).

## Decisions

- D1 The ECC `/plan` command normally waits for confirmation; the owner asked for full autonomy,
  so this plan is written down and executed without waiting.
- D2 Local gate before every commit: pytest (cov ≥ 80 %), ruff check + format, mypy (native and
  `--platform win32`), `npm test`, `pio run -e c3` and `-e c3-battery`, host tests, and the
  Android `assembleDebug` once the wrapper exists.
- D3 Next version number: decided at Phase 3 by content (fixes only → 2.2.2, features → 2.3.0).
  Decided: 2.3.0 (Change WiFi, APK in the release, wifi-setup command). Android app 0.4.0 (versionCode 4).
- D4 Change WiFi: an RTC_NOINIT flag survives the restart; the next WiFi start opens the portal at
  once (STA disconnected, credentials kept; portal timeout 3 min then the saved network again).
  Triggers: app button, BTN2 held alone at boot, `wifi setup` serial, `deskbuddy wifi-setup`.
- D5 `cmd` end detection: an `echo <marker>` line after each command (old firmware's "unknown
  command 'echo'" also ends it). Chosen over a list of silent commands: exact, fast, works with
  every firmware version.
- D6 OLED: send only changed 8x8 tiles + full repaint every 10 s (not a faster I2C clock: the
  board's weak pull-ups are why 100 kHz probing exists).
- D7 Optional Linux AppImage: skipped this release (time better spent on hardware-free checks);
  listed as a follow-up.

## Phase 1 — ship 2.2.1

- [x] 1.1 Run every local check on the applied zip; fix anything red
- [x] 1.2 Commit (Conventional Commits), push main, ci + app green
- [x] 1.3 Tag v2.2.1, release.yml green
- [x] 1.4 Verify release assets + SHA256SUMS; latest/download/DeskBuddy.exe is 2.2.1
- [x] 1.5 (owner ran it: npm needs a passkey) `npm publish`, verify fresh global install → `deskbuddy --version` = 2.2.1

## Phase 2 — bugs and lag

Firmware
- [x] 2.F1 Read all sources; loop never blocks (33 ms frame / 100 ms asleep)
- [x] 2.F2 OLED I2C clock + redraw cost
- [x] 2.F3 BLE/WiFi reconnect + link switch
- [x] 2.F4 JSON: long / emoji / Hindi text vs MAX_LINE 1536 (host tests)
- [x] 2.F5 NVS write rate
- [x] 2.F6 Watchdog safety
- [x] 2.F7 Button debounce (phantom BTN1 click)
- [x] 2.F8 Battery build paths compile and make sense

Tool / installer window / DeskBuddy.exe / npm
- [x] 2.T1 `deskbuddy cmd` exit code 8 for silent commands (TDD)
- [x] 2.T2 Reset / re-enumerate / erased / port-busy handling in flash, erase, install, monitor
- [x] 2.T3 Window never freezes (50 ms poll budget kept)
- [x] 2.T4 Startup time of DeskBuddy.exe and the npm program: measure, improve
- [x] 2.T5 Clear error messages

Android
- [x] 2.A1 Gradle wrapper (gradlew, gradlew.bat, jar) → CI builds APK, release attaches it
- [x] 2.A2 Reconnect after sleep / BT off / WiFi change; stability on both radios
- [x] 2.A3 Notification forwarding delay; nothing on the main thread
- [x] 2.A4 Permissions on Android 12–14; FGS rules for targetSdk 34; battery use

Feature
- [x] 2.W1 Change WiFi while the old network is in range (firmware command + CLI + app button + docs)

Docs
- [x] 2.D1 README, docs/*, CHANGELOG match behaviour

## Phase 3 — release

- [x] 3.1 Version bump in the 3 places (+ Android versionCode/versionName)
- [ ] 3.2 CHANGELOG, commit, push, green CI
- [ ] 3.3 Tag, release, verify assets, npm publish, verify install
- [ ] 3.4 (optional) Linux AppImage

## Log

- 2026-10-13 plan written.
- 2026-10-13 local PlatformIO core in ~/.platformio is broken (littlefs import error); builds use
  PLATFORMIO_CORE_DIR=D:\.deskbuddy\platformio (clean build ~7 min per env).
- 2026-10-13 v2.2.1 committed (4 commits), ci+app green, tag pushed, release green: 10 assets,
  SHA256SUMS match, latest/download/DeskBuddy.exe --version = "DeskBuddy 2.2.1".
- 2026-10-13 npm publish 2.2.1 → EOTP (needs the owner's passkey). Asked the owner.
- PyInstaller >= 6.9: a onefile child started from sys.executable reuses the parent's unpacked
  files (checked in the PyInstaller docs), so `--run-esptool` does not re-extract. No change needed.
- Phase 2 measurements (Windows 10, this PC): DeskBuddy.exe --version 4.1-8.2 s → 2.4-3.5 s;
  npm program --version 465 → 265 ms, ports 470 → 320 ms; python -m deskbuddy --version 760 → 470 ms.
  Firmware timing can only be measured on the board (`status` now prints it).
- Reviews (python, kotlin, cpp, security agents): fixed kick() storm + off-main-thread BLE kick,
  flush re-queue, stale port lists, whole-line end marker, spec filter assertion, STA off for the
  setup portal, stale RTC flag; pinned the Gradle distribution sha256 + wrapper validation in CI.
- Board never plugged in during the session: no hardware tests; checklist given to the owner.
