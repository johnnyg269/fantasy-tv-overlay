# Platform support and honest limits

The target experience is the same: a five-second score-change popup at the top-left, a corner fade, large score typography, manager names, a green/red win-chance bar, and a remote-operated starter matchup sidebar. Availability of a system overlay is determined by the TV operating system and playback path.

| Playback path | Included route | Status and limits |
| --- | --- | --- |
| Compatible Samsung Tizen TV, including an HDMI source | Native Tizen compositor renderer and local companion | Derived from a physically verified Tizen 9 development setup over HDMI. Root compatibility is model and firmware specific. A different device, firmware, built-in app and reboot recovery each require verification. |
| Android TV / Google TV apps on that TV | Android system overlay service | Source implementation with Android's overlay permission. Physical device and app acceptance testing is required. Some devices do not expose the permission, and some apps suppress overlays. |
| Apps on a compatible external Android TV / Google TV streamer | Same Android service on the streamer | Only the streamer's composed picture can contain the overlay. The TV may be any brand with a compatible HDMI input, but the Android device and video app must support the required behavior. |
| Apple TV or console connected to a generic TV | No standalone tvOS/console renderer | A streamer cannot draw over another device's HDMI signal. The included Samsung path can draw over HDMI on the compatible TV itself. |
| Roku, LG webOS, ordinary TVs without a compatible renderer | No native renderer included | Use a supported playback device and its apps, or develop and verify another platform adapter. An in-app web scoreboard does not satisfy the cross-app target. |

“Any TV” therefore means a supported playback route on many TV brands, not a guarantee that arbitrary TV inputs and apps can be composited by this repository. External HDMI hardware compositors are outside the project.

The current Samsung layout supports up to two selected leagues and nine starters per side; larger configurations must be rejected rather than silently truncated. Android supports more rows with scrolling, within its documented parser/layout limits. Choose the leagues and lineup profile before device setup; unusual IDP or large rosters may need a deliberate layout extension. The shared backend currently accepts up to four leagues, which does not expand the Samsung layout's limit.

## Android platform boundaries

The app uses `SYSTEM_ALERT_WINDOW` and checks whether the user granted overlay access. Android documents this as special permission for windows over other apps. Device settings and OEM policy may restrict it. [Android permission reference](https://developer.android.com/reference/android/Manifest.permission#SYSTEM_ALERT_WINDOW)

Apps can ask Android to hide third-party overlays. Protected video apps and OEM implementations must be tested directly; the project does not bypass that restriction. [Android overlay-hiding guidance](https://developer.android.com/security/fraud-prevention/activities#hide_overlay_windows)

The long-lived overlay service uses the `specialUse` foreground-service category with a declared purpose. It starts from the visible setup screen. Publishing through Google Play may require declaration and review. It is not implemented as an unlimited `dataSync` worker. [Android foreground service types](https://developer.android.com/develop/background-work/services/fgs/service-types#special-use)

Android background-start rules also apply; overlay permission alone does not guarantee unattended service startup. No boot recovery guarantee is made. [Android 15 service-start restrictions](https://developer.android.com/about/versions/15/behavior-changes-15#fgs-launch-restrictions)

Remote focus can affect the foreground app. Verify that popup interaction, expanded details and Back leave playback working for every video app you intend to use.

## Samsung platform boundaries

The ordinary Tizen web-app permission model does not grant arbitrary system overlays over other apps and HDMI. This renderer relies on a native compositor path plus temporary root obtained through a separate, compatible tool. Developer Mode and an open SDB port alone do not prove root capability.

The included setup must identify the exact TV and firmware, inspect the upstream compatibility documentation and establish authenticated capability. Do not apply a recipe for a similarly named model. Stop at unsupported firmware rather than attempting unrelated exploits or disabling trust checks.

The root method is an external dependency, not a guarantee by Fantasy TV. Follow its license, scope and prerequisites. See [Samsung instructions](../samsung/README.md).
