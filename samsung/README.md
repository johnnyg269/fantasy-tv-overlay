# Samsung Tizen overlay

This is the native EFL overlay and visible home companion. The design fades from the top-left corner, shows a five-second popup when either matchup's total changes, and opens a starters-only sidebar with Samsung **OK**. **Back** closes it; left/right switch leagues. Person labels come from your own private score feed. Win chance is displayed only when the feed supplies a valid estimate.

An earlier private build was physically validated over Apple TV/HDMI on one Samsung DU8000 model running Tizen 9 and .NET 6. This public version removes that household's configuration and adds setup/security checks. The generalized public build has not been physically validated on other televisions. Built-in Samsung app playback, cold-boot recovery and different firmware require your own checks.

## What you need

- A Samsung TV whose exact model/firmware supports the upstream temporary-root route and the required EFL compositor APIs.
- Developer Mode, a working SDB connection, and a home companion on the same trusted LAN. An open TCP port alone is insufficient.
- macOS or Linux, Python 3.9+, OpenSSL, and Samsung's SDB from the official [Tizen Studio tools](https://developer.tizen.org/development/tizen-studio/download). Native Windows companion operation is not packaged.
- A local .NET 6 SDK build environment, compatible with the .NET runtime on your own TV. This source does not bundle Samsung libraries, firmware or a runtime. .NET 6 is required by the tested TV runtime; it is a legacy development dependency, not a recommendation for a public web service.
- Your own authenticated HTTPS feed. [The repository backend](../backend/) supports a synthetic local demo before you add any account data.

The v0.1 Samsung layout supports **one or two leagues and at most nine starters per side**. A larger lineup/feed is explicitly rejected; it is never silently presented as a full matchup with missing starters. Android's independently implemented layout has its own documented limits.

## Setup

Start with [ROOT_SETUP.md](ROOT_SETUP.md). It covers inventory, Developer Mode, pinned upstream tooling, the explicit root probe, cleanup evidence and staging. Do not skip it or substitute a different owner's IP, firmware declaration or receipt.

Once that guide has verified root, built the renderer and staged its files, start from the repository root:

```sh
python3 samsung/run_tv.py \
  --tv "$TV_IP" --callback-host "$HOST_IP" \
  --model "$TV_MODEL" --firmware "$TV_FIRMWARE" \
  --sdb "$SDB" --root-tool "$ROOT_TOOL" --sdb-module "$SDB_MODULE" \
  --root-receipt samsung/.local/root-probe.json \
  --endpoint "$FANTASY_ENDPOINT" --acknowledge-root-risk --watch --preview
```

The repository also provides `python3 tools/run_samsung.py` to read your own backend configuration and feed token without putting that token on a command line or in logs; see its `--help` for device/setup arguments.

Set `FANTASY_FEED_TOKEN` privately in the host environment. The token is sent in an Authorization header; URL tokens, HTTP over the LAN, redirects, missing credentials and oversized responses are rejected. No household endpoint is supplied by this repository. Use `--allow-loopback-http` only for the synthetic demo at an explicit numeric loopback address on this same companion.

NFL game status is also scoped to the matchup's exact `seasonId` and `week`. Historical, missing-scope, ambiguous or non-regular-season scoreboard entries never acquire a current-game LIVE marker. The worker cache includes that scope so matching player names cannot carry live status into another week.

The initial fresh fetch establishes a quiet baseline. Actual score increases and stat corrections trigger alerts. Projection, metadata and heartbeat updates do not. If two leagues change together, each receives its own five-second popup. A new week, opponent or league identity establishes a new baseline.

The companion uses one transport connection at a time, renews bounded renderer sessions, and retries only the address you entered. It does not install a hidden host service. Keep the companion awake and visible; a Vercel-hosted feed alone does not keep the local TV renderer alive. State is hidden after thirty seconds without a host heartbeat. `--watch` does not prove unattended recovery after a TV reboot.

## Remote and stopping

- **OK** while the popup is visible opens the full sidebar.
- **Back** dismisses the sidebar and returns keys to playback.
- **Left/right** switch the selected league. Up/down also switch leagues in this version.
- In the companion window, `preview` shows current scores for five seconds; `auto` returns to score-change-only alerts.
- Type `quit`, press Ctrl-C, or run `python3 samsung/send_control.py quit` from a separate terminal to stop cleanly.

Validate that video, audio, volume and app navigation continue on the exact HDMI/app path you use. Do not report a visual pass merely because a process started.

## Optional features

- [Apple TV program metadata](APPLE_TV_CONTEXT.md) adds **ON TV** only for an unambiguous fresh two-team title match. It does not tune channels or identify an athlete currently on the field.
- [Private Alexa skill and signed preview relay](alexa_bridge/README.md) can request the five-second popup using your own Echo, skill, endpoint and freshly generated key.
- An optional private `samsung/.local/owner_names.json` can override labels by exact league/team ID. Backend person labels are preserved without it. See `owner_names.py` for its season-scoped schema. Never commit that file.

## Offline checks

From the repository root:

```sh
python3 -m unittest discover -s samsung -p 'test_*.py'
dotnet run --project samsung/checks/AlertPolicyChecks.csproj --configuration Release
```

These checks exercise synthetic score changes, stale data, bench exclusion, owner labels, scene bounds, typography, popup expiry, interaction policy, fixed root-command scope, feed transport and setup guardrails. They do not contact or drive a TV. Build outputs, logs and all device-specific material belong under ignored `.local/`, `bin/` or `obj/` folders.
