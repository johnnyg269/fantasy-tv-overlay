# Contributing

Start with the synthetic demo and run the checks for the components you change. Keep provider adapters separate from renderers so the same authenticated score contract serves both TV paths.

Use fictional manager names, league IDs and scores in tests and screenshots. Never contribute filled configuration, cookies, tokens, pairing stores, skill ZIPs, cloud receipts, device addresses or personal account screenshots. Read [SECURITY.md](SECURITY.md) before reporting a vulnerability.

For bug reports, state the component and sanitized reproduction. A TV issue should identify the model family, OS/firmware and playback path without a serial number, account ID or home address. Distinguish a build/test result from physical playback verification.

For a new provider, follow [the provider adapter guide](docs/fantasy-providers.md). Use read-only authorized access; test correct team identity, scoring-period changes, byes, corrections and bench exclusion. Do not invent projections or probabilities.

For a new renderer or firmware recipe, document the actual capability and acceptance evidence. A launcher-only scoreboard does not satisfy the cross-app goal. Do not label a platform supported based solely on compilation or a similar device.

Keep existing third-party licenses and attribution. Explain what changed, why and which checks ran in the pull request. Mark unavailable hardware checks explicitly.
