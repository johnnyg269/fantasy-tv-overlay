"""Synthetic data only. This module never reads an account or TV."""

import time


def scores(now=None, revision=0):
    now = time.time() if now is None else now
    slots = ("QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "D/ST", "K")

    def side(name, identifier, total):
        return {"teamId": str(identifier), "name": "Demo team", "ownerName": name,
                "displayLabel": name, "score": total, "proj": total + 22.4,
                "players": [{"slot": slot, "name": "Demo player " + str(index + 1),
                             "pts": round(3.2 + index, 2), "proj": round(7.5 + index, 2),
                             "bench": False, "nflHighlightLive": index in (0, 3),
                             "nflGameState": "live" if index in (0, 3) else "final",
                             "nflAvailability": "available", "gameId": "demo-game"}
                            for index, slot in enumerate(slots)]}
    return {"ok": True, "updated": now, "demo": True, "schemaVersion": 1,
            "leagues": [{"ok": True, "leagueId": "demo-" + str(index + 1),
                         "short": label, "leagueName": label, "week": 7, "seasonId": 2026,
                         "winProb": .64, "winProbSource": "synthetic-demo",
                         "me": side("Alex", 1, round(112.38 + index + revision * .1, 2)),
                         "opp": side("Taylor", 2, 104.76 + index)}
                        for index, label in enumerate(("Sunday League", "Friends League"))]}
