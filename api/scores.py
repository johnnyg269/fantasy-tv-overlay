"""Vercel's bounded HTTPS entrypoint. It does not connect to a television."""

from http.server import BaseHTTPRequestHandler
import json
import threading
from backend.config import ConfigurationError
from backend.service import FeedService, write_response


_service = None
_lock = threading.Lock()


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _service
        try:
            with _lock:
                if _service is None:
                    _service = FeedService()
            write_response(self, _service)
        except ConfigurationError:
            body = json.dumps({"ok": False, "error": "Feed is not configured"}).encode("utf-8")
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format, *args):
        pass
