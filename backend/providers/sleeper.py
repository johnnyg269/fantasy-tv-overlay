"""Sleeper's documented read-only NFL API. No account password is requested."""

import json
from pathlib import Path
from ..http_client import ProviderError, get_json
from ..model import STARTER_SLOTS, matchup, number, team, text


BASE = "https://api.sleeper.app/v1"


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def load_players(path):
    file = Path(path)
    try:
        if file.stat().st_size > 32 * 1024 * 1024:
            raise ProviderError("Sleeper player catalog is too large")
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ProviderError("Prepare the daily Sleeper player catalog first") from None
    if not isinstance(data, dict):
        raise ProviderError("Sleeper player catalog must be an object")
    return data


def normalize(config, league, rosters, users, matchups, week, players):
    league = _dict(league)
    if league.get("sport") != "nfl" or str(league.get("season")) != str(config.season):
        raise ProviderError("Sleeper league sport or season does not match")
    own = [m for m in _list(matchups) if isinstance(m, dict) and m.get("roster_id") == config.team_id]
    if len(own) != 1 or own[0].get("matchup_id") is None:
        raise ProviderError("No unique Sleeper matchup; check roster, week, or bye")
    opponents = [m for m in _list(matchups) if isinstance(m, dict)
                 and m.get("matchup_id") == own[0]["matchup_id"] and m.get("roster_id") != config.team_id]
    if len(opponents) != 1:
        raise ProviderError("No unique head-to-head opponent")
    roster_map = {r.get("roster_id"): r for r in _list(rosters) if isinstance(r, dict)}
    user_map = {str(u.get("user_id")): u for u in _list(users) if isinstance(u, dict)}
    slots = [slot for slot in _list(league.get("roster_positions")) if slot in STARTER_SLOTS]

    def convert(match):
        roster_id = match.get("roster_id")
        roster = roster_map.get(roster_id, {})
        owner = user_map.get(str(roster.get("owner_id")), {})
        person = config.owner_names.get(str(roster_id)) or owner.get("display_name")
        name = _dict(owner.get("metadata")).get("team_name") or "Fantasy team"
        lineup = _list(match.get("starters"))
        points = _dict(match.get("players_points"))
        aligned_points = _list(match.get("starters_points"))
        if not slots or len(lineup) != len(slots):
            raise ProviderError("Sleeper starting slots do not match lineup")
        rows = []
        for index, (player_id, slot) in enumerate(zip(lineup, slots)):
            if str(player_id) == "0":  # An empty starting slot, never a bench substitute.
                rows.append({"slot": slot, "name": "Empty slot", "pts": 0, "proj": None, "bench": False})
                continue
            player = _dict(players.get(str(player_id)))
            player_name = player.get("full_name") or " ".join(str(player.get(key) or "") for key in ("first_name", "last_name"))
            if not player_name.strip() and slot in ("DEF", "D/ST", "DST"):
                player_name = str(player_id) + " D/ST"
            if not player_name.strip():
                raise ProviderError("Sleeper starter is absent from player catalog")
            value = points.get(str(player_id), aligned_points[index] if index < len(aligned_points) else None)
            rows.append({"slot": slot, "name": text(player_name), "playerId": str(player_id),
                         "pts": number(value), "proj": None, "bench": False,
                         "proTeamAbbreviation": text(player.get("team"), 8),
                         "injuryStatus": text(player.get("injury_status") or player.get("status"), 30)})
        return team(roster_id, person, name,
                    match.get("custom_points") if match.get("custom_points") is not None else match.get("points"),
                    None, rows)

    return matchup(config, week, convert(own[0]), convert(opponents[0]))


def fetch(config, settings, client=get_json):
    league = client(BASE + "/league/" + config.id)
    state = client(BASE + "/state/nfl") if config.week is None else {}
    if config.week is None and (str(_dict(state).get("season")) != str(config.season)
                                or _dict(state).get("season_type") != "regular"):
        raise ProviderError("Set an explicit week outside the current regular season")
    week = config.week or _dict(state).get("week")
    if type(week) is not int or not 1 <= week <= 30:
        raise ProviderError("Sleeper scoring week is unavailable")
    # The multi-megabyte player catalog is prepared once per day by a separate
    # explicit command. It is never fetched for each poll or serverless cold start.
    players = load_players(settings.sleeper_players_file)
    return normalize(config, league, client(BASE + "/league/" + config.id + "/rosters"),
                     client(BASE + "/league/" + config.id + "/users"),
                     client(BASE + "/league/" + config.id + "/matchups/" + str(week)), week, players)
