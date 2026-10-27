#!/usr/bin/env python3
"""Install a pinned official Android SDK into an isolated Linux CI runner.

No global SDK, sudo, shell interpolation or checked-in binaries are required.
A human reviewing the workflow must explicitly opt in to SDK license acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import tempfile
import urllib.request
import zipfile

# Android repository metadata (repository2-1.xml), cmdline-tools;19.0:
# official SHA-1 5fdcc763663eefb86a5b8879697aa6088b041e70, size 164760899.
# The archive was downloaded, matched to that metadata, then SHA-256 pinned here.
URL = "https://dl.google.com/android/repository/commandlinetools-linux-13114758_latest.zip"
SHA256 = "7ec965280a073311c339e571cd5de778b9975026cfcbe79f2b1cdcb1e15317ee"
SIZE = 164_760_899
PACKAGES = ("platforms;android-35", "build-tools;35.0.0", "platform-tools")


def verify_archive(path: Path, expected_size: int = SIZE, expected_sha256: str = SHA256) -> None:
    if path.stat().st_size != expected_size:
        raise ValueError("Android command-line tools archive size mismatch")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256:
        raise ValueError("Android command-line tools SHA-256 mismatch")


def safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > 5000 or sum(item.file_size for item in members) > 800 * 1024 * 1024:
            raise ValueError("Android tools archive exceeds extraction limits")
        for item in members:
            name = PurePosixPath(item.filename)
            if (name.is_absolute() or ".." in name.parts or "\\" in item.filename or ":" in item.filename
                    or not name.parts or name.parts[0] != "cmdline-tools"
                    or stat.S_ISLNK(item.external_attr >> 16) or item.file_size > 256 * 1024 * 1024):
                raise ValueError("Unsafe Android tools archive member")
            target = destination.joinpath(*name.parts).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("Unsafe Android tools extraction path")
        bundle.extractall(destination)
    tool = destination / "cmdline-tools" / "bin" / "sdkmanager"
    if not tool.is_file():
        raise ValueError("Android tools archive is missing sdkmanager")
    for executable in (destination / "cmdline-tools" / "bin").iterdir():
        if executable.is_file():
            executable.chmod(0o755)


def download(destination: Path) -> None:
    downloaded = 0
    with urllib.request.urlopen(URL, timeout=60) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            downloaded += len(chunk)
            if downloaded > SIZE:
                raise ValueError("Android tools download exceeds the pinned archive size")
            output.write(chunk)
    verify_archive(destination)


def run_manager(command: list[str], environment: dict[str, str], timeout: int) -> None:
    result = subprocess.run(command, input="y\n" * 100, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout, env=environment, check=False)
    if result.returncode:
        raise RuntimeError("Android SDK setup failed:\n" + result.stdout[-3000:])


def export_environment(root: Path) -> None:
    values = {"ANDROID_HOME": str(root), "ANDROID_SDK_ROOT": str(root)}
    if any("\n" in value or "\r" in value for value in values.values()):
        raise ValueError("Invalid SDK environment path")
    env_file, path_file = os.environ.get("GITHUB_ENV"), os.environ.get("GITHUB_PATH")
    if env_file:
        with Path(env_file).open("a", encoding="utf-8") as output:
            for key, value in values.items():
                output.write(key + "=" + value + "\n")
    if path_file:
        with Path(path_file).open("a", encoding="utf-8") as output:
            output.write(str(root / "cmdline-tools" / "19.0" / "bin") + "\n")
            output.write(str(root / "platform-tools") + "\n")
    print("Android SDK 35 installed in the dedicated runner directory; CI environment exported.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-licenses", action="store_true",
                        help="Explicitly accept Android SDK licenses for this ephemeral CI runner")
    parser.add_argument("--verify-archive", type=Path,
                        help="Only verify and safely extract an already downloaded pinned archive; never execute SDK tools")
    args = parser.parse_args(argv)
    if args.verify_archive:
        verify_archive(args.verify_archive)
        with tempfile.TemporaryDirectory(prefix="fantasy-android-verify-") as directory:
            safe_extract(args.verify_archive, Path(directory))
        print("Pinned official Linux archive SHA-256 and safe extraction verified; no SDK tools executed.")
        return 0
    if not args.accept_licenses:
        parser.error("Review https://developer.android.com/studio#terms and explicitly pass --accept-licenses in the CI workflow")
    if platform.system() != "Linux" or platform.machine().lower() not in ("x86_64", "amd64"):
        parser.error("This bootstrap targets Linux x86_64 CI runners only")
    runner = os.environ.get("RUNNER_TEMP")
    if not runner or not os.environ.get("CI"):
        parser.error("RUNNER_TEMP and CI must identify an ephemeral CI runner")
    root = Path(runner).resolve() / "fantasy-android-sdk"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="android-tools-", dir=Path(runner).resolve()) as directory:
        scratch = Path(directory)
        archive = scratch / "tools.zip"
        download(archive)
        safe_extract(archive, scratch / "unpacked")
        installed = root / "cmdline-tools" / "19.0"
        shutil.copytree(scratch / "unpacked" / "cmdline-tools", installed, dirs_exist_ok=True)
    manager = installed / "bin" / "sdkmanager"
    environment = dict(os.environ, ANDROID_HOME=str(root), ANDROID_SDK_ROOT=str(root))
    prefix = [str(manager), "--sdk_root=" + str(root)]
    run_manager(prefix + ["--licenses"], environment, timeout=180)
    run_manager(prefix + list(PACKAGES), environment, timeout=600)
    for required in (root / "platforms" / "android-35" / "android.jar", root / "build-tools" / "35.0.0" / "aapt2"):
        if not required.is_file():
            raise RuntimeError("Android SDK setup did not install a required build package")
    export_environment(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
