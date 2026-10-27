---
name: fantasy-tv-verify
description: Verify Fantasy TV's feed, overlay behavior and private-data boundaries after changes or setup. Use for this repository's acceptance checks and publication preparation; not as a general security certification.
---

# Verify Fantasy TV

Find the repository root containing `AGENTS.md`. Use `docs/VALIDATION.md` for acceptance and `docs/SECURITY_AND_PRIVACY.md` for trust boundaries. Run the selected component's documented checks; synthetic offline tests must not drive a real TV or account.

Check the behavioral contract across provider and renderer changes: quiet initial baseline; alerts only for actual-score changes including corrections; separate league events; five-second expiry; stale-source failure without false alerts; current starting lineup with no bench/reserve rows; explicit unavailable probabilities; owner labels from verified data.

For physical acceptance, identify the TV firmware, playback device and video app privately. Verify the overlay over actual uninterrupted playback, remote OK opening details, Back closing and input release after publisher loss. Android's permission grant and a successful APK build do not prove overlays over every protected app or HDMI source. Samsung root capability on one firmware does not prove another. Do not report tests you did not run.

Before sharing, inspect exact tracked files and every outgoing commit, not just the working tree. Reject filled private configuration, pairing databases, browser/session exports, real owner maps, personal score fixtures, device screenshots, public relay URLs, home network details, signing stores and prebuilt artifacts with unknown provenance. Run the repository's privacy checker and inspect new binary assets for metadata. `.gitignore` does not erase history.

Report discovered issues with file/line evidence and validated impact. State remaining coverage gaps. Automated scanning and source review reduce risk; they cannot prove that a setup is completely secure. If a live secret was committed, revoke or rotate it before discussing history cleanup.
