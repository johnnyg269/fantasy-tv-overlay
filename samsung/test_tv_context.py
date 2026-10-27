import asyncio
import unittest
from types import SimpleNamespace

from tv_context import build_context, match_game_title, read_connected_metadata


def scoreboard():
    def team(identity, name, short, abbreviation):
        return {"id": identity, "displayName": name, "name": short, "abbreviation": abbreviation}
    return {"events": [
        {"id": "game-1", "competitions": [{"competitors": [
            {"team": team("12", "Kansas City Chiefs", "Chiefs", "KC")},
            {"team": team("26", "Seattle Seahawks", "Seahawks", "SEA")}]}]},
        {"id": "game-2", "competitions": [{"competitors": [
            {"team": team("17", "New England Patriots", "Patriots", "NE")},
            {"team": team("18", "New Orleans Saints", "Saints", "NO")}]}]},
    ]}


class ContextTests(unittest.TestCase):
    def test_unambiguous_two_team_name_title(self):
        value = build_context({"app": "Prime Video", "title": "Kansas City Chiefs at Seattle Seahawks"}, scoreboard())
        self.assertEqual(value["matchedGameId"], "game-1")
        self.assertEqual(value["confidence"], "exact-title-pair")
        self.assertFalse(value["manualOverride"])

    def test_nickname_pair_and_uppercase_abbreviations(self):
        self.assertEqual(match_game_title("Chiefs vs. Seahawks", scoreboard()), "game-1")
        self.assertEqual(match_game_title("KC @ SEA", scoreboard()), "game-1")

    def test_channel_and_generic_football_not_inferred(self):
        for title in ("NFL Football", "Thursday Night Football", "CBS Sports", "Prime Video", "Chiefs"):
            self.assertIsNone(match_game_title(title, scoreboard()))

    def test_redzone_and_multiview_remain_unknown(self):
        for title in ("NFL RedZone: Chiefs vs Seahawks", "Multiview KC @ SEA", "Chiefs Seahawks Patriots Saints"):
            self.assertIsNone(match_game_title(title, scoreboard()))

    def test_two_different_games_with_same_pair_is_ambiguous(self):
        data = scoreboard()
        duplicate = dict(data["events"][0], id="old-replay")
        data["events"].append(duplicate)
        self.assertIsNone(match_game_title("Chiefs at Seahawks", data))

    def test_ordinary_no_is_not_saints_abbreviation(self):
        self.assertIsNone(match_game_title("No Patriots news", scoreboard()))

    def test_missing_metadata_does_not_reuse_previous_game(self):
        self.assertIsNone(build_context({}, scoreboard())["matchedGameId"])
        self.assertEqual(build_context({}, scoreboard())["confidence"], "unknown")

    def test_compact_feed_requires_real_game_id(self):
        self.assertIsNone(match_game_title("KC @ SEA", {"nfl": [{"away": "KC", "home": "SEA"}]}))
        self.assertEqual(match_game_title("KC @ SEA", {"nfl": [{"gameId": "real-id", "away": "KC", "home": "SEA"}]}), "real-id")

    def test_manual_game_override_is_explicit_and_validated(self):
        value = build_context({"title": "NFL Football"}, scoreboard(), "game-2")
        self.assertTrue(value["manualOverride"])
        self.assertEqual(value["matchedGameId"], "game-2")
        self.assertEqual(value["confidence"], "manual")
        with self.assertRaises(ValueError):
            build_context({}, scoreboard(), "not-a-known-game")

    def test_manual_redzone_does_not_invent_game(self):
        value = build_context({"title": "Chiefs at Seahawks"}, scoreboard(), "redzone")
        self.assertTrue(value["manualOverride"])
        self.assertIsNone(value["matchedGameId"])
        self.assertEqual(value["source"], "manual-redzone")
        self.assertEqual(value["confidence"], "manual")

    def test_explicit_adapter_calls_only_metadata(self):
        class Metadata:
            app = SimpleNamespace(name="Prime Video", identifier="com.amazon.aiv.AIVApp")
            async def playing(self):
                return SimpleNamespace(title="Chiefs at Seahawks")
        result = asyncio.run(read_connected_metadata(SimpleNamespace(metadata=Metadata())))
        self.assertEqual(result, {"app": "Prime Video", "title": "Chiefs at Seahawks"})


if __name__ == "__main__":
    unittest.main()
