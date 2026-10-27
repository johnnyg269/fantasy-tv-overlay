"""Public ESPN NFL game-state enrichment for copied fantasy player rows.

LIVE means the mapped player's NFL game is in progress, never proof that the
player is literally on the field. Known OUT/IR/inactive players are not marked
for highlighting. Unmatched names, ambiguous mappings, stale data and errors
never produce a positive live indicator. No private ESPN API or cookies are
used; fantasy names are matched locally, never sent as search queries.

Create one NflLiveEnricher for the companion's lifetime. Scoreboard freshness
is 30 seconds, rosters are cached 15 minutes, and team metadata for one day.
Initial roster loading uses at most four concurrent public requests. Call
refresh() once during startup to warm the cache; annotate(..., refresh=False)
can then read the cache without any network work when needed.
"""

from collections import defaultdict
from copy import deepcopy
from datetime import datetime
import json
import math
import queue
import re
import threading
import time
import unicodedata
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
TEAMS_URL = BASE + "/teams"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
UNAVAILABLE = frozenset(("out", "injured-reserve", "inactive", "suspended", "practice-squad"))
METADATA_FIELDS = ("nflGameState", "nflGameLabel", "nflTeamId", "gameId",
                   "mappingConfidence", "nflAvailability", "nflHighlightLive")
# Shared across session renewals; an old slow request cannot raise concurrent
# public traffic above four when the next companion session starts.
_PUBLIC_REQUEST_SLOTS = threading.BoundedSemaphore(4)


def _unknown_metadata():
    return {"nflGameState": "unknown", "nflGameLabel": "Status unavailable",
            "nflTeamId": None, "gameId": None, "mappingConfidence": "unknown",
            "nflAvailability": "unknown", "nflHighlightLive": False}


def _scope(league):
    """NFL regular-season identity, never inferred from a fresh fetch time."""
    year, week = league.get("seasonId"), league.get("week")
    if (type(year) is not int or not 2019 <= year <= 2100
            or type(week) is not int or not 1 <= week <= 18):
        return None
    return (year, week)


def _scoped_player_rows(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("leagues"), list):
        return
    for league in payload["leagues"]:
        if not isinstance(league, dict):
            continue
        scope = _scope(league)
        for side in ("me", "opp"):
            team = league.get(side)
            if isinstance(team, dict) and isinstance(team.get("players"), list):
                for player in team["players"]:
                    if isinstance(player, dict):
                        yield scope, player


def _player_rows(payload):
    for _scope_value, player in _scoped_player_rows(payload):
        yield player


def clear_live_metadata(payload, error=None):
    result = deepcopy(payload)
    for player in _player_rows(result):
        player.update(_unknown_metadata())
    if isinstance(result, dict):
        result["nflLive"] = {"available": False, "error": error}
    return result


def fetch_public_json(url):
    if not url.startswith(BASE + "/"):
        raise ValueError("Only the fixed public ESPN NFL service is allowed")
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "FantasyOverlay/1.0"})
    with urlopen(request, timeout=6) as response:
        content = response.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError("public NFL response exceeds 4 MiB")
    data = json.loads(content.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("public NFL response must be an object")
    return data


def _name(value):
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKD", value).casefold()
    words = re.findall(r"[a-z0-9]+", "".join(ch for ch in text if not unicodedata.combining(ch)))
    while words and words[-1] in ("jr", "sr", "ii", "iii", "iv", "v"):
        words.pop()
    return "".join(words)


def _position(value):
    return re.sub(r"[^A-Z0-9/]", "", str(value or "").upper())


def _compatible(slot, position):
    slot, position = _position(slot), _position(position)
    groups = {
        "QB": {"QB"}, "RB": {"RB", "FB"}, "WR": {"WR"}, "TE": {"TE"},
        "K": {"K", "PK"}, "PK": {"K", "PK"},
        "FLEX": {"RB", "FB", "WR", "TE"}, "RB/WR/TE": {"RB", "FB", "WR", "TE"},
        "W/R/T": {"RB", "FB", "WR", "TE"}, "RB/WR": {"RB", "FB", "WR"},
        "WR/TE": {"WR", "TE"}, "RB/TE": {"RB", "FB", "TE"},
        "SUPERFLEX": {"QB", "RB", "FB", "WR", "TE"},
        "OP": {"QB", "RB", "FB", "WR", "TE"}, "SF": {"QB", "RB", "FB", "WR", "TE"},
        "DL": {"DL", "DE", "DT", "NT", "EDGE"}, "DE": {"DE", "EDGE"},
        "DT": {"DT", "NT"}, "LB": {"LB", "ILB", "OLB", "MLB", "EDGE"},
        "DB": {"DB", "CB", "S", "SS", "FS"}, "CB": {"CB"}, "S": {"S", "SS", "FS"},
    }
    return position in groups[slot] if slot in groups else True


def _availability(athlete, group):
    status = athlete.get("status") if isinstance(athlete.get("status"), dict) else {}
    labels = [str(status.get(key, "")) for key in ("name", "type", "abbreviation")]
    injuries = athlete.get("injuries")
    if isinstance(injuries, list):
        for injury in injuries[:10]:
            if isinstance(injury, dict):
                value = injury.get("status", "")
                if isinstance(value, dict):
                    labels.extend(str(value.get(key, "")) for key in ("name", "type", "abbreviation"))
                else:
                    labels.append(str(value))
    normalized = {_name(label) for label in labels}
    if normalized & {"injuredreserve", "ir", "reserveinjured", "pup", "physicallyunabletoperform"}:
        return "injured-reserve"
    if normalized & {"out", "o"}:
        return "out"
    if normalized & {"suspended", "suspension", "susp"} or _name(group) == "suspended":
        return "suspended"
    if normalized & {"practicesquad", "ps"} or _name(group) == "practicesquad":
        return "practice-squad"
    if normalized & {"inactive", "notactive", "reserve", "retired"}:
        return "inactive"
    if _name(group) == "injuredreserveorout":
        return "inactive"
    if "doubtful" in normalized:
        return "doubtful"
    if "questionable" in normalized:
        return "questionable"
    return "available" if "active" in normalized else "unknown"


def _date(value=None):
    value = value or datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d")
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{8}", value):
        raise ValueError("NFL date must be YYYYMMDD")
    datetime.strptime(value, "%Y%m%d")
    return value


def _teams(data):
    found = {}
    for sport in data.get("sports", [])[:4]:
        for league in sport.get("leagues", [])[:4]:
            for entry in league.get("teams", [])[:40]:
                team = entry.get("team") if isinstance(entry, dict) else None
                if not isinstance(team, dict):
                    continue
                team_id = str(team.get("id", ""))
                if not re.fullmatch(r"[0-9]{1,4}", team_id):
                    continue
                found[team_id] = {key: team.get(key, "") for key in
                                  ("id", "abbreviation", "displayName", "shortDisplayName", "name", "nickname")}
                if len(found) == 32:
                    return found
    return found


def _games(data):
    games, ambiguous = {}, set()
    if not isinstance(data.get("events"), list):
        raise ValueError("NFL scoreboard needs an events array")
    for event in data["events"][:40]:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("id", ""))
        season = event.get("season") or data.get("season") or {}
        week = event.get("week") or data.get("week") or {}
        if not isinstance(season, dict) or not isinstance(week, dict):
            continue
        scope = _scope({"seasonId": season.get("year"), "week": week.get("number")})
        if (not re.fullmatch(r"[1-9][0-9]{0,19}", event_id) or scope is None
                or type(season.get("type")) is not int or season.get("type") != 2):
            continue
        competitions = event.get("competitions")
        if not isinstance(competitions, list):
            continue
        for competition in competitions[:2]:
            if not isinstance(competition, dict):
                continue
            competitors = competition.get("competitors")
            if not isinstance(competitors, list) or len(competitors) != 2:
                continue
            team_ids = []
            for competitor in competitors:
                team = competitor.get("team") if isinstance(competitor, dict) else None
                team_id = str(team.get("id", "")) if isinstance(team, dict) else ""
                if not re.fullmatch(r"[1-9][0-9]{0,5}", team_id):
                    break
                team_ids.append(team_id)
            if len(team_ids) != 2 or len(set(team_ids)) != 2:
                continue
            status = competition.get("status") or event.get("status") or {}
            if not isinstance(status, dict):
                continue
            status_type = status.get("type") if isinstance(status.get("type"), dict) else {}
            phase = {"in": "live", "post": "final", "pre": "scheduled"}.get(status_type.get("state"), "unknown")
            detail = str(status_type.get("shortDetail") or status_type.get("detail") or "").strip()
            if phase == "live":
                period = status.get("period")
                clock = status.get("displayClock")
                if status_type.get("name") == "STATUS_HALFTIME":
                    detail = "Halftime"
                elif type(period) is int and period > 0 and isinstance(clock, str):
                    detail = ("Q" + str(period) if period <= 4 else "OT") + " " + clock
            for index, competitor in enumerate(competitors):
                team_id = team_ids[index]
                opponent = competitors[1 - index]["team"].get("abbreviation", "")
                label = detail or {"live": "Live game", "final": "Final", "scheduled": "Scheduled"}.get(phase, "Status unavailable")
                if opponent:
                    label += (" vs " if competitor.get("homeAway") == "home" else " @ ") + str(opponent)
                game = {"state": phase, "label": label, "gameId": event_id,
                        "seasonId": scope[0], "week": scope[1], "seasonType": 2,
                        "opponentTeamId": team_ids[1 - index]}
                if team_id in ambiguous:
                    continue
                if team_id in games and games[team_id] != game:
                    games.pop(team_id)
                    ambiguous.add(team_id)
                else:
                    games[team_id] = game
    return games


class NflLiveEnricher:
    """Bounded, reusable public-data cache; call methods serially per instance."""

    def __init__(self, fetcher=fetch_public_json, clock=time.time,
                 scoreboard_ttl=30, roster_ttl=900, teams_ttl=86400, max_workers=4):
        if min(scoreboard_ttl, roster_ttl, teams_ttl) <= 0:
            raise ValueError("NFL cache intervals must be positive")
        self.fetcher, self.clock = fetcher, clock
        self.scoreboard_ttl, self.roster_ttl, self.teams_ttl = scoreboard_ttl, roster_ttl, teams_ttl
        self.max_workers = max(1, min(4, int(max_workers)))
        self.teams, self.rosters, self.games = {}, {}, {}
        self.teams_updated = self.scoreboard_updated = None
        self.next_teams_attempt = self.next_scoreboard_attempt = float("-inf")
        self.roster_retry = {}
        self.date = None
        self.last_error = None
        self._lock = threading.Lock()

    def _fetch(self, url, cancel_event=None):
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("NFL refresh cancelled")
            if _PUBLIC_REQUEST_SLOTS.acquire(timeout=0.25):
                break
        try:
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("NFL refresh cancelled")
            return self.fetcher(url)
        finally:
            _PUBLIC_REQUEST_SLOTS.release()

    def refresh(self, date=None, cancel_event=None):
        """Refresh due public caches, never 32 roster requests on each score poll."""
        date = _date(date)
        with self._lock:
            if cancel_event is not None and cancel_event.is_set():
                return self.status()
            now = self.clock()
            errors = []
            if self.date != date:
                self.date, self.games, self.scoreboard_updated = date, {}, None
                self.next_scoreboard_attempt = float("-inf")
            if now >= self.next_teams_attempt:
                self.next_teams_attempt = now + 60
                try:
                    teams = _teams(self._fetch(TEAMS_URL, cancel_event))
                    if not teams:
                        raise ValueError("NFL team metadata was empty")
                    self.teams = teams
                    self.teams_updated = self.clock()
                    self.next_teams_attempt = self.teams_updated + self.teams_ttl
                    self.rosters = {key: value for key, value in self.rosters.items() if key in teams}
                except Exception as error:
                    errors.append("teams: " + type(error).__name__)
            if cancel_event is not None and cancel_event.is_set():
                return self.status()
            if now >= self.next_scoreboard_attempt:
                self.next_scoreboard_attempt = now + self.scoreboard_ttl
                try:
                    self.games = _games(self._fetch(BASE + "/scoreboard?dates=" + date, cancel_event))
                    self.scoreboard_updated = self.clock()
                    self.next_scoreboard_attempt = self.scoreboard_updated + self.scoreboard_ttl
                except Exception as error:
                    errors.append("scoreboard: " + type(error).__name__)
            if cancel_event is not None and cancel_event.is_set():
                return self.status()
            due = [key for key in self.teams if now >= self.roster_retry.get(key, float("-inf"))
                   and (key not in self.rosters or now - self.rosters[key]["updated"] >= self.roster_ttl)]
            if due:
                self._refresh_rosters(due, errors, cancel_event)
            self.last_error = "; ".join(errors) or None
            return self.status()

    def _refresh_rosters(self, due, errors, cancel_event):
        jobs, completed = queue.Queue(), queue.Queue()
        for key in due:
            jobs.put(key)

        def fetch_rosters():
            while cancel_event is None or not cancel_event.is_set():
                try:
                    key = jobs.get_nowait()
                except queue.Empty:
                    return
                try:
                    data = self._fetch(BASE + "/teams/" + key + "/roster", cancel_event)
                    completed.put((key, data, None))
                except Exception as error:
                    completed.put((key, None, error))

        # Do not use ThreadPoolExecutor: its global exit hook joins HTTP
        # workers even after a bounded close(). These workers are all daemon
        # threads, never mutate caches themselves, and stop taking queued work
        # as soon as the session closes.
        for _ in range(min(self.max_workers, len(due))):
            threading.Thread(target=fetch_rosters, name="fantasy-public-http", daemon=True).start()
        remaining = len(due)
        while remaining:
            if cancel_event is not None and cancel_event.is_set():
                return
            try:
                key, data, error = completed.get(timeout=0.25)
            except queue.Empty:
                continue
            self._store_roster(key, data, errors, error)
            remaining -= 1

    def _store_roster(self, key, data, errors, error=None):
        self.roster_retry[key] = self.clock() + 60
        try:
            if error is not None:
                raise error
            if not isinstance(data.get("athletes"), list):
                raise ValueError("NFL roster needs athlete groups")
            declared_team = data.get("team")
            if (isinstance(declared_team, dict) and declared_team.get("id") is not None
                    and str(declared_team["id"]) != key):
                raise ValueError("NFL roster team ID does not match requested team")
            players = []
            for group in data["athletes"][:12]:
                for athlete in group.get("items", [])[:150]:
                    if not isinstance(athlete, dict):
                        continue
                    aliases = {_name(athlete.get(key)) for key in ("fullName", "displayName")}
                    aliases.discard("")
                    if aliases:
                        players.append({"teamId": key, "athleteId": str(athlete.get("id", "")),
                                        "aliases": aliases,
                                        "position": _position(athlete.get("position", {}).get("abbreviation")),
                                        "availability": _availability(athlete, group.get("position"))})
            self.rosters[key] = {"updated": self.clock(), "players": players[:150]}
            self.roster_retry[key] = self.clock() + self.roster_ttl
        except Exception as error:
            errors.append("roster " + key + ": " + type(error).__name__)

    def status(self):
        now = self.clock()
        fresh = self.scoreboard_updated is not None and 0 <= now - self.scoreboard_updated < self.scoreboard_ttl
        return {"available": fresh, "scoreboardUpdated": self.scoreboard_updated,
                "date": self.date, "error": self.last_error}

    def annotate(self, payload, date=None, refresh=True):
        """Return a deep copy enriched with verified game state and live eligibility."""
        if refresh:
            self.refresh(date)
        with self._lock:
            result = deepcopy(payload)
            if not isinstance(result, dict):
                raise ValueError("fantasy scores must be an object")
            now = self.clock()
            fresh = self.status()["available"] and (date is None or self.date == _date(date))
            by_name, defenses = defaultdict(list), defaultdict(set)
            for team_id, team in self.teams.items():
                for key in ("abbreviation", "displayName", "shortDisplayName", "name", "nickname"):
                    alias = _name(team.get(key))
                    if alias:
                        defenses[alias].add(team_id)
            for roster in self.rosters.values():
                if not 0 <= now - roster["updated"] < self.roster_ttl:
                    continue
                for player in roster["players"]:
                    for alias in player["aliases"]:
                        by_name[alias].append(player)
            for league in result.get("leagues", []) if isinstance(result.get("leagues"), list) else []:
                if not isinstance(league, dict):
                    continue
                for side in ("me", "opp"):
                    team = league.get(side)
                    if not isinstance(team, dict) or not isinstance(team.get("players"), list):
                        continue
                    for player in team["players"]:
                        if not isinstance(player, dict):
                            continue
                        metadata = _unknown_metadata()
                        candidates = []
                        if _position(player.get("slot")) in ("D/ST", "DST", "DEF", "D"):
                            defense_name = re.sub(r"(?:\s|[-/])*(?:d\s*/\s*st|dst|defense|def)\s*$", "",
                                                  str(player.get("name", "")), flags=re.I)
                            ids = defenses.get(_name(defense_name), set())
                            if len(ids) == 1:
                                candidates = [{"teamId": next(iter(ids)), "athleteId": "defense",
                                               "availability": "available"}]
                                metadata["mappingConfidence"] = "team-exact"
                        else:
                            matches = [entry for entry in by_name.get(_name(player.get("name")), [])
                                       if _compatible(player.get("slot"), entry["position"])]
                            unique = {(entry["teamId"], entry["athleteId"]): entry for entry in matches}
                            if len(unique) == 1:
                                candidates = list(unique.values())
                                metadata["mappingConfidence"] = "roster-exact-position"
                            elif len(unique) > 1:
                                metadata["mappingConfidence"] = "ambiguous"
                        if len(candidates) == 1:
                            mapped = candidates[0]
                            metadata["nflTeamId"] = mapped["teamId"]
                            metadata["nflAvailability"] = mapped["availability"]
                            game = self.games.get(mapped["teamId"]) if fresh else None
                            if game is not None and _scope(league) != (game["seasonId"], game["week"]):
                                game = None
                            if game is not None:
                                metadata["nflGameState"], metadata["nflGameLabel"] = game["state"], game["label"]
                                metadata["gameId"] = game["gameId"]
                                metadata["nflHighlightLive"] = (game["state"] == "live"
                                                                and mapped["availability"] not in UNAVAILABLE)
                                if mapped["availability"] in UNAVAILABLE:
                                    metadata["nflGameLabel"] = mapped["availability"].upper() + " · " + game["label"]
                        player.update(metadata)
            result["nflLive"] = self.status()
            return result


class NflLiveWorker:
    """One daemon public-data worker; foreground methods never wait for HTTP.

    Cached metadata is keyed by exact season/week, normalized player name and fantasy slot.
    A worker result can never overwrite a newer score, projection, owner, or
    lineup. Closing the worker immediately makes its cache unavailable and
    requests cancellation of queued public roster requests.
    """

    def __init__(self, enricher=None, clock=time.monotonic, metadata_ttl=90,
                 interval=5, date=None):
        if (not math.isfinite(float(metadata_ttl)) or metadata_ttl <= 0
                or not math.isfinite(float(interval)) or interval <= 0):
            raise ValueError("worker cache and refresh intervals must be positive")
        self.enricher = enricher if enricher is not None else NflLiveEnricher()
        self.clock, self.metadata_ttl = clock, min(90, float(metadata_ttl))
        self.interval, self.date = float(interval), date
        self.stop_event, self.wake_event = threading.Event(), threading.Event()
        self._lock = threading.Lock()
        self._latest = None
        self._metadata, self._updated, self._status = {}, None, {"available": False}
        self._valid_for = 0
        self._thread = threading.Thread(target=self._run, name="fantasy-public-nfl", daemon=True)
        self._thread.start()

    def submit_latest(self, payload):
        if self.stop_event.is_set():
            return False
        unique = {}
        for scope, player in _scoped_player_rows(payload):
            if scope is None:
                continue
            key = (scope, _name(player.get("name")), _position(player.get("slot")))
            if key[1] and key not in unique and len(unique) < 512:
                unique[key] = {"name": player.get("name"), "slot": player.get("slot")}
        # Retain only the public NFL season/week scope and player name/slot.
        # Do not copy fantasy league IDs, owners or actual/projection values.
        # Public requests contain only NFL IDs and the date.
        scoped = {}
        for key, player in unique.items():
            scoped.setdefault(key[0], []).append(player)
        slim = {"leagues": [{"seasonId": scope[0], "week": scope[1],
                              "me": {"players": players}}
                             for scope, players in scoped.items()]}
        with self._lock:
            self._latest = slim
        self.wake_event.set()
        return True

    def _run(self):
        next_refresh = float("-inf")
        while not self.stop_event.is_set():
            self.wake_event.wait(timeout=min(self.interval, 1))
            self.wake_event.clear()
            if self.stop_event.is_set():
                break
            with self._lock:
                latest = deepcopy(self._latest)
            if latest is None:
                continue
            now = self.clock()
            if now >= next_refresh:
                try:
                    self.enricher.refresh(self.date, cancel_event=self.stop_event)
                    if self.stop_event.is_set():
                        break
                    enriched = self.enricher.annotate(latest, date=self.date, refresh=False)
                    status = deepcopy(enriched.get("nflLive", {"available": False}))
                    valid_for = self.metadata_ttl
                    source_updated = status.get("scoreboardUpdated")
                    if source_updated is not None:
                        try:
                            source_clock = getattr(self.enricher, "clock", time.time)
                            source_age = float(source_clock()) - float(source_updated)
                            if not math.isfinite(source_age) or source_age < 0:
                                valid_for = 0
                            else:
                                valid_for = min(valid_for, max(0, 90 - source_age))
                        except (TypeError, ValueError, OverflowError):
                            valid_for = 0
                    metadata = {}
                    for scope, player in _scoped_player_rows(enriched):
                        if scope is None:
                            continue
                        key = (scope, _name(player.get("name")), _position(player.get("slot")))
                        metadata[key] = {field: deepcopy(player.get(field, _unknown_metadata()[field]))
                                         for field in METADATA_FIELDS}
                    with self._lock:
                        self._metadata = metadata
                        self._updated = self.clock()
                        self._status = status
                        self._valid_for = valid_for
                except Exception as error:
                    with self._lock:
                        self._metadata, self._updated = {}, None
                        self._valid_for = 0
                        self._status = {"available": False, "error": type(error).__name__}
                next_refresh = self.clock() + self.interval

    def apply_cached(self, payload):
        result = deepcopy(payload)
        with self._lock:
            metadata, updated, status = self._metadata.copy(), self._updated, deepcopy(self._status)
            valid_for = self._valid_for
        age = self.clock() - updated if updated is not None else None
        fresh = (not self.stop_event.is_set() and age is not None
                 and 0 <= age < valid_for and status.get("available") is True)
        for scope, player in _scoped_player_rows(result):
            key = (scope, _name(player.get("name")), _position(player.get("slot")))
            player.update(deepcopy(metadata.get(key, _unknown_metadata())) if fresh else _unknown_metadata())
        if isinstance(result, dict):
            status["available"] = bool(fresh and status.get("available"))
            status["cacheAgeSeconds"] = age
            result["nflLive"] = status
        return result

    def close(self, timeout=1):
        self.stop_event.set()
        self.wake_event.set()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=max(0, min(2, float(timeout))))
