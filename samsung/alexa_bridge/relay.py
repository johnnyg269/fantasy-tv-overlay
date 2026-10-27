#!/usr/bin/env python3
"""Loopback-only authenticated fantasy-preview relay. Python 3.9+, stdlib only."""

import argparse
from contextlib import contextmanager
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from private_config import load_private_json
from voice_protocol import MAX_BODY_BYTES, InvalidRequest, secret_bytes, verify

PATH = "/fantasy/preview"
NONCE_TTL_SECONDS = 600


class CompanionOffline(RuntimeError):
    pass


class CompanionTarget:
    """Import the existing helper and submit one fixed command; never run a shell."""

    def __init__(self, app_dir):
        self.app_dir = Path(app_dir).expanduser().resolve(strict=True)
        helper = self.app_dir / "send_control.py"
        if not helper.is_file() or not (self.app_dir / "run_tv.py").is_file():
            raise ValueError("Choose the existing overlay app directory")
        spec = importlib.util.spec_from_file_location("fantasy_existing_send_control", str(helper))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.write_request = module.write_request
        self.request_path = self.app_dir / ".local/control-request.json"

    def __call__(self):
        # The existing runner holds this flock for its entire lifetime. Checking
        # it does not create a lock file or start/restart/control the runner.
        try:
            with (self.app_dir / ".local/runner.lock").open("r") as stream:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                    raise CompanionOffline("Companion is not running")
        except FileNotFoundError:
            raise CompanionOffline("Companion is not running")
        if self.request_path.exists():
            raise CompanionOffline("A companion control request is already pending")
        self.write_request("preview")


class ReplayStore:
    """Reserve before dispatch so a crash cannot turn a retry into a second action."""

    def __init__(self, path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ValueError("Replay database cannot be a symlink")
        if self.path.parent.stat().st_mode & 0o077:
            raise ValueError("Replay database directory must be private (0700)")
        fd = os.open(str(self.path), os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        os.chmod(str(self.path), 0o600)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, created INTEGER NOT NULL, state TEXT NOT NULL)")
        self.lock = threading.Lock()

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=2)
        try:
            with db:
                yield db
        finally:
            db.close()

    def dispatch(self, request, target, now):
        with self.lock:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM requests WHERE created < ?", (now - NONCE_TTL_SECONDS,))
                previous = db.execute("SELECT state FROM requests WHERE id=?", (request["requestId"],)).fetchone()
                if previous:
                    return (200, "duplicate") if previous[0] == "queued" else (409, "unconfirmed")
                recent = db.execute("SELECT 1 FROM requests WHERE created > ? LIMIT 1", (now - 1,)).fetchone()
                if recent:
                    return 429, "busy"
                db.execute("INSERT INTO requests VALUES (?, ?, 'reserved')", (request["requestId"], now))
            try:
                target()
            except (CompanionOffline, OSError):
                with self._connect() as db:
                    db.execute("DELETE FROM requests WHERE id=?", (request["requestId"],))
                return 503, "offline"
            with self._connect() as db:
                db.execute("UPDATE requests SET state='queued' WHERE id=?", (request["requestId"],))
            return 202, "queued"


class RelayApplication:
    def __init__(self, secret, store, target, clock=time.time):
        self.secret, self.store, self.target, self.clock = secret, store, target, clock

    def accept(self, body, supplied_signature):
        now = int(self.clock())
        try:
            request = verify(body, supplied_signature, self.secret, now)
        except InvalidRequest:
            return 401, {"status": "rejected"}
        try:
            code, status = self.store.dispatch(request, self.target, now)
        except (sqlite3.Error, OSError):
            return 503, {"status": "unconfirmed"}
        return code, {"status": status}


class RelayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "FantasyPreview"
    sys_version = ""

    def setup(self):
        self.request.settimeout(3)
        super().setup()

    def _respond(self, code, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != PATH:
            return self._respond(404, {"status": "not_found"})
        lengths = self.headers.get_all("Content-Length", [])
        signatures = self.headers.get_all("X-Fantasy-Signature", [])
        if (len(lengths) != 1 or len(signatures) != 1 or self.headers.get("Transfer-Encoding")
                or self.headers.get_content_type() != "application/json"):
            return self._respond(400, {"status": "bad_request"})
        try:
            length = int(lengths[0])
        except ValueError:
            return self._respond(400, {"status": "bad_request"})
        if not 0 < length <= MAX_BODY_BYTES:
            return self._respond(413, {"status": "bad_request"})
        try:
            body = self.rfile.read(length)
            if len(body) != length:
                return self._respond(400, {"status": "bad_request"})
            code, result = self.server.application.accept(body, signatures[0])
            return self._respond(code, result)
        except (socket.timeout, BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def do_GET(self):
        self._respond(405, {"status": "method_not_allowed"})

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_GET

    def log_message(self, format_string, *args):
        # Never log headers, signed bodies, request IDs, account IDs or secrets.
        return


class RelayServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, application):
        if address[0] != "127.0.0.1":
            raise ValueError("Relay must bind to IPv4 loopback")
        self.application = application
        self.slots = threading.BoundedSemaphore(4)
        super().__init__(address, RelayHandler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        config = load_private_json(args.config)
        application = RelayApplication(secret_bytes(config["secret_hex"]),
                                       ReplayStore(config["replay_db"]),
                                       CompanionTarget(config["companion_app_dir"]))
        server = RelayServer(("127.0.0.1", 8767), application)
    except (OSError, KeyError, ValueError):
        parser.exit(2, "Bridge configuration is missing, invalid, or unavailable. No credentials were logged.\n")
    print("Fantasy voice relay listening on 127.0.0.1:8767; Funnel is not enabled by this program.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
