#!/usr/bin/env python3
"""Create an Alexa console code-import ZIP. Does not upload or modify an account."""

import argparse
import os
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-config", type=Path)
    args = parser.parse_args()
    output = args.output.expanduser().absolute()
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(str(output), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in ("lambda_function.py", "skill_logic.py", "requirements.txt"):
                archive.write(str(HERE / "lambda" / name), "lambda/" + name)
            archive.write(str(HERE / "voice_protocol.py"), "lambda/voice_protocol.py")
            if args.private_config:
                from private_config import load_private_json
                load_private_json(args.private_config)
                archive.write(str(args.private_config), "lambda/private_config.json")
    print("Created code-import ZIP. Keep it private if it contains configuration.")


if __name__ == "__main__":
    main()
