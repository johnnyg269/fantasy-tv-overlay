# Get temporary root on your own Samsung TV

This guide connects the fantasy overlay to the public **samsung-tv-root** project. Root tooling is a prerequisite because a normal retail Tizen web app cannot supply this project's compositor overlay over another app or HDMI. Developer Mode alone does not grant that capability.

The original overlay was physically demonstrated on `UN85DU8000CXZA`, Tizen 9, firmware `T-NKM2DAKUC-0090-2123.9`, using the generic archive route and the TV's .NET 6 runtime. That is one historical compatibility record, not a Samsung-wide guarantee. Other exact models, regional variants and firmware need their own evidence. Check [upstream compatibility and limitations](https://github.com/chris-ritsen/samsung-tv-root/tree/v0.0.12#what-works) before running a probe.

`archive-root probe` **performs temporary root acquisition and cleanup**. It is not a read-only network or compatibility check. Only target a TV you own or are authorized to modify. Neither this guide nor the companion flashes firmware, changes Home/startup, replaces `/etc/passwd`, replaces Samsung's verification key, disables updates or installs a persistent root service.

## 1. Record the actual device first

Read **Settings → Support → About This TV** and record the complete model and firmware in your ignored local notes. Firmware supplied to the runner is your declaration from that screen; the runner does not claim to independently read it. The model is independently checked against SDB.

Identify the TV's current IPv4 address and this companion computer's current IPv4 address from their network settings. Use only that TV's address; do not scan a household or reuse an example address. Keep both devices on a trusted home LAN with client isolation disabled if that would otherwise block their direct connection.

Use your own values in the terminal session:

```sh
export TV_IP='YOUR_TV_IPV4'
export HOST_IP='YOUR_COMPANION_IPV4'
export TV_MODEL='YOUR_COMPLETE_MODEL'
export TV_FIRMWARE='YOUR_COMPLETE_FIRMWARE'
export SDB='/absolute/path/to/tizen-studio/tools/sdb'
```

The words above are placeholders, not usable defaults. Nothing should be sent to a TV until they have been replaced with its actual values.

## 2. Enable Developer Mode and verify SDB

Open the Samsung **Apps** screen, enter the Developer Mode sequence supported by your TV/remote (commonly `1 2 3 4 5`), enable Developer Mode and enter **this companion's HOST_IP** in **Host PC IP**. Fully restart the TV once. If Developer Mode was already enabled for a different computer, update that address first and restart.

Install SDB through the official [Tizen Studio tools](https://developer.tizen.org/development/tizen-studio/download), not an anonymous binary mirror. Then:

```sh
"$SDB" connect "$TV_IP:26101"
"$SDB" devices
```

Continue only if this exact TV is reported as `device` with the expected model. An HTTP response, ping, open port 26101, a blank handshake or `offline` does not establish SDB readiness. Re-check the TV's Host PC IP, address, restart and LAN isolation if the handshake fails. Do not proceed by guessing a different exploit or disabling the TV's general security settings.

The root tool and score publisher use reverse callbacks from this TV to the companion. Your local firewall must allow the required connection from this identified TV on the trusted LAN. Do not forward SDB or these callback ports through your internet router.

## 3. Fetch the official pinned host tool

From the repository root:

```sh
python3 samsung/tools/fetch_upstream.py
```

This downloads the official v0.0.12 archive for macOS/Linux arm64/x86_64, checks its pinned SHA-256, rejects unsafe archive entries and keeps it under ignored `samsung/.local/tools/`. It does **not** connect to or root a TV. No Samsung proprietary components are downloaded or redistributed by this helper.

The release source is pinned to commit `3b97edf3762db7670585d73e29623dc56195bf98`. The runner also checks the exact SHA-256 of the dependency-free upstream SDB module before importing it. Do not silently upgrade the tool to address a failed root attempt; review that new release and compatibility separately.

```sh
export ROOT_TOOL="$PWD/samsung/.local/tools/samsung-tv-root/samsung-tv-root"
export SDB_MODULE="$PWD/samsung/.local/tools/samsung-tv-root/source/src/samsung_tv_root/sdb.py"
"$ROOT_TOOL" --sdb "$SDB" doctor
```

OpenSSL must be available on the companion's PATH. The upstream tool carries its own archive payloads. Review the official [v0.0.12 README](https://github.com/chris-ritsen/samsung-tv-root/blob/v0.0.12/README.md) if its doctor command reports missing dependencies. Respect any OS prompt about opening a downloaded program; this project does not disable Gatekeeper or other host protections.

## 4. Run and inspect the explicit root probe

After confirming compatibility and authorization, execute the generic archive route on **this** TV:

```sh
umask 077
mkdir -p samsung/.local
chmod 700 samsung/.local
"$ROOT_TOOL" --sdb "$SDB" -o json archive-root probe "$TV_IP" \
  --callback-host "$HOST_IP" > samsung/.local/root-probe.json
chmod 600 samsung/.local/root-probe.json
```

Do not substitute the model-specific `qn90b` or `qn90f` kernel exploit because it appeared in a different owner's video. The generic archive route checks the actual SDB foothold, capabilities, archive support and .NET runtime. An explicit runtime override is for an independently inspected installed runtime; do not invent it to force a failed probe through.

Inspect the private JSON locally. Continue only if it reports all of:

- `host` equals the TV you identified.
- `authenticated` is true, `uid` and `euid` are integer zero.
- `runtime` is 6 or later for this renderer.
- `staging_cleaned` and `system_files_unchanged` are true.

UID zero does not prove every Samsung/SMACK security boundary has been bypassed. The renderer still needs its platform APIs and compositor permissions. A failed probe may have completed earlier staging operations: preserve its receipt, review upstream cleanup guidance and stop before retrying or rebooting. Never reboot/put the TV in standby while a temporary root session is doing its cleanup.

The companion requires a successful private receipt no older than seven days for the same target and refuses broad file permissions, a mismatched model or failed cleanup. Renew the probe after firmware changes. The firmware argument remains an operator declaration; it does not turn an incompatible device into a supported one.

## 5. Build and stage only the overlay

Install Microsoft's .NET 6 SDK in an isolated development environment if needed. Do not upload Samsung assemblies extracted from your TV. This overlay compiles without proprietary reference assemblies:

```sh
dotnet build samsung/FantasyOverlay.csproj -c Release -o samsung/.local/build
dotnet run --project samsung/checks/AlertPolicyChecks.csproj --configuration Release
python3 -m unittest discover -s samsung -p 'test_*.py'
```

The TV must have a matching compatible .NET runtime; compiling successfully on the companion is not runtime proof. Keep all build outputs private/ignored.

Stage the managed renderer and licensed fonts/artwork:

```sh
python3 samsung/stage.py \
  --tv "$TV_IP" --callback-host "$HOST_IP" \
  --model "$TV_MODEL" --firmware "$TV_FIRMWARE" \
  --sdb "$SDB" --root-tool "$ROOT_TOOL" --sdb-module "$SDB_MODULE" \
  --root-receipt samsung/.local/root-probe.json --acknowledge-root-risk
```

Staging checks the model before writing and verifies each pushed file's checksum. It refuses to replace a still-running overlay assembly. Files go only in this project's `/home/owner/share/tmp/sdk_tools/fantasy-overlay` staging directory. The `owner` component is Samsung's system account path, not a person's username. No Home/startup selector, package registry or system service is changed.

## 6. Connect your own feed and verify the visible result

Follow the repository's backend setup to provide `FANTASY_ENDPOINT` and `FANTASY_FEED_TOKEN` privately, then use the complete launch command in [README.md](README.md). Start with `--preview` while someone is watching the TV.

Check a real five-second popup over your actual HDMI/app path, **OK** to open the full starter-only sidebar, **Back** to close, correct person labels and totals, continued picture/sound and normal remote controls after dismissal. Check that stale/disconnected state hides. A process PID, a root receipt, an API response or a desktop mockup is not proof that the TV displays the overlay.

The original physical test covered Apple TV over HDMI. Test built-in streaming apps separately. Protected-content/OEM differences can change overlay behavior.

## Stop and recover

Type `quit`, press Ctrl-C, or run `python3 samsung/send_control.py quit`. The companion requests renderer exit and checks that its PID/assembly ended. If the host disappears, the renderer hides after thirty seconds without fresh state and has a bounded lifetime. `--watch` renews sessions only while the companion remains open.

Temporary root is lost across TV reboot; no persistent root/startup modification is included. Test **full restart** and **standby/wake** separately with the companion running, inspect each new authenticated cleanup receipt and visually verify playback/remote behavior again. Treat unattended reboot recovery as unverified until those tests pass on your own device.

Keep logs and receipts under `.local/`. Redact account IDs, device/network addresses and any authentication data before sharing a diagnostic. Never upload an entire working folder or a paired Apple TV storage file.
