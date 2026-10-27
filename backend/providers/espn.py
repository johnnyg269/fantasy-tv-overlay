"""ESPN football adapter for the undocumented internal read API.

The reference shape is documented by the upstream espn-api project; this is
an independent minimal normalizer, not an ESPN-supported integration.
"""

import json
from urllib.parse import urlencode
from ..http_client import ProviderError, get_json
from ..model import matchup, number, team, text


SLOTS = {0: "QB", 1: "TQB", 2: "RB", 3: "RB/WR", 4: "WR", 5: "WR/TE",
         6: "TE", 7: "OP", 8: "DT", 9: "DE", 10: "LB", 11: "DL", 12: "CB",
         13: "S", 14: "DB", 15: "DP", 16: "D/ST", 17: "K", 18: "P", 19: "HC",
         23: "FLEX"}


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _players(side, scoring_week, season):
    roster = _mapping(side.get("rosterForCurrentScoringPeriod"))
    players = []
    for entry in _list(roster.get("entries"))[:100]:
        entry = _mapping(entry)
        slot = SLOTS.get(entry.get("lineupSlotId"))
        if slot is None:  # BE=20, IR=21, reserve and unknown slots fail closed.
            continue
        pool = _mapping(entry.get("playerPoolEntry"))
        player = _mapping(pool.get("player"))
        if not player:
            raise ProviderError("Starter details are unavailable")
        stats = [stat for stat in _list(player.get("stats")) if isinstance(stat, dict)
                 and stat.get("scoringPeriodId") == scoring_week
                 and stat.get("seasonId", season) == season
                 and stat.get("statSplitTypeId") != 2]
        actual = next((stat for stat in stats if stat.get("statSourceId") == 0), {})
        projected = next((stat for stat in stats if stat.get("statSourceId") == 1), {})
        # appliedStatTotal is already calculated using this league's scoring.
        pts = actual.get("appliedTotal", entry.get("appliedStatTotal"))
        players.append({"slot": slot, "name": text(player.get("fullName")) or "Player unavailable",
                        "playerId": str(player.get("id", "")), "pts": number(pts),
                        "proj": number(projected.get("appliedTotal")), "bench": False,
                        "proTeamId": actual.get("proTeamId", player.get("proTeamId")),
                        "injuryStatus": text(player.get("injuryStatus"), 30)})
    if not players:
        raise ProviderError("Starting lineup is unavailable")
    return players


def normalize(data, config, scoring_week, matchup_period):
    if not isinstance(data, dict):
        raise ProviderError("ESPN response is not a league object")
    candidates = [item for item in _list(data.get("schedule")) if isinstance(item, dict)
                  and item.get("matchupPeriodId") == matchup_period
                  and any(_mapping(item.get(side)).get("teamId") == config.team_id
                          for side in ("home", "away"))]
    if len(candidates) != 1:
        raise ProviderError("No unique matchup; check team, week, or bye")
    fixture = candidates[0]
    own_side = "home" if _mapping(fixture.get("home")).get("teamId") == config.team_id else "away"
    other_side = "away" if own_side == "home" else "home"
    members = {str(member.get("id")): member for member in _list(data.get("members"))
               if isinstance(member, dict)}
    teams = {item.get("id"): item for item in _list(data.get("teams")) if isinstance(item, dict)}

    def convert(key):
        side = _mapping(fixture.get(key))
        identifier = side.get("teamId")
        if type(identifier) is not int or identifier not in teams:
            raise ProviderError("Opponent is unavailable or this is a bye")
        info = teams[identifier]
        owners = []
        for owner_id in _list(info.get("owners"))[:4]:
            member = members.get(str(owner_id), {})
            person = text(" ".join(part for part in (member.get("firstName"), member.get("lastName"))
                                   if isinstance(part, str)), 60)
            if person:
                owners.append(person)
        name = info.get("name") or " ".join(str(info.get(part) or "") for part in ("location", "nickname"))
        return team(identifier, config.owner_names.get(str(identifier)) or " / ".join(owners), name,
                    side.get("totalPointsLive", side.get("totalPoints")),
                    side.get("totalProjectedPointsLive"), _players(side, scoring_week, config.season))

    return matchup(config, scoring_week, convert(own_side), convert(other_side))


def fetch(config, settings, client=get_json):
    base = ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/"
            + str(config.season) + "/segments/0/leagues/" + config.id)
    headers = {}
    if settings.espn_s2:
        headers["Cookie"] = "espn_s2=" + settings.espn_s2 + "; SWID=" + settings.swid
    initial = client(base + "?view=mSettings", headers)
    status = _mapping(_mapping(initial).get("status"))
    scoring_week = config.week or _mapping(initial).get("scoringPeriodId")
    final_week = status.get("finalScoringPeriod")
    if config.week is None and type(scoring_week) is int and type(final_week) is int and 1 <= final_week <= 30:
        scoring_week = min(scoring_week, final_week)
    period = status.get("currentMatchupPeriod")
    if config.week is not None:
        periods = _mapping(_mapping(_mapping(initial).get("settings")).get("scheduleSettings")).get("matchupPeriods", {})
        matching = [int(key) for key, weeks in _mapping(periods).items()
                    if str(key).isdigit() and isinstance(weeks, list) and config.week in weeks]
        if len(matching) != 1:
            raise ProviderError("Configured week does not map to a matchup period")
        period = matching[0]
    if type(scoring_week) is not int or not 1 <= scoring_week <= 30 or type(period) is not int:
        raise ProviderError("ESPN has no active scoring week")
    query = urlencode({"view": ["mMatchupScore", "mScoreboard", "mTeam"],
                       "scoringPeriodId": scoring_week}, doseq=True)
    headers["X-Fantasy-Filter"] = json.dumps({"schedule": {"filterMatchupPeriodIds": {"value": [period]}}})
    return normalize(client(base + "?" + query, headers), config, scoring_week, period)
