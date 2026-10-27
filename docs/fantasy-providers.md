# Connect your fantasy provider

Choose the fantasy provider before TV setup. The overlay consumes a common feed; the backend translates account-specific data into that format. You can display more than one league and mix providers supported by your backend.

| Provider | Included account path | Credentials and status |
| --- | --- | --- |
| ESPN Fantasy Football | ESPN adapter | Publicly viewable leagues can work without cookies. Private leagues use your own `espn_s2` and `SWID` session values on the backend. This integration uses an undocumented ESPN interface and may change. |
| Sleeper NFL | Sleeper adapter | The public read-only API uses league and roster IDs, with no account password or API token. |
| Yahoo Fantasy | Extension guide below | An adapter is not included. Obtain approved Fantasy API access and use Yahoo OAuth 2.0 before implementing one. |
| NFL Fantasy, CBS, Fantrax and other apps | Common-feed adapter | No built-in connector is claimed. Use the provider's permitted API/export route, map it to the contract, and verify it before connecting a TV. |

This is a fantasy **football** overlay. A different sport also needs appropriate lineup rules, scoring-period handling and live-game enrichment; changing the provider name alone does not add those behaviors.

## First run the private setup wizard

From the repository root:

```sh
python3 tools/setup.py
```

The wizard creates ignored `.private/config.json` and a new random feed token. Enter secret values directly in its hidden prompts. Do not send them to an agent in chat, put them in a shell command, or commit the generated file. If you use an agent-operated browser, enter the credentials yourself in private local configuration rather than exposing a cookie table in tool output.

Use an existing account and league. You do not need to create a new account or a new league to display one you already participate in.

## ESPN Fantasy Football

1. Sign in to your own account at [ESPN Fantasy](https://fantasy.espn.com/) and open the intended football league for the season you want.
2. Find your league ID. ESPN documents the ID in league links and in the mobile app under League → League Info. [ESPN's league-ID guide](https://support.espn.com/hc/en-us/articles/360045861791-League-ID)
3. Open **your own team** page and read its `teamId` URL parameter. A team ID identifies a team within that league; it is not a manager's display name, standings row number or NFL team ID. Verify the selected team's matchup against the site.
4. Enter provider `espn`, the league ID as `id`, your team ID as `teamId`, season year and a short label in the local wizard. Add each league separately. IDs are configuration, not secrets, but can identify your private league; keep your filled configuration private.
5. Try the read without cookies if the league is publicly viewable. Do not change a private league to public merely to make an overlay work.
6. For a private league, obtain **only your own** `espn_s2` and `SWID` cookie values from your signed-in browser's developer tools: Application/Storage → Cookies → the ESPN Fantasy origin. Enter those values directly into the wizard's private prompts. Cookie spelling is `espn_s2`; the backend environment variable is `ESPN_S2`. Preserve the SWID value as supplied, including braces when present.

The cookie procedure is an unofficial integration technique, not an ESPN OAuth flow or a scoped application token. Its technical reference is the [unofficial ESPN API project](https://github.com/pseudo-r/Public-ESPN-Fantasy-API). Treat session values as powerful account credentials even though Fantasy TV only performs reads. The overlay does not need your ESPN password and must not automate trades, waivers or lineup changes.

Compare the returned owner labels, opponent, week, actual totals and starting players with the ESPN matchup page. If a field is unavailable, keep it unavailable; do not substitute a nickname for a person's name or bench players for empty starter slots.

If access expires or the backend returns an authentication failure, sign in normally and update only the private server-side credentials. Do not repeatedly retry a rejected session or copy a different person's cookies. Multiple private ESPN accounts need separate backend credential contexts; the included deployment has one ESPN session context.

## Sleeper NFL

Sleeper's [official API](https://docs.sleeper.com/) is read-only and does not require a login token. Follow this discovery chain with your own username:

1. `GET https://api.sleeper.app/v1/user/{username}` returns the stable `user_id`.
2. `GET https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{season}` lists league IDs.
3. `GET https://api.sleeper.app/v1/league/{league_id}/rosters` returns rosters. Match your `user_id` to `owner_id`; use that row's `roster_id`.
4. In the wizard choose `sleeper`, set `id` to the league ID and `teamId` to your roster ID. Keep the long league ID as a string.

Prepare the public NFL player catalog before starting the feed:

```sh
python3 tools/cache_sleeper_players.py
```

Refresh it daily when using Sleeper. It is saved in ignored `runtime-data/sleeper-players.json`; no account information belongs in that directory. Prepare it before a Vercel deployment too: the service does not download this multi-megabyte catalog on each cold start. Follow `backend/README.md` for deployment packaging.

Compare the chosen week's matchup in Sleeper. `starters` determines the lineup; the full `players` array includes bench players. A bye must not become a fabricated matchup. The adapter preserves commissioner-adjusted totals when available. Sleeper display names may be usernames; use private per-team `ownerNames` overrides for the personal names you want shown.

The public API does not supply every projection or win probability required by richer interfaces. Missing fields remain unavailable. Keep polling bounded and cache player metadata. Sleeper's API terms distinguish non-commercial use from commercial licensing; review them for your deployment. [Official API terms and endpoints](https://docs.sleeper.com/)

## Yahoo Fantasy: an extension, not a bundled connector

Yahoo currently requires an application and review for Fantasy API access. Register your own application, request the minimum read access, and obtain approval through the [Yahoo Fantasy developer portal](https://sports.yahoo.com/developer/access/). Approval is separate from possessing a client ID or completing login.

Use Yahoo's documented OAuth 2.0 authorization flow with a registered redirect URI and protected client secret/refresh token. Do not copy Yahoo browser cookies or ask the user for a password. Verify the authorization response, keep refresh tokens server-side and request only needed read scope. [Yahoo Fantasy OAuth documentation](https://sports.yahoo.com/developer/docs/)

Once approved, a new backend adapter must discover the user's season/game, league key and team key, then retrieve the current matchup, points and starter lineup. Follow the adapter checklist below. Until that code and account-level validation exist, this repository does not connect directly to Yahoo.

## Any other fantasy app

Your agent can implement a provider adapter without changing the TV UI:

1. Identify the provider's official API, OAuth process or permitted export. Confirm that the user's account can read its league. A sign-in screen or a public website alone is not proof of a reusable API.
2. Keep its credentials in backend-only private configuration. Use read-only scopes where available. Do not use another installation's endpoint or tokens.
3. Implement [the shared score contract](../backend/CONTRACT.md), translating the provider's league/team identities, current scoring period, actual totals, starter slots and player points. Retain source timestamps and explicit failure states. Add a module under `backend/providers/`, register its `fetch(league, settings)` function in `backend/service.py`'s `ADAPTERS`, and explicitly allow its provider identifier and configuration fields in `backend/config.py`. Keep its HTTP origins and redirect policy fixed; do not add a caller-supplied arbitrary URL proxy.
4. Add fixtures and tests for wrong team selection, no opponent/byes, scoring corrections, matchup-period changes, bench/reserve exclusion, custom scoring, missing projections and unavailable win probabilities. Do not infer missing values from unrelated providers.
5. Verify the feed against the provider's own matchup UI before pairing or rooting a TV. Then run the hardware acceptance checklist.

If the provider offers no permitted automatic read route, a manually updated compatible feed is possible but is not live scoring. State that limitation explicitly. A connector contract is not a claim that every provider is already supported.

## Hosting the private feed

For local use, `python3 -m backend.server` reads `.private/config.json` and listens on loopback by default. The TV needs an explicitly configured reachable HTTPS endpoint or private network route; its `localhost` is not your computer.

For Vercel or another HTTPS host, configure server-side secrets privately:

| Variable | Purpose |
| --- | --- |
| `FANTASY_FEED_TOKEN` | New random bearer token required by your renderers |
| `FANTASY_LEAGUES_JSON` | Your list of provider/league/team/season selections |
| `ESPN_S2` | Your ESPN session value, only for private ESPN leagues |
| `SWID` | Your ESPN user session identifier, only for private ESPN leagues |

Never expose session cookies in the feed response. Send the feed token in the `Authorization` header, not a URL query parameter. Keep responses private and uncached by shared CDNs. See [security and privacy](SECURITY_AND_PRIVACY.md).
