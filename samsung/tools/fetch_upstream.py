#!/usr/bin/env python3
"""Download/checksum the official pinned host tool. Never contacts a television."""

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.request

VERSION = "0.0.12"
COMMIT = "3b97edf3762db7670585d73e29623dc56195bf98"
SDB_HASH = "77c89d9a9f38566dfb2c5ef6a9fd371e54b9e3ca52a0feb3c05fd7cdd60ab153"
ARCHIVES = {
    ("Darwin", "arm64"): ("macos-arm64", "8ee4587462963f8ad0374f921e41050bd9198a7cb0b15899a5f35a7ad8f50f2c"),
    ("Darwin", "x86_64"): ("macos-x86_64", "78579899479550697971d2b2b5641673af2c2619006d286591fced3a1adf49b5"),
    ("Linux", "aarch64"): ("linux-arm64", "cb8297bf3d2ab277ccdcb2f1d20de216eeced37f85d67d77413099c0347dfa62"),
    ("Linux", "x86_64"): ("linux-x86_64", "f7aa3a3b550a65bc7d29b1b6b3fdcd3876fdcaa41dec4766f00ec7e3e64a3232"),
}
MAX_DOWNLOAD = 256 * 1024 * 1024
MAX_UNPACKED = 512 * 1024 * 1024


def safe_members(archive):
    members = archive.getmembers()
    if len(members) > 10000 or sum(member.size for member in members) > MAX_UNPACKED:
        raise ValueError("Release archive exceeds extraction bounds")
    for member in members:
        path = PurePosixPath(member.name)
        if (path.is_absolute() or ".." in path.parts or "\\" in member.name
                or not member.name or not (member.isdir() or member.isfile())):
            raise ValueError("Unsafe entry in release archive")
    return members


def check_install(folder):
    folder = Path(folder)
    module = folder / "source/src/samsung_tv_root/sdb.py"
    executable = folder / "samsung-tv-root"
    if (not executable.is_file() or not module.is_file()
            or hashlib.sha256(module.read_bytes()).hexdigest() != SDB_HASH):
        raise ValueError("Installed release is incomplete or the pinned SDB module differs")
    return executable, module


def download(destination):
    key = (platform.system(), platform.machine().lower())
    if key not in ARCHIVES:
        raise ValueError("This companion supports macOS/Linux arm64/x86_64. Use a supported host; Windows runtime is not packaged.")
    suffix, expected = ARCHIVES[key]
    name = "samsung-tv-root-%s-%s" % (VERSION, suffix)
    url = "https://github.com/chris-ritsen/samsung-tv-root/releases/download/v%s/%s.tar.gz" % (VERSION, name)
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Destination already exists; use --check-only to verify it")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".root-release-", dir=destination.parent) as temporary:
        temporary = Path(temporary)
        path = temporary / "release.tar.gz"
        request = urllib.request.Request(url, headers={"User-Agent": "FantasyTV-setup/1.0"})
        digest, total = hashlib.sha256(), 0
        with urllib.request.urlopen(request, timeout=30) as response, path.open("wb") as output:
            while True:
                block = response.read(64 * 1024)
                if not block:
                    break
                total += len(block)
                if total > MAX_DOWNLOAD:
                    raise ValueError("Release download exceeds the bounded size")
                digest.update(block)
                output.write(block)
        if digest.hexdigest() != expected:
            raise ValueError("Release checksum mismatch; nothing installed")
        unpacked = temporary / "unpacked"
        unpacked.mkdir(mode=0o700)
        with tarfile.open(path, "r:gz") as archive:
            # Explicit extraction avoids traversal, links, devices and setuid bits
            # on Python 3.9 as well as newer runtimes.
            for member in safe_members(archive):
                target = unpacked.joinpath(*PurePosixPath(member.name).parts)
                if member.isdir():
                    target.mkdir(mode=0o700, parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    source = archive.extractfile(member)
                    if source is None:
                        raise ValueError("Cannot read a release member")
                    with source, target.open("xb") as output:
                        shutil.copyfileobj(source, output, length=64 * 1024)
                    target.chmod(0o700 if member.mode & 0o111 else 0o600)
        installed = unpacked / name
        check_install(installed)
        installed.rename(destination)
    return check_install(destination)


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path,
                        default=Path(__file__).resolve().parents[1] / ".local/tools/samsung-tv-root")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        executable, module = check_install(args.destination) if args.check_only else download(args.destination)
        print("Pinned upstream v%s verified. No TV connection or root operation was made." % VERSION)
        print("ROOT_TOOL=" + str(executable))
        print("SDB_MODULE=" + str(module))
        return 0
    except (OSError, ValueError, tarfile.TarError) as error:
        print("Tool setup stopped: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
