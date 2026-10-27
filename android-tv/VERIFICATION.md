# Android verification

Release preparation on **2026-10-26**:

| Check | Result |
| --- | --- |
| Source launcher / official distribution SHA-256 | Passed; Gradle 8.11.1 |
| Java compilation and debug APK assembly | Passed; AGP 8.9.2, JDK 17, Android SDK 35 |
| Java unit tests | 26 passed, 0 failed |
| Android lint | 0 errors; 10 style/performance warnings |
| Real Android TV / Google TV device | **Not tested** |
| Streaming playback, remote focus, HDMI, protected apps, reboot | **Not tested** |
| Alexa preview on Android | **Not integrated** |

The tests cover score changes and corrections, projection-only updates, separate league events, quiet baselines on recovery/week/season/opponent changes, strict HTTPS/token validation, starter filtering, metadata freshness, feed sizes/nesting, and a synthetic fixture generated from the shared backend. Manual preview preserves the active worker and score baseline in service code; a real remote/playback test is still required.

Build artifacts, local SDK paths, signing keys and machine-specific reports are intentionally not included. Build your own APK using the instructions in [README.md](README.md). This is build and policy evidence, not a compatibility certification or security guarantee.
