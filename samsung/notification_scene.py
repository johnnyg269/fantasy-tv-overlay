"""Quiet Sports native score notification, focused on one affected matchup."""

import math
import time

from score_scene import (
    _INTER_ASCII_EM, _fitted_team_name, _freshness,
    _label, _mapping, _number, _polygon, _rect, _round_rect, _score, _text,
    _total_score_label, _total_score_size,
)


WIDTH = 560
HEIGHT = 336
CORNER_SHADE_WIDTH = 1000
CORNER_SHADE_HEIGHT = 650
CONTENT_RIGHT = WIDTH - 44
TRACK_WIDTH = CONTENT_RIGHT - 24
WHITE = "#F2F5F6FF"
MUTED = "#C4CDD0FF"
CAPTION = "#B9C3C8FF"
FAINT = "#AEBCC2FF"
MINT = "#8BDDB5FF"
OPPONENT_RED = "#C9787BFF"
OPPONENT_RED_TEXT = "#F2B7BAFF"
NEUTRAL_TRACK = "#76808A40"
BUTTON_X = 24
BUTTON_Y = 244
BUTTON_WIDTH = 244
BUTTON_HEIGHT = 48
BUTTON_ASSET_MARGIN = 8
BUTTON_IMAGE_X = 16
BUTTON_IMAGE_Y = 236
BUTTON_IMAGE_WIDTH = 260
BUTTON_IMAGE_HEIGHT = 64
STAGE_DIRECTORY = "/home/owner/share/tmp/sdk_tools/fantasy-overlay/"


def _corner_backing(objects):
    """One continuous corner bloom; the accepted content geometry stays fixed."""
    objects.append(dict(type="image", x=0, y=0,
                        width=CORNER_SHADE_WIDTH, height=CORNER_SHADE_HEIGHT,
                        path=STAGE_DIRECTORY + "popup-corner-shade.png", smooth=True))


def _league_selection(scores, league_id, event):
    leagues = _mapping(scores).get("leagues")
    leagues = [item for item in leagues if isinstance(item, dict)] if isinstance(leagues, list) else []
    event = _mapping(event)
    if league_id is None:
        league_id = event.get("selectedLeagueId")
    if league_id is None:
        changed = event.get("changedLeagueIds")
        if isinstance(changed, list) and changed:
            league_id = changed[0]
    if league_id is None:
        return leagues[0] if leagues else {}
    return next((item for item in leagues if str(item.get("leagueId")) == str(league_id)), {})


def _owner_name(team):
    for key in ("ownerName", "displayLabel"):
        value = team.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return "Owner unavailable"


def _right_label(objects, right, y, text, size, color, width=120):
    em = 0
    for character in text:
        index = ord(character) - 32
        em += _INTER_ASCII_EM[index] if 0 <= index < len(_INTER_ASCII_EM) else .85
    text_width = min(width, math.ceil(em * size * 1.04) + 3)
    _label(objects, right - text_width, y, text, size, color,
           width=text_width, semibold=True)


def _percent_text(probability):
    # Avoid presenting rounded 0/100 as certainty for a strictly interior value.
    if 0 < probability <= .0005:
        return "<0.1%"
    if .9995 <= probability < 1:
        return ">99.9%"
    return "%.1f%%" % (probability * 100)


def _clip_at_x(points, edge, keep_left):
    result = []
    previous = points[-1]
    previous_inside = previous[0] <= edge if keep_left else previous[0] >= edge
    for current in points:
        inside = current[0] <= edge if keep_left else current[0] >= edge
        if inside != previous_inside:
            fraction = (edge - previous[0]) / (current[0] - previous[0])
            result.append((edge, round(previous[1] + fraction * (current[1] - previous[1]))))
        if inside:
            result.append(current)
        previous, previous_inside = current, inside
    unique = []
    for point in result:
        if not unique or point != unique[-1]:
            unique.append(point)
    if len(unique) > 1 and unique[0] == unique[-1]:
        unique.pop()
    return unique


def _win_chance(objects, league):
    _label(objects, 24, 160, "Estimated win chance", 14, CAPTION, width=TRACK_WIDTH)
    probability = _number(league.get("winProb"))
    valid = probability is not None and 0 <= probability <= 1
    if valid:
        _label(objects, 24, 183, _percent_text(probability),
               20, MINT, width=262, semibold=True)
        _right_label(objects, CONTENT_RIGHT, 183, _percent_text(1 - probability),
                     20, OPPONENT_RED_TEXT)
    else:
        _label(objects, 24, 183, "Unavailable", 16, MUTED, width=TRACK_WIDTH)

    # Both segments are clipped from one rounded shape, preserving only its
    # outside endcaps. No minimum share is invented for tiny probabilities.
    outline = []
    _round_rect(outline, 24, 214, TRACK_WIDTH, 6, 3, NEUTRAL_TRACK)
    objects.extend(outline)
    if not valid:
        return
    points = [(point["x"], point["y"]) for point in outline[0]["points"]]
    split = 24 + round(TRACK_WIDTH * probability)
    for keep_left, color, has_width in ((True, MINT, split > 24),
                                        (False, OPPONENT_RED, split < CONTENT_RIGHT)):
        if has_width:
            clipped = _clip_at_x(points, split, keep_left)
            if len(clipped) >= 3:
                _polygon(objects, clipped, color)


def _footer(objects, focus):
    # A single selected ivory surface. The 4× skin supplies smooth edges and
    # shallow depth; native Inter keeps the action and remote hint crisp.
    filename = "button-matchup-focus.png" if focus else "button-matchup-idle.png"
    objects.append(dict(type="image", x=BUTTON_IMAGE_X, y=BUTTON_IMAGE_Y,
                        width=BUTTON_IMAGE_WIDTH, height=BUTTON_IMAGE_HEIGHT,
                        path=STAGE_DIRECTORY + filename, smooth=True))
    _label(objects, 42, 255, "View matchup", 18,
           "#18272DFF" if focus else WHITE, width=158, semibold=True)
    _label(objects, 230, 260, "OK", 12,
           "#4F6068FF" if focus else MUTED, width=22, semibold=True)


def build_notification(scores, league_id=None, event=None, focus=True,
                       now=None, stale_after=120):
    """Return native objects for the approved one-matchup Quiet Sports popup.

    Selection priority is explicit league_id, event.selectedLeagueId, first
    event.changedLeagueIds entry, then the first available league. Other league
    names and scores never leak into the selected notification. The event's
    deltas are not displayed. Win chance comes only from a valid provider field
    and is explicitly labeled an estimate. No projection, trend or synthetic
    score/probability is created.
    """
    now = time.time() if now is None else float(now)
    league = _league_selection(scores, league_id, event)
    me, opponent = _mapping(league.get("me")), _mapping(league.get("opp"))
    title = league.get("short") or league.get("leagueName") if league else "LEAGUE UNAVAILABLE"
    title = _fitted_team_name({"name": _text(title, 70).upper()}, 302, 14)
    objects = []
    _corner_backing(objects)
    _label(objects, 24, 14, title, 14, CAPTION, width=302, semibold=True)
    _rect(objects, 24, 37, TRACK_WIDTH, 1, "#DCE8EE18")
    _rect(objects, (24 + CONTENT_RIGHT) // 2, 49, 1, 105, "#DCE8EE12")

    status, status_color = _freshness(_mapping(scores), now, stale_after)
    if _mapping(scores).get("ok") is False or league.get("ok") is False:
        status, status_color = "FEED UNAVAILABLE", "#DCC5A0FF"
    if not status.startswith("UPDATED"):
        _right_label(objects, CONTENT_RIGHT, 17, status, 10, status_color, width=200)
    else:
        week = _number(league.get("week"))
        if week is not None and 1 <= week <= 30:
            _right_label(objects, CONTENT_RIGHT, 17, "WEEK %d" % week, 12, FAINT, width=100)

    total_size = min(_total_score_size(team.get("score"), 68, 230)
                     for team in (me, opponent))
    for team, x, text_color in ((me, 24, WHITE), (opponent, 294, MUTED)):
        _label(objects, x, 54, _fitted_team_name({"name": _owner_name(team)}, 222, 23),
               23, text_color, width=222)
        objects[-1]["height"] = 38  # Native Inter23 geometry is35px; retain descenders.
        _total_score_label(objects, x - 2, 86, team.get("score"),
                           total_size, 230, WHITE)
    _win_chance(objects, league)
    _footer(objects, bool(focus))
    return {"objects": objects}
