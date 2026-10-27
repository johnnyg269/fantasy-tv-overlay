#!/usr/bin/env python3
"""Local account wizard. Secrets are entered privately, never as CLI arguments."""

import argparse
from datetime import datetime
import getpass
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.config import ConfigurationError, load_config


def write_private(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    # Exclusive creation prevents accidentally overwriting an existing account.
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Explain account-free demo; writes no settings")
    args = parser.parse_args()
    if args.demo:
        print("No account or TV needed. From the repo root run:\n  python3 -m backend.server --demo\nThen open http://127.0.0.1:8787/api/scores for synthetic data.\nFor the TV demo, follow your platform README.")
        return
    if not sys.stdin.isatty():
        parser.exit(2, "Run this wizard yourself in a terminal. Never paste credentials into an agent chat.\n")
    target = ROOT / ".private/config.json"
    if target.exists():
        parser.exit(2, "Private settings already exist. Edit them locally or move them aside deliberately.\n")
    print("Fantasy TV private setup\nRead docs/fantasy-providers.md first. No password is requested.\nSettings stay in a git-ignored private file; do not attach it to an issue or chat.")
    leagues = []
    while True:
        provider = input("Provider [espn/sleeper]: ").strip().lower()
        league_id = input("League ID (from your own league): ").strip()
        team_id = int(input("Your actual ESPN team ID / Sleeper roster ID: ").strip())
        season = int(input("Season year [" + str(datetime.now().year) + "]: ").strip() or datetime.now().year)
        label = input("Short display label [Fantasy]: ").strip() or "Fantasy"
        leagues.append({"provider": provider, "id": league_id, "teamId": team_id, "season": season, "label": label})
        if input("Add another league? [y/N]: ").strip().lower() != "y":
            break
    settings = {"leagues": leagues, "feedToken": secrets.token_urlsafe(32)}
    if any(league["provider"] == "espn" for league in leagues):
        if input("Does ESPN require your account to view this league? [y/N]: ").strip().lower() == "y":
            settings["espnS2"] = getpass.getpass("ESPN espn_s2 cookie (hidden): ").strip()
            settings["swid"] = getpass.getpass("ESPN SWID cookie (hidden): ").strip()
    # Validate in memory before saving. An empty environment prevents unrelated
    # shell settings from changing what was just entered.
    from backend.config import parse_leagues, _secret
    parse_leagues(settings["leagues"])
    for key in ("espnS2", "swid"):
        _secret(settings.get(key, ""), key, True)
    if bool(settings.get("espnS2")) != bool(settings.get("swid")):
        raise ConfigurationError("Private ESPN access requires both cookie values")
    write_private(target, settings)
    load_config(environ={}, path=target)
    print("Saved private settings. The feed token was generated and was not printed.\nNext: python3 -m backend.server\nValidate: python3 tools/check_feed.py --endpoint http://127.0.0.1:8787/api/scores --allow-loopback-http")
    if any(league["provider"] == "sleeper" for league in leagues):
        print("Sleeper also needs its public player catalog: python3 tools/cache_sleeper_players.py")
    if os.name == "nt":
        print("Windows: also restrict .private to your own user with Windows file permissions.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, ConfigurationError):
        print("Settings are invalid; check the provider guide. No secret values are logged.", file=sys.stderr)
        raise SystemExit(2)
    except (EOFError, KeyboardInterrupt):
        print("\nSetup cancelled.", file=sys.stderr)
        raise SystemExit(130)
