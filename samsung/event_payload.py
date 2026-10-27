"""Pure score-event metadata and scenes for the native popup/sidebar renderer.

No network, TV, controller mutation, or remote-key ownership occurs here.
The host owns popup events. The renderer owns the user's sidebar-open state;
a normal host ``visible:false`` heartbeat must not close an open sidebar.
Explicit exit and an expired/missing heartbeat always close both views.
"""

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import math


def _number(value):
    if isinstance(value, bool):
        raise ValueError("actual scores and deltas must be numeric, not boolean")
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError("actual scores and deltas must be finite")
        return number.quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError) as error:
        raise ValueError("invalid actual score or delta") from error


def _json_number(value):
    number = float(_number(value))
    if not math.isfinite(number):
        raise ValueError("actual score or delta is outside the JSON number range")
    return number


def _leagues(scores):
    if not isinstance(scores, dict) or not isinstance(scores.get("leagues"), list):
        return []
    result = []
    seen = set()
    for league in scores["leagues"]:
        if not isinstance(league, dict):
            continue
        league_id = str(league.get("leagueId", "")).strip()
        if not league_id or league_id in seen:
            continue
        seen.add(league_id)
        result.append((league_id, league))
    return result


def compare_actual_scores(previous, current):
    """Compare the controller's existing validated score snapshots.

    Each snapshot is ``{leagueId: ((week, meId, oppId), (meActual, oppActual))}``.
    Call this *before* assigning ``controller.baseline = current``. Freshness
    and per-league feed validity remain the existing controller's responsibility.
    First samples and a changed league/week/opponent establish a new baseline;
    they never invent a score event. Negative scoring corrections are retained.
    Projections and player-row changes are deliberately absent from this input.
    """
    event = {"kind": "none", "changedLeagueIds": [], "scoreDeltas": {},
             "resetBaseline": False}
    if not isinstance(current, dict) or not current:
        return event
    if not isinstance(previous, dict) or not previous:
        event["resetBaseline"] = True
        return event
    try:
        if (set(previous) != set(current)
                or any(tuple(previous[key][0]) != tuple(current[key][0])
                       for key in current)):
            event["resetBaseline"] = True
            return event
        for key, current_value in current.items():
            before, after = previous[key][1], current_value[1]
            if len(before) != 2 or len(after) != 2:
                raise ValueError("score snapshot needs two team actuals")
            deltas = tuple(_number(after[index]) - _number(before[index])
                           for index in (0, 1))
            if any(delta != 0 for delta in deltas):
                league_id = str(key)
                event["changedLeagueIds"].append(league_id)
                event["scoreDeltas"][league_id] = {
                    "me": _json_number(deltas[0]),
                    "opp": _json_number(deltas[1]),
                }
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid validated score snapshot") from error
    if event["changedLeagueIds"]:
        event["kind"] = "score-change"
        event["selectedLeagueId"] = event["changedLeagueIds"][0]
    return event


def preview_event(scores, league_id=None):
    """Choose a real matchup for a preview, with no fabricated change/delta."""
    league_ids = [item[0] for item in _leagues(scores)]
    selected = str(league_id) if league_id is not None else None
    if selected not in league_ids:
        selected = league_ids[0] if league_ids else None
    return {"kind": "preview", "selectedLeagueId": selected,
            "changedLeagueIds": [], "scoreDeltas": {}, "resetBaseline": False}


def build_event_state(scores, event=None, visible=False, alert_id=None,
                      duration_seconds=5, now=None, stale_after=120,
                      mode="compact", compact_builder=None,
                      sidebar_builder=None, focus_row=None):
    """Build one selected-matchup popup plus all ready-to-open sidebar scenes.

    ``scene`` is the selected league's compact popup (or its opaque sidebar for
    explicit legacy ``mode='expanded'``). ``sidebarScenes`` contains one scene
    per league so the renderer can open or change the selected league locally
    without waiting for the next host poll. Scene builders receive copies of
    the source data; this function never mutates ESPN's raw payload.

    Renderer rule: local sidebar-open is independent of host popup visibility.
    Keep it open through same-alert heartbeats and popup expiry. A new alert
    updates its content without stealing the user's selected view. Back or the
    toggle closes it. Heartbeat expiry or ``exit:true`` overrides local opening.
    """
    if mode not in ("compact", "expanded"):
        raise ValueError("mode must be compact or expanded")
    if (isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int)
            or not 1 <= duration_seconds <= 30):
        raise ValueError("duration_seconds must be an integer from 1 through 30")
    if alert_id is not None and (not isinstance(alert_id, str)
                                 or not alert_id or len(alert_id) > 256):
        raise ValueError("alert_id must be a nonempty string up to 256 characters")
    if sidebar_builder is None:
        from sidebar_scene import build_sidebar
        sidebar_builder = build_sidebar
    leagues = _leagues(scores)
    league_ids = [item[0] for item in leagues]
    raw_event = event if isinstance(event, dict) else {}
    changed = [str(item) for item in raw_event.get("changedLeagueIds", [])
               if str(item) in league_ids]
    changed = list(dict.fromkeys(changed))
    kind = raw_event.get("kind", "score-change" if changed else "none")
    if kind not in ("none", "preview", "score-change"):
        raise ValueError("event kind must be none, preview or score-change")
    if kind != "score-change":
        changed = []
    selected = raw_event.get("selectedLeagueId")
    selected = str(selected) if selected is not None else None
    if selected not in league_ids:
        selected = changed[0] if changed else (league_ids[0] if league_ids else None)
    selected_league = next((league for key, league in leagues if key == selected), None)
    subset = deepcopy(scores) if isinstance(scores, dict) else {}
    subset["leagues"] = [deepcopy(selected_league)] if selected_league is not None else []
    deltas = {}
    source_deltas = raw_event.get("scoreDeltas", {})
    if not isinstance(source_deltas, dict):
        raise ValueError("scoreDeltas must be a mapping by league ID")
    for league_id in changed:
        delta = source_deltas.get(league_id)
        if isinstance(delta, dict) and "me" in delta and "opp" in delta:
            deltas[league_id] = {"me": _json_number(delta["me"]),
                                 "opp": _json_number(delta["opp"])}
    normalized_event = {"kind": kind, "selectedLeagueId": selected,
                        "changedLeagueIds": changed, "scoreDeltas": deltas}
    if compact_builder is None:
        from notification_scene import build_notification

        def compact_builder(payload, mode="compact", visible=False, now=None,
                            stale_after=120):
            scene = build_notification(payload, league_id=selected,
                                       event=deepcopy(normalized_event), focus=True,
                                       now=now, stale_after=stale_after)
            return {"visible": bool(visible), "mode": mode, "scene": scene}
    state = compact_builder(subset, mode="compact", visible=visible, now=now,
                            stale_after=stale_after)
    state = deepcopy(state)
    sidebar_scenes = []
    for league_id, _league in leagues:
        scene = sidebar_builder(deepcopy(scores), league_id=league_id,
                                focus_row=focus_row)
        if not isinstance(scene, dict) or not isinstance(scene.get("objects"), list):
            raise ValueError("sidebar builder must return a scene.objects array")
        sidebar_scenes.append({"leagueId": league_id, "scene": deepcopy(scene)})
    state["mode"] = mode
    state["selectedLeagueId"] = selected
    state["event"] = normalized_event
    state["sidebarScenes"] = sidebar_scenes
    state["sidebarPolicy"] = {"holdWhileOpen": True,
                              "closeOnHeartbeatExpiry": True,
                              "closeOnExit": True,
                              "newAlertKeepsOpen": True}
    if mode == "expanded" and selected is not None:
        state["scene"] = deepcopy(next(item["scene"] for item in sidebar_scenes
                                        if item["leagueId"] == selected))
    if alert_id is not None:
        state["alertId"] = alert_id
        state["durationSeconds"] = duration_seconds
    return state
