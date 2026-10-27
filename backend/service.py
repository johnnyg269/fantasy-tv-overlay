"""Authenticated feed service shared by local HTTP and the Vercel handler."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hmac
import json
import threading
import time
from .config import ConfigurationError, load_config
from .demo import scores as demo_scores
from .http_client import ProviderError
from .live import GameStatus
from .providers import espn, sleeper


ADAPTERS = {"espn": espn.fetch, "sleeper": sleeper.fetch}


class FeedService:
    def __init__(self, config=None, demo=False, clock=time.time, adapters=None, game_status=None):
        self.demo, self.clock = demo, clock
        self.config = None if demo else (config or load_config())
        self.adapters = ADAPTERS if adapters is None else adapters
        self.game_status = GameStatus(clock=clock) if game_status is None else game_status
        self.lock = threading.Lock()
        self.cached, self.next_attempt = None, float("-inf")

    def authorized(self, authorization):
        if self.demo:
            return True
        if not isinstance(authorization, str) or not authorization.startswith("Bearer ") or len(authorization) > 1024:
            return False
        supplied = authorization[7:]
        # Byte comparisons handle malformed non-ASCII headers without throwing.
        return hmac.compare_digest(supplied.encode("utf-8"), self.config.feed_token.encode("ascii"))

    def scores(self):
        if self.demo:
            # Deliberately change scores every 20 seconds for an observable
            # initial-baseline → score-change → five-second-hide demo.
            return demo_scores(self.clock(), int(self.clock() // 20) % 100)
        with self.lock:
            now = self.clock()
            if now < self.next_attempt and self.cached is not None:
                return deepcopy(self.cached)
            self.next_attempt = now + 5

            def read(league):
                try:
                    return self.adapters[league.provider](league, self.config)
                except Exception:
                    # Never serialize an exception or provider response. It can
                    # contain account objects, request headers, or private URLs.
                    raise ProviderError("Fantasy provider unavailable; check private settings locally") from None

            try:
                with ThreadPoolExecutor(max_workers=min(4, len(self.config.leagues))) as pool:
                    leagues = list(pool.map(read, self.config.leagues))
                result = {"ok": True, "schemaVersion": 1, "updated": self.clock(), "leagues": leagues}
                result = self.game_status.annotate(result)
                self.cached = result
            except ProviderError:
                # Do not freshen an old score timestamp or return partial data
                # as successful. Renderers retain their old baseline then hide.
                self.cached = {"ok": False, "error": "Fantasy provider unavailable", "leagues": []}
            # Cache from completion, so a slow provider cannot immediately
            # launch another full fetch for every request waiting on the lock.
            self.next_attempt = self.clock() + 5
            return deepcopy(self.cached)


def respond(service, path, authorization=None):
    headers = {"Cache-Control": "private, no-store, max-age=0", "Pragma": "no-cache",
               "Content-Type": "application/json; charset=utf-8", "X-Content-Type-Options": "nosniff"}
    if path == "/health":
        return 200, headers, {"ok": True}
    if path != "/api/scores":
        return 404, headers, {"ok": False, "error": "Not found"}
    if not service.authorized(authorization):
        return 401, {**headers, "WWW-Authenticate": "Bearer"}, {"ok": False, "error": "Unauthorized"}
    payload = service.scores()
    return (200 if payload.get("ok") is True else 503), headers, payload


def write_response(handler, service):
    # No token in query strings; only the exact route is accepted.
    status, headers, payload = respond(service, handler.path, handler.headers.get("Authorization"))
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    for key, value in headers.items():
        handler.send_header(key, value)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
