"""Feed transport security uses synthetic loopback servers only."""
import io
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from feed_client import MAX_RESPONSE_BYTES, fetch_scores, validate_endpoint


class FeedClientTests(unittest.TestCase):
    def test_https_does_not_allow_url_embedded_secrets_or_queries(self):
        for value in (None, "", "https://user:pass@example.invalid/api/scores",
                      "https://example.invalid/api/scores?token=private",
                      "https://example.invalid/api/scores#secret", "https://example.invalid./api/scores",
                      "file:///tmp/scores.json", "https://example.invalid/\napi"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_endpoint(value)
        self.assertEqual(validate_endpoint("https://example.invalid/api/scores"),
                         "https://example.invalid/api/scores")

    def test_http_requires_explicit_numeric_loopback_exception(self):
        for value in ("http://127.0.0.1:8787/api/scores", "http://[::1]:8787/api/scores"):
            with self.assertRaises(ValueError):
                validate_endpoint(value)
            self.assertEqual(validate_endpoint(value, True), value)
        for value in ("http://localhost/api/scores", "http://192.0.2.5/api/scores",
                      "http://example.invalid/api/scores", "http://0.0.0.0/api/scores"):
            with self.assertRaises(ValueError):
                validate_endpoint(value, True)

    def test_private_https_requires_separate_valid_token_before_network(self):
        with patch.dict(os.environ, {}, clear=True), patch("feed_client.build_opener") as network:
            with self.assertRaises(ValueError):
                fetch_scores("https://example.invalid/api/scores")
            network.assert_not_called()
        for token in ("short", "a" * 32 + "\n", "a" * 513):
            with patch("feed_client.build_opener") as network, self.assertRaises(ValueError):
                fetch_scores("https://example.invalid/api/scores", token=token)
            network.assert_not_called()

    def test_bounded_response_and_bearer_header(self):
        class Response(io.BytesIO):
            pass
        payload = {"ok": True, "updated": 1000,
                   "leagues": [{"leagueId": "example", "me": {}, "opp": {}}]}
        with patch("feed_client.build_opener") as factory:
            factory.return_value.open.return_value = Response(json.dumps(payload).encode())
            self.assertEqual(fetch_scores("https://example.invalid/api/scores", token="z" * 64), payload)
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer " + "z" * 64)
            self.assertNotIn("z" * 64, request.full_url)
        with patch("feed_client.build_opener") as factory, self.assertRaises(ValueError):
            factory.return_value.open.return_value = Response(b"x" * (MAX_RESPONSE_BYTES + 1))
            fetch_scores("https://example.invalid/api/scores", token="z" * 64)

    def test_large_lineups_are_rejected_instead_of_silently_truncated(self):
        def fetch(payload):
            with patch("feed_client.build_opener") as factory:
                factory.return_value.open.return_value = io.BytesIO(json.dumps(payload).encode())
                return fetch_scores("https://example.invalid/api/scores", token="z" * 64)
        starters = [{"slot": "IDP", "name": "Example Player %d" % number} for number in range(9)]
        team = {"players": starters + [{"slot": "BE", "name": "Example Bench"}] * 10}
        payload = {"leagues": [{"me": team, "opp": {}}]}
        self.assertEqual(fetch(payload), payload)
        team["players"].append({"slot": "QB", "name": "Tenth Starter"})
        with self.assertRaisesRegex(ValueError, "nine starters"):
            fetch(payload)

    def test_more_than_two_leagues_are_rejected_instead_of_mislabelled_tabs(self):
        with patch("feed_client.build_opener") as factory, self.assertRaisesRegex(ValueError, "one or two leagues"):
            factory.return_value.open.return_value = io.BytesIO(json.dumps({
                "leagues": [{"me": {}, "opp": {}} for unused in range(3)]}).encode())
            fetch_scores("https://example.invalid/api/scores", token="z" * 64)

    def test_redirect_never_contacts_destination_or_forwards_authorization(self):
        destination_hits = []
        class Destination(BaseHTTPRequestHandler):
            def do_GET(self):
                destination_hits.append(self.headers.get("Authorization"))
                self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
            def log_message(self, *args): pass
        destination = ThreadingHTTPServer(("127.0.0.1", 0), Destination)
        target = "http://127.0.0.1:%d/target" % destination.server_address[1]
        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302); self.send_header("Location", target); self.end_headers()
            def log_message(self, *args): pass
        redirect = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        threads = [threading.Thread(target=server.serve_forever, daemon=True)
                   for server in (destination, redirect)]
        for thread in threads: thread.start()
        try:
            with self.assertRaises(ValueError):
                fetch_scores("http://127.0.0.1:%d/api/scores" % redirect.server_address[1],
                             allow_loopback_http=True, token="z" * 64)
            self.assertEqual(destination_hits, [])
        finally:
            for server in (redirect, destination): server.shutdown(); server.server_close()
            for thread in threads: thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
