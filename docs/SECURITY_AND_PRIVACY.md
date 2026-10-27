# Security and privacy design

The public source should be reusable without carrying anyone else's household setup. Your installation creates new private configuration, tokens and pairings. Review dependencies and use a trusted device/network; the project does not claim to eliminate every risk.

## Assets and trust boundaries

| Asset | Intended location | Exposure to prevent |
| --- | --- | --- |
| ESPN session values / future provider OAuth tokens | Backend-only secret configuration | Chat, Git, browser/client bundles, feed responses, logs |
| Feed read token | Backend and each authorized renderer | URL parameters, redirect targets, screenshots, public config |
| League/team selections and owner names | Private installation config and authenticated feed | Public fixtures, issue attachments, shared CDN cache |
| TV addresses, SDK paths and pairing credentials | Ignored local setup | Public receipts, browser exports, logs, Git history |
| Voice signing key and household/skill identifiers | Private relay and user's private skill configuration | Public ZIPs, skill examples, request logs |
| TV privileged access | Explicitly selected compatible device on the LAN | Internet-facing SDB/root listener or an unrestricted cloud shell |

An attacker may reach a public feed/voice endpoint, submit malformed data, replay a request, send a forged source response, or obtain accidentally committed files. The user's authenticated backend and paired local devices are trusted for their declared role; compromise of the host, TV, root dependency or cloud account is outside what application validation can fully contain.

## Backend controls

Use a fresh random bearer token for the feed, even for a public fantasy league. Unauthorized requests must not receive scores, names or detailed configuration errors. Keep any health response minimal. Do not allow HTTP request parameters to select arbitrary upstream URLs or credentials.

TLS protects device-to-feed traffic. Reject redirects while carrying authorization so a changed endpoint cannot receive a token intended for another host. Do not place tokens in query strings. Restrict response sizes, timeouts, league counts and concurrent work; cache upstream reads and back off after provider failures. Data age must refer to the source read, not the time a stale response was served.

Use `Cache-Control: private, no-store` for authenticated output and avoid permissive cross-origin access. A private token is still sensitive when the response contains only scores. Keep provider responses and exception text out of public logs.

The local server listens on loopback by default. Making it reachable by a TV is a separate networking choice: use a trusted private route or a properly configured HTTPS host. Do not bind a development server publicly and assume the feed token replaces TLS or network limits.

## Renderer controls

The Android renderer stores settings in application-private storage and receives only the feed token, never ESPN session cookies. Android device owners, rooted-device software, backups or malicious local administrators can still read data outside the application's normal boundary. Do not install unknown APKs or reuse signing keys from another installation.

The Samsung companion uses authenticated SDB and temporary root on an exact compatible target. Treat its external root tool as privileged software. Obtain it from the pinned official upstream source, verify provenance, read the compatibility requirements, and stop when unsupported. Do not disable peer/receipt checks to make a connection pass.

Native scenes and feed input should be bounded, text sanitized and starter slots explicit. On stale publisher state or service shutdown, hide the overlay and release remote input. Never let feed data become a shell command, arbitrary file path, application launch or watch URL.

## Optional voice boundary

Expose only the fixed preview route through HTTPS. The public request needs a fresh timestamp, authenticated signature and persistent replay protection. The private skill validates its own skill and household user. Acknowledgment is distinct from verified TV display; ambiguous delivery should not claim success or blindly retry a second popup.

The relay stays on loopback behind the chosen ingress. It must not expose start/stop, SDB, arbitrary commands, file reads or the whole companion interface. Use a new signing key for each installation. Upload it only to the user's own private skill/configuration through a deliberate setup step.

## Sharing checklist

Before any public push, inspect the exact outgoing file set and every outgoing commit. Use a clean export or new repository when publishing a private working directory; a later redaction commit does not remove old content.

Exclude all of the following:

- Filled `.private/`, `.local/`, `.env` and generated setup files.
- Pairing stores, signing keystores, cookies, tokens, ZIP uploads, SQLite replay stores, caches and runtime logs.
- Real manager/league fixtures and private owner-name maps.
- TV photos/screenshots, browser exports, cloud receipts, household endpoints and device network details.
- Local virtual environments, SDKs, root-tool binaries, build output and unknown prebuilt artifacts.

Use synthetic data and freshly generated preview artwork. Inspect image metadata as well as visible pixels. Retain third-party license notices when distributing permitted font/UI assets. `.gitignore` is a safeguard for future additions, not proof that existing history is clean.

## Responding to exposure

Revoke/rotate the affected credential first, then remove it from tracked content and history if necessary. Inspect provider/cloud/voice access records privately and update all paired clients with replacement credentials. Treat published cookies and signing ZIPs as compromised even if they were visible only briefly.
