#!/usr/bin/env python3
"""Explicit AirPlay pairing with hidden PIN and private atomic storage.

No credential values are printed. No app launches, remote buttons or playback
commands are sent. Import and --help never make a network request.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import warnings

import pyatv
from pyatv.const import Protocol
from pyatv.storage.file_storage import FileStorage


PRIVATE_DIRECTORY = Path(__file__).resolve().parent / ".local"
STORAGE_PATH = PRIVATE_DIRECTORY / "apple-tv-storage.json"
EXPECTED_VERSION = "0.18.0"


class SetupError(Exception):
    """A known error whose message is safe to show without credential values."""


def quiet_logging() -> None:
    # pyatv's AirPlay protocol logs credentials at DEBUG. Do not enable logs.
    logging.disable(logging.CRITICAL)


def private_directory(create: bool) -> None:
    if not PRIVATE_DIRECTORY.exists() and not PRIVATE_DIRECTORY.is_symlink():
        if not create:
            raise SetupError("No AirPlay pairing is stored. Run this explicit pairing helper first.")
        PRIVATE_DIRECTORY.mkdir(mode=0o700)
    info = PRIVATE_DIRECTORY.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise SetupError("Private storage directory must be a real directory owned by this user.")
    os.chmod(PRIVATE_DIRECTORY, 0o700)


class PrivateFileStorage(FileStorage):
    """pyatv storage with atomic mode-600 writes and no symlink following."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__(str(STORAGE_PATH), loop)

    def _read_file(self) -> str:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(STORAGE_PATH, flags)
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600):
                raise SetupError("AirPlay storage must be a regular file owned by this user with mode 600.")
            return stream.read()

    async def load(self) -> None:
        if STORAGE_PATH.is_symlink():
            raise SetupError("Refusing a symlink at the AirPlay storage path.")
        await super().load()

    def _save_file(self, dumped: dict) -> None:
        if STORAGE_PATH.is_symlink():
            raise SetupError("Refusing a symlink at the AirPlay storage path.")
        descriptor, temporary = tempfile.mkstemp(prefix=".airplay-", dir=PRIVATE_DIRECTORY)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(dumped, stream, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, STORAGE_PATH)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


async def storage_for(create: bool) -> PrivateFileStorage:
    private_directory(create)
    storage = PrivateFileStorage(asyncio.get_running_loop())
    await storage.load()
    return storage


async def discover_target(args, storage):
    # Deliberately omit hosts=[...]: pyatv's unicast scanner sends TCP wake knocks.
    devices = await pyatv.scan(asyncio.get_running_loop(), protocol=Protocol.AirPlay,
                               storage=storage, timeout=args.timeout)
    matches = [device for device in devices
               if str(device.address) == args.host and device.name == args.name]
    if len(matches) != 1:
        raise SetupError("Expected exactly one AirPlay device with the requested host and name.")
    config = matches[0]
    if config.deep_sleep:
        raise SetupError("Apple TV is sleeping. Wake it yourself, then rerun this command.")
    service = config.get_service(Protocol.AirPlay)
    if service is None:
        raise SetupError("The selected device did not advertise AirPlay.")
    return config, service


def hidden_pin(device_name: str) -> int:
    # Fail instead of allowing getpass to fall back to echoing stdin.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        value = getpass.getpass("Enter the 4-digit PIN shown on " + device_name + " Apple TV (hidden): ")
    if re.fullmatch(r"[0-9]{4}", value) is None:
        raise SetupError("PIN must contain exactly four digits. Rerun pair to try again.")
    return int(value)


def save_device_config(args):
    from alexa_bridge.private_config import load_private_json
    path = PRIVATE_DIRECTORY / "apple-tv.json"
    config = {"host": args.host, "name": args.name}
    if path.exists() or path.is_symlink():
        if load_private_json(path) != config:
            raise SetupError("Existing private Apple TV configuration names a different device; review it locally before changing it.")
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(config, stream, separators=(",", ":"))
        stream.write("\n")


async def pair_airplay(args) -> int:
    if not args.allow_pairing:
        raise SetupError("Pairing is disabled without --allow-pairing.")
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise SetupError("Pairing requires an interactive terminal for the hidden PIN prompt.")
    storage = await storage_for(create=True)
    config, service = await discover_target(args, storage)
    if service.credentials:
        save_device_config(args)
        print("AirPlay is already paired in this private store.")
        return 0
    pairing = await pyatv.pair(config, Protocol.AirPlay, asyncio.get_running_loop(),
                               storage=storage, name="Fantasy overlay AirPlay setup")
    try:
        print("Starting AirPlay pairing. Look at the Apple TV for its PIN.", flush=True)
        await asyncio.wait_for(pairing.begin(), timeout=15)
        if not pairing.device_provides_pin:
            raise SetupError("This device did not offer the expected on-screen PIN flow.")
        pairing.pin(hidden_pin(args.name))
        await asyncio.wait_for(pairing.finish(), timeout=15)
        if not pairing.has_paired:
            raise SetupError("AirPlay pairing was not confirmed. No credentials were saved.")
        await storage.save()
        save_device_config(args)
        print("AirPlay paired. Credentials and device configuration were saved privately.")
        return 0
    finally:
        await asyncio.wait_for(pairing.close(), timeout=5)


def unicast_ipv4(value: str) -> str:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as error:
        raise argparse.ArgumentTypeError("Use an explicit IPv4 address.") from error
    if address.is_multicast or address.is_unspecified or address.is_loopback:
        raise argparse.ArgumentTypeError("Use the Apple TV's unicast LAN IPv4 address.")
    return str(address)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--host", required=True, type=unicast_ipv4)
    result.add_argument("--name", required=True, help="Exact advertised Apple TV name")
    result.add_argument("--timeout", type=int, choices=range(1, 16), default=4, metavar="1..15")
    result.add_argument("--allow-pairing", action="store_true",
                        help="Authorize pairing and the on-screen PIN prompt for this device")
    return result


async def execute(args) -> int:
    from importlib.metadata import version
    if version("pyatv") != EXPECTED_VERSION:
        raise SetupError("This helper was prepared for pyatv 0.18.0. Review it before using another version.")
    return await pair_airplay(args)


def main(argv=None) -> int:
    os.umask(0o077)
    quiet_logging()
    cli = parser()
    args = cli.parse_args(argv)
    try:
        return asyncio.run(execute(args))
    except SetupError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("Cancelled. No credential values were printed.", file=sys.stderr)
        return 130
    except Exception as error:
        # Exception messages/tracebacks can contain protocol payloads. Never print them.
        print("AirPlay setup failed (" + type(error).__name__ + "). No credential values were printed.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
