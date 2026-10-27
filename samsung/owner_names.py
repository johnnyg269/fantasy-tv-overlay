"""Verified local person labels, scoped by ESPN league and actual team ID.

This module reads only a private .local/owner_names.json file. It does not contact
ESPN, read cookies, infer a manager from a fantasy-team nickname, or publish
personal names. League-table row numbers are never used as team IDs.
"""

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import unicodedata


SEASON = date.today().year
OWNER_UNAVAILABLE = "Owner unavailable"
DEFAULT_PATH = Path(__file__).resolve().parent / ".local/owner_names.json"


def _identity(value):
    if isinstance(value, bool) or value is None:
        return ""
    return str(value).strip()


def _person_name(value):
    if not isinstance(value, str):
        return ""
    # Prevent control characters from entering a display label, while keeping
    # the verified person's spelling and ordinary Unicode punctuation intact.
    clean = "".join(character if character.isprintable()
                    and unicodedata.category(character) != "Cf" else " "
                    for character in value)
    return " ".join(clean.split())[:80]


def load_owner_names(path=None, season=SEASON):
    """Load a stable local map once per controller creation.

    Return ``{leagueId: {teamId: personName}}``. A missing file or an explicitly
    different season produces an empty mapping, so labels remain honest.
    Malformed files raise ValueError and callers may fall back to the same
    unavailable label without treating this as a score-feed failure.
    """
    path = DEFAULT_PATH if path is None else Path(path)
    try:
        with path.open(encoding="utf-8") as stream:
            document = json.load(stream)
    except FileNotFoundError:
        return {}
    if not isinstance(document, dict) or document.get("schemaVersion") != 1:
        raise ValueError("owner mapping must use schemaVersion 1")
    if str(document.get("season")) != str(season):
        return {}
    leagues = document.get("leagues")
    if not isinstance(leagues, dict):
        raise ValueError("owner mapping needs a leagues object")
    result = {}
    for league_id, teams in leagues.items():
        if not isinstance(teams, dict):
            raise ValueError("owner mapping league entries must be team-ID objects")
        league = {}
        for team_id, value in teams.items():
            name = _person_name(value)
            if _identity(team_id) and name:
                league[_identity(team_id)] = name
        if _identity(league_id):
            result[_identity(league_id)] = league
    return result


def annotate_owner_names(payload, owner_mapping, season=SEASON):
    """Copy score data and annotate me/opp with verified person labels only.

    Original team names, abbreviations, scores, team IDs and NFL player names
    are preserved. ``ownerName`` and ``displayLabel`` both carry the person
    label; missing mappings carry OWNER_UNAVAILABLE instead of a team name.
    """
    if not isinstance(payload, dict):
        raise ValueError("score payload must be an object")
    result = deepcopy(payload)
    mapping = owner_mapping if isinstance(owner_mapping, dict) else {}
    declared_season = payload.get("seasonId", payload.get("season"))
    if isinstance(declared_season, dict):
        declared_season = declared_season.get("year")
    if declared_season is not None and str(declared_season) != str(season):
        mapping = {}
    leagues = result.get("leagues")
    if not isinstance(leagues, list):
        return result
    for league in leagues:
        if not isinstance(league, dict):
            continue
        teams = mapping.get(_identity(league.get("leagueId")), {})
        if not isinstance(teams, dict):
            teams = {}
        for side in ("me", "opp"):
            team = league.get(side)
            if not isinstance(team, dict):
                continue
            name = (_person_name(teams.get(_identity(team.get("teamId")))))
            # The normalized private backend already resolves the current
            # matchup's manager. A private local map may override that label.
            if not name:
                name = _person_name(team.get("ownerName")) or _person_name(team.get("displayLabel"))
            label = name or OWNER_UNAVAILABLE
            team["ownerName"] = label
            team["displayLabel"] = label
    return result
