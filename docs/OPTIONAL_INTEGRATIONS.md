# Optional integrations

First establish ordinary score-change alerts and remote controls on your own TV. These integrations add separate private credentials and additional services; neither is necessary to display the basic overlay.

## Alexa preview request

The included Samsung companion has an optional private voice bridge. Its route is a private Alexa skill → authenticated HTTPS preview endpoint → loopback relay → companion preview. Consult `samsung/alexa_bridge/README.md` for the actual files and setup commands.

Create your own skill and fresh signing key. The account/skill identifiers in your generated configuration are private. A locally prepared skill upload ZIP contains a secret; never commit or attach it to an issue.

Use the skill's explicit invocation first. Once a spoken request has been physically verified, add an Alexa Routine with a phrase such as “fantasy update” and a custom action invoking your private skill. The skill response means a preview request was delivered or queued according to the relay; only an observed TV popup confirms display.

The bridge is an optional Samsung companion integration. Android voice dispatch is not claimed as implemented unless an Android-specific receiving path is added and verified. Do not route a public request to an Android exported component without authentication.

The local companion and relay must be awake and connected. Hosting the skill in the cloud does not keep the home renderer running. HTTPS ingress should expose only the signed preview route, not a general control API, SDB or root callbacks.

Primary references: [Alexa-hosted skill creation](https://developer.amazon.com/en-US/docs/alexa/hosted-skills/alexa-hosted-skills-create.html), [development skill testing](https://www.developer.amazon.com/en-US/docs/alexa/test/test-your-skill-overview.html), [Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel).

## Apple TV Now Playing context

The Samsung companion can optionally observe a paired Apple TV's Now Playing title while that Apple TV is being watched. See `samsung/APPLE_TV_CONTEXT.md`. Use the included helper's own setup path and keep its pairing store in ignored local storage. It should read metadata, not change playback, power, apps or channels.

Fresh, unambiguous titles identifying both NFL teams can support `ON TV` labels for that game. App support varies. Generic titles, RedZone, multiview, stale metadata or unavailable titles should produce no game match. `ON TV` is metadata-based context, not visual recognition or a guarantee that a particular athlete is on the field.

The observer stops on sleep/disconnect and may need a new viewing session. Do not repeatedly wake or reconnect to a sleeping device to obtain a label. Android's current renderer does not automatically gain Apple TV metadata from running on a different device.

Primary references: [pyatv supported features](https://pyatv.dev/documentation/supported_features/), [pyatv wake/sleep and metadata FAQ](https://pyatv.dev/support/faq/).

## Player-to-game switching

Automatic channel/game tuning is not included. A video-provider web URL or successful app launch does not prove it can tune a live game on a TV device. Any future implementation must use a provider-supported route, verify the exact game and preserve clear user control. Keep it disabled until physical testing establishes the full behavior.
