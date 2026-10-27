import fcntl
import http.client
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from private_config import load_private_json
from relay import CompanionOffline, CompanionTarget, RelayApplication, RelayServer, ReplayStore
from voice_protocol import encode_request, make_request, signature

SECRET = bytes.fromhex("a1" * 32)
NOW = 1800000000


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        self.db_path = self.private / "replay.sqlite3"
        self.target = Mock()
        self.store = ReplayStore(self.db_path)
        self.app = RelayApplication(SECRET, self.store, self.target, clock=lambda: NOW)

    def tearDown(self):
        self.folder.cleanup()

    def submit(self, request=None, signed=None):
        request = request or make_request("request-12345678", NOW)
        return self.app.accept(encode_request(request), signed or signature(request, SECRET))

    def test_valid_request_is_queued_once_and_survives_restart(self):
        self.assertEqual(self.submit(), (202, {"status": "queued"}))
        self.app.store = ReplayStore(self.db_path)
        self.assertEqual(self.submit(), (200, {"status": "duplicate"}))
        self.target.assert_called_once_with()
        self.assertEqual(self.db_path.stat().st_mode & 0o777, 0o600)

    def test_crash_reservation_is_not_replayed_or_claimed_as_queued(self):
        with sqlite3.connect(str(self.db_path)) as db:
            db.execute("INSERT INTO requests VALUES (?, ?, 'reserved')", ("request-12345678", NOW))
        self.app.store = ReplayStore(self.db_path)
        self.assertEqual(self.submit(), (409, {"status": "unconfirmed"}))
        self.target.assert_not_called()

    def test_tampered_request_is_rejected(self):
        original = make_request("request-12345678", NOW)
        changed = dict(original, requestId="request-87654321")
        self.assertEqual(self.submit(changed, signature(original, SECRET))[0], 401)
        self.target.assert_not_called()

    def test_only_preview_is_possible_even_with_valid_signature(self):
        for action in ("quit", "show", "expanded", "auto", "preview; quit"):
            request = dict(make_request("request-12345678", NOW), action=action)
            self.assertEqual(self.submit(request)[0], 401)
        self.target.assert_not_called()

    def test_expired_future_bool_extra_and_duplicate_fields_are_rejected(self):
        for changes in ({"timestamp": NOW - 31}, {"timestamp": NOW + 6},
                        {"timestamp": True}, {"version": True}, {"extra": "x"}):
            request = dict(make_request("request-12345678", NOW), **changes)
            signed = signature(request, SECRET)
            self.assertEqual(self.submit(request, signed)[0], 401)
        duplicate = b'{"version":1,"version":1,"timestamp":1800000000,"requestId":"request-12345678","action":"preview"}'
        self.assertEqual(self.app.accept(duplicate, "v1=" + "0" * 64)[0], 401)
        self.target.assert_not_called()

    def test_missing_signature_malformed_json_and_oversize_fail_closed(self):
        valid = encode_request(make_request("request-12345678", NOW))
        for body, signed in ((valid, ""), (b"{", "v1=" + "0" * 64),
                             (b"x" * 1025, "v1=" + "0" * 64)):
            self.assertEqual(self.app.accept(body, signed)[0], 401)
        self.target.assert_not_called()

    def test_offline_does_not_leave_a_success_record_and_can_retry(self):
        self.target.side_effect = CompanionOffline()
        self.assertEqual(self.submit(), (503, {"status": "offline"}))
        self.target.side_effect = None
        self.assertEqual(self.submit(), (202, {"status": "queued"}))

    def test_burst_with_new_request_id_is_limited(self):
        self.assertEqual(self.submit()[0], 202)
        self.assertEqual(self.submit(make_request("request-87654321", NOW))[0], 429)
        self.target.assert_called_once_with()

    def test_database_directory_must_be_private(self):
        self.private.chmod(0o755)
        with self.assertRaises(ValueError):
            ReplayStore(self.db_path)

    def test_configuration_permissions_are_enforced(self):
        config = self.private / "mac.json"
        config.write_text('{"secret_hex":"not-a-real-secret"}')
        config.chmod(0o644)
        with self.assertRaises(ValueError):
            load_private_json(config)
        config.chmod(0o600)
        self.assertIn("secret_hex", load_private_json(config))

    def test_server_cannot_bind_to_lan(self):
        with self.assertRaises(ValueError):
            RelayServer(("0.0.0.0", 0), self.app)

    def test_http_methods_paths_size_and_valid_post(self):
        server = RelayServer(("127.0.0.1", 0), self.app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        def exchange(method, path, body=b"", headers=None):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            try:
                connection.request(method, path, body=body, headers=headers or {})
                reply = connection.getresponse()
                result = reply.status, json.loads(reply.read())
                self.assertEqual(reply.getheader("Cache-Control"), "no-store")
                return result
            finally:
                connection.close()
        try:
            self.assertEqual(exchange("GET", "/fantasy/preview")[0], 405)
            self.assertEqual(exchange("POST", "/other")[0], 404)
            self.assertEqual(exchange("POST", "/fantasy/preview", b"{}")[0], 400)
            headers = {"Content-Type": "application/json", "X-Fantasy-Signature": "v1=" + "0" * 64}
            self.assertEqual(exchange("POST", "/fantasy/preview", b"x" * 1025, headers)[0], 413)
            request = make_request("request-12345678", NOW)
            headers["X-Fantasy-Signature"] = signature(request, SECRET)
            self.assertEqual(exchange("POST", "/fantasy/preview", encode_request(request), headers),
                             (202, {"status": "queued"}))
            self.target.assert_called_once_with()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_existing_helper_integration_writes_only_preview_to_temporary_app(self):
        # Copy the actual helper into a temporary fixture. No running application
        # or production control file is touched by this integration test.
        production_helper = HERE.parent / "send_control.py"
        if not production_helper.is_file():
            production_helper = HERE.parents[1] / "outputs/TVFantasyOverlay/app/send_control.py"
        app = self.root / "app"
        app.mkdir()
        shutil.copyfile(str(production_helper), str(app / "send_control.py"))
        (app / "run_tv.py").write_text("# fixture\n")
        local = app / ".local"
        local.mkdir(mode=0o700)
        target = CompanionTarget(app)
        with self.assertRaises(CompanionOffline):
            target()
        with (local / "runner.lock").open("w") as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            target()
            payload = json.loads((local / "control-request.json").read_text())
            self.assertEqual(payload["command"], "preview")
            with self.assertRaises(CompanionOffline):
                target()
        self.assertEqual(json.loads((local / "control-request.json").read_text())["command"], "preview")


if __name__ == "__main__":
    unittest.main()
