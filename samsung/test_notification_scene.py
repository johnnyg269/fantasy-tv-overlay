import copy
import json
import hashlib
import math
from functools import lru_cache
from pathlib import Path
import struct
import unittest
import zlib

from notification_scene import HEIGHT, WIDTH, CORNER_SHADE_WIDTH, CORNER_SHADE_HEIGHT, TRACK_WIDTH, CONTENT_RIGHT, MINT, OPPONENT_RED, BUTTON_X, BUTTON_Y, BUTTON_WIDTH, BUTTON_HEIGHT, BUTTON_ASSET_MARGIN, BUTTON_IMAGE_WIDTH, BUTTON_IMAGE_HEIGHT, build_notification
from score_scene import TOTAL_FONT, TOTAL_FONT_SOURCE


def fixture():
    return {"updated": 1000, "ok": True, "leagues": [
        {"leagueId": "A", "short": "LEAGUE ONE", "week": 7,
         "me": {"name": "Example Team One", "ownerName": "Alex Morgan", "score": 111.62, "proj": 150},
         "opp": {"name": "Example Team Two", "ownerName": "Casey Taylor", "score": 86.72, "proj": 120}},
        {"leagueId": "B", "short": "LEAGUE TWO", "week": 7,
         "me": {"name": "Example", "ownerName": "Alex Morgan", "score": 153.18},
         "opp": {"name": "Next Man Up", "displayLabel": "Jordan Riley", "score": 89.78}},
    ]}


def labels(scene):
    return [obj["text"] for obj in scene["objects"] if obj["type"] == "text"]


@lru_cache(maxsize=1)
def shade_pixels():
    """Decode the actual checked-in stdlib-generated RGBA PNG, without PIL."""
    path = Path(__file__).resolve().parent / "assets" / "ui" / "popup-corner-shade.png"
    png = path.read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    position, compressed = 8, bytearray()
    width = height = None
    while position < len(png):
        length = struct.unpack(">I", png[position:position + 4])[0]
        kind = png[position + 4:position + 8]
        payload = png[position + 8:position + 8 + length]
        checksum = struct.unpack(">I", png[position + 8 + length:position + 12 + length])[0]
        assert checksum == zlib.crc32(kind + payload) & 0xffffffff
        if kind == b"IHDR":
            width, height, depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            assert (depth, color_type, compression, filtering, interlace) == (8, 6, 0, 0, 0)
        elif kind == b"IDAT":
            compressed.extend(payload)
        position += length + 12
        if kind == b"IEND":
            break
    rows = zlib.decompress(bytes(compressed))
    stride = width * 4 + 1
    assert len(rows) == stride * height
    assert all(rows[y * stride] == 0 for y in range(height))
    return width, height, rows, stride


def shade_rgba(x, y):
    width, height, rows, stride = shade_pixels()
    assert 0 <= x < width and 0 <= y < height
    offset = y * stride + 1 + x * 4
    return tuple(rows[offset:offset + 4])


def white_video_contrast(color, alpha):
    def luminance(channels):
        linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                  for value in channels]
        return sum(weight * value for weight, value in zip((.2126, .7152, .0722), linear))
    foreground = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    opacity = alpha / 255
    background = [value / 255 * opacity + 1 - opacity for value in (8, 13, 18)]
    return (luminance(foreground) + .05) / (luminance(background) + .05)


class NotificationTests(unittest.TestCase):
    def test_explicit_selection_shows_exactly_one_matchup(self):
        text = labels(build_notification(fixture(), league_id="B", now=1005))
        for expected in ("LEAGUE TWO", "Alex Morgan", "Jordan Riley", "153.18", "89.78"):
            self.assertIn(expected, text)
        for other in ("LEAGUE ONE", "Example Team One", "Example Team Two", "111.62"):
            self.assertNotIn(other, text)

    def test_event_selects_affected_league_and_explicit_argument_has_priority(self):
        event = {"selectedLeagueId": "B", "changedLeagueIds": ["A", "B"]}
        self.assertIn("LEAGUE TWO", labels(build_notification(fixture(), event=event, now=1005)))
        self.assertIn("LEAGUE ONE", labels(build_notification(fixture(), league_id="A", event=event, now=1005)))
        self.assertIn("LEAGUE TWO", labels(build_notification(
            fixture(), event={"changedLeagueIds": ["B"]}, now=1005)))

    def test_footer_has_ok_button_and_focus_is_visible(self):
        focused = build_notification(fixture(), now=1005)
        unfocused = build_notification(fixture(), focus=False, now=1005)
        self.assertIn("OK", labels(focused))
        self.assertIn("View matchup", labels(focused))
        self.assertNotEqual(focused, unfocused)
        self.assertEqual(labels(focused), labels(unfocused))

    def test_real_owner_names_are_preserved_without_fantasy_team_labels(self):
        text = labels(build_notification(fixture(), now=1005))
        self.assertIn("Alex Morgan", text)
        self.assertIn("Casey Taylor", text)
        self.assertNotIn("Example Team One", text)
        self.assertNotIn("Example Team Two", text)
        self.assertIn("111.62", text)
        self.assertIn("86.72", text)

    def test_missing_owner_never_falls_back_to_fantasy_team_name(self):
        data = fixture()
        for league in data["leagues"]:
            for side in ("me", "opp"):
                league[side].pop("ownerName", None)
                league[side].pop("displayLabel", None)
        text = labels(build_notification(data, now=1005))
        self.assertIn("Owner unavailable", text)
        self.assertNotIn("Example Team One", text)
        self.assertNotIn("Example Team Two", text)

    def test_no_unrequested_delta_projection_or_missing_probability_is_invented(self):
        event = {"scoreDeltas": {"A": {"me": 3.2, "opp": -1}}}
        text = " ".join(labels(build_notification(fixture(), event=event, now=1005)))
        for absent in ("+3.20", "150.00", "Projected", "50.0%", "FANTASY"):
            self.assertNotIn(absent, text)
        self.assertIn("Estimated win chance", text)
        self.assertIn("Unavailable", text)

    def test_safe_native_geometry_and_scene_budget(self):
        scene = build_notification(fixture(), now=1005)
        self.assertEqual((scene["objects"][0]["x"], scene["objects"][0]["y"]), (0, 0))
        self.assertLessEqual(len(scene["objects"]), 256)
        for obj in scene["objects"]:
            self.assertGreaterEqual(obj["x"], 0)
            self.assertGreaterEqual(obj["y"], 0)
            self.assertLessEqual(obj["x"] + obj["width"], CORNER_SHADE_WIDTH)
            self.assertLessEqual(obj["y"] + obj["height"], CORNER_SHADE_HEIGHT)
            if obj["type"] == "polygon":
                self.assertTrue(3 <= len(obj["points"]) <= 128)
                for point in obj["points"]:
                    self.assertTrue(0 <= point["x"] <= WIDTH)
                    self.assertTrue(0 <= point["y"] <= HEIGHT)
            if obj["type"] == "text":
                self.assertTrue(obj["fontSource"].endswith(".ttf"))
                self.assertLessEqual(obj["x"] + obj["width"], WIDTH)
                self.assertLessEqual(obj["y"] + obj["height"], HEIGHT)

    def test_backing_is_one_continuous_corner_image_without_rectangular_plate(self):
        scene = build_notification(fixture(), now=1005)
        backing = scene["objects"][0]
        self.assertEqual(backing, dict(type="image", x=0, y=0, width=1000, height=650,
                                      path="/home/owner/share/tmp/sdk_tools/fantasy-overlay/popup-corner-shade.png",
                                      smooth=True))
        self.assertFalse(any(obj["type"] == "gradient" for obj in scene["objects"]))
        self.assertFalse(any(obj["type"] == "rectangle" and obj["width"] == WIDTH
                             and obj["height"] == HEIGHT for obj in scene["objects"]))

    def test_actual_corner_png_matches_recorded_profile_and_continuous_field(self):
        folder = Path(__file__).resolve().parent / "assets" / "ui"
        profile = json.loads((folder / "popup-corner-shade.json").read_text())
        self.assertEqual(hashlib.sha256((folder / profile["asset"]).read_bytes()).hexdigest(),
                         profile["sha256"])
        self.assertEqual((profile["width"], profile["height"], profile["maxAlpha"],
                          profile["radiusX"], profile["radiusY"], profile["color"]),
                         (1000, 650, 220, 800, 450, "#080D12"))
        self.assertEqual(shade_pixels()[:2], (CORNER_SHADE_WIDTH, CORNER_SHADE_HEIGHT))
        for y in range(0, CORNER_SHADE_HEIGHT, 25):
            for x in range(0, CORNER_SHADE_WIDTH, 25):
                radius_squared = ((x + .5) / 800) ** 2 + ((y + .5) / 450) ** 2
                alpha = round(220 * math.exp(-(radius_squared ** 4)))
                self.assertEqual(shade_rgba(x, y), (8, 13, 18, alpha))
        self.assertEqual(shade_rgba(0, 0)[3], 220)
        self.assertLessEqual(shade_rgba(999, 0)[3], 1)
        self.assertEqual(shade_rgba(0, 649)[3], 0)
        self.assertLessEqual(abs(shade_rgba(640, 0)[3] - shade_rgba(0, 360)[3]), 1)
        for samples in ([shade_rgba(x, 213)[3] for x in range(1000)],
                        [shade_rgba(516, y)[3] for y in range(650)]):
            self.assertTrue(all(a >= b for a, b in zip(samples, samples[1:])))
            self.assertLessEqual(max(a - b for a, b in zip(samples, samples[1:])), 3)
        for a, b in (((559, 200), (560, 200)), ((200, 335), (200, 336))):
            self.assertLessEqual(abs(shade_rgba(*a)[3] - shade_rgba(*b)[3]), 2)

    def test_provider_win_probability_controls_exact_pixel_partition(self):
        for probability, green_width, red_width, mine, theirs in (
            (0, 0, 492, "0.0%", "100.0%"),
            (1, 492, 0, "100.0%", "0.0%"),
            (.5, 246, 246, "50.0%", "50.0%"),
            (.998, 491, 1, "99.8%", "0.2%"),
        ):
            data = fixture()
            data["leagues"][0]["winProb"] = probability
            scene = build_notification(data, now=1005)
            text = labels(scene)
            self.assertIn("Estimated win chance", text)
            self.assertIn(mine, text)
            self.assertIn(theirs, text)
            segments = {obj["color"]: obj for obj in scene["objects"]
                        if obj["type"] == "polygon" and obj["color"] in (MINT, OPPONENT_RED)}
            self.assertEqual(segments.get(MINT, {}).get("width", 0), green_width)
            self.assertEqual(segments.get(OPPONENT_RED, {}).get("width", 0), red_width)

    def test_missing_invalid_or_nonfinite_probability_is_neutral_unavailable(self):
        for probability in (None, float("nan"), float("inf"), -0.1, 1.1, True, "bad"):
            data = fixture()
            data["leagues"][0]["winProb"] = probability
            scene = build_notification(data, now=1005)
            self.assertIn("Unavailable", labels(scene))
            self.assertFalse(any(obj["type"] == "polygon" and obj["color"] in
                                 (MINT, OPPONENT_RED) for obj in scene["objects"]))
            self.assertFalse(any("%" in text for text in labels(scene)))
            json.dumps(scene, allow_nan=False)

    def test_tiny_shares_are_not_given_an_artificial_minimum_or_rounded_certainty(self):
        data = fixture()
        data["leagues"][0]["winProb"] = .000001
        scene = build_notification(data, now=1005)
        self.assertIn("<0.1%", labels(scene))
        self.assertIn(">99.9%", labels(scene))
        self.assertFalse(any(obj["type"] == "polygon" and obj["color"] == MINT
                             for obj in scene["objects"]))

    def test_bottom_content_padding_balances_the_right_edge(self):
        scene = build_notification(fixture(), now=1005)
        image = next(obj for obj in scene["objects"] if obj["type"] == "image"
                     and Path(obj["path"]).name.startswith("button-matchup-"))
        self.assertEqual(image["x"] + BUTTON_ASSET_MARGIN, BUTTON_X)
        self.assertEqual(image["y"] + BUTTON_ASSET_MARGIN, BUTTON_Y)
        self.assertEqual(image["width"] - 2 * BUTTON_ASSET_MARGIN, BUTTON_WIDTH)
        self.assertEqual(image["height"] - 2 * BUTTON_ASSET_MARGIN, BUTTON_HEIGHT)
        bottom_padding = HEIGHT - (BUTTON_Y + BUTTON_HEIGHT)
        self.assertEqual(bottom_padding, WIDTH - CONTENT_RIGHT)
        self.assertGreaterEqual(bottom_padding, 40)

    def test_action_uses_selected_surface_art_and_native_inter_labels(self):
        scene = build_notification(fixture(), now=1005)
        images = [obj for obj in scene["objects"] if obj["type"] == "image"
                  and Path(obj["path"]).name.startswith("button-matchup-")]
        self.assertEqual(len(images), 1)
        self.assertTrue(images[0]["path"].endswith("button-matchup-focus.png"))
        self.assertTrue(images[0]["smooth"])
        self.assertFalse(any(obj["type"] in ("polygon", "ellipse") and
                             BUTTON_Y <= obj["y"] < BUTTON_Y + BUTTON_HEIGHT
                             for obj in scene["objects"]))
        label = next(obj for obj in scene["objects"] if obj.get("text") == "View matchup")
        self.assertEqual(label["size"], 18)
        self.assertEqual(label["font"], "Inter")
        self.assertIn("OK", labels(scene))
        idle = build_notification(fixture(), focus=False, now=1005)
        self.assertTrue(next(obj for obj in idle["objects"] if obj["type"] == "image"
                                  and Path(obj["path"]).name.startswith("button-matchup-"))
                        ["path"].endswith("button-matchup-idle.png"))

    def test_selected_surface_assets_are_real_four_times_rgba_pngs(self):
        folder = Path(__file__).resolve().parent / "assets" / "ui"
        files = []
        for state in ("focus", "idle"):
            data = (folder / ("button-matchup-" + state + ".png")).read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", data[16:24]),
                             (BUTTON_IMAGE_WIDTH * 4, BUTTON_IMAGE_HEIGHT * 4))
            self.assertEqual((data[24], data[25]), (8, 6))
            files.append(data)
        self.assertNotEqual(files[0], files[1])

    def test_sports_typeface_is_reserved_for_exactly_the_two_totals(self):
        scene = build_notification(fixture(), now=1005)
        sports = [obj for obj in scene['objects'] if obj.get('font') == TOTAL_FONT]
        self.assertEqual({obj['text'] for obj in sports}, {'111.62', '86.72'})
        self.assertTrue(all(obj['fontSource'] == TOTAL_FONT_SOURCE for obj in sports))
        self.assertTrue(all(obj['size'] == 68 for obj in sports))
        self.assertTrue(all(obj['width'] == 230 for obj in sports))
        self.assertTrue(all(obj['font'] == 'Inter' for obj in scene['objects']
                            if obj['type'] == 'text' and obj not in sports))

    def test_long_totals_keep_exact_digits_and_shared_fitted_typeface(self):
        data = fixture()
        data["leagues"][0]["me"]["score"] = 8888.88
        scene = build_notification(data, now=1005)
        score = next(obj for obj in scene["objects"] if obj.get("text") == "8888.88")
        self.assertEqual(score["fontSource"], TOTAL_FONT_SOURCE)
        self.assertLessEqual(score["size"], 68)
        self.assertEqual(score["width"], 230)
        totals = [obj for obj in scene["objects"] if obj.get("fontSource") == TOTAL_FONT_SOURCE]
        self.assertEqual({obj["size"] for obj in totals}, {score["size"]})

    def test_unchanged_text_keeps_contrast_over_white_video_using_actual_corner_png(self):
        data = fixture()
        data["leagues"][0]["winProb"] = .998
        for now in (1005, 1300):
            scene = build_notification(data, now=now)
            percentages = [obj for obj in scene["objects"] if obj.get("text", "").endswith("%")]
            self.assertEqual(len(percentages), 2)
            for label in percentages:
                self.assertGreaterEqual(label["size"], 19)
            for label in scene["objects"]:
                if label["type"] != "text" or label["y"] >= BUTTON_Y:
                    continue
                # Check even unused text-box space at its lowest opacity point.
                x = label["x"] + label["width"] - 1
                y = label["y"] + label["height"] - 1
                ratio = white_video_contrast(label["color"], shade_rgba(x, y)[3])
                self.assertGreaterEqual(ratio, 3 if label["size"] >= 24 else 4.5,
                                        (label["text"], x, y, ratio))
        self.assertGreaterEqual(white_video_contrast("#F2B7BAFF", shade_rgba(516, 213)[3]), 4.5)

    def test_stale_and_error_labels_remain_explicit(self):
        self.assertTrue(any("STALE" in value for value in labels(build_notification(fixture(), now=1300))))
        data = fixture()
        data["ok"] = False
        self.assertIn("FEED UNAVAILABLE", labels(build_notification(data, now=1005)))

    def test_long_names_fit_with_ellipsis_instead_of_hidden_clipping(self):
        data = fixture()
        data["leagues"][0]["me"]["ownerName"] = "W" * 100
        text = labels(build_notification(data, now=1005))
        fitted = [value for value in text if value.startswith("WWW")]
        self.assertEqual(len(fitted), 1)
        self.assertTrue(fitted[0].endswith("…"))

    def test_nonfinite_actual_is_not_fabricated_zero_or_invalid_json(self):
        data = fixture()
        data["leagues"][0]["me"]["score"] = float("nan")
        scene = build_notification(data, now=1005)
        self.assertIn("—", labels(scene))
        json.dumps(scene, allow_nan=False)

    def test_unknown_explicit_league_does_not_show_the_wrong_matchup(self):
        text = labels(build_notification(fixture(), league_id="missing", now=1005))
        self.assertIn("LEAGUE UNAVAILABLE", text)
        self.assertNotIn("Example Team One", text)
        self.assertNotIn("Next Man Up", text)


if __name__ == "__main__":
    unittest.main()
