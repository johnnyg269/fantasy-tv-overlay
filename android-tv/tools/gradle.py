#!/usr/bin/env python3
"""Small source-only Gradle launcher; verifies the pinned official distribution.

Requires Python 3.9+ and JDK 17. No Gradle wrapper JAR or build outputs are checked in.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

VERSION = "8.11.1"
SHA256 = "f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6"
URL = f"https://services.gradle.org/distributions/gradle-{VERSION}-bin.zip"


def main() -> int:
    project = Path(__file__).resolve().parents[1]
    base = Path(os.environ.get("GRADLE_USER_HOME", str(Path.home() / ".gradle"))) / "fantasy-tv-distributions"
    target = base / f"gradle-{VERSION}"
    executable = target / "bin" / ("gradle.bat" if os.name == "nt" else "gradle")
    if not executable.is_file():
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="gradle-download-", dir=base) as scratch:
            scratch = Path(scratch)
            archive = scratch / "gradle.zip"
            digest = hashlib.sha256()
            with urllib.request.urlopen(URL, timeout=60) as response, archive.open("wb") as destination:
                while chunk := response.read(1024 * 1024):
                    destination.write(chunk)
                    digest.update(chunk)
            if digest.hexdigest() != SHA256:
                raise SystemExit("Gradle distribution checksum mismatch; refusing to execute it.")
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    path = (scratch / member.filename).resolve()
                    if not path.is_relative_to(scratch.resolve()):
                        raise SystemExit("Invalid Gradle archive path.")
                bundle.extractall(scratch)
            source = scratch / f"gradle-{VERSION}"
            if os.name != "nt":
                (source / "bin" / "gradle").chmod(0o755)
            try:
                source.rename(target)
            except FileExistsError:
                if not executable.is_file():
                    raise
    if os.name == "nt":
        return subprocess.call([str(executable), *sys.argv[1:]], cwd=project, shell=False)
    os.chdir(project)
    os.execv(str(executable), [str(executable), *sys.argv[1:]])
    return 1

if __name__ == "__main__":
    sys.exit(main())
