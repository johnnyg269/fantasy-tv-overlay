# Optional private Alexa voice link

Create your own personal **Fantasy Scores** custom skill and an optional Alexa Routine such as “Alexa, fantasy update.” It requests the existing five-second TV popup. This folder is source and a setup template: it contains no deployed skill, household account ID, public endpoint or signing credential.

The route is **Echo → your Alexa-hosted handler → your HTTPS Tailscale Funnel → this companion's loopback relay → the existing preview control**. Your home companion, TV session, relay, internet and Tailscale must be running. A cloud score endpoint alone cannot wake a stopped companion or keep its renderer alive.

This adapter currently targets the Samsung companion. It is not an Android voice-control integration or a published universal Alexa skill.

## Security properties

- Each household creates its own 256-bit signing key; no example key can control a real instance.
- The handler verifies the skill ID and allowed household account ID before requesting anything.
- The relay binds only `127.0.0.1:8767` and accepts **POST `/fantasy/preview`** with a valid HMAC signature, a fresh timestamp and the fixed preview action.
- Requests have a bounded 1 KiB body, a thirty-second validity window, persistent replay protection, at-most-once dispatch and bounded connection handling.
- GET, other paths/actions, unsigned/tampered/expired requests and arbitrary commands are refused. Redirects are not followed by the handler.
- The relay checks that this companion's lifetime lock is held and refuses to overwrite a pending local control request. It cannot start the companion, install anything, change channels or execute shell commands.
- Request envelopes, account tokens and credential values are not logged. A success response means **preview requested**, not independently confirmed TV display.

This is a limited design with regression tests, not a guarantee against every possible vulnerability. Keep the host, Tailscale and cloud runtime updated, and disable the optional public endpoint when you no longer use it.

## 1. Create your own development skill

In your own Amazon Developer account, create a **Custom**, **Alexa-hosted Python** skill. Keep it private in Development for the same Amazon account used by your Echo. Use `fantasy scores` as the invocation name or choose another permitted name and update the model/routine accordingly.

Import the interaction model in `skill-package/interactionModels/custom/en-US.json` and build it. `skill-package/skill.json` is a manifest template, not a deployed endpoint. Preserve the hosted endpoint Amazon generates for your skill. Do not submit/certify a public skill merely to use it at home.

Record your own skill ID and allowed account user ID privately. The allowed account ID comes from the `context.System.user.userId` field in **your own** test request. An entire request envelope can include tokens: do not save it in this repository, copy it into an issue or paste it into chat. Copy only the needed identifier directly into private local setup. Never use another household's IDs.

## 2. Prepare the host and deliberate HTTPS exposure

Install Tailscale using its official instructions. Set up the intended companion node and obtain its HTTPS Funnel name. Funnel exposes this one restricted relay to the internet; enabling it is a deliberate change to your network access, not a step performed automatically by these Python tools.

Scope the Funnel entitlement to the intended host in your tailnet policy instead of casually enabling it for every member. Preserve existing policy rules. Review the exact change before applying it; no template in this repository replaces a whole tailnet policy.

See the official [Funnel setup and access-control documentation](https://tailscale.com/docs/features/tailscale-funnel) and [Funnel CLI](https://tailscale.com/docs/reference/tailscale-cli/funnel). The destination must be the relay at `http://127.0.0.1:8767`, with HTTPS on public port 443. The only accepted URL is `https://YOUR-NODE.YOUR-TAILNET.ts.net/fantasy/preview`.

Do not expose SDB, a root shell, a broad file server or the ordinary control helper. Do not forward router ports to the TV. Existing Samsung/SmartThings Alexa integration by itself does not supply this custom overlay action.

## 3. Generate fresh private configuration

From the repository root, supply your own values through private local environment variables (never commit their contents):

```sh
python3 samsung/alexa_bridge/create_config.py \
  --directory samsung/.local/alexa --app-dir samsung \
  --skill-id "$ALEXA_SKILL_ID" --user-id "$ALEXA_ALLOWED_USER_ID" \
  --relay-url "$FANTASY_RELAY_URL"
```

The destination must not already exist. The generator creates a new key and writes:

- `mac.json`: local companion directory, replay database path and signing key. The legacy filename also works on a supported Linux host.
- `alexa.json`: the expected skill/account IDs, exact HTTPS URL and the same dedicated preview key.

Both files are 0600 in a 0700 directory. The key is not printed. These are local secrets, not sample configuration to share or copy between households.

Start the ordinary Samsung watch session. When valid `samsung/.local/alexa/mac.json` is present, the watch starts one optional relay child and stops it with the session. It does not enable Funnel or alter networking. Missing/invalid voice configuration leaves fantasy scores usable.

## 4. Import the private handler

Generate a code-import archive locally:

```sh
python3 samsung/alexa_bridge/prepare_upload.py \
  --output samsung/.local/alexa/skill-code-private.zip \
  --private-config samsung/.local/alexa/alexa.json
```

**This generated ZIP contains a signing secret. Keep it local and upload it only into your own private Alexa-hosted skill. Never attach it to chat, a GitHub issue, a release or source control.** The generator does not upload or modify an Amazon account.

Use the Alexa Developer Console's code import to upload the archive. It places these files in the hosted `lambda/` directory:

- `lambda_function.py`
- `skill_logic.py`
- `voice_protocol.py`
- `requirements.txt`
- `private_config.json` (your generated configuration)

The handler entry point is `lambda_function.lambda_handler`. Build/deploy the hosted code and enable Development testing for your own skill. If Amazon's current hosted Python runtime differs from your local test runtime, run the handler checks under that runtime before relying on it.

## 5. Verify the full route and choose a phrase

With the companion running and someone watching the TV:

1. Confirm GET requests cannot trigger the relay and an unsigned POST is rejected. Do not put the signing key in a URL, browser address bar or diagnostic output.
2. Test **“Alexa, ask Fantasy Scores to show my score.”** Confirm the popup actually appears for five seconds while playback continues.
3. In your Alexa app, create a personal Routine with the voice trigger **“fantasy update”** (or **“show me my fantasy score”**) and the custom action **“ask fantasy scores to show my score.”** Use the Echo that hears the trigger.
4. Test the Routine on your physical Echo. A successful simulator response or routine creation is not proof of physical TV display.

A generic voice assistant response can mean the phrase did not invoke your skill; use the explicit ask phrase to separate invocation from delivery. An offline/unconfirmed response should stay truthful instead of saying the TV displayed anything.

## Stop, revoke and rotate

Stop the Samsung companion to stop its relay child. Disable the Funnel rule/public listener through your own Tailscale configuration to remove public reachability. Disable/delete your private Alexa skill or Routine if you no longer use them. Deleting a local key does not remove a copy previously uploaded to Amazon.

If a generated ZIP or key is exposed, stop the relay, remove the old local configuration, generate a fresh key and update both sides. Keep the old key disabled; do not put it in a public incident report. The score-feed token and preview-signing key are separate credentials.

## Offline checks

Only the hosted-handler tests need Amazon's SDK dependency. Host relay operation uses Python's standard library. Run from the repository root:

```sh
python3 -m venv samsung/.local/alexa-test-venv
samsung/.local/alexa-test-venv/bin/python -m pip install -r samsung/alexa_bridge/lambda/requirements.txt
samsung/.local/alexa-test-venv/bin/python -m unittest discover -s samsung/alexa_bridge/tests
```

The suite uses synthetic skill IDs, request envelopes, keys and temporary loopback sockets. It does not contact Amazon, enable Funnel, publish a skill or drive a TV.

References: [Alexa-hosted skills](https://developer.amazon.com/en-US/docs/alexa/hosted-skills/alexa-hosted-skills-create.html), [development skill testing](https://www.developer.amazon.com/en-US/docs/alexa/test/test-your-skill-overview.html), [Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel).
