"""Optional, one-session Apple TV metadata worker; importing does no networking.

Run under an already installed pyatv runtime, with --active-session only while
watching that Apple TV. Never pairs, sends controls, launches apps or reconnects.
AirPlay-only multicast discovery avoids pyatv's deliberate unicast TCP wake
knocks. Deep-sleep candidates are rejected, but shallow sleep is not reliably
detectable before connection: this is an explicit watching-session helper.

The system-Python controller consumes only the private atomic cache. Public NFL
scoreboard requests run independently of metadata; a missing/stale scoreboard
means an unknown game, never a scheduled-game guess.
"""

import argparse
import asyncio
import datetime
import ipaddress
import json
import logging
import math
import os
from pathlib import Path
import signal
import tempfile
import time
import urllib.request
from zoneinfo import ZoneInfo

from tv_context import _clean, build_context


ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
SCOREBOARD_INTERVAL = 30.0
SCOREBOARD_MAX_AGE = 60.0
NFL_TIMEZONE = ZoneInfo("America/New_York")


def atomic_private_write(path, value):
    """Replace a small cache atomically, without exposing partial JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".tv-context-",
                                         dir=str(path.parent), delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(str(temporary), 0o600)
            stream.write(encoded)
            stream.flush()
        os.replace(str(temporary), str(path))
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def unavailable(status, now, power="unknown"):
    return dict(build_context({}, {}), available=False, capturedAt=now,
                status=status, powerState=power, appIdentifier=None,
                contentIdentifier=None, itunesStoreIdentifier=None)


def _cached_identifier(value, maximum):
    """Keep a bounded public metadata identifier verbatim in the private cache.

    Identifiers are app-specific and opaque, so never normalize or truncate
    them. Control/nonprinting characters invalidate the value instead.
    """
    if (isinstance(value, str) and 0 < len(value) <= maximum and value.strip()
            and all(character.isprintable() for character in value)):
        return value
    return None


def _cached_itunes_identifier(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def power_name(value):
    name = getattr(value, "name", value)
    return name.casefold() if isinstance(name, str) and name.casefold() in {
        "on", "off"} else "unknown"


def cached_power(device):
    """The MRP implementation reads cached device-info, not a power request."""
    try:
        return power_name(device.power.power_state)
    except Exception:
        return "unknown"


def metadata_envelope(device, playing, scoreboard, now, power):
    state = getattr(getattr(playing, "device_state", None), "name", None)
    if state in {"Idle", "Stopped", "Loading"}:
        return unavailable("idle", now, power)
    try:
        app = device.metadata.app
    except Exception:
        app = None
    metadata = {"app": _clean(getattr(app, "name", None)
                               or getattr(app, "identifier", None)),
                "title": _clean(getattr(playing, "title", None))}
    for key in metadata:
        if metadata[key] and len(metadata[key]) > 4096:
            metadata[key] = None
    context = build_context(metadata, scoreboard)
    # These public properties are already cached by pyatv's MRP metadata
    # interface. Reading them makes no request and does not establish that an
    # app-specific identifier is a launchable URL. Keep them in this private
    # worker cache only; tv_context.read_context_cache deliberately omits them.
    return dict(context, available=bool(context["title"] or context["app"]),
                capturedAt=now, status="ok" if context["title"] or context["app"]
                else "unavailable", powerState=power,
                appIdentifier=_cached_identifier(getattr(app, "identifier", None), 256),
                contentIdentifier=_cached_identifier(getattr(playing, "content_identifier", None), 512),
                itunesStoreIdentifier=_cached_itunes_identifier(
                    getattr(playing, "itunes_store_identifier", None)))


def scoreboard_date(now=None):
    now = datetime.datetime.now(datetime.timezone.utc) if now is None else now
    return now.astimezone(NFL_TIMEZONE).strftime("%Y%m%d")


def fetch_public_scoreboard():
    """Fixed public endpoint, no fantasy cookies or private authentication."""
    url = ESPN_SCOREBOARD + "?dates=" + scoreboard_date()
    request = urllib.request.Request(url, headers={"Accept": "application/json",
                                                   "User-Agent": "FantasyOverlay/1.0"})
    with urllib.request.urlopen(request, timeout=5) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("scoreboard response too large")
    result = json.loads(raw)
    if not isinstance(result, dict) or not isinstance(result.get("events"), list):
        raise ValueError("scoreboard response needs events")
    return result


class ScoreboardCache:
    def __init__(self, fetcher=fetch_public_scoreboard, clock=time.monotonic):
        self.fetcher, self.clock = fetcher, clock
        self.value, self.updated = {}, None

    def fresh(self):
        if self.updated is None or not 0 <= self.clock() - self.updated <= SCOREBOARD_MAX_AGE:
            return {}
        return self.value

    async def run(self, stop):
        while not stop.is_set():
            began = self.clock()
            try:
                result = await asyncio.to_thread(self.fetcher)
                self.value, self.updated = result, self.clock()
            except Exception:
                # Existing data expires naturally; no fabricated successful refresh.
                pass
            delay = max(0.01, SCOREBOARD_INTERVAL - (self.clock() - began))
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass


class SessionObserver:
    """Receives already subscribed MRP updates, exposing no control methods."""
    def __init__(self):
        self.changed = asyncio.Event()
        self.stopped = asyncio.Event()
        self.reason = None

    def stop(self, reason):
        if self.reason is None:
            self.reason = reason
        self.stopped.set()
        self.changed.set()

    def connection_lost(self, exception):
        self.stop("disconnected")

    def connection_closed(self):
        self.stop("disconnected")

    def powerstate_update(self, old, new):
        if power_name(new) == "off":
            self.stop("sleeping")
        else:
            self.changed.set()

    def playstatus_update(self, updater, playstatus):
        self.changed.set()

    def playstatus_error(self, updater, exception):
        self.stop("unavailable")


async def observe_connected(device, cache, *, seconds=28800, sample_seconds=10,
                            scoreboard=None, observer=None, stop_event=None,
                            clock=time.time, timer=time.monotonic,
                            writer=atomic_private_write):
    """Observe one existing connection. No discovery/reconnect or controls."""
    observer = observer or SessionObserver()
    stop_event = stop_event or asyncio.Event()
    scoreboard = scoreboard or ScoreboardCache()
    deadline = timer() + seconds
    device.listener = observer
    try:
        device.power.listener = observer
    except Exception:
        pass
    try:
        device.push_updater.listener = observer
        device.push_updater.start()
    except Exception:
        # Cached sampling still works on a protocol lacking push callbacks.
        pass
    while not stop_event.is_set() and not observer.stopped.is_set() and timer() < deadline:
        observer.changed.clear()
        power = cached_power(device)
        if power == "off":
            observer.stop("sleeping")
            break
        try:
            playing = await asyncio.wait_for(device.metadata.playing(), timeout=5)
            # A sleep/disconnect event may have arrived during that await.
            power = cached_power(device)
            if observer.stopped.is_set() or stop_event.is_set():
                break
            if power == "off":
                observer.stop("sleeping")
                break
            value = metadata_envelope(device, playing, scoreboard.fresh(), clock(), power)
        except Exception:
            observer.stop("unavailable")
            break
        writer(cache, value)
        delay = min(sample_seconds, max(0, deadline - timer()))
        waits = [asyncio.create_task(observer.changed.wait()),
                 asyncio.create_task(stop_event.wait())]
        try:
            await asyncio.wait(waits, timeout=delay, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in waits:
                task.cancel()
            await asyncio.gather(*waits, return_exceptions=True)
    reason = observer.reason or ("disabled" if stop_event.is_set() else "expired")
    writer(cache, unavailable(reason, clock(), "off" if reason == "sleeping" else "unknown"))
    return reason


async def connect_once(args):
    """Single multicast AirPlay discovery and authenticated connection.

    Do not replace this with hosts=[...]: pyatv's unicast scanner performs
    deliberate TCP wake knocks. No credential values are logged or returned.
    """
    import pyatv
    from pyatv.const import Protocol
    from pyatv.storage.file_storage import FileStorage

    loop = asyncio.get_running_loop()
    storage = FileStorage(str(args.storage), loop)
    await storage.load()
    configs = await pyatv.scan(loop, protocol=Protocol.AirPlay, storage=storage, timeout=3)
    configs = [config for config in configs if str(config.address) == args.host
               and (args.name is None or config.name == args.name)]
    if len(configs) != 1:
        return None, "unavailable"
    config = configs[0]
    if config.deep_sleep:
        return None, "sleeping"
    service = config.get_service(Protocol.AirPlay)
    if service is None or not service.credentials:
        return None, "unpaired"
    device = await asyncio.wait_for(pyatv.connect(config, loop, storage=storage), timeout=15)
    return device, None


async def close_device(device):
    try:
        tasks = device.close()
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5)
    except Exception:
        pass


async def run_worker(args, connector=connect_once):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    atomic_private_write(args.cache, unavailable("starting", time.time()))
    device = None
    scoreboard_stop = asyncio.Event()
    scoreboard_task = None
    try:
        device, reason = await connector(args)
        if stop.is_set():
            atomic_private_write(args.cache, unavailable("disabled", time.time()))
            return 0
        if device is None:
            atomic_private_write(args.cache, unavailable(reason, time.time(),
                                                         "off" if reason == "sleeping" else "unknown"))
            return 0
        scoreboard = ScoreboardCache()
        scoreboard_task = asyncio.create_task(scoreboard.run(scoreboard_stop))
        await observe_connected(device, args.cache, seconds=args.seconds,
                                sample_seconds=args.sample_seconds,
                                scoreboard=scoreboard, stop_event=stop)
        return 0
    except asyncio.CancelledError:
        atomic_private_write(args.cache, unavailable("disabled", time.time()))
        raise
    except Exception:
        # Never dump pyatv configuration, credentials, exception text or tracebacks.
        atomic_private_write(args.cache, unavailable("unavailable", time.time()))
        return 1
    finally:
        scoreboard_stop.set()
        if scoreboard_task is not None:
            scoreboard_task.cancel()
            await asyncio.gather(scoreboard_task, return_exceptions=True)
        if device is not None:
            await close_device(device)
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--host", required=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--seconds", type=float, default=28800)
    parser.add_argument("--sample-seconds", type=float, default=10)
    parser.add_argument("--active-session", action="store_true", required=True,
                        help="Enable one session while explicitly watching this Apple TV")
    args = parser.parse_args(argv)
    try:
        args.host = str(ipaddress.IPv4Address(args.host))
    except ValueError:
        parser.error("--host needs an IPv4 address")
    if not math.isfinite(args.seconds) or not 1 <= args.seconds <= 86400:
        parser.error("--seconds must be between 1 and 86400")
    if not math.isfinite(args.sample_seconds) or not 1 <= args.sample_seconds <= 60:
        parser.error("--sample-seconds must be between 1 and 60")
    if args.storage.resolve() == args.cache.resolve():
        parser.error("--storage and --cache must be different files")
    return args


def main(argv=None):
    args = parse_args(argv)
    os.umask(0o077)
    # Protocol debug/error text may contain configuration; cache only status.
    logging.getLogger("pyatv").setLevel(logging.CRITICAL)
    return asyncio.run(run_worker(args))


if __name__ == "__main__":
    raise SystemExit(main())
