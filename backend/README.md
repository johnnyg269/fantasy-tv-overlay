# Private fantasy feed

Use Python 3.10 or newer. No third-party Python packages are required for this backend. Start in the repository root. [Choose and connect a provider first](../docs/fantasy-providers.md).

```sh
python3 tools/setup.py
python3 -m backend.server
```

The wizard generates a fresh feed token and creates `.private/config.json` with restrictive permissions. It never prints credentials. Do not paste this file, cookies, tokens or an authenticated feed into chat, issues or public logs. Windows users must also restrict that folder's access with their filesystem permissions. It is excluded from Git and Vercel uploads. A new installation has no access to anyone else's account.

For an account-free local demonstration:

```sh
python3 tools/setup.py --demo
python3 -m backend.server --demo
```

Only the loopback demo is unauthenticated. Its synthetic scores change every 20 seconds. Test with `python3 tools/check_feed.py --demo --endpoint http://127.0.0.1:8787/api/scores --allow-loopback-http`. This is a data demo; it does not install an overlay or contact a TV.

For Sleeper, run `python3 tools/cache_sleeper_players.py` first. It downloads only public NFL metadata to ignored `runtime-data/sleeper-players.json` and refuses repeat downloads within 24 hours. Refresh once daily; it does not run automatically. The server never downloads that large catalog for each poll or cold start. Never store account information in `runtime-data`.

For a real private feed, use the same check command without `--demo`. The check reads the token from private configuration and prints counts only. Verify actual owner, opponent, week, totals and starting lineup privately against your provider before connecting the TV. The API serves normalized data described in [CONTRACT.md](CONTRACT.md).

## Configuration

Local JSON fields: `feedToken`, `leagues`, optional `espnS2`, `swid`, `sleeperPlayersFile`. Each league has `provider`, `id`, `teamId`, `season`, `label`, optional `week` and `ownerNames` (team ID to preferred manager name). The [synthetic league example](../examples/leagues.example.json) illustrates the shape. `week` is usually omitted so the provider's current week follows automatically. Mixed ESPN and Sleeper leagues are supported. One process caches a successful result for five seconds; respect upstream rate limits and avoid duplicate deployments polling the same accounts.

The equivalent deployment environment variables are:

| Variable | Purpose |
|---|---|
| `FANTASY_FEED_TOKEN` | Fresh 32+ character URL-safe secret; separate from all provider credentials |
| `FANTASY_LEAGUES_JSON` | JSON array with your own provider IDs, team/roster IDs and labels |
| `ESPN_S2`, `SWID` | Both private ESPN cookie values, only for private ESPN leagues |
| `FANTASY_CONFIG` | Local private JSON location; ignored on Vercel |
| `FANTASY_SLEEPER_PLAYERS_FILE` | Public catalog path; default `runtime-data/sleeper-players.json` |

Server-side credentials stay on the backend. TV clients receive only the feed token and normalized matchups. The local server binds `127.0.0.1` and caps concurrent connections. For a networked client use HTTPS through an operator-configured reverse proxy or deploy the HTTPS handler. No port-forwarding or network policy is changed by these scripts.

## Optional Vercel deployment

The included `api/scores.py` and `vercel.json` deploy the read-only feed; they **do not move the Samsung renderer, root session, local Apple TV observer, or Alexa home bridge into the cloud**. Samsung still needs an awake home companion. Android's service runs on the Android device. See [architecture](../docs/ARCHITECTURE.md).

1. Create your own Vercel project linked to your fork, with this repository as its root. Keep deployment accounts and permissions your own. Install Vercel CLI only from its official distribution if using the CLI path.
2. Add the environment variables above in Vercel's environment settings or its secret input prompts. Do not put secret values into `vercel.json`, shell command arguments, GitHub Actions variables, a shared chat or committed `.env` files. Configure Preview separately; omit credentials from untrusted previews.
3. If using Sleeper, prepare the daily public catalog before a local CLI deployment. `includeFiles` bundles only `runtime-data/**`; never use that folder for credentials. A Git-only deployment needs an explicit build-time public catalog step or its own maintained metadata store; a GitHub fork alone does not include the ignored catalog.
4. Deploy, then validate `/api/scores` over HTTPS: no token must return 401, correct token must return only your expected matchups, and responses must include `Cache-Control: private, no-store`. Misconfiguration/provider failure returns 503 with no account details. Vercel Deployment Protection, if enabled, needs a deliberate access arrangement for your TV; do not blindly disable an account-wide protection policy.
5. Set the TV client's endpoint to your deployment's `/api/scores` and enter its feed token privately. Never point new installations at the original author's deployment.

This code has synthetic fixture tests. Real ESPN/Sleeper account acceptance, deployment settings, provider schema changes and device compatibility need verification on each installation. ESPN's internal endpoint is undocumented and can change. Sleeper's documented API is read-only and has usage limits; follow its current terms.
