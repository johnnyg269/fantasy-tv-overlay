"""Loopback development/companion feed. Use an HTTPS reverse proxy remotely."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from .config import ConfigurationError
from .service import FeedService, write_response


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def handler_for(service):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FantasyTV"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def do_GET(self):
            write_response(self, service)

        def log_message(self, format, *args):
            pass  # Query strings and auth headers never reach an access log.

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Synthetic loopback-only data; no accounts or TV")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port from 1024 through 65535")
    try:
        service = FeedService(demo=args.demo)
    except ConfigurationError as error:
        parser.exit(2, str(error) + ". Run python3 tools/setup.py.\n")
    server = LocalServer(("127.0.0.1", args.port), handler_for(service))
    print("Fantasy TV " + ("synthetic demo" if args.demo else "private feed") + " listening on loopback port " + str(args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
