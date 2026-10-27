"""Load private configuration without printing values or evaluating shell text."""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
from typing import Optional


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class League:
    provider: str
    id: str
    team_id: int
    season: int
    label: str
    week: Optional[int] = None
    owner_names: dict = field(default_factory=dict, repr=False)

    @property
    def key(self):
        return self.provider + ":" + self.id


@dataclass(frozen=True)
class Config:
    leagues: tuple
    feed_token: str = field(repr=False)
    espn_s2: str = field(default="", repr=False)
    swid: str = field(default="", repr=False)
    sleeper_players_file: str = "runtime-data/sleeper-players.json"


def _secret(value, name, cookie=False):
    if not isinstance(value, str) or len(value) > 16384:
        raise ConfigurationError(name + " has an invalid format")
    if any(ord(char) < 33 or ord(char) > 126 for char in value):
        raise ConfigurationError(name + " contains invalid characters")
    if cookie and any(char in value for char in ";\r\n"):
        raise ConfigurationError(name + " contains invalid characters")
    return value


def parse_leagues(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            raise ConfigurationError("League settings must be a JSON array") from None
    if not isinstance(value, list) or not 1 <= len(value) <= 4:
        raise ConfigurationError("Configure one to four leagues")
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise ConfigurationError("Each league must be an object")
        provider = item.get("provider", "espn")
        if provider not in ("espn", "sleeper"):
            raise ConfigurationError("Provider needs an implemented, registered adapter")
        league_id = str(item.get("id", ""))
        if not re.fullmatch(r"[1-9][0-9]{0,23}", league_id):
            raise ConfigurationError("League ID must contain only digits")
        team_id = item.get("teamId")
        season = item.get("season")
        week = item.get("week")
        if type(team_id) is not int or not 1 <= team_id <= 10000:
            raise ConfigurationError("teamId must be the actual team or roster ID")
        if type(season) is not int or not 2019 <= season <= 2100:
            raise ConfigurationError("Set the fantasy season year")
        if week is not None and (type(week) is not int or not 1 <= week <= 30):
            raise ConfigurationError("Optional week must be between 1 and 30")
        label = item.get("label", "Fantasy")
        if not isinstance(label, str) or not label.strip() or len(label) > 60:
            raise ConfigurationError("League label must be 1–60 characters")
        owners = item.get("ownerNames", {})
        if not isinstance(owners, dict) or len(owners) > 100 or any(
                not isinstance(key, str) or not key.isdigit() or not isinstance(person, str)
                or not person.strip() or len(person) > 60 for key, person in owners.items()):
            raise ConfigurationError("ownerNames must map team IDs to display names")
        result.append(League(provider, league_id, team_id, season, label.strip(), week, owners))
    if len({league.key for league in result}) != len(result):
        raise ConfigurationError("A league may only be configured once")
    return tuple(result)


def load_config(environ=None, path=None):
    env = os.environ if environ is None else environ
    raw = {}
    # A serverless deployment uses environment secrets only. Never read a local
    # development account file accidentally included in a deployment.
    if not env.get("VERCEL"):
        config_path = Path(path or env.get("FANTASY_CONFIG", ".private/config.json"))
        if config_path.exists():
            try:
                if config_path.stat().st_size > 65536:
                    raise ConfigurationError("Private configuration is too large")
                raw = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise ConfigurationError("Cannot read private configuration") from None
            if not isinstance(raw, dict):
                raise ConfigurationError("Private configuration must be an object")
    leagues = parse_leagues(env.get("FANTASY_LEAGUES_JSON", raw.get("leagues")))
    token = _secret(env.get("FANTASY_FEED_TOKEN", raw.get("feedToken", "")), "Feed token")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token):
        raise ConfigurationError("Generate a feed token of at least 32 URL-safe characters")
    s2 = _secret(env.get("ESPN_S2", raw.get("espnS2", "")), "ESPN_S2", True)
    swid = _secret(env.get("SWID", raw.get("swid", "")), "SWID", True)
    if bool(s2) != bool(swid):
        raise ConfigurationError("Private ESPN access needs both ESPN_S2 and SWID")
    return Config(leagues, token, s2, swid,
                  env.get("FANTASY_SLEEPER_PLAYERS_FILE", raw.get(
                      "sleeperPlayersFile", "runtime-data/sleeper-players.json")))
