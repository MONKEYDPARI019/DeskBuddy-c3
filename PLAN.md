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

## Phase 1 — ship 2.2.1

- [ ] 1.1 Run every local check on the applied zip; fix anything red
- [ ] 1.2 Commit (Conventional Commits), push main, ci + app green
- [ ] 1.3 Tag v2.2.1, release.yml green
- [ ] 1.4 Verify release assets + SHA256SUMS; latest/download/DeskBuddy.exe is 2.2.1
- [ ] 1.5 `npm publish`, verify fresh global install → `deskbuddy --version` = 2.2.1

## Phase 2 — bugs and lag

Firmware
- [ ] 2.F1 Read all sources; loop never blocks (33 ms frame / 100 ms asleep)
- [ ] 2.F2 OLED I2C clock + redraw cost
- [ ] 2.F3 BLE/WiFi reconnect + link switch
- [ ] 2.F4 JSON: long / emoji / Hindi text vs MAX_LINE 1536 (host tests)
- [ ] 2.F5 NVS write rate
- [ ] 2.F6 Watchdog safety
- [ ] 2.F7 Button debounce (phantom BTN1 click)
- [ ] 2.F8 Battery build paths compile and make sense

Tool / installer window / DeskBuddy.exe / npm
- [ ] 2.T1 `deskbuddy cmd` exit code 8 for silent commands (TDD)
- [ ] 2.T2 Reset / re-enumerate / erased / port-busy handling in flash, erase, install, monitor
- [ ] 2.T3 Window never freezes (50 ms poll budget kept)
- [ ] 2.T4 Startup time of DeskBuddy.exe and the npm program: measure, improve
- [ ] 2.T5 Clear error messages

Android
- [ ] 2.A1 Gradle wrapper (gradlew, gradlew.bat, jar) → CI builds APK, release attaches it
- [ ] 2.A2 Reconnect after sleep / BT off / WiFi change; stability on both radios
- [ ] 2.A3 Notification forwarding delay; nothing on the main thread
- [ ] 2.A4 Permissions on Android 12–14; FGS rules for targetSdk 34; battery use

Feature
- [ ] 2.W1 Change WiFi while the old network is in range (firmware command + CLI + app button + docs)

Docs
- [ ] 2.D1 README, docs/*, CHANGELOG match behaviour

## Phase 3 — release

- [ ] 3.1 Version bump in the 3 places (+ Android versionCode/versionName)
- [ ] 3.2 CHANGELOG, commit, push, green CI
- [ ] 3.3 Tag, release, verify assets, npm publish, verify install
- [ ] 3.4 (optional) Linux AppImage

## Log

- 2026-10-13 plan written.
