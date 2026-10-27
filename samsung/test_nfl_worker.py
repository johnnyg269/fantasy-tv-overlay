"""NFL worker concurrency/freshness checks; no network or TV operations."""

from copy import deepcopy
import threading
import time
import unittest

from nfl_live import BASE, NflLiveEnricher, NflLiveWorker, TEAMS_URL


def scores(points=10, projection=20, owner="Current Owner"):
    return {"updated": 1000, "leagues": [{"leagueId": "private-id", "seasonId": 2026, "week": 7, "me": {
        "ownerName": owner,
        "players": [{"name": "Josh Allen", "slot": "QB", "pts": points, "proj": projection}]
    }}]}


class FakeEnricher:
    def __init__(self):
        self.entered, self.release = threading.Event(), threading.Event()
        self.release.set()
        self.received = None

    def refresh(self, date=None, cancel_event=None):
        self.entered.set()
        self.release.wait(timeout=2)

    def annotate(self, payload, **kwargs):
        self.received = deepcopy(payload)
        result = deepcopy(payload)
        team = result["leagues"][0]["me"]
        # Deliberately poison non-metadata fields in a completed old worker
        # clone. apply_cached must never copy these values onto fresh scores.
        team["ownerName"] = "OLD OWNER"
        for player in team["players"]:
            player.update({"pts": -999, "proj": -888,
                           "nflGameState": "live", "nflGameLabel": "Q4 1:00",
                           "nflTeamId": "2", "gameId": "game",
                           "mappingConfidence": "roster-exact-position",
                           "nflAvailability": "available", "nflHighlightLive": True})
        result["nflLive"] = {"available": True}
        return result


class NflWorkerTests(unittest.TestCase):
    def wait_cached(self, worker):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            state = worker.apply_cached(scores())
            if state["nflLive"]["available"]:
                return state
            time.sleep(0.005)
        self.fail("fake worker did not populate its cache")

    def test_sick_public_network_cannot_block_foreground_heartbeat_or_close(self):
        fake = FakeEnricher()
        fake.release.clear()
        worker = NflLiveWorker(enricher=fake)
        try:
            worker.submit_latest(scores())
            self.assertTrue(fake.entered.wait(timeout=1))
            started = time.monotonic()
            state = worker.apply_cached(scores())
            self.assertLess(time.monotonic() - started, 0.1)
            self.assertFalse(state["leagues"][0]["me"]["players"][0]["nflHighlightLive"])
            started = time.monotonic()
            worker.close(timeout=0.02)
            self.assertLess(time.monotonic() - started, 0.1)
        finally:
            fake.release.set()
            worker.close(timeout=1)

    def test_worker_copies_only_metadata_never_old_points_projection_or_owner(self):
        fake = FakeEnricher()
        worker = NflLiveWorker(enricher=fake)
        try:
            worker.submit_latest(scores())
            self.wait_cached(worker)
            fresh = scores(123.45, 155.67, "New Verified Owner")
            original = deepcopy(fresh)
            enriched = worker.apply_cached(fresh)
            team = enriched["leagues"][0]["me"]
            self.assertEqual(team["ownerName"], "New Verified Owner")
            self.assertEqual(team["players"][0]["pts"], 123.45)
            self.assertEqual(team["players"][0]["proj"], 155.67)
            self.assertTrue(team["players"][0]["nflHighlightLive"])
            self.assertEqual(fresh, original)
            self.assertNotIn("private-id", repr(fake.received))
            self.assertNotIn("ownerName", repr(fake.received))
            self.assertNotIn("pts", repr(fake.received))
        finally:
            worker.close()

    def test_live_metadata_expires_at_90_seconds_and_close_clears_it(self):
        now = [1000]
        worker = NflLiveWorker(enricher=FakeEnricher(), clock=lambda: now[0],
                               metadata_ttl=999, interval=10000)
        try:
            worker.submit_latest(scores())
            self.wait_cached(worker)
            now[0] += 89.9
            self.assertTrue(worker.apply_cached(scores())["nflLive"]["available"])
            now[0] += 0.1
            expired = worker.apply_cached(scores())
            self.assertFalse(expired["nflLive"]["available"])
            self.assertEqual(expired["leagues"][0]["me"]["players"][0]["nflGameState"], "unknown")
            self.assertFalse(expired["leagues"][0]["me"]["players"][0]["nflHighlightLive"])
        finally:
            worker.close()
        self.assertFalse(worker.apply_cached(scores())["nflLive"]["available"])

    def test_cached_player_cannot_transfer_live_to_another_week_or_season(self):
        worker = NflLiveWorker(enricher=FakeEnricher(), interval=10000)
        try:
            worker.submit_latest(scores())
            self.wait_cached(worker)
            for field, value in (("seasonId", 2025), ("week", 8), ("seasonId", None),
                                 ("week", None), ("week", True)):
                source = scores(); source["leagues"][0][field] = value
                player = worker.apply_cached(source)["leagues"][0]["me"]["players"][0]
                self.assertFalse(player["nflHighlightLive"])
                self.assertEqual(player["nflGameState"], "unknown")
                self.assertIsNone(player["gameId"])
            self.assertTrue(worker.apply_cached(scores())["leagues"][0]["me"]["players"][0]["nflHighlightLive"])
        finally:
            worker.close()

    def test_same_player_in_two_league_scopes_is_not_deduplicated_across_scopes(self):
        worker = NflLiveWorker(enricher=FakeEnricher(), interval=10000)
        try:
            source = scores()
            other = deepcopy(source["leagues"][0]); other["week"] = 8
            source["leagues"].append(other)
            worker.submit_latest(source)
            with worker._lock:
                slim = deepcopy(worker._latest)
            self.assertEqual({(league["seasonId"], league["week"]) for league in slim["leagues"]},
                             {(2026, 7), (2026, 8)})
            self.assertNotIn("private-id", repr(slim))
            self.assertNotIn("ownerName", repr(slim))
            self.assertNotIn("pts", repr(slim))
        finally:
            worker.close()

    def test_expiry_accounts_for_scoreboard_age_before_metadata_was_copied(self):
        now = [1000]
        fake = FakeEnricher()
        fake.clock = lambda: now[0]
        original = fake.annotate

        def annotate(payload, **kwargs):
            result = original(payload, **kwargs)
            result["nflLive"]["scoreboardUpdated"] = 975
            return result

        fake.annotate = annotate
        worker = NflLiveWorker(enricher=fake, clock=lambda: now[0], interval=10000)
        try:
            worker.submit_latest(scores())
            self.wait_cached(worker)
            now[0] = 1064.9
            self.assertTrue(worker.apply_cached(scores())["nflLive"]["available"])
            now[0] = 1065
            self.assertFalse(worker.apply_cached(scores())["nflLive"]["available"])
        finally:
            worker.close()

    def test_real_roster_pool_is_daemon_cancelled_and_shared_across_sessions(self):
        release, four_started = threading.Event(), threading.Event()
        guard, calls = threading.Lock(), []
        counter = [0]

        def fetch(url):
            calls.append(url)
            if url == TEAMS_URL:
                return {"sports": [{"leagues": [{"teams": [
                    {"team": {"id": str(i), "name": "Team" + str(i)}} for i in range(1, 9)
                ]}]}]}
            if "/scoreboard?" in url:
                return {"events": []}
            self.assertTrue(url.startswith(BASE + "/teams/"))
            with guard:
                counter[0] += 1
                if counter[0] == 4:
                    four_started.set()
            release.wait(timeout=3)
            return {"athletes": []}

        old = NflLiveWorker(enricher=NflLiveEnricher(fetcher=fetch), date="20261025")
        new = None
        try:
            old.submit_latest(scores())
            self.assertTrue(four_started.wait(timeout=1))
            threads = [thread for thread in threading.enumerate()
                       if thread.name == "fantasy-public-http"]
            self.assertTrue(threads)
            self.assertTrue(all(thread.daemon for thread in threads))
            started = time.monotonic()
            old.close(timeout=0.5)
            self.assertLess(time.monotonic() - started, 0.75)
            self.assertFalse(old._thread.is_alive())
            # Old blocked HTTP requests retain all four shared slots. A new
            # session must wait rather than creating a second batch of four.
            new = NflLiveWorker(enricher=NflLiveEnricher(fetcher=fetch), date="20261025")
            new.submit_latest(scores())
            time.sleep(0.02)
            self.assertEqual(sum(url == TEAMS_URL for url in calls), 1)
            self.assertEqual(sum("/roster" in url for url in calls), 4)
        finally:
            if new is not None:
                new.close(timeout=0.5)
            release.set()
            old.close()


if __name__ == "__main__":
    unittest.main()
