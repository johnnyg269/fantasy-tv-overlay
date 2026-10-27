"""Translucent native matchup sidebar scenes; no TV/network actions occur here."""

import math

from score_scene import (
    _INTER_ASCII_EM, _fitted_team_name, _label, _mapping, _number, _score, _text,
    _polygon, _round_rect,
)
from notification_scene import _clip_at_x, _percent_text


WIDTH = 720
HEIGHT = 1080
RIGHT_FADE = 180
ROW_START = 356
ROW_PITCH = 64
WHITE = "#F4F6F9FF"
MUTED = "#ACB7C7FF"
FAINT = "#788697FF"
MINT = "#B1DCCCFF"
WARNING = "#DCC5A0FF"
LIVE_MINT = "#8BDDB5FF"
LIVE_WASH = "#8BDDB50F"
PROB_GREEN = "#8BDDB5FF"
PROB_RED = "#C9787BFF"
PROB_GREEN_TEXT = "#AFEACDFF"
PROB_RED_TEXT = "#FFD0D3FF"

# A false bench flag alone is insufficient evidence that a roster entry starts.
# ESPN's reserve/bench codes are excluded before the explicit starter allowlist.
RESERVE_SLOTS = {
    "BE", "BN", "BENCH", "IR", "IR+", "IL", "IL+", "RES", "RESERVE",
    "RESERVES", "INJUREDRESERVE", "INJUREDRESERVE+", "NA", "TAXI", "PUP",
    "SUSP", "DNP", "NFI", "INACTIVE",
}
STARTER_SLOTS = {
    "QB", "RB", "WR", "TE", "K", "PK", "D/ST", "DST", "DEF", "D",
    "FLEX", "SUPERFLEX", "SF", "OP", "RB/WR", "WR/TE", "RB/TE",
    "RB/WR/TE", "QB/RB/WR/TE", "Q/W/R/T", "W/R/T", "W/R", "W/T",
    "IDP", "DP", "DL", "DE", "DT", "LB", "DB", "CB", "S", "SS",
    "FS", "EDGE", "DFLEX", "DL/LB", "LB/DB", "D-FLEX",
}


def _rectangle(objects, x, y, width, height, color):
    objects.append(dict(type="rectangle", x=x, y=y, width=width,
                        height=height, color=color))


def _gradient_backing_layer(objects, y, height, color):
    """A readable content core with a continuous fade into adjacent TV video."""
    _rectangle(objects, 0, y, WIDTH, height, color)
    objects.append(dict(type="gradient", x=WIDTH, y=y,
                        width=RIGHT_FADE, height=height,
                        start_color=color, end_color=color[:7] + "00",
                        direction="horizontal"))


def _slot(value):
    # Whitespace and case do not change the meaning of a lineup slot.
    return "".join(str(value or "").upper().split())


def _true_flag(value):
    return value is True or value == 1 or (isinstance(value, str)
                                          and value.strip().lower() == "true")


def starter_players(team, limit=9):
    """Return verified starters; ``limit=None`` validates the full lineup."""
    players = _mapping(team).get("players")
    if not isinstance(players, list):
        return []
    result = []
    for player in players:
        if not isinstance(player, dict):
            continue
        if any(_true_flag(player.get(flag)) for flag in
               ("bench", "isBench", "reserve", "isReserve", "injuredReserve")):
            continue
        slot = _slot(player.get("slot"))
        if slot in RESERVE_SLOTS or slot not in STARTER_SLOTS:
            continue
        result.append(player)
        if limit is not None and len(result) == limit:
            break
    return result


def _short_slot(player):
    slot = _slot(player.get("slot"))
    return {
        "SUPERFLEX": "SF", "QB/RB/WR/TE": "SF", "Q/W/R/T": "SF",
        "FLEX": "FLX", "RB/WR/TE": "FLX", "W/R/T": "FLX",
        "DST": "D/ST", "DEF": "D/ST", "RB/WR": "R/W",
        "WR/TE": "W/T", "RB/TE": "R/T", "D-FLEX": "DFX",
        "DFLEX": "DFX",
    }.get(slot, slot)


def _is_live_player(player):
    """Require positive NFL enrichment; game phase alone is insufficient.

    LIVE describes the player's NFL game being in progress, not an assertion
    that the athlete is taking the current snap. Known unavailable players
    never receive the green treatment, even if enrichment is inconsistent.
    """
    unavailable = {"out", "injured-reserve", "inactive", "suspended", "practice-squad"}
    availability = str(player.get("nflAvailability", "")).strip().lower()
    availability = availability.replace("_", "-").replace(" ", "-")
    return (player.get("nflHighlightLive") is True
            and str(player.get("nflGameState", "")).strip().lower() == "live"
            and availability not in unavailable)


def _is_on_tv(player, context):
    if context.get("available") is not True:
        return False
    if context.get("confidence") not in ("exact-title-pair", "manual"):
        return False
    matched = context.get("matchedGameId")
    game_id = player.get("gameId")
    return (isinstance(matched, str) and bool(matched.strip())
            and game_id is not None and str(game_id) == matched)


def _live_style(objects, top, offset, on_tv=False):
    # Tint only this manager's player cell; the paired opponent may not be live.
    _rectangle(objects, 22 + offset, top - 3, 338, 60, LIVE_WASH)
    objects.append(dict(type="ellipse", x=28 + offset, y=top + 41,
                        width=4, height=4, color=LIVE_MINT))
    _label(objects, 36 + offset, top + 36, "ON TV" if on_tv else "LIVE",
           10, LIVE_MINT, width=43, semibold=True)


def _number_label(objects, x, y, value, size, width, color=WHITE, digits=1):
    text = _score(value, digits)
    em = 0
    for character in text:
        index = ord(character) - 32
        em += _INTER_ASCII_EM[index] if 0 <= index < len(_INTER_ASCII_EM) else .85
    text_width = min(width, math.ceil(em * size) + 3)
    _label(objects, x + width - text_width, y, text, size, color,
           width=text_width, semibold=True)


def _league_list(scores):
    leagues = _mapping(scores).get("leagues")
    return [league for league in leagues if isinstance(league, dict)] if isinstance(leagues, list) else []


def _selected_league(leagues, league_id):
    if league_id is None:
        return leagues[0] if leagues else {}
    return next((league for league in leagues
                 if str(league.get("leagueId")) == str(league_id)), {})


def _week(league):
    value = _number(league.get("week"))
    return "WEEK %d" % value if value is not None and 1 <= value <= 30 else "WEEK —"


def _team_header(objects, team, x, width):
    from score_scene import _total_score_label

    owner = "Owner unavailable"
    for key in ("ownerName", "displayLabel"):
        value = team.get(key)
        if isinstance(value, str) and value.strip():
            owner = value
            break
    _label(objects, x, 116, _fitted_team_name({"name": owner}, width, 23),
           23, WHITE, width=width)
    objects[-1]["height"] = 38
    _total_score_label(objects, x - 2, 150, team.get("score"), 60, 306, color=WHITE)
    _label(objects, x, 215, "PROJ", 10, FAINT, width=44)
    _label(objects, x + 56, 210, _score(team.get("proj")),
           16, MUTED, width=250, semibold=True)


def _win_chance(objects, league):
    _label(objects, 28, 235, "Estimated win chance", 14, "#D2DADDFF", width=664)
    probability = _number(league.get("winProb"))
    valid = probability is not None and 0 <= probability <= 1
    if valid:
        _label(objects, 28, 257, _percent_text(probability), 20,
               PROB_GREEN_TEXT, width=306, semibold=True)
        _label(objects, 384, 257, _percent_text(1 - probability), 20,
               PROB_RED_TEXT, width=306, semibold=True)
    else:
        _label(objects, 28, 257, "Unavailable", 16, MUTED, width=664)

    track = []
    _round_rect(track, 28, 289, 664, 8, 4, "#76808A40")
    objects.extend(track)
    if not valid:
        return
    points = [(point["x"], point["y"]) for point in track[0]["points"]]
    split = 28 + round(664 * probability)
    for keep_left, color, has_width in ((True, PROB_GREEN, split > 28),
                                        (False, PROB_RED, split < 692)):
        if has_width:
            clipped = _clip_at_x(points, split, keep_left)
            if len(clipped) >= 3:
                _polygon(objects, clipped, color)


def build_sidebar(scores, league_id=None, focus_row=None):
    """Build a full-height glass left sidebar for one league's matchup.

    ``league_id`` selects the affected league. An unknown explicit selection
    displays unavailable content instead of silently showing another matchup.
    The table is read-only by default. An explicitly valid numeric ``focus_row``
    may highlight one of its nine rows for a caller that supplies row navigation.
    All text is bounded, and uses the TV's installed Inter files.
    """
    leagues = _league_list(scores)
    league = _selected_league(leagues, league_id)
    context = _mapping(_mapping(scores).get("tvContext"))
    me, opponent = _mapping(league.get("me")), _mapping(league.get("opp"))
    selected_id = str(league.get("leagueId")) if league else None
    if (isinstance(focus_row, bool) or not isinstance(focus_row, (int, float))
            or not 0 <= focus_row <= 8 or not math.isfinite(focus_row)
            or int(focus_row) != focus_row):
        focus_row = None
    else:
        focus_row = int(focus_row)

    objects = []
    # All content stays on the 69% core. The 180px feather extends beyond the
    # content, so the score columns retain contrast without a hard panel edge.
    _gradient_backing_layer(objects, 0, HEIGHT, "#101820B0")
    _gradient_backing_layer(objects, 0, 275, "#1018200C")
    _gradient_backing_layer(objects, 1012, 68, "#10182010")
    for index, tab in enumerate(leagues[:2]):
        x = 28 + index * 356
        selected = selected_id == str(tab.get("leagueId"))
        label = _text(tab.get("short") or tab.get("leagueName"), 27)
        _label(objects, x, 25, label, 14, WHITE if selected else FAINT,
               width=310, semibold=selected)
        if selected:
            _rectangle(objects, x, 60, 306, 2, MINT)
    _rectangle(objects, 28, 62, WIDTH - 56, 1, "#FFFFFF12")

    meta = _week(league) + "  ·  MATCHUP" if league else "LEAGUE UNAVAILABLE"
    _label(objects, 28, 86, meta, 12, MUTED if league else WARNING, width=664)
    _team_header(objects, me, 28, 306)
    _team_header(objects, opponent, 384, 306)
    _label(objects, 342, 171, "vs", 13, FAINT, width=28)
    _win_chance(objects, league)
    _rectangle(objects, 28, 309, WIDTH - 56, 1, "#FFFFFF14")
    _label(objects, 28, 326, "STARTING LINEUP", 12, MUTED, width=664, semibold=True)

    mine, theirs = starter_players(me), starter_players(opponent)
    for row in range(9):
        top = ROW_START + row * ROW_PITCH
        if row == focus_row:
            _rectangle(objects, 22, top - 6, WIDTH - 44, 59, "#FFFFFF0B")
            _rectangle(objects, 22, top + 6, 2, 31, "#B1DCCC7A")
        elif row % 2 == 0:
            _rectangle(objects, 22, top - 6, WIDTH - 44, 59, "#FFFFFF03")
        for players, offset in ((mine, 0), (theirs, 356)):
            if row >= len(players):
                _label(objects, 76 + offset, top + 14, "—", 20, FAINT, width=270)
                continue
            player = players[row]
            if _is_live_player(player):
                _live_style(objects, top, offset, on_tv=_is_on_tv(player, context))
            _label(objects, 28 + offset, top + 10, _short_slot(player),
                   11, FAINT, width=43)
            _label(objects, 76 + offset, top + 5,
                   _fitted_team_name(player, 270, 20), 20, WHITE, width=270)
            _number_label(objects, 73 + offset, top + 31, player.get("pts"),
                          22, 62)
            _label(objects, 142 + offset, top + 42, "PTS", 10, FAINT, width=36)
            _label(objects, 214 + offset, top + 42, "PROJ", 10, FAINT, width=38)
            _number_label(objects, 260 + offset, top + 35, player.get("proj"),
                          16, 60, MUTED)

    if not mine and not theirs:
        _label(objects, 28, 950, "STARTING LINEUP DATA UNAVAILABLE", 12, WARNING, width=664)
    else:
        title = context.get("title")
        if context.get("available") is True and isinstance(title, str) and title.strip():
            caption = _fitted_team_name({"name": "WATCHING · " + _text(title, 180)},
                                        664, 11)
            _label(objects, 28, 950, caption, 11, MUTED, width=664)
        else:
            _label(objects, 28, 950, "Starting lineup", 11, FAINT, width=664)
    if league.get("ok") is False or _mapping(scores).get("ok") is False:
        _label(objects, 28, 980, "SCORE FEED UNAVAILABLE", 11, WARNING, width=664)
    _rectangle(objects, 28, 1011, WIDTH - 56, 1, "#FFFFFF16")
    _label(objects, 28, 1035, "BACK  Close", 14, WHITE, width=270, semibold=True)
    _label(objects, 358, 1038, "LEFT / RIGHT  Switch league", 11, MUTED, width=338)
    return {"objects": objects}
