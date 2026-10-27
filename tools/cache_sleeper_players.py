#!/usr/bin/env python3
"""Download Sleeper's public NFL catalog at most once per 24 hours locally."""

import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.http_client import ProviderError, get_json


def main():
    target = ROOT / "runtime-data/sleeper-players.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and time.time() - target.stat().st_mtime < 86400:
        print("The public player catalog is less than 24 hours old; no download needed.")
        return
    data = get_json("https://api.sleeper.app/v1/players/nfl", maximum=32 * 1024 * 1024)
    if not isinstance(data, dict) or not data:
        raise ProviderError("Player catalog must be a nonempty object")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(data, stream, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    os.replace(temporary, target)
    print("Saved the public NFL player catalog. Do not run again for 24 hours.\nThis ignored file contains public player metadata only; never store account settings in runtime-data.")


if __name__ == "__main__":
    try:
        main()
    except ProviderError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
