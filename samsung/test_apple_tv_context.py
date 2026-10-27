import asyncio
import datetime
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import apple_tv_context as worker
from test_tv_context import scoreboard
from tv_context import read_context_cache


def playing(title="Chiefs at Seahawks", state="Playing"):
    return SimpleNamespace(title=title, device_state=SimpleNamespace(name=state))


class FakeDevice:
    """No remote-control, app-launch, pair or stream interface exists."""
    def __init__(self, power="On", title="Chiefs at Seahawks"):
        self.power = SimpleNamespace(power_state=SimpleNamespace(name=power))
        self.push_updater = SimpleNamespace(start=lambda: None)
        self.metadata = SimpleNamespace(app=SimpleNamespace(name="YouTube TV"))
        self.calls = 0

        async def read():
            self.calls += 1
            return playing(title)
        self.metadata.playing = read


class WorkerTests(unittest.TestCase):
    def test_atomic_cache_private_and_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".local" / "tv-context.json"
            worker.atomic_private_write(path, {"title": "A", "capturedAt": 10})
            worker.atomic_private_write(path, {"title": "B", "capturedAt": 11})
            self.assertEqual(json.loads(path.read_text())["title"], "B")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_generic_title_available_but_game_unknown(self):
        value = worker.metadata_envelope(FakeDevice(), playing("Football Night in America"),
                                         scoreboard(), 100, "on")
        self.assertTrue(value["available"])
        self.assertEqual(value["title"], "Football Night in America")
        self.assertIsNone(value["matchedGameId"])
        self.assertEqual(value["confidence"], "unknown")

    def test_exact_pair_resolves_only_supplied_fresh_scoreboard(self):
        value = worker.metadata_envelope(FakeDevice(), playing(), scoreboard(), 100, "on")
        self.assertEqual(value["matchedGameId"], "game-1")
        self.assertEqual(value["confidence"], "exact-title-pair")
        value = worker.metadata_envelope(FakeDevice(), playing(), {}, 100, "on")
        self.assertIsNone(value["matchedGameId"])

    def test_idle_stopped_loading_discard_cached_old_title(self):
        for state in ("Idle", "Stopped", "Loading"):
            value = worker.metadata_envelope(FakeDevice(), playing(state=state),
                                             scoreboard(), 100, "on")
            self.assertFalse(value["available"])
            self.assertIsNone(value["title"])

    def test_paused_metadata_still_allowed(self):
        # Prime Video can report Paused even during playback; do not invent a
        # not-watching conclusion from this app-specific field.
        value = worker.metadata_envelope(FakeDevice(), playing(state="Paused"),
                                         scoreboard(), 100, "on")
        self.assertTrue(value["available"])

    def test_provider_identifiers_are_private_cached_values_without_extra_reads(self):
        device = FakeDevice()
        device.metadata.app.identifier = "test.youtube.TV"
        current = playing()
        current.content_identifier = "Opaque:AbC-123/CaseSensitive"
        current.itunes_store_identifier = 123
        value = worker.metadata_envelope(device, current, scoreboard(), 100, "on")
        self.assertEqual(value["appIdentifier"], "test.youtube.TV")
        self.assertEqual(value["contentIdentifier"], "Opaque:AbC-123/CaseSensitive")
        self.assertEqual(value["itunesStoreIdentifier"], 123)
        self.assertEqual(value["matchedGameId"], "game-1")
        self.assertEqual(device.calls, 0)

    def test_provider_identifier_bounds_and_controls_fail_without_normalizing(self):
        device, current = FakeDevice(), playing()
        for field, source, maximum in (("appIdentifier", device.metadata.app, 256),
                                       ("contentIdentifier", current, 512)):
            attribute = "identifier" if field == "appIdentifier" else "content_identifier"
            setattr(source, attribute, "A" * maximum)
            value = worker.metadata_envelope(device, current, scoreboard(), 100, "on")
            self.assertEqual(value[field], "A" * maximum)
            for invalid in ("A" * (maximum + 1), "", "   ", None, 123, True,
                            "one\ntwo", "one\ttwo", "one\x00two", "one\x7ftwo",
                            "one\x85two", "one\u200btwo"):
                with self.subTest(field=field, value=repr(invalid)[:40]):
                    setattr(source, attribute, invalid)
                    value = worker.metadata_envelope(device, current, scoreboard(), 100, "on")
                    self.assertIsNone(value[field])

    def test_itunes_identifier_requires_positive_integer_not_boolean(self):
        current = playing()
        for invalid in (None, False, True, 0, -1, "123", 1.0):
            with self.subTest(value=invalid):
                current.itunes_store_identifier = invalid
                value = worker.metadata_envelope(FakeDevice(), current, scoreboard(), 100, "on")
                self.assertIsNone(value["itunesStoreIdentifier"])
        current.itunes_store_identifier = 1
        self.assertEqual(worker.metadata_envelope(FakeDevice(), current, scoreboard(),
                                                  100, "on")["itunesStoreIdentifier"], 1)

    def test_unavailable_context_clears_provider_identifiers(self):
        device = FakeDevice()
        device.metadata.app.identifier = "test.youtube.TV"
        for state in ("Idle", "Stopped", "Loading"):
            current = playing(state=state)
            current.content_identifier = "opaque-id"
            current.itunes_store_identifier = 123
            value = worker.metadata_envelope(device, current, scoreboard(), 100, "on")
            self.assertTrue(all(value[field] is None for field in
                                ("appIdentifier", "contentIdentifier", "itunesStoreIdentifier")))
        for status in ("expired", "sleeping", "disconnected", "disabled", "starting"):
            value = worker.unavailable(status, 100)
            self.assertTrue(all(value[field] is None for field in
                                ("appIdentifier", "contentIdentifier", "itunesStoreIdentifier")))

    def test_scoreboard_age_expires_without_false_refresh(self):
        now = [100]
        cache = worker.ScoreboardCache(clock=lambda: now[0])
        cache.value, cache.updated = scoreboard(), 100
        self.assertTrue(cache.fresh())
        now[0] = 161
        self.assertEqual(cache.fresh(), {})
        now[0] = 99
        self.assertEqual(cache.fresh(), {})

    def test_scoreboard_date_uses_eastern_at_utc_midnight(self):
        now = datetime.datetime(2026, 10, 26, 1, tzinfo=datetime.timezone.utc)
        self.assertEqual(worker.scoreboard_date(now), "20261025")

    def test_sleeping_device_never_reads_metadata(self):
        async def check():
            device, writes = FakeDevice(power="Off"), []
            reason = await worker.observe_connected(device, "unused", seconds=0.01,
                                                     writer=lambda path, value: writes.append(value))
            self.assertEqual(reason, "sleeping")
            self.assertEqual(device.calls, 0)
            self.assertEqual(writes[-1]["status"], "sleeping")
            self.assertFalse(writes[-1]["available"])
        asyncio.run(check())

    def test_disconnection_stops_without_reconnect(self):
        async def check():
            device, observer, writes = FakeDevice(), worker.SessionObserver(), []
            async def read():
                observer.connection_lost(RuntimeError("private message"))
                return playing()
            device.metadata.playing = read
            reason = await worker.observe_connected(device, "unused", observer=observer,
                                                     writer=lambda path, value: writes.append(value))
            self.assertEqual(reason, "disconnected")
            self.assertEqual(len(writes), 1)
            self.assertNotIn("private message", json.dumps(writes))
        asyncio.run(check())

    def test_sleep_event_during_metadata_await_drops_result(self):
        async def check():
            device, observer, writes = FakeDevice(), worker.SessionObserver(), []
            async def read():
                observer.powerstate_update("On", "Off")
                return playing()
            device.metadata.playing = read
            reason = await worker.observe_connected(device, "unused", observer=observer,
                                                     writer=lambda path, value: writes.append(value))
            self.assertEqual(reason, "sleeping")
            self.assertTrue(all(not value["available"] for value in writes))
        asyncio.run(check())

    def test_normal_session_expires_and_clears_last_title(self):
        async def check():
            device, writes = FakeDevice(), []
            await worker.observe_connected(device, "unused", seconds=0.01,
                                            sample_seconds=1,
                                            writer=lambda path, value: writes.append(value))
            self.assertTrue(writes[0]["available"])
            self.assertFalse(writes[-1]["available"])
            self.assertEqual(writes[-1]["status"], "expired")
            self.assertIsNone(writes[-1]["title"])
        asyncio.run(check())

    def test_stop_event_clears_immediately(self):
        async def check():
            stop, writes = asyncio.Event(), []
            stop.set()
            await worker.observe_connected(FakeDevice(), "unused", stop_event=stop,
                                            writer=lambda path, value: writes.append(value))
            self.assertEqual(writes[-1]["status"], "disabled")
        asyncio.run(check())

    def test_cli_requires_explicit_session_and_bounded_times(self):
        base = ["--storage", "private.json", "--cache", "cache.json", "--host", "192.168.1.2"]
        with patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                worker.parse_args(base)
            with self.assertRaises(SystemExit):
                worker.parse_args(base + ["--active-session", "--seconds", "nan"])
            with self.assertRaises(SystemExit):
                worker.parse_args(base + ["--active-session", "--seconds", "86401"])
            with self.assertRaises(SystemExit):
                worker.parse_args(["--storage", "same.json", "--cache", "same.json",
                                   "--host", "192.168.1.2", "--active-session"])
        self.assertTrue(worker.parse_args(base + ["--active-session"]).active_session)

    def test_one_multicast_airplay_discovery_no_host_knocks(self):
        async def check():
            config = SimpleNamespace(address="192.168.1.2", name="Living Room",
                                     deep_sleep=False,
                                     get_service=lambda protocol: SimpleNamespace(credentials="secret"))
            calls = []
            async def scan(loop, **kwargs):
                calls.append(kwargs)
                return [config]
            async def connect(config, loop, **kwargs):
                return FakeDevice()
            class Storage:
                def __init__(self, path, loop):
                    pass
                async def load(self):
                    pass
            module = SimpleNamespace(scan=scan, connect=connect)
            modules = {"pyatv": module,
                       "pyatv.const": SimpleNamespace(Protocol=SimpleNamespace(AirPlay="airplay")),
                       "pyatv.storage.file_storage": SimpleNamespace(FileStorage=Storage)}
            with patch.dict("sys.modules", modules):
                device, reason = await worker.connect_once(SimpleNamespace(
                    host="192.168.1.2", name="Living Room", storage="private.json"))
            self.assertIsNone(reason)
            self.assertIsNotNone(device)
            self.assertEqual(len(calls), 1)
            self.assertNotIn("hosts", calls[0])
            self.assertEqual(calls[0]["protocol"], "airplay")
        asyncio.run(check())

    def test_deep_sleep_rejected_before_any_connection(self):
        async def check():
            config = SimpleNamespace(address="192.168.1.2", name="Living Room", deep_sleep=True)
            async def scan(loop, **kwargs):
                return [config]
            async def connect(*args, **kwargs):
                self.fail("Sleeping configuration must not be connected")
            class Storage:
                def __init__(self, path, loop):
                    pass
                async def load(self):
                    pass
            with patch.dict("sys.modules", {
                "pyatv": SimpleNamespace(scan=scan, connect=connect),
                "pyatv.const": SimpleNamespace(Protocol=SimpleNamespace(AirPlay="airplay")),
                "pyatv.storage.file_storage": SimpleNamespace(FileStorage=Storage)}):
                device, reason = await worker.connect_once(SimpleNamespace(
                    host="192.168.1.2", name="Living Room", storage="private.json"))
            self.assertIsNone(device)
            self.assertEqual(reason, "sleeping")
        asyncio.run(check())


class CacheReaderTests(unittest.TestCase):
    def cache(self, root, **changes):
        value = worker.metadata_envelope(FakeDevice(), playing(), scoreboard(), 100, "on")
        value.update(changes)
        path = Path(root) / "context.json"
        path.write_text(json.dumps(value))
        return path

    def test_fresh_complete_context_and_stale_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.cache(folder)
            value = read_context_cache(path, now=150)
            self.assertEqual(value["matchedGameId"], "game-1")
            self.assertTrue(value["available"])
            value = read_context_cache(path, now=161)
            self.assertFalse(value["available"])
            self.assertIsNone(value["title"])
            self.assertIsNone(value["matchedGameId"])

    def test_provider_identifiers_do_not_leave_private_worker_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.cache(folder, appIdentifier="test.youtube.TV",
                              contentIdentifier="https://tv.youtube.com/watch/opaque-id",
                              itunesStoreIdentifier=123)
            value = read_context_cache(path, now=110)
            self.assertTrue(value["available"])
            self.assertEqual(value["matchedGameId"], "game-1")
            for field in ("appIdentifier", "contentIdentifier", "itunesStoreIdentifier"):
                self.assertNotIn(field, value)

    def test_future_missing_invalid_and_oversized_fail_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.cache(folder)
            self.assertFalse(read_context_cache(path, now=99)["available"])
            path.write_text("[not json")
            self.assertFalse(read_context_cache(path, now=100)["available"])
            path.write_text(" " * 65537)
            self.assertFalse(read_context_cache(path, now=100)["available"])
            path.unlink()
            self.assertFalse(read_context_cache(path, now=100)["available"])

    def test_off_or_unavailable_clears_game_and_title(self):
        with tempfile.TemporaryDirectory() as folder:
            for changes in ({"powerState": "off"}, {"available": False},
                            {"status": "sleeping"}, {"status": "disconnected"}):
                value = read_context_cache(self.cache(folder, **changes), now=110)
                self.assertFalse(value["available"])
                self.assertIsNone(value["matchedGameId"])
                self.assertIsNone(value["title"])

    def test_confidence_and_game_id_must_agree(self):
        with tempfile.TemporaryDirectory() as folder:
            for changes in ({"confidence": "unknown"}, {"manualOverride": True},
                            {"matchedGameId": 123}, {"capturedAt": True},
                            {"capturedAt": float("nan")}):
                value = read_context_cache(self.cache(folder, **changes), now=110)
                self.assertFalse(value["available"])


if __name__ == "__main__":
    unittest.main()
