"""Bounded HTTPS score reads with a separate bearer secret and no redirects."""

import ipaddress
import json
import os
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from sidebar_scene import starter_players


MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        # In particular, never forward a feed credential to a redirect target.
        raise ValueError("Score endpoint redirects are not permitted")


def validate_endpoint(endpoint, allow_loopback_http=False):
    if not isinstance(endpoint, str) or not 1 <= len(endpoint) <= 2048:
        raise ValueError("Set your own score endpoint")
    if any(ord(character) < 33 or ord(character) == 127 for character in endpoint):
        raise ValueError("Score endpoint contains invalid characters")
    url = urlsplit(endpoint)
    try:
        port = url.port
    except ValueError:
        raise ValueError("Score endpoint has an invalid port") from None
    if (not url.hostname or url.username is not None or url.password is not None
            or url.fragment or url.query or url.hostname.endswith(".")):
        raise ValueError("Use a score URL without credentials, queries or fragments")
    loopback = False
    try:
        loopback = ipaddress.ip_address(url.hostname).is_loopback
    except ValueError:
        pass
    if url.scheme != "https" and not (
            allow_loopback_http and url.scheme == "http" and loopback):
        raise ValueError("HTTPS is required; the explicit demo exception is loopback HTTP only")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Score endpoint has an invalid port")
    return endpoint


def fetch_scores(endpoint, *, allow_loopback_http=False, token=None):
    validate_endpoint(endpoint, allow_loopback_http)
    secret = os.environ.get("FANTASY_FEED_TOKEN", "") if token is None else token
    if secret and (not isinstance(secret, str) or not 32 <= len(secret) <= 512
                   or any(ord(character) < 33 or ord(character) > 126 for character in secret)):
        raise ValueError("Feed token must contain 32..512 printable non-space ASCII characters")
    if not secret and urlsplit(endpoint).scheme == "https":
        raise ValueError("Set FANTASY_FEED_TOKEN for your private score feed")
    headers = {"Accept": "application/json", "User-Agent": "FantasyTV/1.0"}
    if secret:
        headers["Authorization"] = "Bearer " + secret
    request = Request(endpoint, headers=headers)
    with build_opener(NoRedirect).open(request, timeout=8) as response:
        content = response.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError("Score response exceeds 2 MiB")
    try:
        payload = json.loads(content.decode("utf-8"))
    except RecursionError:
        raise ValueError("Score response is too deeply nested") from None
    if (not isinstance(payload, dict) or not isinstance(payload.get("leagues"), list)
            or not 1 <= len(payload["leagues"]) <= 2):
        raise ValueError("This Samsung layout supports one or two leagues; select at most two in your private feed")
    for league in payload["leagues"]:
        if not isinstance(league, dict):
            raise ValueError("Invalid league entry")
        for side in ("me", "opp"):
            team = league.get(side)
            if not isinstance(team, dict):
                raise ValueError("Invalid matchup entry")
            players = team.get("players", [])
            if not isinstance(players, list) or len(players) > 100:
                raise ValueError("Lineup response exceeds the safe roster bound")
            if len(starter_players(team, limit=None)) > 9:
                raise ValueError("This Samsung layout supports at most nine starters per side; larger lineups are not yet supported")
    return payload
