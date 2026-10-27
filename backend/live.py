"""Optional NFL game status, joined by provider team identity, never by guesses."""

from copy import deepcopy
import json
import re
import threading
import time
from urllib.request import Request, build_opener
from .http_client import NoRedirect, ProviderError


URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"


def _read():
    try:
        with build_opener(NoRedirect()).open(Request(URL, headers={"User-Agent": "FantasyTV/1.0"}), timeout=5) as response:
            body = response.read(4 * 1024 * 1024 + 1)
        if len(body) > 4 * 1024 * 1024:
            raise ProviderError("NFL response too large")
        return json.loads(body)
    except (OSError, ValueError, RecursionError):
        raise ProviderError("NFL metadata unavailable") from None


class GameStatus:
    def __init__(self, fetcher=_read, clock=time.time):
        self.fetcher, self.clock = fetcher, clock
        self.updated, self.next_attempt, self.games = 0, 0, {}
        self.lock = threading.Lock()

    def annotate(self, payload):
        with self.lock:
            now = self.clock()
            if now >= self.next_attempt:
                self.next_attempt = now + 30
                try:
                    data = self.fetcher()
                    games = {}
                    ambiguous = set()
                    for event in data.get("events", [])[:32]:
                        event_id = str(event.get("id", ""))
                        season = event.get("season") or data.get("season") or {}
                        week = event.get("week") or data.get("week") or {}
                        year, week_number, season_type = season.get("year"), week.get("number"), season.get("type")
                        if (not re.fullmatch(r"[1-9][0-9]{0,19}", event_id)
                                or type(year) is not int or type(week_number) is not int
                                or season_type != 2):
                            continue
                        for competition in event.get("competitions", [])[:2]:
                            status = competition.get("status", {}).get("type", {})
                            phase = status.get("state")
                            state = "live" if phase == "in" else "final" if phase == "post" else "scheduled"
                            for competitor in competition.get("competitors", [])[:2]:
                                team = competitor.get("team", {})
                                value = (event_id, state, year, week_number)
                                team_id = str(team.get("id", ""))
                                abbr = str(team.get("abbreviation", "")).upper()
                                keys = []
                                if re.fullmatch(r"[1-9][0-9]{0,5}", team_id):
                                    keys.append(("id", team_id))
                                if re.fullmatch(r"[A-Z]{2,4}", abbr):
                                    keys.append(("abbr", abbr))
                                for key in keys:
                                    if key in ambiguous:
                                        continue
                                    if key in games and games[key] != value:
                                        games.pop(key)
                                        ambiguous.add(key)
                                    else:
                                        games[key] = value
                    self.games, self.updated = games, now
                except (ProviderError, AttributeError, TypeError, ValueError):
                    pass
            result = deepcopy(payload)
            fresh = 0 <= now - self.updated <= 90
            unavailable = {"OUT", "IR", "INJURED RESERVE", "INJURED_RESERVE", "INJURY_RESERVE",
                           "INACTIVE", "SUSPENDED", "SUSPENSION", "PUP", "RESERVE/PUP", "DOUBTFUL"}
            for league in result.get("leagues", []):
                for side in ("me", "opp"):
                    for player in league.get(side, {}).get("players", []):
                        abbr = str(player.get("proTeamAbbreviation", "")).upper()
                        abbr = {"JAC": "JAX", "LA": "LAR", "WAS": "WSH"}.get(abbr, abbr)
                        identity = ("id", str(player["proTeamId"])) if player.get("proTeamId") is not None else ("abbr", abbr)
                        game = self.games.get(identity) if fresh else None
                        if game and (league.get("seasonId") != game[2] or league.get("week") != game[3]):
                            game = None
                        available = str(player.get("injuryStatus", "")).upper() not in unavailable
                        player.update(nflHighlightLive=bool(game and game[1] == "live" and available),
                                      nflGameState=game[1] if game else "unknown",
                                      nflAvailability="available" if available else "out",
                                      gameId=game[0] if game else None)
            result["nflLive"] = {"available": fresh, "updated": self.updated if fresh else None}
            return result
