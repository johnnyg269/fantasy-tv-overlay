#!/usr/bin/env python3
"""Check your feed without printing its token, account IDs, or manager names."""

import argparse
import ipaddress
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.config import load_config
from backend.http_client import NoRedirect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--allow-loopback-http", action="store_true")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    url = urlsplit(args.endpoint)
    try:
        loopback = ipaddress.ip_address(url.hostname).is_loopback
    except ValueError:
        loopback = False
    if (url.username or url.password or url.query or url.fragment or url.path != "/api/scores"
            or not url.hostname or (url.scheme != "https" and not (
                args.allow_loopback_http and url.scheme == "http" and loopback))):
        parser.error("Use an HTTPS /api/scores URL; explicit numeric loopback HTTP is for local checks only")
    headers = {"Accept": "application/json"}
    if not args.demo:
        headers["Authorization"] = "Bearer " + load_config().feed_token
    with build_opener(NoRedirect()).open(Request(args.endpoint, headers=headers), timeout=30) as response:
        body = response.read(2 * 1024 * 1024 + 1)
    if len(body) > 2 * 1024 * 1024:
        raise ValueError("Feed is too large")
    data = json.loads(body)
    if data.get("ok") is not True or not isinstance(data.get("leagues"), list):
        raise ValueError("Feed is unavailable")
    rows = sum(len(league.get(side, {}).get("players", [])) for league in data["leagues"] for side in ("me", "opp"))
    print("Feed validated: " + str(len(data["leagues"])) + " matchups, " + str(rows) + " starting-player rows. Account details and token withheld.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Feed check failed. Check private settings, HTTPS access, and provider availability locally; no request details are logged.", file=sys.stderr)
        raise SystemExit(2)
