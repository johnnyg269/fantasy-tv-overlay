#!/usr/bin/env python3
"""Prepare new private configuration files; never print the shared secret."""

import argparse
import json
import os
from pathlib import Path
import secrets
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lambda"))
from skill_logic import validate_config


def write_new(path, data):
    with os.fdopen(os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--skill-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--relay-url", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    directory = args.directory.expanduser().absolute()
    app = args.app_dir.expanduser().resolve(strict=True)
    if not (app / "send_control.py").is_file() or not (app / "run_tv.py").is_file():
        parser.error("Choose the existing overlay app directory")
    config = validate_config({"expected_skill_id": args.skill_id, "allowed_user_id": args.user_id,
                              "relay_url": args.relay_url, "secret_hex": secrets.token_hex(32)})
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_new(directory / "mac.json", {"secret_hex": config["secret_hex"],
                                        "companion_app_dir": str(app),
                                        "replay_db": str(directory / "replay.sqlite3")})
    write_new(directory / "alexa.json", config)
    print("Created owner-only mac.json and alexa.json. The secret was not printed.")


if __name__ == "__main__":
    main()
