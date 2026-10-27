---
name: fantasy-tv-setup
description: Set up this repository's fantasy football overlay on a user's own compatible Samsung Tizen or Android TV playback device, including their own fantasy-provider feed. Use for installation, account connection and device setup; not for unrelated TV changes.
---

# Set up Fantasy TV

Find the repository root containing `AGENTS.md`. Paths below are relative to that root. Read `docs/AGENT_WALKTHROUGH.md`, `docs/PLATFORMS.md` and `docs/fantasy-providers.md` before choosing a route.

Establish two independent inputs early: the fantasy provider and the actual video playback device. A video app on Apple TV is a different target from the same app on Android TV. A compatible streamer overlays its own apps, not another HDMI source. Do not substitute an in-app scoreboard for the requested cross-app overlay.

1. Run the synthetic demo and offline checks from the root README. Then run `python3 tools/setup.py` to create a fresh ignored private configuration. ESPN and Sleeper adapters are included; other providers require a verified backend adapter.
2. Have the user enter secrets directly into hidden local prompts or their hosting provider's secret UI. Never collect cookies, token values, signing keys or pairing stores in chat. Keep ESPN session cookies server-side; a renderer receives only its separate feed token. Confirm league/team/season identities and starter rows against the user's own fantasy UI.
3. Follow the selected renderer's README. For Samsung, also read its root setup document and validate exact model/firmware support in the pinned upstream dependency before executing it. Developer Mode or TCP reachability is not authenticated SDB or root capability. Use only the chosen target and reversible staging; unsupported compatibility is a blocker to that route.
4. For Android, obtain the user's overlay permission through the TV settings if supported and start from the setup screen. Do not assume overlay permission, protected-app compatibility, focus behavior or reboot persistence across OEMs.
5. Verify the hardware behaviors in `docs/VALIDATION.md`. Observe actual playback, the five-second popup, OK, starters-only details, Back, stale-feed handling and sleep/restart behavior. Keep source, build, simulator and physical results distinct.

Ordinary setup does not authorize publishing the user's configuration or opening SDB/root callbacks to the internet. Voice and Apple TV context are optional; read `docs/OPTIONAL_INTEGRATIONS.md` when requested and create fresh per-installation keys. Public sample files must remain synthetic. Hand over clear start/stop instructions and state exactly which device must remain running.
