"""Conservative Apple TV program context; importing this module never uses a network.

The CLI consumes local JSON only. The optional asynchronous adapter reads from
an ALREADY connected pyatv device only when explicitly called; it does not scan,
pair, send power commands, launch apps, send buttons, request artwork or control playback.
"""

import argparse
import asyncio
import json
import math
import re
import time
import unicodedata
from collections.abc import Mapping
from pathlib import Path


_ALIAS_KEYS = ("displayName", "shortDisplayName", "name", "abbreviation")
_MULTIGAME = re.compile(r"\bred\s*zone\b|\bmultiview\b|\bmulti\s+view\b", re.I)


def _clean(value):
    if not isinstance(value, str):
        return None
    clean = "".join(ch if ch.isprintable() and unicodedata.category(ch) != "Cf" else " "
                    for ch in value)
    clean = " ".join(clean.split())
    return clean or None


def _normal(value):
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def _team(value):
    if isinstance(value, str):
        value = {"abbreviation": value}
    if not isinstance(value, Mapping):
        return None
    aliases = tuple(dict.fromkeys(_clean(value.get(key)) for key in _ALIAS_KEYS
                                 if _clean(value.get(key))))
    if not aliases:
        return None
    identity = value.get("id")
    key = "id:" + str(identity) if identity is not None else "name:" + _normal(aliases[0])
    return {"key": key, "aliases": aliases}


def _games(scoreboard):
    if isinstance(scoreboard, list):
        events = scoreboard
    elif isinstance(scoreboard, Mapping):
        events = next((scoreboard[key] for key in ("events", "games", "nfl")
                       if isinstance(scoreboard.get(key), list)), [])
    else:
        events = []
    output = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        game_id = event.get("id", event.get("gameId"))
        if game_id is None or isinstance(game_id, bool):
            continue
        teams = []
        competitions = event.get("competitions")
        if isinstance(competitions, list) and competitions:
            competition = competitions[0]
            competitors = competition.get("competitors", []) if isinstance(competition, Mapping) else []
            teams = [_team(item.get("team")) for item in competitors if isinstance(item, Mapping)]
        else:
            teams = [_team(event.get("away", event.get("awayTeam"))),
                     _team(event.get("home", event.get("homeTeam")))]
        if len(teams) == 2 and all(teams) and teams[0]["key"] != teams[1]["key"]:
            output.append({"id": str(game_id), "teams": teams})
    return output


def _alias_present(alias, title):
    normalized = _normal(alias)
    if not normalized:
        return False
    # Short abbreviations such as NO/NE must appear as actual uppercase tokens,
    # not ordinary words such as "no" or "ne" in a program title.
    if re.fullmatch(r"[A-Za-z]{1,3}", alias):
        return bool(re.search(r"(?<![A-Za-z0-9])" + re.escape(alias.upper())
                              + r"(?![A-Za-z0-9])", title))
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(normalized)
                          + r"(?![a-z0-9])", _normal(title)))


def match_game_title(title, scoreboard):
    """Return one supplied scoreboard game ID only for an unambiguous team pair.

    No channel/app-to-team lookup, fuzzy matching, schedule inference, image
    recognition or previous-game carry-over is performed.
    """
    title = _clean(title)
    if not title or len(title) > 4096 or _MULTIGAME.search(title):
        return None
    games = _games(scoreboard)
    teams = {}
    for game in games:
        for team in game["teams"]:
            teams.setdefault(team["key"], set()).update(team["aliases"])
    matched = {key for key, aliases in teams.items()
               if any(_alias_present(alias, title) for alias in aliases)}
    if len(matched) != 2:
        return None
    matches = {game["id"] for game in games
               if {team["key"] for team in game["teams"]} == matched}
    return next(iter(matches)) if len(matches) == 1 else None


def build_context(metadata, scoreboard, manual_override=None):
    """Build the stable context envelope from explicit metadata and scoreboard.

    confidence is categorical: exact-title-pair, manual, or unknown. A match
    identifies a title's supplied team pair; it does not prove live video,
    playback latency, or which pane of a multiview is being watched.
    manual_override is a known scoreboard game ID, 'redzone', or None.
    """
    metadata = metadata if isinstance(metadata, Mapping) else {}
    app = metadata.get("app")
    if isinstance(app, Mapping):
        app = app.get("name") or app.get("identifier")
    title = _clean(metadata.get("title"))
    app = _clean(app)
    result = {"source": "apple-tv-metadata" if title or app else "unknown",
              "app": app, "title": title, "matchedGameId": None,
              "confidence": "unknown", "manualOverride": False}
    if manual_override is not None:
        selected = str(manual_override).strip()
        result.update(source="manual", manualOverride=True)
        if _normal(selected).replace(" ", "") == "redzone":
            result.update(source="manual-redzone", confidence="manual")
            return result
        known_ids = {game["id"] for game in _games(scoreboard)}
        if selected not in known_ids:
            raise ValueError("manual game ID is not present in the supplied NFL scoreboard")
        result.update(matchedGameId=selected, confidence="manual")
        return result
    match = match_game_title(title, scoreboard)
    if match is not None:
        result.update(matchedGameId=match, confidence="exact-title-pair")
    return result


def read_context_cache(path, now=None, max_age=60):
    """Read a complete worker envelope locally, failing closed on stale data.

    This function uses only the filesystem and the standard library, allowing
    the overlay's system Python to consume a separate pyatv runtime's cache.
    It never carries a previous title or game forward after any failure.
    """
    unknown = dict(build_context({}, {}), available=False, capturedAt=None,
                   status="unavailable", powerState="unknown")
    now = time.time() if now is None else now
    if (isinstance(now, bool) or not isinstance(now, (int, float))
            or not math.isfinite(now) or not 0 < max_age <= 3600):
        return unknown
    try:
        path = Path(path)
        if path.stat().st_size > 65536:
            return unknown
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return unknown
    if not isinstance(value, Mapping):
        return unknown
    captured = value.get("capturedAt")
    if (isinstance(captured, bool) or not isinstance(captured, (float, int))
            or not math.isfinite(captured) or not 0 <= now - captured <= max_age):
        return dict(unknown, status="stale")
    if (value.get("available") is not True or value.get("status") != "ok"
            or value.get("powerState") == "off"):
        return dict(unknown, capturedAt=captured,
                    status=value.get("status") if value.get("status") in {
                        "sleeping", "disconnected", "disabled", "expired", "starting",
                        "unavailable", "idle", "unpaired"} else "unavailable")
    app, title = _clean(value.get("app")), _clean(value.get("title"))
    if any(text and len(text) > 4096 for text in (app, title)) or not (app or title):
        return unknown
    confidence = value.get("confidence")
    manual = value.get("manualOverride") is True
    game_id = value.get("matchedGameId")
    if (confidence not in {"unknown", "exact-title-pair", "manual"}
            or manual != (confidence == "manual")
            or (game_id is not None and (not isinstance(game_id, str)
                                         or not game_id or len(game_id) > 256))
            or (confidence == "unknown" and game_id is not None)
            or (confidence == "exact-title-pair" and (game_id is None or not title))):
        return unknown
    return {"source": "manual-redzone" if manual and game_id is None else
                      "manual" if manual else "apple-tv-metadata",
            "app": app, "title": title, "matchedGameId": game_id,
            "confidence": confidence, "manualOverride": manual,
            "available": True, "capturedAt": captured, "status": "ok",
            "powerState": value.get("powerState") if value.get("powerState")
                          in {"on", "unknown"} else "unknown"}


async def read_connected_metadata(device, timeout=5.0):
    """Explicit read from an already connected pyatv AppleTV interface.

    Does not establish a connection or pair. The caller owns that lifecycle.
    Apple TV network requests can wake a sleeping device; enable this adapter
    only while the user is watching that Apple TV.
    """
    playing = await asyncio.wait_for(device.metadata.playing(), timeout=timeout)
    try:
        app = device.metadata.app
    except Exception:
        # The optional playing-app feature can be unavailable while title works.
        app = None
    return {"app": getattr(app, "name", None) or getattr(app, "identifier", None),
            "title": getattr(playing, "title", None)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Resolve TV context from local JSON; no device/network calls")
    parser.add_argument("--metadata", type=Path, help="local {app,title} JSON")
    parser.add_argument("--scoreboard", type=Path, required=True, help="local ESPN events or known-ID game list")
    parser.add_argument("--manual-game", help="known game ID or redzone; no automatic selection")
    args = parser.parse_args(argv)
    metadata = json.loads(args.metadata.read_text()) if args.metadata else {}
    scoreboard = json.loads(args.scoreboard.read_text())
    try:
        result = build_context(metadata, scoreboard, args.manual_game)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
