"""Offline score-popup regression tests; no network or TV is accessed."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from controller import ScoreController, atomic_write


def score_payload():
    return {
        "updated": 1000,
        "ok": True,
        "leagues": [
            {"leagueId": "A", "week": 7, "ok": True, "short": "LEAGUE A",
             "me": {"teamId": 8, "name": "My team", "score": 100.10, "proj": 150},
             "opp": {"teamId": 1, "name": "Opponent", "score": 90.20, "proj": 140}},
            {"leagueId": "B", "week": 7, "ok": True, "short": "LEAGUE B",
             "me": {"teamId": 6, "name": "My team B", "score": 99.30, "proj": 160},
             "opp": {"teamId": 2, "name": "Opponent B", "score": 98.40, "proj": 155}},
        ],
    }


def scene_text(state):
    return " ".join(obj.get("text", "") for obj in state["scene"]["objects"])


class FakeClock:
    def __init__(self):
        self.wall = 1000.0
        self.monotonic = 50.0

    def advance(self, seconds):
        self.wall += seconds
        self.monotonic += seconds


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.state_path = Path(self.directory.name) / "state.json"
        self.clock = FakeClock()
        self.payload = score_payload()
        self.fetch_error = None
        self.fetch_delay = 0
        self.fetch_calls = 0
        self.published = []

        def fetch(_endpoint):
            self.fetch_calls += 1
            self.clock.advance(self.fetch_delay)
            if self.fetch_error is not None:
                raise self.fetch_error
            return copy.deepcopy(self.payload)

        def publish(path, state):
            # A transport must only receive a completely replaced JSON file.
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), state)
            self.published.append(copy.deepcopy(state))

        self.controller = ScoreController(
            self.state_path, fetcher=fetch, publish=publish,
            clock=lambda: self.clock.wall,
            timer_clock=lambda: self.clock.monotonic,
            fetch_seconds=1, heartbeat_seconds=1,
        )

    def tearDown(self):
        self.directory.cleanup()

    def advance(self, seconds=1):
        self.clock.advance(seconds)
        result = self.controller.tick()
        return result if result is not None else self.controller.current_state()

    def establish_baseline(self):
        state = self.controller.tick()
        self.assertFalse(state["visible"])
        self.assertNotIn("alertId", state)
        self.assertIsNotNone(self.controller.baseline)
        return state

    def trigger_score_change(self):
        self.establish_baseline()
        self.payload["leagues"][0]["me"]["score"] += 1
        state = self.advance()
        self.assertTrue(state["visible"])
        return state

    def test_first_fresh_snapshot_establishes_hidden_baseline(self):
        state = self.establish_baseline()
        self.assertTrue(state["feed"]["available"])
        self.assertEqual(state["feed"]["sourceUpdated"], 1000)
        self.assertEqual(len(self.published), 1)

    def test_changes_in_either_league_or_opponent_trigger(self):
        self.establish_baseline()
        self.payload["leagues"][1]["opp"]["score"] += 0.01
        state = self.advance()
        self.assertTrue(state["visible"])
        self.assertIsInstance(state["alertId"], str)
        self.assertTrue(state["alertId"])
        self.assertEqual(state["durationSeconds"], 5)
        self.assertEqual(state["selectedLeagueId"], "B")
        self.assertEqual(state["event"]["changedLeagueIds"], ["B"])
        self.assertEqual(state["event"]["scoreDeltas"], {"B": {"me": 0.0, "opp": 0.01}})
        self.assertNotIn("My team", [obj.get("text") for obj in state["scene"]["objects"]])

    def test_negative_stat_correction_also_triggers(self):
        self.establish_baseline()
        self.payload["leagues"][0]["me"]["score"] -= 2
        state = self.advance()
        self.assertTrue(state["visible"])
        self.assertIn("98.10", scene_text(state))

    def test_projections_players_probability_and_timestamp_do_not_trigger(self):
        self.establish_baseline()
        self.payload["leagues"][0]["me"]["proj"] = 300
        self.payload["leagues"][0]["me"]["players"] = [{"pts": 10}]
        self.payload["leagues"][1]["winProb"] = 0.95
        self.payload["updated"] = self.clock.wall + 1
        state = self.advance()
        self.assertFalse(state["visible"])
        self.assertNotIn("alertId", state)

    def test_duplicate_poll_and_heartbeat_never_extend_alert(self):
        first = self.trigger_score_change()
        deadline = self.controller.alert_until
        for _ in range(4):
            state = self.advance()
            self.assertTrue(state["visible"])
            self.assertEqual(state["alertId"], first["alertId"])
            self.assertEqual(self.controller.alert_until, deadline)

    def test_expiry_publishes_hidden_state_at_exactly_five_seconds(self):
        first = self.trigger_score_change()
        self.assertTrue(self.advance(4.99)["visible"])
        state = self.advance(0.01)
        self.assertFalse(state["visible"])
        self.assertEqual(state["alertId"], first["alertId"])
        self.assertFalse(self.published[-1]["visible"])

    def test_new_real_change_restarts_five_seconds_with_new_identity(self):
        first = self.trigger_score_change()
        self.advance(3)
        self.payload["leagues"][1]["me"]["score"] += 0.1
        second = self.advance()
        self.assertTrue(second["visible"])
        self.assertNotEqual(second["alertId"], first["alertId"])
        self.assertEqual(self.controller.alert_until, self.clock.monotonic + 5)
        self.assertTrue(self.advance(4.99)["visible"])
        self.assertFalse(self.advance(0.01)["visible"])

    def test_preview_expires_without_resetting_baseline_or_faking_scores(self):
        self.establish_baseline()
        baseline = copy.deepcopy(self.controller.baseline)
        scores = copy.deepcopy(self.controller.scores)
        self.controller.apply_command("preview")
        preview = self.published[-1]
        self.assertTrue(preview["visible"])
        self.assertTrue(preview["alertId"])
        self.assertEqual(preview["durationSeconds"], 5)
        self.assertEqual(preview["event"]["kind"], "preview")
        self.assertEqual(preview["event"]["scoreDeltas"], {})
        self.assertEqual(self.controller.baseline, baseline)
        self.assertEqual(self.controller.scores, scores)
        self.assertFalse(self.advance(5)["visible"])
        self.assertTrue(self.controller.automatic)
        self.assertEqual(self.controller.baseline, baseline)

    def test_stale_and_error_reads_do_not_advance_baseline_recovery_alerts_once(self):
        self.establish_baseline()
        baseline = copy.deepcopy(self.controller.baseline)
        self.payload["updated"] = 800
        self.payload["leagues"][0]["me"]["score"] += 10
        state = self.advance()
        self.assertFalse(state["visible"])
        self.assertIn("STALE", scene_text(state))
        self.assertEqual(self.controller.baseline, baseline)
        self.fetch_error = OSError("offline")
        state = self.advance()
        self.assertFalse(state["visible"])
        self.assertIn("FEED UNAVAILABLE", scene_text(state))
        self.assertEqual(self.controller.baseline, baseline)
        self.fetch_error = None
        self.payload["updated"] = self.clock.wall
        recovered = self.advance()
        self.assertTrue(recovered["visible"])
        self.assertEqual(self.advance()["alertId"], recovered["alertId"])

    def test_startup_errors_and_stale_reads_do_not_establish_baseline(self):
        self.fetch_error = OSError("offline")
        state = self.controller.tick()
        self.assertFalse(state["visible"])
        self.assertIsNone(self.controller.baseline)
        self.fetch_error = None
        self.payload["updated"] = 800
        self.assertFalse(self.advance()["visible"])
        self.assertIsNone(self.controller.baseline)
        self.payload["updated"] = self.clock.wall
        state = self.advance()
        self.assertFalse(state["visible"])
        self.assertIsNotNone(self.controller.baseline)

    def test_week_matchup_and_league_identity_changes_rebaseline(self):
        self.establish_baseline()
        for field, value in (("week", 8), ("opponent", 99), ("leagueId", "C")):
            if field == "opponent":
                self.payload["leagues"][0]["opp"]["teamId"] = value
            else:
                self.payload["leagues"][0][field] = value
            self.payload["leagues"][0]["me"]["score"] = 0
            state = self.advance()
            self.assertFalse(state["visible"])
            self.assertNotIn("alertId", state)

    def test_float_noise_below_score_precision_is_ignored(self):
        self.establish_baseline()
        self.payload["leagues"][0]["me"]["score"] = 100.1000000001
        state = self.advance()
        self.assertFalse(state["visible"])
        self.assertNotIn("alertId", state)

    def test_missing_or_nonfinite_actuals_never_become_zero_score_alerts(self):
        self.establish_baseline()
        baseline = copy.deepcopy(self.controller.baseline)
        for value in (None, float("nan"), float("inf"), True):
            self.payload["leagues"][0]["me"]["score"] = value
            state = self.advance()
            self.assertFalse(state["visible"])
            self.assertEqual(self.controller.baseline, baseline)
            json.dumps(state, allow_nan=False)

    def test_expiry_is_monotonic_even_if_wall_clock_moves_backwards(self):
        first = self.trigger_score_change()
        self.clock.wall -= 3600
        self.clock.monotonic += 5
        state = self.controller.tick()
        self.assertFalse(state["visible"])
        self.assertEqual(state["alertId"], first["alertId"])

    def test_fetch_latency_does_not_consume_popup_duration(self):
        self.establish_baseline()
        self.fetch_delay = 3
        self.payload["leagues"][0]["me"]["score"] += 1
        state = self.advance()
        self.assertTrue(state["visible"])
        self.assertEqual(self.controller.alert_until, self.clock.monotonic + 5)

    def test_bad_source_timestamp_is_rejected_without_false_alert(self):
        self.establish_baseline()
        baseline = copy.deepcopy(self.controller.baseline)
        self.payload["updated"] = self.clock.wall + 90
        self.payload["leagues"][0]["me"]["score"] += 10
        state = self.advance()
        self.assertFalse(state["visible"])
        self.assertIn("future", self.controller.last_error)
        self.assertEqual(self.controller.baseline, baseline)

    def test_manual_preview_omits_alert_id_and_quit_sends_exit(self):
        self.establish_baseline()
        self.controller.apply_command("show")
        self.assertTrue(self.published[-1]["visible"])
        self.assertNotIn("alertId", self.published[-1])
        self.assertFalse(self.controller.automatic)
        self.assertFalse(self.controller.apply_command("quit"))
        self.assertFalse(self.published[-1]["visible"])
        self.assertTrue(self.published[-1]["exit"])

    def test_invalid_serialization_preserves_previous_atomic_file(self):
        atomic_write(self.state_path, {"visible": False})
        with self.assertRaises(ValueError):
            atomic_write(self.state_path, {"value": float("nan")})
        self.assertEqual(json.loads(self.state_path.read_text()), {"visible": False})
        self.assertEqual(list(Path(self.directory.name).iterdir()), [self.state_path])

    def test_both_changed_leagues_cycle_as_distinct_five_second_popups(self):
        self.establish_baseline()
        self.payload["leagues"][0]["me"]["score"] += 1
        self.payload["leagues"][1]["opp"]["score"] -= 2
        first = self.advance()
        self.assertEqual(first["selectedLeagueId"], "A")
        self.assertEqual(first["event"]["changedLeagueIds"], ["A", "B"])
        self.assertEqual(first["event"]["scoreDeltas"]["B"], {"me": 0.0, "opp": -2.0})
        second = self.advance(5)
        self.assertTrue(second["visible"])
        self.assertEqual(second["selectedLeagueId"], "B")
        self.assertNotEqual(first["alertId"], second["alertId"])
        self.assertEqual(self.controller.alert_until, self.clock.monotonic + 5)
        self.assertFalse(self.advance(5)["visible"])

    def test_waiting_league_is_not_starved_by_repeated_updates_in_first_league(self):
        self.establish_baseline()
        self.payload["leagues"][0]["me"]["score"] += 1
        self.payload["leagues"][1]["me"]["score"] += 2
        self.advance()
        for _ in range(4):
            self.payload["leagues"][0]["me"]["score"] += 0.1
            state = self.advance()
            self.assertEqual(state["selectedLeagueId"], "A")
        self.payload["leagues"][0]["me"]["score"] += 0.1
        second = self.advance()
        self.assertEqual(second["selectedLeagueId"], "B")
        self.assertEqual(self.controller.alert_until, self.clock.monotonic + 5)
        for _ in range(4):
            self.payload["leagues"][0]["me"]["score"] += 0.1
            self.assertEqual(self.advance()["selectedLeagueId"], "B")
        next_a = self.advance()
        self.assertEqual(next_a["selectedLeagueId"], "A")
        self.assertAlmostEqual(next_a["event"]["scoreDeltas"]["A"]["me"], 0.9)

    def test_control_revision_changes_only_for_explicit_commands(self):
        first = self.establish_baseline()
        self.assertEqual(first["controlRevision"], 0)
        self.assertEqual(self.advance()["controlRevision"], 0)
        self.payload["leagues"][0]["me"]["score"] += 1
        self.assertEqual(self.advance()["controlRevision"], 0)
        for index, command in enumerate(("show", "hide", "preview", "expanded", "compact", "auto"), 1):
            self.controller.apply_command(command)
            self.assertEqual(self.published[-1]["controlRevision"], index)
            self.assertEqual(self.advance()["controlRevision"], index)
        self.controller.apply_command("quit")
        self.assertEqual(self.published[-1]["controlRevision"], 7)

    def test_every_hidden_heartbeat_keeps_current_starters_only_sidebars_available(self):
        for league in self.payload["leagues"]:
            league["me"]["players"] = [
                {"slot": "QB", "name": "Starting QB", "pts": 12.3},
                {"slot": "BE", "name": "Bench Player", "pts": 99.9, "bench": True},
                {"slot": "IR", "name": "Reserve Player", "pts": 88.8},
            ]
        state = self.establish_baseline()
        self.assertEqual([entry["leagueId"] for entry in state["sidebarScenes"]], ["A", "B"])
        for entry in state["sidebarScenes"]:
            labels = " ".join(obj.get("text", "") for obj in entry["scene"]["objects"])
            self.assertIn("Starting QB", labels)
            self.assertNotIn("Bench Player", labels)
            self.assertNotIn("Reserve Player", labels)
        self.assertTrue(state["sidebarPolicy"]["holdWhileOpen"])
        self.assertTrue(state["sidebarPolicy"]["closeOnHeartbeatExpiry"])
        self.assertEqual(self.advance()["sidebarScenes"], state["sidebarScenes"])

    def test_cached_nfl_live_updates_sidebar_without_triggering_score_popup(self):
        class LiveCache:
            live = False

            def submit_latest(self, payload):
                pass

            def apply_cached(self, payload):
                result = copy.deepcopy(payload)
                result["nflLive"] = {"available": self.live}
                for league in result.get("leagues", []):
                    for side in ("me", "opp"):
                        for player in league.get(side, {}).get("players", []):
                            player.update({"nflGameState": "live" if self.live else "unknown",
                                           "nflHighlightLive": self.live,
                                           "nflAvailability": "available"})
                return result

        live = LiveCache()
        self.controller.live_enricher = live
        self.payload["leagues"][0]["me"]["players"] = [
            {"slot": "QB", "name": "Josh Allen", "pts": 20, "proj": 30}]
        self.establish_baseline()
        baseline = copy.deepcopy(self.controller.baseline)
        live.live = True
        state = self.advance()
        self.assertFalse(state["visible"])
        self.assertNotIn("alertId", state)
        self.assertEqual(self.controller.baseline, baseline)
        self.assertTrue(state["nflLive"]["available"])
        labels = " ".join(obj.get("text", "") for obj in state["sidebarScenes"][0]["scene"]["objects"])
        self.assertIn("LIVE", labels)

    def test_optional_nfl_failure_does_not_fail_fantasy_feed_or_replay_live(self):
        class BrokenLive:
            def submit_latest(self, payload):
                pass

            def apply_cached(self, payload):
                raise OSError("public NFL timeout")

        self.controller.live_enricher = BrokenLive()
        state = self.establish_baseline()
        self.assertTrue(state["feed"]["available"])
        self.assertFalse(state["nflLive"]["available"])
        self.assertIsNone(self.controller.last_error)


if __name__ == "__main__":
    unittest.main()
