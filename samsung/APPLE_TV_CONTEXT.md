# Optional Apple TV program metadata

This adds the current program title and an **ON TV** marker when an eligible live starter's NFL game uniquely matches a fresh title. It does not tune channels, capture protected video, send playback/power commands or infer the game from a channel alone. The feature is optional: a missing title or pairing does not interrupt fantasy scores.

The native Samsung overlay still covers HDMI; this metadata worker runs privately on the home companion. It does not turn an ordinary Apple TV into a cross-app overlay platform.

## Set up your own pairing

Use a separate Python 3.12 environment for the optional `pyatv==0.18.0` dependency. From the repository root:

```sh
python3.12 -m venv samsung/.local/apple-tv-venv
samsung/.local/apple-tv-venv/bin/python -m pip install pyatv==0.18.0
```

Wake the Apple TV yourself and read its current LAN address and exact device name. Run the deliberate pairing helper in an **interactive terminal**:

```sh
samsung/.local/apple-tv-venv/bin/python samsung/pair_apple_tv.py \
  --host "$APPLE_TV_IP" --name "$APPLE_TV_NAME" --allow-pairing
```

The helper starts one AirPlay pairing flow. Enter the four-digit PIN from the Apple TV into the terminal's hidden prompt yourself. Do not send the PIN or credentials into a public issue, chat transcript or repository. A headless/non-interactive invocation refuses to echo the PIN as a fallback.

Only a confirmed pairing is saved. Credentials go to ignored `samsung/.local/apple-tv-storage.json` (0600), and the selected host/name go to `samsung/.local/apple-tv.json` (0600). The private directory is 0700. An existing configuration naming a different device is not silently replaced. No credential values are printed; protocol debug logging is disabled. No app is launched and no channel is changed.

The ordinary `run_tv.py` watch starts the optional worker when these files and its private runtime exist. Use `--no-tv-context` to disable it. Pairing is never triggered automatically by the watch runner.

## Behavior and limits

The worker makes one AirPlay-only multicast discovery and one authenticated cached-metadata connection for an explicitly active watching session. It rejects reported deep sleep, stops on an Off event or disconnect, clears its cache and never reconnects automatically. Unicast scanning is deliberately avoided because pyatv's unicast scanner sends TCP wake traffic.

This is not a guaranteed wake-free presence detector: shallow sleep and missing power events cannot always be recognized. Connection setup and protocol heartbeats still use the network. Start it only when you intend to watch that Apple TV.

The current app and title are sampled from cached metadata every ten seconds and on push updates. Idle, stopped and loading clear the title; paused metadata is allowed because some TV apps report that state during normal playback. App-reported metadata can be absent or can differ from the foreground app.

Public ESPN NFL scoreboard metadata is requested separately at most once per thirty seconds. Only an unambiguous two-team title match against a scoreboard no older than sixty seconds yields a game ID. Generic titles, channels, RedZone and multiview do not imply a game. A title match does not prove live video timing or that a specific athlete is on the field. **LIVE** means the athlete's game is in progress, with known inactive/out status excluded.

The private cache is atomically replaced with mode 0600. Stale, malformed, future-dated, off/disconnected and unavailable cache entries clear the ON TV marker. Private provider content identifiers stay in the worker's local cache and are not passed to the TV renderer or interpreted as watch URLs.

Provider-to-game switching is not part of this public release. A matching title, installed app or acknowledged app launch does not establish a working direct-to-game link.

## Optional offline checks

```sh
samsung/.local/apple-tv-venv/bin/python -m unittest discover -s samsung/optional_tests
```

These checks mock pairing/discovery and verify private storage; they do not contact a device. The regular Samsung tests also cover stale metadata, title matching, worker shutdown and the separation between program metadata and fantasy score-change events.

References: [pyatv pairing and storage](https://pyatv.dev/documentation/pairing/), [pyatv metadata/power interfaces](https://pyatv.dev/api/interface/), [pyatv wake behavior and missing metadata](https://pyatv.dev/support/faq/).
