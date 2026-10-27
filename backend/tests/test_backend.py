import copy
import json
import http.client
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.config import Config, ConfigurationError, League, load_config, parse_leagues
from backend.demo import scores
from backend.http_client import ProviderError, get_json
from backend.live import GameStatus
from backend.providers import espn, sleeper
from backend.service import FeedService, respond
from backend.server import LocalServer, handler_for


TOKEN = "TEST_ONLY_FEED_TOKEN_NOT_A_CREDENTIAL_1234"
LEAGUE = League("espn", "123456", 1, 2026, "Test league")


def espn_fixture():
    def side(identifier, points):
        entries = [{"lineupSlotId": 0, "appliedStatTotal": 12.25,
                    "playerPoolEntry": {"player": {"id": identifier, "fullName": "Demo player",
                      "proTeamId": 2, "stats": [{"scoringPeriodId": 7, "seasonId": 2026,
                      "statSourceId": 0, "appliedTotal": 12.25, "proTeamId": 1},
                      {"scoringPeriodId": 7, "seasonId": 2026, "statSourceId": 1, "appliedTotal": 20}]}}},
                   {"lineupSlotId": 20, "playerPoolEntry": {"player": {"fullName": "Bench private"}}},
                   {"lineupSlotId": 21, "playerPoolEntry": {"player": {"fullName": "Reserve private"}}}]
        return {"teamId": identifier, "totalPoints": points - 10, "totalPointsLive": points,
                "totalProjectedPointsLive": points + 20,
                "rosterForCurrentScoringPeriod": {"entries": entries}}
    return {"members": [{"id": "member-a", "firstName": "Alex", "lastName": "Example"},
                         {"id": "member-b", "firstName": "Taylor", "lastName": "Sample"}],
            "teams": [{"id": 1, "name": "Team A", "owners": ["member-a"]},
                      {"id": 2, "name": "Team B", "owners": ["member-b"]}],
            "schedule": [{"matchupPeriodId": 7, "home": side(1, 112.38), "away": side(2, 104.76)}]}


def sleeper_fixture():
    return ({"sport": "nfl", "season": "2026", "roster_positions": ["QB", "FLEX", "BN", "BN"]},
            [{"roster_id": 1, "owner_id": "u-a"}, {"roster_id": 2, "owner_id": "u-b"}],
            [{"user_id": "u-a", "display_name": "Alex"}, {"user_id": "u-b", "display_name": "Taylor"}],
            [{"roster_id": 1, "matchup_id": 9, "points": 101.25,
              "starters": ["p1", "0"], "players_points": {"p1": 20.5, "bench": 50}},
             {"roster_id": 2, "matchup_id": 9, "points": 99.75,
              "starters": ["p2", "p3"], "starters_points": [16.5, 8]}],
            {"p1": {"full_name": "Demo passer", "team": "BUF", "status": "Active"},
             "p2": {"full_name": "Other passer", "team": "NE"},
             "p3": {"full_name": "Other receiver", "team": "KC"}})


class ConfigTests(unittest.TestCase):
    def test_environment_secrets_are_not_represented(self):
        env = {"VERCEL": "1", "FANTASY_LEAGUES_JSON": json.dumps([{
            "provider": "espn", "id": "123456", "teamId": 1, "season": 2026}]),
            "FANTASY_FEED_TOKEN": TOKEN, "ESPN_S2": "TEST_COOKIE_ONLY", "SWID": "TEST_SWID_ONLY"}
        config = load_config(env)
        self.assertNotIn(TOKEN, repr(config))
        self.assertNotIn("TEST_COOKIE_ONLY", repr(config))
        self.assertEqual(config.leagues[0].key, "espn:123456")

    def test_serverless_does_not_read_local_private_file(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "config.json"
            file.write_text(json.dumps({"feedToken": TOKEN, "leagues": [{"id": "123456", "teamId": 1, "season": 2026}]}))
            with self.assertRaises(ConfigurationError):
                load_config({"VERCEL": "1"}, path=file)

    def test_bad_provider_identifiers_and_duplicates_fail(self):
        base = {"provider": "espn", "id": "123456", "teamId": 1, "season": 2026}
        for change in ({"provider": "arbitrary-code"}, {"id": "../secret"}, {"teamId": True},
                       {"season": "2026"}, {"week": 0}, {"ownerNames": {"1": 23}}):
            with self.assertRaises(ConfigurationError):
                parse_leagues([{**base, **change}])
        with self.assertRaises(ConfigurationError):
            parse_leagues([base, base])

    def test_local_json_secrets_and_injection_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = {"feedToken": TOKEN, "leagues": [{"id": "123456", "teamId": 1, "season": 2026}],
                      "espnS2": "test;injected=bad", "swid": "test"}
            path.write_text(json.dumps(config))
            with self.assertRaises(ConfigurationError):
                load_config({}, path)
            config["espnS2"] = "test-cookie"
            path.write_text(json.dumps(config))
            self.assertEqual(load_config({}, path).swid, "test")


class EspnTests(unittest.TestCase):
    def test_live_total_owner_identity_and_starting_rows(self):
        data = espn_fixture()
        result = espn.normalize(data, LEAGUE, 7, 7)
        self.assertEqual(result["me"]["ownerName"], "Alex Example")
        self.assertEqual(result["me"]["score"], 112.38)
        self.assertEqual(len(result["me"]["players"]), 1)
        self.assertEqual(result["me"]["players"][0]["proTeamId"], 1)
        self.assertEqual(result["me"]["players"][0]["pts"], 12.25)
        self.assertIsNone(result["winProb"])
        self.assertEqual(data, espn_fixture())

    def test_away_side_swaps_own_and_opponent_correctly(self):
        config = League("espn", "123456", 2, 2026, "Test league")
        result = espn.normalize(espn_fixture(), config, 7, 7)
        self.assertEqual(result["me"]["teamId"], "2")
        self.assertEqual(result["opp"]["teamId"], "1")

    def test_bye_ambiguous_matchup_and_invalid_total_fail_closed(self):
        for mutate in (lambda d: d["schedule"][0].pop("away"),
                       lambda d: d["schedule"].append(copy.deepcopy(d["schedule"][0])),
                       lambda d: d["schedule"][0]["home"].update(totalPointsLive=float("nan"))):
            data = espn_fixture()
            mutate(data)
            with self.assertRaises(ProviderError):
                espn.normalize(data, LEAGUE, 7, 7)

    def test_no_guessing_manager_from_team_name(self):
        data = espn_fixture()
        data["members"] = []
        self.assertEqual(espn.normalize(data, LEAGUE, 7, 7)["me"]["ownerName"], "Owner unavailable")

    def test_private_cookie_only_sent_to_fixed_origin_and_week_filter(self):
        calls = []
        def client(url, headers):
            calls.append((url, dict(headers)))
            if "mSettings" in url:
                return {"scoringPeriodId": 7, "status": {"currentMatchupPeriod": 7}}
            return espn_fixture()
        espn.fetch(LEAGUE, Config((LEAGUE,), TOKEN, "test-cookie", "test-swid"), client)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(url.startswith("https://lm-api-reads.fantasy.espn.com/") for url, _ in calls))
        self.assertIn("scoringPeriodId=7", calls[1][0])
        self.assertIn("filterMatchupPeriodIds", calls[1][1]["X-Fantasy-Filter"])
        self.assertNotIn("test-cookie", calls[1][0])

    def test_auto_week_uses_root_field_and_caps_final_period(self):
        for root_week, final_week, expected in ((7, 17, 7), (18, 17, 17)):
            calls = []
            def client(url, headers):
                calls.append(url)
                if "mSettings" in url:
                    return {"scoringPeriodId": root_week, "status": {
                        "currentScoringPeriod": 8, "currentMatchupPeriod": 7, "finalScoringPeriod": final_week}}
                return espn_fixture()
            result = espn.fetch(LEAGUE, Config((LEAGUE,), TOKEN), client)
            self.assertIn("scoringPeriodId=" + str(expected), calls[1])
            self.assertEqual(result["week"], expected)


class SleeperTests(unittest.TestCase):
    def normalize(self, parts=None, config=None):
        league, rosters, users, matchups, players = parts or sleeper_fixture()
        return sleeper.normalize(config or League("sleeper", "123456789012345678", 1, 2026, "Test league"),
                                 league, rosters, users, matchups, 7, players)

    def test_starters_not_roster_or_bench_and_correct_points(self):
        result = self.normalize()
        self.assertEqual([p["name"] for p in result["me"]["players"]], ["Demo passer", "Empty slot"])
        self.assertEqual(result["me"]["players"][0]["pts"], 20.5)
        self.assertEqual(result["opp"]["players"][1]["pts"], 8)
        self.assertIsNone(result["me"]["proj"])
        self.assertIsNone(result["winProb"])

    def test_custom_points_zero_is_not_replaced(self):
        parts = sleeper_fixture()
        parts[3][0]["custom_points"] = 0
        self.assertEqual(self.normalize(parts)["me"]["score"], 0)

    def test_unknown_player_missing_slot_and_bye_fail(self):
        for mutate in (lambda p: p[4].pop("p1"),
                       lambda p: p[3][0].update(starters=["p1"]),
                       lambda p: p[3][0].update(matchup_id=None)):
            parts = sleeper_fixture()
            mutate(parts)
            with self.assertRaises(ProviderError):
                self.normalize(parts)

    def test_preferred_manager_names_are_explicit(self):
        config = League("sleeper", "123456789012345678", 1, 2026, "Test league", owner_names={"1": "Alex Example"})
        self.assertEqual(self.normalize(config=config)["me"]["ownerName"], "Alex Example")

    def test_missing_catalog_does_not_download_automatically(self):
        with self.assertRaises(ProviderError):
            sleeper.load_players("/nonexistent-catalog-for-test.json")


class ServiceTests(unittest.TestCase):
    def service(self, adapter=None, clock=lambda: 1000):
        return FeedService(Config((LEAGUE,), TOKEN), clock=clock,
                           adapters={"espn": adapter or (lambda c, s: scores(1000)["leagues"][0])},
                           game_status=type("Identity", (), {"annotate": lambda self, d: d})())

    def test_no_auth_means_no_provider_request_and_no_data(self):
        calls = []
        service = self.service(lambda c, s: calls.append(1))
        for auth in (None, "", "Bearer wrong", "Bearer \u2603", "Basic example"):
            status, headers, body = respond(service, "/api/scores", auth)
            self.assertEqual(status, 401)
            self.assertNotIn("leagues", body)
            self.assertEqual(headers["Cache-Control"], "private, no-store, max-age=0")
        self.assertEqual(calls, [])

    def test_query_tokens_and_unknown_routes_never_authenticate(self):
        for path in ("/api/scores?token=example", "/api/scores/", "/.private/config.json"):
            self.assertEqual(respond(self.service(), path, "Bearer " + TOKEN)[0], 404)

    def test_cache_coalesces_then_expires_and_uses_source_time(self):
        clock = [1000]
        calls = []
        service = self.service(lambda c, s: (calls.append(1) or scores(1000)["leagues"][0]), lambda: clock[0])
        first = service.scores()
        clock[0] = 1002
        self.assertEqual(service.scores()["updated"], first["updated"])
        self.assertEqual(len(calls), 1)
        clock[0] = 1006
        self.assertEqual(service.scores()["updated"], 1006)
        self.assertEqual(len(calls), 2)

    def test_provider_error_never_echoes_exception_secret_or_stale_success(self):
        def fail(c, s):
            raise RuntimeError("Sensitive test marker should never escape")
        service = self.service(fail)
        status, _, body = respond(service, "/api/scores", "Bearer " + TOKEN)
        self.assertEqual(status, 503)
        self.assertEqual(body["leagues"], [])
        self.assertNotIn("updated", body)
        self.assertNotIn("Sensitive", json.dumps(body))

    def test_slow_fetch_caches_from_completion_not_start(self):
        clock, calls = [1000], []
        def slow(c, s):
            calls.append(1)
            clock[0] += 10
            return scores(clock[0])["leagues"][0]
        service = self.service(slow, lambda: clock[0])
        service.scores()
        clock[0] += 2
        service.scores()
        self.assertEqual(len(calls), 1)

    def test_demo_is_synthetic_and_observable(self):
        service = FeedService(demo=True, clock=lambda: 1000)
        payload = respond(service, "/api/scores")[2]
        self.assertTrue(payload["demo"])
        self.assertEqual(payload["leagues"][0]["me"]["ownerName"], "Alex")


class BoundaryTests(unittest.TestCase):
    def test_real_loopback_http_auth_routes_and_cache_headers(self):
        service = FeedService(Config((LEAGUE,), TOKEN),
            adapters={"espn": lambda c, s: scores(1000)["leagues"][0]},
            game_status=type("Identity", (), {"annotate": lambda self, d: d})())
        server = LocalServer(("127.0.0.1", 0), handler_for(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for route, auth, expected in (("/api/scores", None, 401),
                    ("/api/scores?token=example", "Bearer " + TOKEN, 404),
                    ("/api/scores", "Bearer " + TOKEN, 200)):
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                connection.request("GET", route, headers={"Authorization": auth} if auth else {})
                response = connection.getresponse()
                body = json.loads(response.read())
                self.assertEqual(response.status, expected)
                self.assertIn("no-store", response.getheader("Cache-Control"))
                self.assertNotIn("Access-Control-Allow-Origin", response.headers)
                self.assertNotIn(TOKEN, json.dumps(body))
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_credentials_cannot_be_sent_to_another_origin(self):
        for url in ("http://api.sleeper.app/v1/state/nfl", "https://api.sleeper.app.attacker.invalid/",
                    "https://user:password@api.sleeper.app/", "https://127.0.0.1/", "file:///etc/hosts"):
            with self.assertRaises(ProviderError):
                get_json(url)

    def test_live_game_badge_identity_and_known_out_suppression(self):
        clock = [1000]
        state = GameStatus(lambda: {"season": {"year": 2026, "type": 2}, "week": {"number": 7},
            "events": [{"id": "1001", "competitions": [{
            "status": {"type": {"state": "in"}}, "competitors": [{"team": {"id": "1", "abbreviation": "BUF"}}]}]}]}, lambda: clock[0])
        payload = scores(1000)
        for league in payload["leagues"]:
            for side in ("me", "opp"):
                for player in league[side]["players"]:
                    player["proTeamId"] = 1
        payload["leagues"][0]["me"]["players"][0]["injuryStatus"] = "OUT"
        enriched = state.annotate(payload)
        self.assertFalse(enriched["leagues"][0]["me"]["players"][0]["nflHighlightLive"])
        self.assertTrue(enriched["leagues"][0]["me"]["players"][1]["nflHighlightLive"])
        state.fetcher = lambda: (_ for _ in ()).throw(ProviderError("unavailable"))
        clock[0] += 91
        self.assertFalse(state.annotate(payload)["leagues"][0]["me"]["players"][1]["nflHighlightLive"])

    def test_live_metadata_cannot_join_other_seasons_weeks_or_blank_identities(self):
        def source():
            return {"season": {"year": 2026, "type": 2}, "week": {"number": 7},
                    "events": [{"id": "1001", "competitions": [{"status": {"type": {"state": "in"}},
                    "competitors": [{"team": {"id": "1", "abbreviation": "BUF"}}, {"team": {}}]}]}]}
        for change in ("season", "week", "identity", "ambiguous"):
            data = source()
            payload = scores(1000)
            row = payload["leagues"][0]["me"]["players"][0]
            row["proTeamId"] = 1
            if change == "season":
                payload["leagues"][0]["seasonId"] = 2020
            elif change == "week":
                payload["leagues"][0]["week"] = 1
            elif change == "identity":
                row.pop("proTeamId")
                row["proTeamAbbreviation"] = ""
            else:
                other = copy.deepcopy(data["events"][0])
                other["id"] = "1002"
                data["events"].append(other)
            enriched = GameStatus(lambda: data, lambda: 1000).annotate(payload)
            self.assertFalse(enriched["leagues"][0]["me"]["players"][0]["nflHighlightLive"], change)


if __name__ == "__main__":
    unittest.main()
