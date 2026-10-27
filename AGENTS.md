# Instructions for an agent setting up Fantasy TV

Read [README.md](README.md), then [docs/AGENT_WALKTHROUGH.md](docs/AGENT_WALKTHROUGH.md). The intended outcome is a real overlay above playback, a five-second popup on actual fantasy score changes, and a remote-controlled starter-only matchup sidebar. A dashboard or browser scoreboard alone does not satisfy it.

## Before accessing devices or accounts

Establish the user's fantasy provider, existing league/team, TV platform/model/firmware, viewing device/input, and a home device that can remain awake if choosing Samsung. Reuse answers already provided. Read [docs/fantasy-providers.md](docs/fantasy-providers.md), the platform matrix, and only the relevant platform README. Never infer root compatibility from brand, a reachable port, or another model. Android uses overlay permission, not the Samsung root route. LG/webOS, Roku, Apple TV and ordinary TVs do not have an equivalent implementation in this repository. An external Android device's overlay applies to playback on that device; it cannot draw over an unrelated TV input.

Use `.agents/skills/fantasy-tv-setup/SKILL.md` for the setup workflow and `.agents/skills/fantasy-tv-verify/SKILL.md` for functional acceptance. These skills are project-local and portable. Follow current host instructions for skill discovery; they can be read directly if not automatically loaded. Do not install plugins, alter cloud permissions, expose ports, enable root, pair devices, change account visibility, publish data, or buy hardware merely because a reference mentions them. Carry out the user's requested setup within its scope and explain consequential changes when they become necessary.

## Personal data boundary

Do not request passwords, cookies, OAuth tokens, feed tokens, pairing codes or key files in chat. The human enters credentials in their own private settings/terminal or provider-hosted consent flow. Keep account and device material in ignored `.private/` or `.local/` directories, with restrictive file permissions. Never commit raw API responses, owner mappings, private endpoints, device addresses, logs, screenshots of accounts, credentials, generated ZIPs or pairing databases. Do not copy a user's existing working directory wholesale into a fork.

The included demo is synthetic and account-free. Start there, then verify the user's provider privately. Read-only data access only: no fantasy lineup changes, transactions, purchases, ad bypasses or streaming access circumvention. A provider without an included adapter needs an authorized read integration and fixture tests; see [backend/CONTRACT.md](backend/CONTRACT.md). Do not claim "all fantasy apps supported" from a generic JSON interface.

## Validation and reporting

Run `python3 tools/verify.py` before and after changes. No script in the automated checks may contact a TV, acquire root, read production cookies, pair an Apple TV, expose an HTTP listener publicly, or invoke Alexa. Android builds may download official SDK/Maven dependencies; keep SDKs, local paths, keys, build outputs and virtual environments out of Git. Samsung builds need the documented .NET toolchain and user-supplied supported root SDK; no proprietary TV assemblies or prebuilt root tools are distributed here.

Preserve actual-score baseline rules: first sample quiet; projections quiet; week/opponent changes quiet; both positive changes and scoring corrections trigger; multiple league updates queue independently. Stale or missing input hides positive indicators and releases remote focus. Back must close the sidebar while video/audio continue. Public provider failures must not freshen old scores or log private bodies. Do not enable game switching without a verified provider route and actual playback acceptance. The prepared private experiments are intentionally absent.

Label source tests, native builds, emulator checks and physical TV acceptance separately. Record the exact device/firmware/input when the user confirms a result. Never claim cross-app HDMI, reboot recovery, or cloud-only operation from compilation. Changing Tizen model/firmware or Android OEM/app may invalidate previous evidence.

Before publishing a fork: inspect the exact staged diff, run `python3 tools/audit_public_tree.py` and a current secret scanner, use synthetic examples, and check Git history as well as current files. CI is unprivileged and must never receive household credentials or root access.
