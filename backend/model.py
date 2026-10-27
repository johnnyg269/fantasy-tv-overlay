"""The small renderer contract. Upstream account objects never pass through."""

import math
import unicodedata
from .http_client import ProviderError


STARTER_SLOTS = frozenset(("QB", "TQB", "RB", "WR", "TE", "FLEX", "RB/WR", "WR/TE",
                           "RB/WR/TE", "SUPERFLEX", "SUPER_FLEX", "OP", "D/ST", "DST",
                           "DEF", "K", "PK", "P", "HC", "DT", "DE", "DL", "LB", "CB",
                           "S", "DB", "DP", "IDP", "EDGE", "UTIL", "W/R", "W/T", "W/R/T"))


def text(value, limit=80):
    if not isinstance(value, str):
        return ""
    return " ".join("".join(c if c.isprintable() and unicodedata.category(c) != "Cf"
                            else " " for c in value).split())[:limit]


def number(value, required=False):
    try:
        result = float(value) if not isinstance(value, bool) and value is not None else None
    except (ValueError, TypeError, OverflowError):
        result = None
    if result is None or not math.isfinite(result) or abs(result) > 100000:
        if required:
            raise ProviderError("Provider score is missing or invalid")
        return None
    return round(result, 2)


def team(team_id, owner, name, score, projected, players):
    person = text(owner, 60) or "Owner unavailable"
    return {"teamId": str(team_id), "ownerName": person, "displayLabel": person,
            "name": text(name, 60) or "Fantasy team", "score": number(score, True),
            "proj": number(projected), "players": players}


def matchup(config, week, me, opp):
    if type(week) is not int or not 1 <= week <= 30:
        raise ProviderError("Provider week is unavailable")
    # Providers without a trustworthy win-probability field get an honest
    # unavailable bar. No fabricated probability or undocumented scoring model.
    return {"leagueId": config.key, "leagueName": text(config.label, 60),
            "short": text(config.label, 26), "week": week, "seasonId": config.season,
            "provider": config.provider, "ok": True, "me": me, "opp": opp,
            "winProb": None}
