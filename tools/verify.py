#!/usr/bin/env python3
"""Offline functional checks. No account, TV, root, pairing, or Alexa invocation."""

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd=ROOT):
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
    print("Running " + " ".join(str(arg) for arg in args), flush=True)
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dotnet", help="Explicit .NET SDK executable")
    parser.add_argument("--require-native", action="store_true")
    parser.add_argument("--require-voice", action="store_true", help="Require optional Alexa handler SDK tests too")
    parser.add_argument("--android", action="store_true", help="Also compile/lint/test Android (official SDK/JDK needed)")
    args = parser.parse_args()
    run([sys.executable, "-m", "unittest", "discover", "-s", "backend/tests", "-v"])
    run([sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py", "-v"], ROOT / "samsung")
    if importlib.util.find_spec("ask_sdk_core") is not None:
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], ROOT / "samsung/alexa_bridge")
    elif args.require_voice:
        parser.exit(2, "Alexa handler checks require samsung/alexa_bridge/lambda/requirements.txt in your virtual environment.\n")
    else:
        for pattern in ("test_bridge.py", "test_relay_session.py"):
            run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v"], ROOT / "samsung/alexa_bridge")
        print("Alexa SDK handler tests skipped: install its optional test requirements to include them.")
    sdk = args.dotnet or shutil.which("dotnet")
    if sdk:
        run([sdk, "run", "--project", "samsung/checks/AlertPolicyChecks.csproj", "--configuration", "Release"])
        run([sdk, "build", "samsung/FantasyOverlay.csproj", "--configuration", "Release"])
    elif args.require_native:
        parser.exit(2, "Native checks require the documented .NET SDK.\n")
    else:
        print("Native .NET checks skipped: SDK not on PATH. Use --dotnet or --require-native in a configured environment.")
    if args.android:
        launcher = ["cmd", "/c", "gradlew.bat"] if os.name == "nt" else ["./gradlew"]
        run(launcher + ["--no-daemon", "testDebugUnitTest", "lintDebug", "assembleDebug"], ROOT / "android-tv")
    else:
        print("Android build skipped: use --android with JDK 17 and Android SDK 35.")
    run([sys.executable, "tools/audit_public_tree.py"])
    print("Requested offline checks passed. Physical-device behavior is a separate acceptance test.")


if __name__ == "__main__":
    main()
