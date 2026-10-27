# Build your own Fantasy TV

Fantasy TV shows fantasy football score changes in a five-second corner popup. Remote OK opens a translucent matchup sidebar with starting players, scores, projections and available win percentages. Back returns to the picture. Your league data and device configuration belong to your installation.

Start with the synthetic demo. It requires no ESPN account, TV pairing or public endpoint. Then choose a TV path before entering private account details.

## Let Codex guide the setup

Clone this repository into a new folder and give your Codex agent this prompt:

> Read AGENTS.md, docs/AGENT_WALKTHROUGH.md and the fantasy-tv-setup skill in .agents/skills/. Help me build my own Fantasy TV installation. Start with the synthetic demo. Check which fantasy provider, TV platform and playback device I use before choosing adapters. Keep credentials in ignored local configuration; do not ask me to paste them into chat. Verify actual overlays and remote controls on my device before calling setup complete.

Repo-local skills are included in `.agents/skills/`; the walkthrough remains usable if your agent does not discover that folder automatically. No paid Codex plugin is required by this project.

## Choose a path

Read [the platform matrix](PLATFORMS.md). A scoreboard displayed inside an app is different from an overlay over the app you are watching. The Samsung and Android renderers target the latter experience, subject to their platform requirements.

- **Compatible Samsung Tizen:** the native renderer uses temporary root access and a local companion. Exact model and firmware compatibility must be established before any root operation. See [Samsung setup](../samsung/README.md) and [the root-access walkthrough](../samsung/ROOT_SETUP.md).
- **Android TV / Google TV:** build the Android app and grant its system overlay permission if your TV offers it. The service runs on the device playing the video. See [Android setup](../android-tv/README.md).
- **Other TVs:** a compatible Android TV / Google TV streamer can provide this experience for video apps running on that streamer. It does not overlay another HDMI input, a console or the TV's own apps. No universal software-only solution is included.

## Connect your own scores

The backend adapts your selected ESPN or Sleeper leagues to the shared score format. Follow the complete [fantasy provider guide](fantasy-providers.md) to identify your league, team, season and required access. It also explains how your agent can add Yahoo or another provider through the same contract. ESPN access is unofficial and may change. Private ESPN leagues require your own session credentials; the backend keeps them server-side. The renderer uses a separate feed token. Read [privacy and security](SECURITY_AND_PRIVACY.md) before making the feed reachable outside your computer.

Use the same scores endpoint with either renderer. Never point a new installation at someone else's deployment. Do not put session cookies, feed tokens or manager names in a public repository.

## Verify the experience

Use [the acceptance checklist](VALIDATION.md) with the actual TV and video app. In particular, verify that the popup appears over uninterrupted playback, that OK opens the starters-only sidebar and that Back closes it. Source tests and a successful build do not establish those hardware behaviors.

Voice control and Apple TV metadata are optional. Establish the ordinary score overlay first; see [optional integrations](OPTIONAL_INTEGRATIONS.md).
