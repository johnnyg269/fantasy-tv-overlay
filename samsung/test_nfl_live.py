"""Public NFL enrichment policies tested with synthetic JSON, never the network."""

from copy import deepcopy
import json
import threading
import time
import unittest

from nfl_live import BASE, NflLiveEnricher, TEAMS_URL, _games


def team(team_id, abbreviation, nickname):
    return {"team": {"id": str(team_id), "abbreviation": abbreviation,
                     "displayName": nickname + " City " + nickname,
                     "shortDisplayName": nickname, "name": nickname}}


def athlete(athlete_id, name, position, status="Active", injuries=None):
    return {"id": str(athlete_id), "fullName": name, "displayName": name,
            "position": {"abbreviation": position},
            "status": {"name": status, "type": status.lower()},
            "injuries": injuries or []}


def scoreboard(phase="in"):
    return {"events": [{"id": "1001", "season": {"year": 2026, "type": 2}, "week": {"number": 7}, "status": {
        "period": 4, "displayClock": "3:22",
        "type": {"state": phase, "shortDetail": "Final" if phase == "post" else "Live"}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"id": "1", "abbreviation": "BUF"}},
            {"homeAway": "away", "team": {"id": "2", "abbreviation": "JAX"}},
        ]}]}]}


def payload():
    return {"updated": 1000, "leagues": [{"leagueId": "private-league-id", "seasonId": 2026, "week": 7,
        "me": {"ownerName": "Verified Owner", "players": [
            {"name": "Josh Allen", "slot": "QB", "pts": 20},
            {"name": "Buffalo D/ST", "slot": "D/ST", "pts": 5},
            {"name": "Out Receiver", "slot": "WR", "pts": 1},
            {"name": "IR Receiver", "slot": "WR", "pts": 2},
            {"name": "Unknown Person", "slot": "RB", "pts": 3},
        ]}, "opp": {"players": []}}]}


class NflLiveTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.calls = []
        self.phase = "in"
        self.fail_scoreboard = False
        self.rosters = {
            "1": {"athletes": [{"position": "offense", "items": [
                athlete("11", "Josh Allen", "QB"),
                athlete("12", "Out Receiver", "WR", injuries=[{"status": "Out"}]),
                athlete("13", "IR Receiver", "WR", status="Day-To-Day",
                        injuries=[{"status": "Injured Reserve"}]),
            ]}]},
            "2": {"athletes": [{"position": "defense", "items": [
                athlete("21", "Josh Allen", "LB"),
            ]}]},
        }

        def fetch(url):
            self.calls.append(url)
            if url == TEAMS_URL:
                return {"sports": [{"leagues": [{"teams": [team(1, "BUF", "Buffalo"),
                                                             team(2, "JAX", "Jacksonville")]}]}]}
            if "/scoreboard?" in url:
                if self.fail_scoreboard:
                    raise OSError("public service unavailable")
                return scoreboard(self.phase)
            key = url.split("/teams/")[1].split("/")[0]
            return deepcopy(self.rosters[key])

        self.enricher = NflLiveEnricher(fetcher=fetch, clock=lambda: self.now)

    def annotate(self, source=None):
        return self.enricher.annotate(payload() if source is None else source, date="20261025")

    def test_exact_name_and_qb_position_disambiguate_josh_allen(self):
        result = self.annotate()
        player = result["leagues"][0]["me"]["players"][0]
        self.assertEqual(player["nflTeamId"], "1")
        self.assertEqual(player["gameId"], "1001")
        self.assertEqual(player["nflGameState"], "live")
        self.assertTrue(player["nflHighlightLive"])
        self.assertEqual(player["nflGameLabel"], "Q4 3:22 vs JAX")

    def test_defense_alias_uses_team_metadata_not_player_roster(self):
        defense = self.annotate()["leagues"][0]["me"]["players"][1]
        self.assertEqual(defense["nflTeamId"], "1")
        self.assertEqual(defense["mappingConfidence"], "team-exact")
        self.assertTrue(defense["nflHighlightLive"])

    def test_confirmed_out_and_ir_are_not_highlighted_during_live_game(self):
        players = self.annotate()["leagues"][0]["me"]["players"]
        for player, availability in ((players[2], "out"), (players[3], "injured-reserve")):
            self.assertEqual(player["nflGameState"], "live")
            self.assertFalse(player["nflHighlightLive"])
            self.assertEqual(player["nflAvailability"], availability)
            self.assertIn(availability.upper(), player["nflGameLabel"])

    def test_unknown_and_position_ambiguous_never_get_live_status(self):
        source = payload()
        source["leagues"][0]["me"]["players"].append({"name": "Josh Allen", "slot": "BE"})
        players = self.annotate(source)["leagues"][0]["me"]["players"]
        self.assertEqual(players[4]["nflGameState"], "unknown")
        self.assertFalse(players[4]["nflHighlightLive"])
        self.assertEqual(players[-1]["mappingConfidence"], "ambiguous")
        self.assertEqual(players[-1]["nflGameState"], "unknown")

    def test_final_and_scheduled_are_never_highlighted(self):
        for phase, expected in (("post", "final"), ("pre", "scheduled")):
            self.phase = phase
            self.now += 31
            player = self.annotate()["leagues"][0]["me"]["players"][0]
            self.assertEqual(player["nflGameState"], expected)
            self.assertFalse(player["nflHighlightLive"])

    def test_cache_reuses_rosters_and_refreshes_scoreboard_only_every_30_seconds(self):
        self.annotate()
        self.assertEqual(len(self.calls), 4)
        for _ in range(5):
            self.now += 5
            self.annotate()
        self.assertEqual(len(self.calls), 4)
        self.now += 5
        self.annotate()
        self.assertEqual(len(self.calls), 5)
        self.assertEqual(sum("/roster" in url for url in self.calls), 2)

    def test_scoreboard_fetch_failure_cannot_replay_stale_live_status(self):
        self.assertTrue(self.annotate()["leagues"][0]["me"]["players"][0]["nflHighlightLive"])
        self.now += 30
        self.fail_scoreboard = True
        result = self.annotate()
        self.assertFalse(result["nflLive"]["available"])
        for player in result["leagues"][0]["me"]["players"]:
            self.assertEqual(player["nflGameState"], "unknown")
            self.assertFalse(player["nflHighlightLive"])

    def test_copy_preserves_raw_names_stats_owners_and_no_private_data_in_urls(self):
        source = payload()
        original = deepcopy(source)
        result = self.annotate(source)
        self.assertEqual(source, original)
        self.assertEqual(result["leagues"][0]["me"]["players"][0]["name"], "Josh Allen")
        self.assertEqual(result["leagues"][0]["me"]["players"][0]["pts"], 20)
        self.assertEqual(result["leagues"][0]["me"]["ownerName"], "Verified Owner")
        self.assertTrue(all(url.startswith(BASE + "/") for url in self.calls))
        self.assertFalse(any("private-league-id" in url or "Josh" in url for url in self.calls))
        json.dumps(result, allow_nan=False)

    def test_stale_roster_and_unloaded_cache_are_unknown(self):
        empty = self.enricher.annotate(payload(), date="20261025", refresh=False)
        self.assertFalse(empty["leagues"][0]["me"]["players"][0]["nflHighlightLive"])
        self.annotate()
        self.now += 900
        result = self.enricher.annotate(payload(), date="20261025", refresh=False)
        self.assertEqual(result["leagues"][0]["me"]["players"][0]["nflGameState"], "unknown")

    def test_reserve_group_blocks_even_contradictory_active_status(self):
        self.rosters["1"]["athletes"][0]["position"] = "injuredReserveOrOut"
        player = self.annotate()["leagues"][0]["me"]["players"][0]
        self.assertFalse(player["nflHighlightLive"])
        self.assertEqual(player["nflAvailability"], "inactive")

    def test_roster_with_conflicting_declared_team_id_cannot_create_live_mapping(self):
        self.rosters["1"]["team"] = {"id": "999"}
        player = self.annotate()["leagues"][0]["me"]["players"][0]
        self.assertEqual(player["nflGameState"], "unknown")
        self.assertFalse(player["nflHighlightLive"])

    def test_historical_season_week_and_missing_scope_never_become_current_live(self):
        self.annotate()
        for season, week in ((2025, 7), (2026, 8), (None, 7), (2026, None),
                             (True, 7), (2026, True), ("2026", 7), (2026, "7")):
            source = payload()
            source["leagues"][0].update(seasonId=season, week=week)
            result = self.enricher.annotate(source, date="20261025", refresh=False)
            for player in result["leagues"][0]["me"]["players"]:
                self.assertFalse(player["nflHighlightLive"])
                self.assertEqual(player["nflGameState"], "unknown")
                self.assertIsNone(player["gameId"])

    def test_scoreboard_scope_is_retained_from_event_or_valid_header(self):
        data = scoreboard()
        game = _games(data)["1"]
        self.assertEqual((game["seasonId"], game["week"], game["seasonType"]), (2026, 7, 2))
        event = data["events"][0]
        data["season"] = event.pop("season")
        data["week"] = event.pop("week")
        self.assertEqual(_games(data)["1"], game)

    def test_missing_invalid_or_non_regular_scoreboard_scope_is_not_guessed(self):
        for section, field, value in (("season", "year", None), ("season", "year", True),
                                      ("season", "type", 1), ("season", "type", 3),
                                      ("season", "type", "2"), ("week", "number", None),
                                      ("week", "number", 0), ("week", "number", 19)):
            data = scoreboard(); data["events"][0][section][field] = value
            with self.subTest(section=section, field=field, value=value):
                self.assertEqual(_games(data), {})

    def test_missing_or_invalid_game_and_team_identity_cannot_produce_live(self):
        for event_id in (None, "", "not-a-game-id", 0, False):
            data = scoreboard(); data["events"][0]["id"] = event_id
            self.assertEqual(_games(data), {})
        for team_id in (None, "", "invalid", 0, False, "2"):
            data = scoreboard()
            data["events"][0]["competitions"][0]["competitors"][0]["team"]["id"] = team_id
            self.assertEqual(_games(data), {})

    def test_conflicting_games_for_one_team_fail_closed_in_either_order(self):
        data = scoreboard()
        second = deepcopy(data["events"][0]); second["id"] = "1002"
        second["competitions"][0]["competitors"][1]["team"]["id"] = "3"
        data["events"].append(second)
        self.assertNotIn("1", _games(data))
        data["events"].reverse()
        self.assertNotIn("1", _games(data))
        # An identical duplicated event is harmless and retains its identity.
        data = scoreboard(); data["events"].append(deepcopy(data["events"][0]))
        self.assertEqual(_games(data)["1"]["gameId"], "1001")

    def test_maximum_concurrency_is_four_for_initial_public_roster_load(self):
        guard = threading.Lock()
        active, maximum = [0], [0]

        def fetch(url):
            if url == TEAMS_URL:
                return {"sports": [{"leagues": [{"teams": [team(i, "T" + str(i), "Team" + str(i))
                                                             for i in range(1, 9)]}]}]}
            if "/scoreboard?" in url:
                return {"events": []}
            with guard:
                active[0] += 1
                maximum[0] = max(maximum[0], active[0])
            time.sleep(0.005)
            with guard:
                active[0] -= 1
            return {"athletes": []}

        enricher = NflLiveEnricher(fetcher=fetch, clock=lambda: 1000, max_workers=99)
        enricher.refresh("20261025")
        self.assertLessEqual(maximum[0], 4)
        self.assertEqual(len(enricher.rosters), 8)


if __name__ == "__main__":
    unittest.main()
