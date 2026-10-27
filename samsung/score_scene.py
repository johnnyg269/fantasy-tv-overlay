"""Convert the existing ESPN score response into a plain EFL scene.

No network or TV access occurs here. The scene contains plain text, not markup.
Coordinates use the TV's 1920 x 1080 logical canvas.
"""

import argparse
import json
import math
import sys
import time
import unicodedata


WHITE = "#F7F8FAFF"
MUTED = "#B7BEC9FF"
FAINT = "#8E98A7FF"
ACCENT = "#D5DFECFF"
WARNING = "#DFCBA8FF"
PANEL = "#171D27EF"
LINE = "#FFFFFF13"
FONT = "Inter"
FONT_DIRECTORY = "/home/owner/share/tmp/sdk_tools/fantasy-overlay/"
TOTAL_FONT = "Bebas Neue"
TOTAL_FONT_SOURCE = "/home/owner/share/tmp/sdk_tools/fantasy-overlay/BebasNeue-Regular.ttf"
# Advance widths for printable ASCII from the bundled QuietInter-Medium.ttf,
# in em units. A small margin below accounts for native font rasterization.
_INTER_ASCII_EM = (
    .267,.304,.494,.639,.646,.993,.653,.313,.369,.369,.521,.667,.303,.462,.303,.370,
    .646,.415,.616,.627,.656,.603,.630,.571,.629,.630,.303,.315,.667,.667,.667,.527,
    .982,.709,.657,.733,.722,.603,.589,.748,.745,.272,.575,.688,.565,.913,.756,.767,
    .642,.769,.648,.646,.653,.740,.709,1.003,.701,.696,.641,.369,.370,.369,.477,.463,
    .337,.568,.618,.577,.618,.587,.379,.620,.602,.252,.252,.559,.252,.888,.602,.604,
    .618,.618,.387,.539,.340,.602,.575,.829,.557,.575,.559,.440,.346,.440,.667,
)


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _text(value, maximum=30):
    if value is None:
        return "—"
    # Evas text objects do not parse HTML/XML. Keep names literal while removing
    # embedded controls, including bidi controls and newlines, from remote data.
    clean = "".join(
        ch if ch.isprintable() and unicodedata.category(ch) != "Cf" else " "
        for ch in str(value)
    )
    clean = " ".join(clean.split())
    if not clean:
        return "—"
    return clean if len(clean) <= maximum else clean[: maximum - 1].rstrip() + "…"


def _score(value, digits=2):
    number = _number(value)
    if number is None or abs(number) > 9999:
        return "—"
    return format(number, ".%df" % digits)


def _rect(objects, x, y, width, height, color):
    objects.append(dict(type="rectangle", x=x, y=y, width=width,
                        height=height, color=color))


def _polygon(objects, points, color):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    objects.append(dict(type="polygon", points=[dict(x=x, y=y) for x, y in points],
                        color=color, x=min(xs), y=min(ys),
                        width=max(xs) - min(xs), height=max(ys) - min(ys)))


def _round_rect(objects, x, y, width, height, radius, color):
    radius = min(radius, width / 2, height / 2)
    corners = ((x + width - radius, y + radius, -90),
               (x + width - radius, y + height - radius, 0),
               (x + radius, y + height - radius, 90),
               (x + radius, y + radius, 180))
    points = []
    for center_x, center_y, start in corners:
        for step in range(9):
            angle = math.radians(start + step * 90 / 8)
            points.append((round(center_x + math.cos(angle) * radius),
                           round(center_y + math.sin(angle) * radius)))
    _polygon(objects, points, color)


def _broadcast_fade(objects, x, y, width, height, compact=False):
    """Near-black broadcast backing, feathered along its right/bottom edges.

    The broad readable area is one quiet translucent wash. Fine native strips
    feather the outside edges; the corner combines both fades without stacking
    alpha. No border, shadow, plate, neon trim or invented data visualization.
    """
    fade_x, fade_y = (80, 20) if compact else (112, 56)
    core_w, core_h = width - fade_x, height - fade_y
    steps = 16 if compact else 8
    corner_steps = 8 if compact else 4
    alpha = 238

    def opacity(position):
        return 1 - (position * position * (3 - 2 * position))

    def fill(left, top, box_w, box_h, factor):
        _rect(objects, left, top, box_w, box_h,
              "#080C12%02X" % round(alpha * factor))

    fill(x, y, core_w, core_h, 1)
    for strip in range(steps):
        left = round(strip * fade_x / steps)
        right = round((strip + 1) * fade_x / steps)
        top = round(strip * fade_y / steps)
        bottom = round((strip + 1) * fade_y / steps)
        factor = opacity((strip + 0.5) / steps)
        fill(x + core_w + left, y, right - left, core_h, factor)
        fill(x, y + core_h + top, core_w, bottom - top, factor)
    for row in range(corner_steps):
        top, bottom = round(row * fade_y / corner_steps), round((row + 1) * fade_y / corner_steps)
        for column in range(corner_steps):
            left, right = round(column * fade_x / corner_steps), round((column + 1) * fade_x / corner_steps)
            factor = opacity((row + 0.5) / corner_steps) * opacity((column + 0.5) / corner_steps)
            fill(x + core_w + left, y + core_h + top, right - left, bottom - top, factor)


def _label(objects, x, y, text, size=20, color=WHITE, width=350, semibold=False):
    objects.append(dict(type="text", x=x, y=y, text=str(text), size=size,
                        color=color, font=FONT, width=width, height=size + 10,
                        fontSource=FONT_DIRECTORY + ("QuietInter-Semibold.ttf" if semibold
                                                    else "QuietInter-Medium.ttf")))


def _total_score_size(value, preferred, width):
    # Bebas advances include a guard for the TV's wider native rasterization.
    # Round each glyph up and retain four pixels at the text box's edge.
    text = _score(value)
    advances = {'.': .20, '-': .29}
    size = int(preferred)
    while size > 24 and sum(math.ceil(advances.get(ch, .42) * size)
                             for ch in text) + 4 > width:
        size -= 1
    return size


def _total_score_label(objects, x, y, value, size, width, color=WHITE):
    """The sports face is reserved for matchup totals; other labels stay Inter."""
    size = _total_score_size(value, size, width)
    _label(objects, x, y, _score(value), size, color, width=width, semibold=True)
    if _score(value) == '—':
        return
    objects[-1].update(font=TOTAL_FONT, fontSource=TOTAL_FONT_SOURCE,
                       height=size + 26)


def _freshness(scores, now, stale_after):
    updated = _number(scores.get("updated"))
    if updated is None or updated < 0:
        return "NO UPDATE TIME", WARNING
    age = max(0, now - updated)
    if age > stale_after:
        elapsed = "%dm" % (age // 60) if age < 3600 else "%dh" % (age // 3600)
        return "STALE · " + elapsed + " ago", WARNING
    return "UPDATED %ds AGO" % age, ACCENT


def _teams(league):
    return _mapping(league.get("me")), _mapping(league.get("opp"))


def _league_title(league):
    return _text(league.get("short") or league.get("leagueName"), 26)


def _week(league):
    number = _number(league.get("week"))
    return "WK %d" % number if number is not None and 1 <= number <= 30 else ""


def _team_name(team, maximum):
    return _text(team.get("name"), maximum) if team else "TEAM UNAVAILABLE"


def _fitted_team_name(team, width, size):
    name = _team_name(team, 100)

    def advance(character):
        index = ord(character) - 32
        if 0 <= index < len(_INTER_ASCII_EM):
            return _INTER_ASCII_EM[index]
        return 1.05 if unicodedata.east_asian_width(character) in ("F", "W") else .85

    budget = (width - 4) / (size * 1.04)
    if sum(advance(character) for character in name) <= budget:
        return name
    used, result = 0.0, []
    for character in name:
        step = advance(character)
        if used + step + 1.0 > budget:
            break
        result.append(character)
        used += step
    return "".join(result).rstrip() + "…"


def _compact(objects, leagues, status, status_color):
    x, y, width, height = 0, 0, 600, 300
    _broadcast_fade(objects, x, y, width, height, compact=True)
    _label(objects, x + 28, y + 18, "FANTASY", 14, WHITE, width=230,
           semibold=True)
    if not status.startswith("UPDATED"):
        _label(objects, x + 312, y + 20, status, 11, status_color, width=256)
    else:
        weeks = {_week(league) for league in leagues if _week(league)}
        if len(weeks) == 1:
            _label(objects, x + 466, y + 20, next(iter(weeks)).replace("WK ", "WEEK "),
                   12, FAINT, width=100)
    for index in range(2):
        top = y + 53 + index * 124
        if index >= len(leagues):
            _label(objects, x + 28, top + 30, "LEAGUE UNAVAILABLE", 22, MUTED)
            continue
        league = leagues[index]
        me, opponent = _teams(league)
        _label(objects, x + 28, top, _league_title(league), 14, MUTED, 520,
               semibold=True)
        if league.get("ok") is False:
            _label(objects, x + 28, top + 34, "SCORES UNAVAILABLE", 22, WARNING)
            continue
        _label(objects, x + 28, top + 24, _fitted_team_name(me, 240, 22),
               22, WHITE, 240)
        _label(objects, x + 328, top + 24, _fitted_team_name(opponent, 244, 22),
               22, MUTED, 244)
        _label(objects, x + 26, top + 50, _score(me.get("score")), 46, WHITE, 244,
               semibold=True)
        _label(objects, x + 284, top + 65, "–", 22, FAINT, 26)
        _label(objects, x + 326, top + 50, _score(opponent.get("score")), 46,
               WHITE, 248, semibold=True)
        if index == 0:
            _rect(objects, x + 28, top + 111, width - 100, 1, "#FFFFFF16")


def _starters(team):
    players = team.get("players")
    if not isinstance(players, list):
        return []
    return [p for p in players if isinstance(p, dict) and not p.get("bench")][:9]


def _expanded_league(objects, league, x, y, width):
    me, opponent = _teams(league)
    _label(objects, x, y, _league_title(league), 17, ACCENT, 600)
    _label(objects, x + width - 66, y + 1, _week(league), 15, FAINT, 66)
    if league.get("ok") is False:
        _label(objects, x, y + 40, "SCORES UNAVAILABLE", 22, WARNING)
        return
    # Each side is a fixed-width column. Player names are intentionally short
    # so unusually long team/player data cannot flood the rest of the screen.
    _label(objects, x, y + 33, _team_name(me, 23), 21, width=350)
    _label(objects, x + 389, y + 33, _team_name(opponent, 23), 21, MUTED, 350)
    _label(objects, x, y + 63, _score(me.get("score")), 36, width=190, semibold=True)
    _label(objects, x + 389, y + 63, _score(opponent.get("score")), 36,
           WHITE, 190, semibold=True)
    _label(objects, x + 188, y + 76, "PROJ " + _score(me.get("proj")), 15,
           FAINT, 170)
    _label(objects, x + 568, y + 76, "PROJ " + _score(opponent.get("proj")), 15,
           FAINT, 170)
    _rect(objects, x, y + 112, width, 1, LINE)
    for offset in (0, 389):
        _label(objects, x + offset, y + 124, "STARTERS", 12, FAINT, 200)
        _label(objects, x + offset + 256, y + 124, "PTS", 12, FAINT, 45)
        _label(objects, x + offset + 307, y + 124, "PROJ", 12, FAINT, 48)
    mine, theirs = _starters(me), _starters(opponent)
    for row in range(9):
        row_y = y + 150 + row * 25
        if row % 2 == 0:
            _round_rect(objects, x - 6, row_y - 3, width + 12, 25, 5, "#FFFFFF04")
        for players, offset in ((mine, 0), (theirs, 389)):
            if row >= len(players):
                continue
            player = players[row]
            _label(objects, x + offset, row_y, _text(player.get("slot"), 4),
                   13, FAINT, 42)
            _label(objects, x + offset + 44, row_y, _text(player.get("name"), 20),
                   16, WHITE, 210)
            _label(objects, x + offset + 256, row_y, _score(player.get("pts"), 1),
                   14, WHITE, 48)
            _label(objects, x + offset + 307, row_y, _score(player.get("proj"), 1),
                   14, MUTED, 48)
    probability = _number(league.get("winProb"))
    if probability is not None and 0 <= probability <= 1:
        _label(objects, x, y + 387, "EST. WIN CHANCE  %.1f%%" % (100 * probability),
               13, MUTED, 500)


def _expanded(objects, leagues, status, status_color):
    x, y, width, height = 0, 0, 816, 1008
    _broadcast_fade(objects, x, y, width, height)
    _label(objects, x + 28, y + 23, "FANTASY MATCHUPS", 19, width=450, semibold=True)
    if not status.startswith("UPDATED"):
        _label(objects, x + 552, y + 31, status, 11, status_color, width=245)
    _rect(objects, x + 24, y + 70, width - 48, 1, LINE)
    for index in range(2):
        top = y + 92 + index * 436
        if index >= len(leagues):
            _label(objects, x + 28, top + 24, "LEAGUE UNAVAILABLE", 23, MUTED)
            continue
        _expanded_league(objects, leagues[index], x + 28, top, width - 56)
        if index == 0:
            _rect(objects, x + 24, top + 418, width - 48, 1, LINE)
    _label(objects, x + 28, y + height - 36,
           "ACTUAL SCORES · PROJECTIONS MAY CHANGE", 12, FAINT, 760)


def build_state(scores, mode="compact", visible=True, now=None, stale_after=120):
    """Return renderer state; data freshness is based on upstream, not fetch time.

    Only the first two leagues are displayed, in the endpoint's order. Missing
    data produces explicit unavailable labels rather than invented zero scores.
    """
    if mode not in ("compact", "expanded"):
        raise ValueError("mode must be compact or expanded")
    scores = _mapping(scores)
    now = time.time() if now is None else float(now)
    leagues = scores.get("leagues")
    leagues = [_mapping(item) for item in leagues[:2]] if isinstance(leagues, list) else []
    status, status_color = _freshness(scores, now, stale_after)
    if scores.get("ok") is False:
        status, status_color = "FEED UNAVAILABLE", WARNING
    objects = []
    (_expanded if mode == "expanded" else _compact)(objects, leagues, status,
                                                   status_color)
    return dict(visible=bool(visible), mode=mode, scene=dict(objects=objects))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scores", help="Existing score response JSON file")
    parser.add_argument("--mode", choices=("compact", "expanded"), default="compact")
    parser.add_argument("--hidden", action="store_true")
    args = parser.parse_args()
    with open(args.scores, encoding="utf-8") as stream:
        scores = json.load(stream)
    json.dump(build_state(scores, args.mode, not args.hidden), sys.stdout,
              ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
