"""Synthetic manager labels; never consult a real league or saved household."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from controller import ScoreController
from owner_names import OWNER_UNAVAILABLE, annotate_owner_names, load_owner_names


MAPPING = {"league-a": {"2": "Alex Morgan", "4": "Casey Taylor"}}


class OwnerNamesTests(unittest.TestCase):
    def fixture(self):
        return {"updated": 1000, "ok": True, "leagues": [
            {"leagueId": "league-a", "week": 7, "ok": True,
             "me": {"teamId": 2, "name": "Example Team", "score": 100,
                    "players": [{"slot": "QB", "name": "Example Quarterback", "pts": 20}]},
             "opp": {"teamId": 4, "name": "Another Team", "score": 90,
                     "players": [{"slot": "RB", "name": "Example Runner", "pts": 10}]}}
        ]}

    def test_team_ids_are_not_league_table_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "owners.json"
            path.write_text(json.dumps({"schemaVersion": 1, "season": date.today().year,
                                        "leagues": MAPPING}))
            mapping = load_owner_names(path)
        self.assertEqual(mapping["league-a"]["4"], "Casey Taylor")
        self.assertNotIn("1", mapping["league-a"])

    def test_copy_annotation_preserves_original_and_player_data(self):
        payload = self.fixture()
        original = deepcopy(payload)
        league = annotate_owner_names(payload, MAPPING)["leagues"][0]
        self.assertEqual(league["me"]["ownerName"], "Alex Morgan")
        self.assertEqual(league["opp"]["displayLabel"], "Casey Taylor")
        self.assertEqual(league["me"]["name"], "Example Team")
        self.assertEqual(league["me"]["players"][0]["name"], "Example Quarterback")
        self.assertEqual(payload, original)

    def test_unknown_owner_does_not_fall_back_to_team_name(self):
        payload = self.fixture()
        payload["leagues"][0]["opp"]["teamId"] = 999
        team = annotate_owner_names(payload, MAPPING)["leagues"][0]["opp"]
        self.assertEqual(team["ownerName"], OWNER_UNAVAILABLE)

    def test_private_backend_owner_is_preserved_and_controls_cleaned(self):
        payload = self.fixture()
        payload["leagues"][0]["me"]["ownerName"] = "Alex\nMorgan\u202e"
        team = annotate_owner_names(payload, {})["leagues"][0]["me"]
        self.assertEqual(team["ownerName"], "Alex Morgan")
        self.assertNotEqual(team["ownerName"], team["name"])

    def test_map_from_other_season_cannot_override_current_backend_owner(self):
        payload = self.fixture()
        payload["seasonId"] = date.today().year + 1
        payload["leagues"][0]["me"]["ownerName"] = "New Manager"
        team = annotate_owner_names(payload, MAPPING)["leagues"][0]["me"]
        self.assertEqual(team["ownerName"], "New Manager")

    def test_missing_file_and_wrong_season_are_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "owners.json"
            self.assertEqual(load_owner_names(path), {})
            path.write_text(json.dumps({"schemaVersion": 1, "season": 1900,
                                        "leagues": MAPPING}))
            self.assertEqual(load_owner_names(path), {})

    def test_controller_preserves_backend_owner_without_private_mapping(self):
        payload = self.fixture()
        payload["leagues"][0]["me"]["ownerName"] = "Alex Morgan"
        original = deepcopy(payload)
        with tempfile.TemporaryDirectory() as folder, patch("controller.load_owner_names", return_value={}):
            controller = ScoreController(Path(folder) / "state.json", fetcher=lambda _: payload,
                                         clock=lambda: 1000, timer_clock=lambda: 10)
            state = controller.tick()
            self.assertEqual(controller.scores["leagues"][0]["me"]["ownerName"], "Alex Morgan")
            self.assertEqual(payload, original)
            self.assertIn("sidebarScenes", state)


if __name__ == "__main__":
    unittest.main()
