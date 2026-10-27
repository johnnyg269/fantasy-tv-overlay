import copy
import json
import unittest

from sidebar_scene import LIVE_WASH, PROB_GREEN, PROB_RED, ROW_START, ROW_PITCH, build_sidebar, starter_players
from score_scene import TOTAL_FONT_SOURCE


def fixture():
    starters = [
        {"slot": slot, "name": "Player " + str(index), "pts": 10 + index,
         "proj": 20 + index, "bench": False}
        for index, slot in enumerate(("QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "D/ST", "K"))
    ]
    reserves = [
        {"slot": "BE", "name": "Bench by slot", "pts": 999, "bench": False},
        {"slot": "BN", "name": "BN by slot", "pts": 999, "bench": False},
        {"slot": "IR", "name": "IR by slot", "pts": 999, "bench": False},
        {"slot": "RES", "name": "Reserve by slot", "pts": 999, "bench": False},
        {"slot": "QB", "name": "Bench by flag", "pts": 999, "bench": True},
    ]
    return {"leagues": [
        {"leagueId": "A", "short": "LEAGUE A", "leagueName": "First League", "week": 7,
         "me": {"name": "My Team A", "ownerName": "Alex Morgan", "score": 100, "proj": 140,
                "players": copy.deepcopy(reserves + starters)},
         "opp": {"name": "Opponent A", "ownerName": "Casey Taylor", "score": 90, "proj": 120,
                 "players": copy.deepcopy(reserves + starters)}, "winProb": .65},
        {"leagueId": "B", "short": "LEAGUE B", "leagueName": "Second League", "week": 7,
         "me": {"name": "My Team B", "ownerName": "Alex Morgan", "score": 110, "players": copy.deepcopy(starters)},
         "opp": {"name": "Opponent B", "displayLabel": "Jordan Riley", "score": 105, "players": copy.deepcopy(starters)}}
    ]}


def labels(scene):
    return [obj["text"] for obj in scene["objects"] if obj["type"] == "text"]


class SidebarTests(unittest.TestCase):
    def test_glass_background_is_translucent_and_full_height(self):
        scene = build_sidebar(fixture())
        self.assertEqual(scene["objects"][0], {
            "type": "rectangle", "x": 0, "y": 0, "width": 720,
            "height": 1080, "color": "#101820B0"})
        alpha = int(scene["objects"][0]["color"][-2:], 16)
        self.assertTrue(165 <= alpha <= 190)
        for obj in scene["objects"]:
            if obj["type"] == "rectangle" and obj["width"] > 600 and obj["height"] > 1:
                self.assertLess(int(obj["color"][-2:], 16), 255)

    def test_backing_and_header_footer_feather_into_tv_without_hard_edge(self):
        scene = build_sidebar(fixture())
        gradients = [obj for obj in scene["objects"] if obj["type"] == "gradient"]
        self.assertEqual(len(gradients), 3)
        for gradient in gradients:
            self.assertEqual(gradient["x"], 720)
            self.assertEqual(gradient["width"], 180)
            self.assertEqual(gradient["direction"], "horizontal")
            self.assertTrue(gradient["end_color"].endswith("00"))
        self.assertEqual(gradients[0]["height"], 1080)
        self.assertFalse(any(obj["type"] == "rectangle" and obj["x"] == 719
                             and obj["height"] == 1080 for obj in scene["objects"]))

    def test_read_only_table_has_no_default_or_invalid_row_focus(self):
        for focus in (None, False, "3", "invalid", -1, 9, 10 ** 1000, 3.5,
                      float("nan"), float("inf")):
            scene = build_sidebar(fixture(), focus_row=focus)
            self.assertFalse(any(obj.get("color") == "#B1DCCC7A"
                                 for obj in scene["objects"]))
        self.assertIn("Starting lineup", labels(build_sidebar(fixture())))

    def test_explicit_valid_numeric_focus_still_highlights_requested_row(self):
        for focus in (0, 3, 8, 3.0):
            scene = build_sidebar(fixture(), focus_row=focus)
            indicators = [obj for obj in scene["objects"] if obj.get("color") == "#B1DCCC7A"]
            self.assertEqual(len(indicators), 1)
            self.assertEqual(indicators[0]["y"], ROW_START + int(focus) * ROW_PITCH + 6)

    def test_bench_flags_and_reserve_slots_are_filtered_before_limit(self):
        data = fixture()
        for side in ("me", "opp"):
            starters = starter_players(data["leagues"][0][side])
            self.assertEqual(len(starters), 9)
            self.assertEqual(starters[-1]["slot"], "K")
        text = " ".join(labels(build_sidebar(data)))
        for forbidden in ("Bench by slot", "BN by slot", "IR by slot", "Reserve by slot", "Bench by flag", "999"):
            self.assertNotIn(forbidden, text)

    def test_extended_reserve_aliases_and_unknown_slots_cannot_sneak_in(self):
        players = [{"slot": slot, "name": slot, "bench": False}
                   for slot in ("BENCH", "IR+", "IL", "IL+", "RESERVE", "TAXI", "NA", "unknown", "")]
        self.assertEqual(starter_players({"players": players}), [])
        self.assertEqual(starter_players({"players": [{"slot": "RB", "bench": "true"}]}), [])
        self.assertEqual(starter_players({"players": [{"slot": "RB", "isReserve": True}]}), [])

    def test_starter_position_variants_and_idp_are_allowed(self):
        players = [{"slot": slot, "name": slot, "bench": False}
                   for slot in ("SUPERFLEX", "RB/WR/TE", "OP", "DST", "DL", "LB", "DB", "EDGE", "PK")]
        self.assertEqual(len(starter_players({"players": players})), 9)

    def test_live_badge_and_wash_apply_only_to_that_players_side(self):
        data = fixture()
        player = data["leagues"][0]["me"]["players"][5]
        player.update(nflHighlightLive=True, nflGameState="live",
                      nflAvailability="available", nflGameLabel="Q4 5:42 vs ABC")
        scene = build_sidebar(data)
        self.assertEqual(labels(scene).count("LIVE"), 1)
        washes = [obj for obj in scene["objects"] if obj.get("color") == LIVE_WASH]
        self.assertEqual(len(washes), 1)
        self.assertEqual((washes[0]["x"], washes[0]["width"]), (22, 338))
        self.assertIn("Player 0", labels(scene))

    def test_opponent_live_cell_does_not_color_our_paired_cell(self):
        data = fixture()
        player = data["leagues"][0]["opp"]["players"][7]
        player.update(nflHighlightLive=True, nflGameState="live", nflAvailability="unknown")
        scene = build_sidebar(data)
        washes = [obj for obj in scene["objects"] if obj.get("color") == LIVE_WASH]
        self.assertEqual(len(washes), 1)
        self.assertEqual(washes[0]["x"], 378)
        self.assertEqual(washes[0]["y"], ROW_START + 2 * ROW_PITCH - 3)

    def test_known_out_or_unavailable_player_never_gets_live_highlight(self):
        for availability in ("out", "injured-reserve", "inactive", "suspended",
                             "practice-squad", "Injured Reserve"):
            data = fixture()
            data["leagues"][0]["me"]["players"][5].update(
                nflHighlightLive=True, nflGameState="live", nflAvailability=availability)
            scene = build_sidebar(data)
            self.assertNotIn("LIVE", labels(scene))
            self.assertFalse(any(obj.get("color") == LIVE_WASH for obj in scene["objects"]))

    def test_game_phase_without_positive_boolean_enrichment_cannot_fake_live(self):
        for fields in ({"nflGameState": "live"},
                       {"nflGameState": "live", "nflHighlightLive": "true"},
                       {"nflGameState": "final", "nflHighlightLive": True},
                       {"nflGameState": "scheduled", "nflHighlightLive": True},
                       {"nflGameState": "unknown", "nflHighlightLive": True}):
            data = fixture()
            data["leagues"][0]["me"]["players"][5].update(fields)
            self.assertNotIn("LIVE", labels(build_sidebar(data)))

    def test_unknown_enrichment_preserves_default_styling_exactly(self):
        data = fixture()
        baseline = build_sidebar(data)
        for side in ("me", "opp"):
            for player in data["leagues"][0][side]["players"]:
                player.update(nflHighlightLive=False, nflGameState="unknown",
                              nflAvailability="unknown")
        self.assertEqual(build_sidebar(data), baseline)

    def test_fresh_exact_context_marks_only_matching_live_game_on_tv(self):
        data = fixture()
        for side, game in (("me", "G1"), ("opp", "G2")):
            data["leagues"][0][side]["players"][5].update(
                nflHighlightLive=True, nflGameState="live", nflAvailability="available",
                gameId=game)
        data["tvContext"] = {"available": True, "title": "ABC at DEF",
                             "matchedGameId": "G1", "confidence": "exact-title-pair"}
        scene = build_sidebar(data)
        self.assertEqual(labels(scene).count("ON TV"), 1)
        self.assertEqual(labels(scene).count("LIVE"), 1)
        self.assertIn("WATCHING · ABC at DEF", labels(scene))
        on_tv = next(obj for obj in scene["objects"] if obj.get("text") == "ON TV")
        self.assertEqual(on_tv["width"], 43)
        self.assertEqual(on_tv["size"], 10)
        self.assertIn("Player 0", labels(scene))

    def test_generic_fresh_title_is_shown_without_guessing_a_game(self):
        data = fixture()
        data["leagues"][0]["me"]["players"][5].update(
            nflHighlightLive=True, nflGameState="live", gameId="G1")
        data["tvContext"] = {"available": True, "title": "Football Night in America",
                             "matchedGameId": None, "confidence": "unknown"}
        text = labels(build_sidebar(data))
        self.assertIn("WATCHING · Football Night in America", text)
        self.assertIn("LIVE", text)
        self.assertNotIn("ON TV", text)

    def test_stale_missing_or_unconfirmed_context_cannot_mark_on_tv(self):
        for available, confidence, matched in ((False, "exact-title-pair", "G1"),
                                               (None, "manual", "G1"),
                                               (True, "unknown", "G1"),
                                               (True, "exact-title-pair", "")):
            data = fixture()
            data["leagues"][0]["me"]["players"][5].update(
                nflHighlightLive=True, nflGameState="live", gameId="G1")
            data["tvContext"] = {"available": available, "title": "ABC at DEF",
                                 "matchedGameId": matched, "confidence": confidence}
            text = labels(build_sidebar(data))
            self.assertNotIn("ON TV", text)
            if available is not True:
                self.assertFalse(any(value.startswith("WATCHING") for value in text))

    def test_manual_context_still_requires_eligible_live_player(self):
        data = fixture()
        player = data["leagues"][0]["me"]["players"][5]
        player.update(nflHighlightLive=True, nflGameState="live", gameId="G1",
                      nflAvailability="available")
        data["tvContext"] = {"available": True, "title": "Manually selected game",
                             "matchedGameId": "G1", "confidence": "manual"}
        self.assertIn("ON TV", labels(build_sidebar(data)))
        player["nflAvailability"] = "out"
        text = labels(build_sidebar(data))
        self.assertNotIn("ON TV", text)
        self.assertNotIn("LIVE", text)

    def test_context_title_is_sanitized_and_bounded(self):
        data = fixture()
        data["tvContext"] = {"available": True, "title": "W" * 300 + "\n\x00",
                             "matchedGameId": None, "confidence": "unknown"}
        scene = build_sidebar(data)
        caption = next(obj for obj in scene["objects"] if obj.get("text", "").startswith("WATCHING"))
        self.assertTrue(caption["text"].endswith("…"))
        self.assertNotIn("\n", caption["text"])
        self.assertNotIn("\x00", caption["text"])
        self.assertLessEqual(caption["x"] + caption["width"], 720)

    def test_all_live_starters_fit_budget_and_live_bench_remains_excluded(self):
        data = fixture()
        for side in ("me", "opp"):
            for player in data["leagues"][0][side]["players"]:
                player.update(nflHighlightLive=True, nflGameState="live",
                              nflAvailability="available")
        scene = build_sidebar(data)
        self.assertEqual(labels(scene).count("LIVE"), 18)
        self.assertNotIn("Bench by flag", labels(scene))
        self.assertLessEqual(len(scene["objects"]), 256)
        for obj in scene["objects"]:
            self.assertLessEqual(obj["x"] + obj["width"], 900)
            self.assertLessEqual(obj["y"] + obj["height"], 1080)

    def test_selected_league_and_both_tabs_are_clear(self):
        text = labels(build_sidebar(fixture(), league_id="B"))
        self.assertIn("LEAGUE A", text)
        self.assertIn("LEAGUE B", text)
        self.assertIn("WEEK 7  ·  MATCHUP", text)
        self.assertNotIn("Second League", text)
        self.assertIn("Alex Morgan", text)
        self.assertIn("Jordan Riley", text)
        self.assertNotIn("My Team A", text)
        self.assertNotIn("My Team B", text)
        self.assertNotIn("Opponent B", text)
        self.assertIn("BACK  Close", text)
        self.assertIn("LEFT / RIGHT  Switch league", text)

    def test_unknown_explicit_league_is_not_replaced_by_a_different_matchup(self):
        text = labels(build_sidebar(fixture(), league_id="missing"))
        self.assertIn("LEAGUE UNAVAILABLE", text)
        self.assertNotIn("My Team A", text)
        self.assertNotIn("My Team B", text)

    def test_long_names_are_fitted_and_every_text_is_bounded(self):
        data = fixture()
        data["leagues"][0]["me"]["ownerName"] = "W" * 80
        data["leagues"][0]["me"]["players"] = [{"slot": "QB", "name": "W" * 80, "pts": 10}]
        scene = build_sidebar(data)
        self.assertTrue(any(text.endswith("…") for text in labels(scene)))
        self.assertLessEqual(len(scene["objects"]), 256)
        for obj in scene["objects"]:
            self.assertTrue(0 <= obj["x"] <= 900)
            self.assertTrue(0 <= obj["y"] <= 1080)
            self.assertLessEqual(obj["x"] + obj["width"], 900)
            self.assertLessEqual(obj["y"] + obj["height"], 1080)
            if obj["type"] == "text":
                self.assertLessEqual(obj["x"] + obj["width"], 720)
                self.assertIn("fontSource", obj)
                self.assertTrue(obj["fontSource"].endswith(".ttf"))

    def test_missing_owner_has_no_fantasy_fallback_and_player_names_stay_players(self):
        data = fixture()
        for side in ("me", "opp"):
            data["leagues"][0][side].pop("ownerName", None)
            data["leagues"][0][side]["players"][5]["ownerName"] = "Wrong player owner"
        text = labels(build_sidebar(data, league_id="A"))
        self.assertIn("Owner unavailable", text)
        self.assertNotIn("My Team A", text)
        self.assertNotIn("Opponent A", text)
        self.assertIn("Player 0", text)
        self.assertNotIn("Wrong player owner", text)

    def test_no_win_probability_is_invented(self):
        data = fixture()
        text = labels(build_sidebar(data, league_id="B"))
        self.assertIn("Estimated win chance", text)
        self.assertIn("Unavailable", text)
        self.assertFalse(any("%" in value for value in text))
        text = labels(build_sidebar(data, league_id="A"))
        self.assertIn("65.0%", text)
        self.assertIn("35.0%", text)
        self.assertEqual(text.count("Estimated win chance"), 1)

    def test_win_chance_bar_uses_provider_ratio_without_minimum_share(self):
        for probability, green_width, red_width, mine, opponent in (
            (0, 0, 664, "0.0%", "100.0%"),
            (1, 664, 0, "100.0%", "0.0%"),
            (.5, 332, 332, "50.0%", "50.0%"),
            (.998, 663, 1, "99.8%", "0.2%"),
            (.000001, 0, 664, "<0.1%", ">99.9%"),
        ):
            data = fixture()
            data["leagues"][0]["winProb"] = probability
            scene = build_sidebar(data)
            self.assertIn(mine, labels(scene))
            self.assertIn(opponent, labels(scene))
            segments = {obj["color"]: obj for obj in scene["objects"]
                        if obj["type"] == "polygon" and obj["color"] in (PROB_GREEN, PROB_RED)}
            self.assertEqual(segments.get(PROB_GREEN, {}).get("width", 0), green_width)
            self.assertEqual(segments.get(PROB_RED, {}).get("width", 0), red_width)

    def test_invalid_probability_keeps_neutral_unavailable_bar(self):
        for probability in (None, float("nan"), float("inf"), -.1, 1.1, True):
            data = fixture()
            data["leagues"][0]["winProb"] = probability
            scene = build_sidebar(data)
            self.assertIn("Unavailable", labels(scene))
            self.assertFalse(any("%" in value for value in labels(scene)))
            self.assertFalse(any(obj["type"] == "polygon" and obj["color"] in
                                 (PROB_GREEN, PROB_RED) for obj in scene["objects"]))
            json.dumps(scene, allow_nan=False)

    def test_probability_and_projection_section_preserves_all_nine_spacious_rows(self):
        scene = build_sidebar(fixture())
        objects = scene["objects"]
        percentages = [obj for obj in objects if obj.get("text") in ("65.0%", "35.0%")]
        self.assertEqual({obj["x"] for obj in percentages}, {28, 384})
        self.assertEqual({obj["y"] for obj in percentages}, {257})
        for name in ("Player " + str(index) for index in range(9)):
            players = [obj for obj in objects if obj.get("text") == name]
            self.assertEqual(len(players), 2)
            self.assertTrue(all(obj["size"] == 20 for obj in players))
        player_names = [obj for obj in objects if obj.get("text", "").startswith("Player ")]
        self.assertEqual(min(obj["y"] for obj in player_names), 361)
        self.assertEqual(max(obj["y"] for obj in player_names), 873)
        self.assertIn("140.00", labels(scene))
        self.assertIn("120.00", labels(scene))

    def test_sports_font_is_reserved_for_two_matchup_totals(self):
        scene = build_sidebar(fixture())
        text = [obj for obj in scene["objects"] if obj["type"] == "text"]
        totals = [obj for obj in text if obj["fontSource"] == TOTAL_FONT_SOURCE]
        self.assertEqual({obj["text"] for obj in totals}, {"100.00", "90.00"})
        self.assertEqual(len(totals), 2)
        self.assertTrue(all(obj["size"] == 60 for obj in totals))
        self.assertTrue(all(obj["width"] == 306 for obj in totals))
        self.assertTrue(all(obj["font"] == "Inter" for obj in text if obj not in totals))

    def test_owner_percentage_labels_remain_readable_over_bright_video(self):
        scene = build_sidebar(fixture())

        def rgb(color):
            return [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]

        def luminance(channels):
            linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                      for value in channels]
            return sum(weight * value for weight, value in zip((.2126, .7152, .0722), linear))

        base = scene["objects"][0]["color"]
        alpha = int(base[-2:], 16) / 255
        # Conservatively ignore the extra header wash; white is the brightest
        # possible underlying video through the unchanged 69% core.
        background = [value * alpha + 1 - alpha for value in rgb(base)]
        percentages = [obj for obj in scene["objects"] if obj.get("text", "").endswith("%")]
        self.assertEqual(len(percentages), 2)
        for label in percentages:
            ratio = (luminance(rgb(label["color"])) + .05) / (luminance(background) + .05)
            self.assertGreaterEqual(ratio, 4.5)

    def test_nonfinite_scores_are_safe_json_and_no_zero_is_fabricated(self):
        data = fixture()
        data["leagues"][0]["me"]["score"] = float("nan")
        data["leagues"][0]["me"]["players"][5]["pts"] = None
        scene = build_sidebar(data)
        self.assertIn("—", labels(scene))
        json.dumps(scene, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
