"""Pure contract checks; no network, remote keys or TV access."""

from copy import deepcopy
from decimal import Decimal
import json
import unittest

from event_payload import build_event_state, compare_actual_scores, preview_event


class EventPayloadTests(unittest.TestCase):
    def test_signed_actual_deltas_and_identity_reset(self):
        before = {"A": (("7", "1", "2"), (Decimal("10.10"), Decimal("20.20")))}
        after = {"A": (("7", "1", "2"), (Decimal("9.90"), Decimal("20.50")))}
        event = compare_actual_scores(before, after)
        self.assertEqual(event["scoreDeltas"], {"A": {"me": -0.2, "opp": 0.3}})
        after["A"] = (("8", "1", "2"), after["A"][1])
        reset = compare_actual_scores(before, after)
        self.assertTrue(reset["resetBaseline"])
        self.assertEqual(reset["kind"], "none")
        self.assertEqual(reset["scoreDeltas"], {})

    def test_builders_cannot_mutate_raw_payload_and_popup_focuses_changed_league(self):
        scores = {"updated": 1000, "leagues": [
            {"leagueId": "A", "me": {"score": 10}},
            {"leagueId": "B", "me": {"score": 20}},
        ]}
        original = deepcopy(scores)
        selected = []

        def compact(payload, **kwargs):
            selected.append(payload["leagues"][0]["leagueId"])
            payload["leagues"].clear()
            return {"visible": kwargs["visible"], "mode": "compact", "scene": {"objects": []}}

        def sidebar(payload, league_id=None, focus_row=0):
            payload["leagues"].clear()
            return {"objects": [{"type": "text", "text": league_id}]}

        event = {"kind": "score-change", "changedLeagueIds": ["B"],
                 "scoreDeltas": {"B": {"me": 0.1, "opp": 0}}}
        state = build_event_state(scores, event, True, "alert-1",
                                  compact_builder=compact, sidebar_builder=sidebar)
        self.assertEqual(selected, ["B"])
        self.assertEqual(state["selectedLeagueId"], "B")
        self.assertEqual(len(state["sidebarScenes"]), 2)
        self.assertEqual(scores, original)
        json.dumps(state, allow_nan=False)

    def test_preview_defaults_first_league_and_has_no_fabricated_deltas(self):
        event = preview_event({"leagues": [{"leagueId": "A"}, {"leagueId": "B"}]})
        self.assertEqual(event["selectedLeagueId"], "A")
        self.assertEqual(event["kind"], "preview")
        self.assertEqual(event["changedLeagueIds"], [])
        self.assertEqual(event["scoreDeltas"], {})


if __name__ == "__main__":
    unittest.main()
