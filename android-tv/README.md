# Android TV / Google TV overlay

This is a native TV app, not a web page left open over a video. It uses Android's **Display over other apps** permission to draw the same compact score card and full matchup sidebar as the Samsung version.

**Status:** source implemented; debug APK, Java policy/parser tests and Android lint are checked during the public release process. Physical Android TV playback, remote behavior, OEM permission screens, HDMI and protected streaming apps still require device testing. Do not interpret a successful build as proof that a specific TV permits overlays.

## What it does

- Shows a top-left, five-second card after either manager's actual score changes, including scoring corrections. The initial snapshot and a new matchup establish a quiet baseline. Projection changes never trigger alerts.
- Uses person names, licensed Inter labels and button text, Bebas Neue totals, a green/red **estimated** win-chance bar and a smooth corner fade.
- Remote **OK** during an interactive popup opens the full starting lineup. **Back** closes it and releases focus. **Left/Right** switches leagues; **Up/Down** scrolls when a lineup has more than nine starters. Bench, IR and unknown lineup slots are excluded. Up to forty starters per side are supported; larger lineups are rejected instead of silently truncated.
- Highlights players whose NFL game is live, when the feed supplies confirmed live metadata. **ON TV** also requires a fresh, explicit game match in `tvContext`. It does not read your screen or guess from the current app.
- Polls an authenticated HTTPS feed every five seconds, with one request at a time. Errors clear the overlay; the first valid snapshot after an error is quiet. Manual preview retains the running score baseline.
- Includes fictional demo data that needs no account or network.

## Which televisions this can cover

Install it on an Android TV / Google TV television, or on a compatible Android TV / Google TV streaming device. An external device can overlay the apps running **on that device**. It cannot overlay an Apple TV, console or other separate HDMI input. Some streaming apps use Android's overlay-hiding protection, and some manufacturers restrict the permission or place HDMI above application overlays. Respect those restrictions; this app includes no accessibility, DRM or protected-window bypass.

Interactive overlays must receive remote focus. Some video apps may pause on focus loss. Use the **passive alerts** setting if that happens; passive popups cannot offer remote OK. This is a real platform tradeoff, so run the playback tests below before calling your device supported.

The service starts only from the visible setup app and stops cleanly. It does not request boot launch, force itself to restart, acquire a wake lock or promise operation while the TV is powered off. After a TV reboot, open Fantasy TV and start alerts again. Google Play approval for this `specialUse` foreground-service use case is not established; this project is intended for building and sideloading your own app.

## Build

Use JDK 17, Python 3.9+, Android SDK Platform 35 and Build Tools 35.0.0. Android Studio can install the SDK and lets you review and accept the SDK's terms. Set `JAVA_HOME` and `ANDROID_HOME`, or let Android Studio create an ignored `local.properties`.

```sh
cd android-tv
./gradlew --no-daemon testDebugUnitTest lintDebug assembleDebug
```

Windows: run `gradlew.bat` with Python and JDK 17 installed. The launcher is a small, auditable Python source file rather than a checked-in wrapper JAR. It downloads **Gradle 8.11.1 from its official distribution URL and verifies the pinned SHA-256 before extraction**. The first build downloads Google's Android Gradle Plugin and the pinned test libraries from Google Maven/Maven Central. Inspect `settings.gradle`, `build.gradle` and `tools/gradle.py` before running.

For an ephemeral Linux x86_64 CI runner with no Android SDK, the workflow can explicitly opt in to SDK license acceptance with `python3 android-tv/tools/install_ci_sdk.py --accept-licenses`. The helper verifies a pinned official Google command-line tools archive, installs SDK 35 and Build Tools 35.0.0 inside `RUNNER_TEMP`, and exports the SDK paths for subsequent GitHub Actions steps. It never installs a global SDK. Review Google's SDK terms before enabling that flag in your own workflow. Bootstrap archive/path/license-gate tests run with `python3 -m unittest discover -s android-tv/tools -p test_install_ci_sdk.py`.

The local APK is `app/build/outputs/apk/debug/app-debug.apk`. It is signed with your development machine's debug key, not a shared project key. Do not distribute your signing keys. Use your own release key for a distribution build; no signing credentials are included here.

To sideload, use the TV manufacturer's documented developer flow and a current Android SDK `adb` connection that you explicitly authorize on your own device:

```sh
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Do not publish an ADB port to the internet. Disconnect development access after installation.

## First run

1. Launch **Fantasy TV** from the TV's app list.
2. Keep **fictional demo data** checked. Select **Allow display over other apps** and enable the permission for Fantasy TV. If the system does not offer the permission, stop: that device needs a different supported path.
3. Select **Save and preview**. The app returns to your previous TV screen and shows the sample card. Press **OK**, then **Back**. The demo changes scores every thirty seconds while alerts are running.
4. Build your private backend using the repository's setup guide. Enter its HTTPS `/api/scores` endpoint and a dedicated feed token of 32–256 URL-safe characters. Uncheck demo mode, save and start alerts. Never use an ESPN session cookie as the TV feed token.
5. Return to your streaming app and run the acceptance checklist below.

A blank token field retains the saved token. **Erase private settings** removes all app settings and its Keystore entry. To replace a saved token, enter a new one. To revoke it, rotate the backend token as well; erasing a TV alone does not revoke a copied credential.

## Data and privacy

The feed contract is the shared normalized shape in the main repository. Important fields:

- Root `ok: true`, numeric `updated` (Unix seconds) and one to sixteen valid leagues. Source data older than 120 seconds or more than 60 seconds in the future is rejected.
- Each league has a unique `leagueId` (including provider prefixes such as `espn:123`), a week and `me`/`opp`. Each team needs its stable `teamId`, `ownerName`, numeric `score`, optional `proj`, and `players`.
- Players need an allowlisted starter `slot`, `name`, `pts` and optional `proj`. Explicit bench/reserve flags always exclude an entry. Live treatment requires `nflHighlightLive: true`, `nflGameState: "live"`, and no known unavailable status.
- A provider win probability must be a number from zero to one. Missing or invalid probabilities display **Unavailable**; the app never invents a prediction.
- Optional `tvContext` needs `available: true`, `confidence: "exact-title-pair"` or `"manual"`, a matching `matchedGameId`, and numeric `updated` no more than thirty seconds old. Without it, the app displays LIVE only.

HTTPS certificate checks use Android's system trust store. Cleartext, URL credentials, URL query strings and redirects are refused. Feed bodies are capped at 1 MiB and JSON depth at 32; text and collection sizes are bounded. Bearer tokens are encrypted with an Android Keystore AES-GCM key in private app storage. App backup and setup-page screenshots are disabled. There are no analytics, ads, screenshot readers or arbitrary network-command handlers. The service is not exported; incoming launcher intent extras are ignored.

A compromised device, an authorized feed server or someone with your feed token can still access that feed. Use a dedicated, revocable token and keep your backend private. There is no claim of absolute security.

## Acceptance checklist (per device and playback app)

Record exact model, Android TV version and app version in your own private build notes; redact account information in shared reports.

- First network snapshot is quiet. A real score change in either league opens the correct card for five seconds; a projection-only update does not.
- Picture and sound continue. OK opens the sidebar, only verified starters appear, Back closes it and the underlying app immediately receives remote keys again.
- Win percentages match the feed in both views; absent probabilities remain unavailable.
- A network error or stale source clears the overlay. Recovery establishes a quiet baseline. Stop removes both overlay and foreground service.
- All streaming apps you care about are checked separately. Built-in HDMI, protected video and external HDMI devices are separate tests.
- Permission and restart behavior is checked after a full TV reboot. Do not publish a compatibility claim before that test.

## Official platform references

- [Overlay permission and its user approval](https://developer.android.com/reference/android/Manifest.permission#SYSTEM_ALERT_WINDOW)
- [Application overlay window type and system control of its placement](https://developer.android.com/reference/android/view/WindowManager.LayoutParams#TYPE_APPLICATION_OVERLAY)
- [Foreground service types and special-use declaration](https://developer.android.com/develop/background-work/services/fgs/service-types#special-use)
- [Android 15 background-start restrictions](https://developer.android.com/about/versions/15/behavior-changes-15#fgs-launch-restrictions)
- [Apps may hide third-party overlay windows](https://developer.android.com/security/fraud-prevention/activities#hide_overlay_windows)
- [Android Gradle Plugin 8.9 compatibility](https://developer.android.com/build/releases/agp-8-9-0-release-notes)
