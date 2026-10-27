#!/usr/bin/env python3
"""Check tracked publication files; never inspect or print private file contents."""

from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PARTS = {".private", ".local", ".venv", ".vercel", "__pycache__", "node_modules", ".gradle", "obj", "bin", "build"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".heic", ".jpg", ".jpeg",
                      ".apk", ".aab", ".dll", ".exe", ".zip", ".log", ".pyc", ".dmg"}
BINARY_SUFFIXES = {".ttf", ".png"}
PATTERNS = [
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("personal home path", re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+/(?!share/|tmp/)")),
    ("cloud access token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16})\b")),
    ("private Alexa skill identifier", re.compile(r"amzn1\.ask\.skill\.[0-9a-f]{8}-[0-9a-f-]{27,}")),
    ("personal tunnel hostname", re.compile(r"[A-Za-z0-9-]+\.tail[a-z0-9]+\.ts\.net")),
]


def tracked():
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True)
    return [Path(item.decode("utf-8")) for item in result.stdout.split(b"\0") if item]


def inspect(paths):
    findings = []
    for relative in paths:
        path = ROOT / relative
        if path.is_symlink():
            findings.append((str(relative), "symbolic link is not permitted in the publication tree"))
            continue
        if any(part in PRIVATE_PARTS for part in relative.parts) or relative.suffix.lower() in FORBIDDEN_SUFFIXES:
            findings.append((str(relative), "private/generated material is tracked"))
            continue
        name = relative.name.lower()
        if name.startswith(".env") and name != ".env.example" or name in ("local.properties", "owner_names.json", "private_config.json"):
            findings.append((str(relative), "private settings file is tracked"))
            continue
        body = path.read_bytes()
        if relative.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            text = body.decode("utf-8")
        except UnicodeError:
            findings.append((str(relative), "unreviewed binary format"))
            continue
        for category, pattern in PATTERNS:
            if pattern.search(text):
                # A scanner's own regex source is not a secret value.
                if relative == Path("tools/audit_public_tree.py"):
                    continue
                findings.append((str(relative), category))
    return findings


def main():
    paths = tracked()
    if not paths:
        print("No tracked files. Stage the reviewed allowlist before auditing.", file=sys.stderr)
        return 2
    findings = inspect(paths)
    for path, category in findings:
        print(path + ": " + category)
    print("Publication boundary: " + str(len(paths)) + " tracked files, " + str(len(findings)) + " issues. Values withheld.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
