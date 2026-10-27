import copy
import json
import unittest

from score_scene import build_state


def fixture():
    return {"updated": 1000, "leagues": [
        {"short": "LEAGUE A", "week": 7, "ok": True,
         "me": {"name": "My team", "score": 123.45, "proj": 145.67,
                "players": [{"slot": "QB", "name": "A Player", "pts": 10,
                             "proj": 20}]},
         "opp": {"name": "Their team", "score": 98.76, "proj": 110,
                 "players": []}, "winProb": 0.8},
        {"short": "LEAGUE B", "week": 7, "ok": True,
         "me": {"name": "My team B", "score": 50.05},
         "opp": {"name": "Their team B", "score": 60.06}}
    ]}


def texts(state):
    return [o["text"] for o in state["scene"]["objects"] if o["type"] == "text"]


class ScoreSceneTests(unittest.TestCase):
    def test_compact_keeps_both_matchups(self):
        labels = texts(build_state(fixture(), now=1005))
        for expected in ("LEAGUE A", "LEAGUE B", "123.45", "98.76", "50.05", "60.06"):
            self.assertIn(expected, labels)

    def test_broadcast_graphic_stays_upper_left_and_omits_healthy_debug_status(self):
        state = build_state(fixture(), now=1005)
        labels = texts(state)
        self.assertIn("FANTASY", labels)
        self.assertNotIn("FANTASY UPDATE", labels)
        self.assertFalse(any(label.startswith("UPDATED") for label in labels))
        self.assertFalse(any("Proj" in label for label in labels))
        backing = state["scene"]["objects"][0]
        self.assertEqual((backing["x"], backing["y"]), (0, 0))
        self.assertGreaterEqual(int(backing["color"][-2:], 16), 235)
        for obj in state["scene"]["objects"]:
            self.assertGreaterEqual(obj["x"], 0)
            self.assertGreaterEqual(obj["y"], 0)
            self.assertLessEqual(obj["x"] + obj["width"], 600)
            self.assertLessEqual(obj["y"] + obj["height"], 300)

    def test_compact_name_fitting_uses_space_without_cutting_glyphs(self):
        data = fixture()
        data["leagues"][0]["opp"]["name"] = "ExampleTeamTwo"
        self.assertIn("ExampleTeamTwo", texts(build_state(data, now=1005)))
        data["leagues"][0]["opp"]["name"] = "W" * 40
        state = build_state(data, now=1005)
        fitted = [label for label in texts(state) if label.startswith("WWW")]
        self.assertEqual(len(fitted), 1)
        self.assertTrue(fitted[0].endswith("…"))
        self.assertLess(len(fitted[0]), 15)

    def test_text_uses_existing_inter_sources(self):
        state = build_state(fixture(), now=1005)
        for obj in state["scene"]["objects"]:
            if obj["type"] == "text":
                self.assertEqual(obj["font"], "Inter")
                self.assertTrue(obj["fontSource"].endswith(("QuietInter-Medium.ttf",
                                                          "QuietInter-Semibold.ttf")))

    def test_remote_strings_are_plain_text_and_control_free(self):
        data = fixture()
        data["leagues"][0]["me"]["name"] = '<b>A&B</b>\n\x00\u202e'
        labels = texts(build_state(data, now=1005))
        self.assertIn('<b>A&B</b>', labels)
        self.assertTrue(all("\n" not in label and "\x00" not in label and
                            "\u202e" not in label for label in labels))
        json.dumps(build_state(data, now=1005), allow_nan=False)

    def test_nonfinite_scores_and_probabilities_never_render_as_values(self):
        data = fixture()
        data["leagues"][0]["me"]["score"] = float("nan")
        data["leagues"][0]["opp"]["score"] = float("inf")
        data["leagues"][0]["winProb"] = float("nan")
        state = build_state(data, mode="expanded", now=1005)
        labels = texts(state)
        self.assertIn("—", labels)
        self.assertFalse(any("nan" in s.lower() or "inf" in s.lower() for s in labels))
        self.assertFalse(any("WIN CHANCE" in s for s in labels))
        json.dumps(state, allow_nan=False)

    def test_missing_teams_and_leagues_do_not_show_zero(self):
        labels = texts(build_state({"leagues": [{}]}, now=1005))
        self.assertIn("TEAM UNAVAILABLE", labels)
        self.assertIn("LEAGUE UNAVAILABLE", labels)
        self.assertNotIn("0.00", labels)

    def test_stale_status_uses_source_timestamp(self):
        data = fixture()
        self.assertTrue(any("STALE" in s for s in texts(build_state(data, now=1300))))
        del data["updated"]
        self.assertIn("NO UPDATE TIME", texts(build_state(data, now=1300)))

    def test_geometry_is_inside_canvas_and_scene_budget(self):
        data = fixture()
        players = [{"slot": "FLEX", "name": "A very long player name " * 4,
                    "pts": 999.9, "proj": 999.9} for _ in range(20)]
        for league in data["leagues"]:
            league["me"]["players"] = copy.deepcopy(players)
            league["opp"]["players"] = copy.deepcopy(players)
        for mode in ("compact", "expanded"):
            objects = build_state(data, mode=mode, now=1005)["scene"]["objects"]
            self.assertLessEqual(len(objects), 256)
            for obj in objects:
                self.assertGreaterEqual(obj["x"], 0)
                self.assertGreaterEqual(obj["y"], 0)
                self.assertLessEqual(obj["x"] + obj["width"], 1920)
                self.assertLessEqual(obj["y"] + obj["height"], 1080)
                if obj["type"] == "polygon":
                    self.assertGreaterEqual(len(obj["points"]), 3)
                    self.assertLessEqual(len(obj["points"]), 128)
                    for point in obj["points"]:
                        self.assertTrue(0 <= point["x"] <= 1920)
                        self.assertTrue(0 <= point["y"] <= 1080)

    def test_expanded_uses_only_existing_probability_and_omits_bench(self):
        data = fixture()
        data["leagues"][0]["me"]["players"].append(
            {"name": "Bench Player", "slot": "BE", "pts": 10, "bench": True})
        labels = texts(build_state(data, mode="expanded", now=1005))
        self.assertIn("EST. WIN CHANCE  80.0%", labels)
        self.assertNotIn("Bench Player", labels)

    def test_hidden_state_and_invalid_mode(self):
        self.assertFalse(build_state(fixture(), visible=False, now=1005)["visible"])
        with self.assertRaises(ValueError):
            build_state(fixture(), mode="unknown")


if __name__ == "__main__":
    unittest.main()
