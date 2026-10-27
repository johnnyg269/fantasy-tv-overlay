#!/usr/bin/env python3
"""Launch Samsung companion with the local feed token kept out of CLI/chat."""

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.config import ConfigurationError, load_config


def main():
    args = sys.argv[1:]
    if not args or "--help" in args:
        print("Use the Samsung README/root setup first. Then replace 'python3 samsung/run_tv.py'\nwith 'python3 tools/run_samsung.py' in its launch command. All TV/model/root gates\nremain in force. This wrapper reads only your private backend feed token and\npasses it through the child environment; it never prints it or puts it in argv.")
        return
    try:
        token = load_config().feed_token
    except ConfigurationError:
        print("Create your own private backend configuration first with tools/setup.py.", file=sys.stderr)
        raise SystemExit(2)
    env = dict(os.environ, FANTASY_FEED_TOKEN=token)
    os.execve(sys.executable, [sys.executable, str(ROOT / "samsung/run_tv.py")] + args, env)


if __name__ == "__main__":
    main()
