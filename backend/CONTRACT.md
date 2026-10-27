# Score feed contract, version 1

`GET /api/scores` uses `Authorization: Bearer <private feed token>`. The token belongs to the viewer's deployment. It is never a cookie, query parameter, or shared project token. Responses carry `Cache-Control: private, no-store`.

```json
{
  "schemaVersion": 1,
  "ok": true,
  "updated": 1790000000,
  "leagues": [{
    "leagueId": "demo-1",
    "short": "Sunday League",
    "week": 7,
    "winProb": 0.64,
    "me": {
      "teamId": "1", "ownerName": "Alex", "displayLabel": "Alex",
      "name": "Demo team", "score": 112.38, "proj": 134.78,
      "players": [{"slot": "QB", "name": "Demo player", "pts": 20.5,
                   "proj": 24.0, "bench": false}]
    },
    "opp": {
      "teamId": "2", "ownerName": "Taylor", "displayLabel": "Taylor",
      "name": "Demo team", "score": 104.76, "proj": 127.16,
      "players": [{"slot": "QB", "name": "Demo opponent", "pts": 18.0,
                   "proj": 22.0, "bench": false}]
    }
  }]
}
```

Everything in the example is synthetic. `updated` is Unix **seconds**, stamped only after successful upstream reads. A failed read must return non-2xx with `ok:false`, never freshen an old timestamp or substitute zero scores. Each league ID is stable and unique across providers; `teamId` is the actual provider team/roster ID. `week`, own team, or opponent changes reset the comparison baseline. The first sample is quiet. Only changes to the two actual `score` values trigger popups, including negative corrections; projections never trigger alerts.

`ownerName` and `displayLabel` identify the manager; do not infer them from a team nickname. Private `ownerNames` overrides can supply preferred names. `players` contains starting slots only, in lineup order. Exclude bench, IR, reserve, taxi and unknown slots. Actual points may be `null` when unavailable, never invent zero. Individual player scores must use the league's scoring settings, not default NFL points. Multiweek matchup totals and current-week rows are different scopes; preserve the upstream total and week correctly. Byes, median-only opponents, ambiguous matchups and unsupported roster shapes fail closed.

`winProb` is a number from 0 to 1, or `null`. A trustworthy provider/adapter may supply it with a documented `winProbSource`. The shipped ESPN and Sleeper adapters currently return `null`; the UI shows **Unavailable** rather than inventing a win percentage. Demo percentages are synthetic. Projections are also nullable. No betting data is used.

Optional per-player metadata: `nflHighlightLive` (boolean), `nflGameState` (`live`, `scheduled`, `final`, `unknown`), `nflAvailability`, `nflGameLabel`, `gameId`. LIVE means the player's NFL game is underway and no known unavailability suppresses the badge; it never proves that player is on the field. Unmatched identities, stale metadata and errors clear positive badges. Optional `tvContext` requires `updated` (Unix seconds), `available:true`, `matchedGameId`, and `confidence:"exact-title-pair"` or an explicit supported manual selection. Android expires that context after 30 seconds. App name or generic football title alone cannot mean ON TV.

Renderers reject stale/future source timestamps, finite-score violations and unsafe feed redirects. Never put account cookies, pairing data, upstream response objects, streaming URLs, or arbitrary commands in this contract. The public API is read-only; TV control and Alexa preview use a separate, authenticated local interface.
