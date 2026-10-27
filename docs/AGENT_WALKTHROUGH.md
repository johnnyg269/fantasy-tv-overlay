# A walkthrough for your Codex agent

Use this document with `AGENTS.md` and the repo-local [setup skill](../.agents/skills/fantasy-tv-setup/SKILL.md). Work in the user's clone; do not search for or reuse the original developer's personal files, endpoints or device credentials.

## 1. Establish the provider and playback path

Ask which fantasy provider and league the user wants, then follow [the provider guide](fantasy-providers.md). ESPN and Sleeper adapters are included; Yahoo and other apps require a verified adapter. Use an existing account. Establish the chosen team's scores and lineup before root or TV pairing. Check the renderer's league/lineup capacity too: the current Samsung profile supports two selected leagues and nine starters per side; never drop additional starters silently.

Ask for or discover the TV platform, exact model/firmware and the device that runs the video app. “YouTube TV” alone is insufficient: it may run on Android TV, Samsung or Apple TV. Use [the support matrix](PLATFORMS.md) to select a viable renderer.

Keep the user's desired experience: an overlay over the current video, not a replacement launcher or a full-screen scoreboard. Explain the platform limit before the user enters credentials or buys hardware. If a route is unsupported, state the missing capability clearly.

## 2. Run a synthetic installation first

Follow the root README's demo commands. Inspect synthetic fixtures and the shared schema. Build the selected renderer and run its offline checks. No real league credentials, household IDs, TV pairing or public endpoint are needed to establish that the source builds and the UI consumes the contract.

Confirm that the demo changes actual scores. A static screenshot cannot prove the five-second alert, quiet initial baseline or score-correction behavior.

## 3. Create private configuration

Use the provided setup tooling and ignored local paths. Let the user enter session credentials directly in a local terminal, private settings UI or hosting-provider secret interface. Avoid command-line secret arguments where process history could retain them. Do not request cookie values, feed tokens, signing keys or pairing databases in chat.

Create new random feed and voice keys for each installation. Keep ESPN credentials on the backend; only the separate read token goes to a renderer. Use a private owner-name mapping if needed. Do not derive identity from fantasy team nicknames.

Before publishing any configuration or diagnostic bundle, inspect its exact files and Git history. `.gitignore` does not remove files already tracked or present in an earlier commit.

## 4. Connect the renderer

For Samsung, read [Samsung setup](../samsung/README.md) and [the root-access walkthrough](../samsung/ROOT_SETUP.md). Establish exact model and firmware compatibility with the external root dependency before running it. Confirm SDB authentication and authenticated root capability; an open TCP port is not sufficient. Keep staging reversible and do not change firmware or system files to make an unsupported model fit.

For Android, read [Android setup](../android-tv/README.md). Install the app on the actual playback device, grant overlay access through its settings if supported, and start it from the visible setup screen. Confirm foreground-service behavior and remote focus. Do not use accessibility automation or key injection to work around apps that suppress overlays.

Use a reachable HTTPS feed with the install's own token. A loopback demo endpoint is reachable only from the same computer; the TV's `localhost` is the TV itself. Set up a private network or HTTPS hosting for device testing according to the user’s chosen route.

## 5. Test actual video and controls

Complete [the acceptance checklist](VALIDATION.md) on hardware. Record the TV model, firmware, playback device and video app privately. Keep public evidence synthetic or redact it carefully. Distinguish source checks, successful build, simulator results and physical acceptance.

If the popup appears but OK pauses video or Back exits the video app, the platform integration is incomplete. If a panel only appears inside Fantasy TV, it is not a verified cross-app overlay.

## 6. Add optional integrations

Read [optional integrations](OPTIONAL_INTEGRATIONS.md) only when needed. Alexa introduces a public request boundary and a signing key; Apple TV context introduces pairing credentials. Establish ordinary overlay behavior first. Do not expose the SDK, SDB, root callback or a general control endpoint to the internet.

Player-to-game tuning is intentionally unavailable until a provider-specific route can be physically proven. An app-launch acknowledgment or browser watch URL does not prove channel tuning on a TV device.

## 7. Hand over truthful operation instructions

Explain which device must remain running, how to start and stop, how stale data behaves, and what happens after sleep or reboot. Check the selected renderer’s actual recovery behavior rather than assuming a successful initial launch will persist.

List what was verified and what remains untested. Do not label an installation universal, always-on, fully secure or complete without evidence for those claims.
