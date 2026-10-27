#!/usr/bin/env python3
"""Request an allowlisted command from this folder's running overlay companion.

Uses a private local JSON file only. It opens no network listener and never
evaluates a shell command or sends signals to other processes.
"""

import argparse
import json
import os
from pathlib import Path
import tempfile
import time
import uuid


ALLOWED_COMMANDS = frozenset(("auto", "hide", "show", "preview", "quit",
                              "toggle", "compact", "expanded"))
REQUEST_PATH = Path(__file__).resolve().parent / ".local/control-request.json"
MAX_REQUEST_BYTES = 4096


def write_request(command, request_path=None):
    if command not in ALLOWED_COMMANDS:
        raise ValueError("Command is not allowed")
    path = REQUEST_PATH if request_path is None else Path(request_path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    request = {"command": command, "nonce": uuid.uuid4().hex,
               "issuedAtNS": time.time_ns()}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=str(path.parent), prefix=".control-",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(request, stream, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    return request


def take_request(request_path, launched_at_ns):
    """Atomically claim one file, validate it, then delete that claimed copy.

    Claiming with rename ensures a newer request cannot be deleted while the
    companion is reading the old one. Stale/invalid requests are discarded
    without executing anything. A quit left by an earlier launch is harmless.
    """
    path = Path(request_path)
    claimed = path.with_name(".control-consuming-" + uuid.uuid4().hex + ".json")
    try:
        os.replace(str(path), str(claimed))
    except FileNotFoundError:
        return None
    try:
        with claimed.open("rb") as stream:
            content = stream.read(MAX_REQUEST_BYTES + 1)
        if len(content) > MAX_REQUEST_BYTES:
            return None
        request = json.loads(content.decode("utf-8"))
        if not isinstance(request, dict):
            return None
        command = request.get("command")
        nonce = request.get("nonce")
        issued = request.get("issuedAtNS")
        if (not isinstance(command, str) or command not in ALLOWED_COMMANDS
                or not isinstance(nonce, str) or not 1 <= len(nonce) <= 128
                or isinstance(issued, bool) or not isinstance(issued, int)
                or issued < launched_at_ns):
            return None
        return {"command": command, "nonce": nonce, "issuedAtNS": issued}
    except (OSError, ValueError, UnicodeError):
        return None
    finally:
        try:
            claimed.unlink()
        except FileNotFoundError:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=sorted(ALLOWED_COMMANDS),
                        default="quit")
    args = parser.parse_args(argv)
    try:
        write_request(args.command)
    except (OSError, ValueError) as error:
        print("Could not request overlay control: " + str(error))
        return 1
    if args.command == "quit":
        print("Stop requested. The running overlay companion will hide the "
              "overlay and finish its cleanup.")
    else:
        print("Requested overlay command: " + args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
