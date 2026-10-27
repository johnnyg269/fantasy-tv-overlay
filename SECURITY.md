# Security

Fantasy TV contains privileged TV integration and optional account/voice credentials. Use your own devices and fantasy accounts. Keep filled configuration out of Git. No software project can promise complete security; source review and automated checks do not certify every TV firmware, dependency, host or network.

## Reporting a vulnerability

Use the repository's **Security → Report a vulnerability** option when private reporting is available. Include the affected version, component, minimal reproduction and impact with synthetic data. Do not include live cookies, feed tokens, signing keys, pairing stores, account IDs or home network details.

If private reporting is unavailable, open a minimal issue asking for a private reporting channel without disclosing exploit details or credentials. A normal public bug report should contain only sanitized logs and synthetic fixtures.

If a secret was exposed, revoke or rotate it immediately. Removing a file or rewriting history does not revoke a credential already copied by another party.

## Supported boundary

- The backend performs reads for configured fantasy leagues; it does not make trades, change lineups or provide an account-login service.
- Session cookies and OAuth credentials belong only on the backend. Renderers use a separate feed token.
- Samsung SDB/root access stays on a trusted home network. Do not expose SDB, reverse callbacks or an arbitrary remote shell to the internet.
- Android uses a system overlay permission and a foreground service. It does not bypass apps that suppress overlays or promise that all OEMs permit them.
- Optional voice ingress accepts only an authenticated, fresh preview request. It must never become a generic TV-control endpoint.

Read [the security and privacy design](docs/SECURITY_AND_PRIVACY.md) before hosting or extending the project. Only the current default branch receives fixes; no response-time or long-term support commitment is implied.
