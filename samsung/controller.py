#!/usr/bin/env python3
"""Local score polling and toggle controls for the native fantasy overlay.

This process writes renderer JSON only. A caller may supply a Python publish
callback to transport the completed local file; no shell commands are run.
"""

import argparse
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
import math
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import uuid
from urllib.error import URLError
from feed_client import fetch_scores, validate_endpoint

from event_payload import build_event_state, compare_actual_scores, preview_event
from owner_names import annotate_owner_names, load_owner_names


DEFAULT_ENDPOINT = os.environ.get("FANTASY_ENDPOINT")


def atomic_write(path, state):
    """Replace the local state atomically; incomplete JSON is never published."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=str(path.parent),
                                         prefix="." + path.name + ".",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(state, stream, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _timestamp(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


class ScoreController:
    """Reusable controller with an optional transport callback.

    ``publish(path, state)`` runs after the atomic local replacement. A TV
    transport should stage that completed file and atomically rename it on the
    TV. The callback is ordinary Python, never an evaluated command string.
    ``fetcher(endpoint)`` and ``clock()`` may be injected for offline tests.
    """

    def __init__(self, state_file, endpoint=DEFAULT_ENDPOINT, mode="compact",
                 visible=True, publish=None, fetcher=fetch_scores,
                 clock=time.time, fetch_seconds=5, heartbeat_seconds=10,
                 stale_after=120, automatic=True, timer_clock=None,
                 live_enricher=None, context_provider=None):
        if mode not in ("compact", "expanded"):
            raise ValueError("mode must be compact or expanded")
        if fetch_seconds <= 0 or heartbeat_seconds <= 0 or stale_after <= 0:
            raise ValueError("polling, heartbeat and stale intervals must be positive")
        self.state_file = Path(state_file)
        self.endpoint = endpoint
        self.mode = mode
        self.automatic = bool(automatic)
        self.visible = False if self.automatic else bool(visible)
        self.publish = publish
        self.fetcher = fetcher
        self.clock = clock
        self.live_enricher = live_enricher
        self.context_provider = context_provider
        try:
            self.owner_mapping = load_owner_names()
        except (OSError, ValueError, UnicodeError) as error:
            self.owner_mapping = {}
            print("Owner lookup unavailable: " + str(error), file=sys.stderr, flush=True)
        # Real popup expiry uses a monotonic clock. A supplied test clock drives
        # both clocks unless the caller explicitly supplies timer_clock too.
        self.timer_clock = timer_clock or (time.monotonic if clock is time.time else clock)
        self.fetch_seconds = float(fetch_seconds)
        self.heartbeat_seconds = float(heartbeat_seconds)
        self.stale_after = float(stale_after)
        self.scores = None
        self.last_error = None
        self.next_fetch = float("-inf")
        self.next_heartbeat = float("-inf")
        self.baseline = None
        self.alert_id = None
        self.alert_until = None
        self.duration_seconds = 5
        self.shutdown = False
        self.last_event = {"kind": "none", "changedLeagueIds": [], "scoreDeltas": {}}
        self.pending_events = []
        self.current_from_queue = False
        self.control_revision = 0

    def _score_snapshot(self, payload, now):
        """Fresh actuals plus matchup identity, with no projection comparison."""
        updated = _timestamp(payload.get("updated"))
        if payload.get("ok") is False or updated is None or now - updated > self.stale_after:
            return None
        leagues = payload.get("leagues")
        if not isinstance(leagues, list) or not leagues:
            return None
        snapshot = {}
        for league in leagues:
            if not isinstance(league, dict) or league.get("ok") is False:
                return None
            league_id = str(league.get("leagueId", "")).strip()
            me, opponent = league.get("me"), league.get("opp")
            if not league_id or not isinstance(me, dict) or not isinstance(opponent, dict):
                return None
            if league_id in snapshot:
                return None
            week = league.get("week")
            me_id, opponent_id = me.get("teamId"), opponent.get("teamId")
            if week is None or me_id is None or opponent_id is None:
                return None
            actuals = []
            try:
                for team in (me, opponent):
                    value = team.get("score")
                    if isinstance(value, bool):
                        return None
                    value = Decimal(str(value))
                    if not value.is_finite():
                        return None
                    actuals.append(value.quantize(Decimal("0.01")))
            except (InvalidOperation, ValueError, TypeError):
                return None
            snapshot[league_id] = ((str(week), str(me_id), str(opponent_id)), tuple(actuals))
        return snapshot

    def _start_event(self, event, timer_now, queued=False):
        self.last_event = deepcopy(event)
        self.alert_id = uuid.uuid4().hex
        self.alert_until = timer_now + self.duration_seconds
        self.visible = True
        self.current_from_queue = queued

    def _queue_event(self, event, league_id):
        queued = deepcopy(event)
        queued["selectedLeagueId"] = league_id
        for previous in self.pending_events:
            if previous.get("selectedLeagueId") == league_id:
                # Coalesce a team's further updates while its popup waits.
                # Summing two-decimal actual deltas preserves scoring corrections.
                old_delta = previous["scoreDeltas"].get(league_id, {})
                new_delta = queued["scoreDeltas"].get(league_id, {})
                queued["scoreDeltas"][league_id] = {
                    side: float((Decimal(str(old_delta.get(side, 0)))
                                 + Decimal(str(new_delta.get(side, 0))))
                                .quantize(Decimal("0.01")))
                    for side in ("me", "opp")
                }
                previous.clear()
                previous.update(queued)
                return
        self.pending_events.append(queued)

    def _check_scores(self, payload, now, timer_now):
        if not self.automatic:
            return
        snapshot = self._score_snapshot(payload, now)
        if snapshot is None:
            # Stale/failed reads never advance the comparison baseline.
            return
        event = compare_actual_scores(self.baseline, snapshot)
        self.baseline = snapshot
        if event["resetBaseline"]:
            # New league/week/opponent is a different matchup, not a score event.
            self.visible = False
            self.alert_until = None
            self.alert_id = None
            self.pending_events.clear()
            self.last_event = {"kind": "none", "changedLeagueIds": [], "scoreDeltas": {}}
            return
        changed = event["changedLeagueIds"]
        if not changed:
            return
        if self.pending_events or self.current_from_queue and self.alert_until is not None:
            for league_id in changed:
                self._queue_event(event, league_id)
            return
        self._start_event(event, timer_now)
        for league_id in changed[1:]:
            self._queue_event(event, league_id)

    def _refresh(self, now, timer_now):
        # Schedule the next attempt even after an endpoint failure, avoiding an
        # unbounded retry loop or an error response replacing the last scores.
        self.next_fetch = timer_now + self.fetch_seconds
        try:
            payload = self.fetcher(self.endpoint)
            now, timer_now = self.clock(), self.timer_clock()
            if not isinstance(payload, dict) or not isinstance(payload.get("leagues"), list):
                raise ValueError("score response must contain a leagues array")
            updated = _timestamp(payload.get("updated"))
            if updated is None:
                raise ValueError("score response has no valid source timestamp")
            if updated > now + 60:
                raise ValueError("score response timestamp is more than 60 seconds in the future")
            self.scores = self._annotate_live(annotate_owner_names(payload, self.owner_mapping),
                                               submit=True)
            self.last_error = None
            self._check_scores(payload, now, timer_now)
        except (URLError, OSError, ValueError, UnicodeError) as error:
            self.last_error = " ".join(str(error).split())[:240] or type(error).__name__
        finally:
            self.next_fetch = self.timer_clock() + self.fetch_seconds

    def _annotate_live(self, payload, submit=False):
        if self.live_enricher is None:
            return payload
        try:
            if submit:
                self.live_enricher.submit_latest(payload)
            return self.live_enricher.apply_cached(payload)
        except Exception as error:
            # NFL status is optional enrichment, not a fantasy score-feed error.
            from nfl_live import clear_live_metadata
            return clear_live_metadata(payload, error=type(error).__name__)

    def current_state(self, now=None):
        now = self.clock() if now is None else float(now)
        payload = self._annotate_live(dict(self.scores) if self.scores is not None else {})
        if self.context_provider is not None:
            try:
                context = self.context_provider()
                payload["tvContext"] = deepcopy(context) if isinstance(context, dict) else {"available": False}
            except Exception:
                # Program metadata is optional. Losing it cannot alter scores,
                # trigger a popup or retain an old ON TV indication.
                payload["tvContext"] = {"available": False}
        if self.last_error is not None or self.scores is None:
            # The scene builder retains existing scores but clearly labels the
            # failed feed. Advancing a heartbeat never advances source freshness.
            payload["ok"] = False
        state = build_event_state(payload, event=self.last_event, mode=self.mode,
                                  visible=self.visible, now=now,
                                  stale_after=self.stale_after)
        state["controlRevision"] = self.control_revision
        if "nflLive" in payload:
            state["nflLive"] = deepcopy(payload["nflLive"])
        if "tvContext" in payload:
            state["tvContext"] = deepcopy(payload["tvContext"])
        updated = _timestamp(payload.get("updated"))
        state["feed"] = {
            "available": self.last_error is None and self.scores is not None
                         and payload.get("ok") is not False,
            "sourceUpdated": updated,
            "ageSeconds": max(0, now - updated) if updated is not None else None,
            "error": self.last_error,
        }
        if self.alert_id is not None:
            state["alertId"] = self.alert_id
            state["durationSeconds"] = self.duration_seconds
        if self.shutdown:
            state["exit"] = True
        return state

    def publish_current(self, now=None, timer_now=None):
        now = self.clock() if now is None else float(now)
        timer_now = self.timer_clock() if timer_now is None else float(timer_now)
        state = self.current_state(now)
        atomic_write(self.state_file, state)
        if self.publish is not None:
            self.publish(self.state_file, state)
        self.next_heartbeat = timer_now + self.heartbeat_seconds
        return state

    def tick(self, force_publish=False):
        now = self.clock()
        timer_now = self.timer_clock()
        if self.automatic and self.alert_until is not None and timer_now >= self.alert_until:
            self.visible = False
            self.alert_until = None
            force_publish = True
        if timer_now >= self.next_fetch:
            self._refresh(now, timer_now)
            now, timer_now = self.clock(), self.timer_clock()
            # Source changes/errors should appear immediately, even between
            # periodic heartbeat writes.
            force_publish = True
        if self.automatic and self.alert_until is None and self.pending_events:
            self._start_event(self.pending_events.pop(0), self.timer_clock(), queued=True)
            force_publish = True
        if force_publish or timer_now >= self.next_heartbeat:
            return self.publish_current(now, timer_now)
        return None

    def apply_command(self, command):
        """Apply one console control; return False for quit, True otherwise."""
        command = command.strip().lower()
        if command in ("auto", "automatic"):
            self.automatic = True
            self.visible = False
            self.baseline = None
            self.alert_id = None
            self.alert_until = None
            self.pending_events.clear()
            self.current_from_queue = False
            self.last_event = {"kind": "none", "changedLeagueIds": [], "scoreDeltas": {}}
        elif command == "preview":
            # A display check uses the real current scores. It preserves the
            # automatic comparison baseline and expires like a normal popup.
            self.automatic = True
            self._start_event(preview_event(self.scores), self.timer_clock())
        elif command in ("compact", "expanded"):
            self.mode = command
        elif command in ("hide", "show", "toggle"):
            self.automatic = False
            self.alert_id = None
            self.alert_until = None
            self.pending_events.clear()
            self.current_from_queue = False
            self.last_event = {"kind": "none", "changedLeagueIds": [], "scoreDeltas": {}}
            self.visible = not self.visible if command == "toggle" else command == "show"
        elif command in ("quit", "exit", "q"):
            self.visible = False
            self.shutdown = True
            self.control_revision += 1
            self.publish_current()
            return False
        elif command in ("", "help", "?"):
            return True
        else:
            raise ValueError("Use auto, preview, compact, expanded, hide, show, toggle or quit")
        self.control_revision += 1
        # Controls do not wait for a network refresh. Hiding is immediate even
        # when the next score request would fail or take several seconds.
        self.publish_current()
        return True


def _read_console(commands):
    for line in sys.stdin:
        commands.put(line)
    commands.put("quit")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", type=Path,
                        default=Path(__file__).resolve().parent / ".local/state.json")
    parser.add_argument("--endpoint", default=os.environ.get("FANTASY_ENDPOINT"))
    parser.add_argument("--allow-loopback-http", action="store_true",
                        help="Allow HTTP to a numeric loopback address for the synthetic demo only")
    parser.add_argument("--mode", choices=("compact", "expanded"), default="compact")
    parser.add_argument("--hidden", action="store_true")
    automatic = parser.add_mutually_exclusive_group()
    automatic.add_argument("--automatic", dest="automatic", action="store_true",
                           help="Show a five-second popup on each actual score change (default)")
    automatic.add_argument("--manual", dest="automatic", action="store_false",
                           help="Show the panel continuously for manual preview")
    parser.set_defaults(automatic=True)
    parser.add_argument("--poll-seconds", type=float, default=5,
                        help="Score polling interval (default: 5 seconds)")
    parser.add_argument("--once", action="store_true",
                        help="Fetch and write one state, then exit")
    parser.add_argument("--input", type=Path,
                        help="Read existing score JSON instead of making network requests")
    parser.add_argument("--no-console", action="store_true",
                        help="Poll until interrupted without reading stdin")
    args = parser.parse_args(argv)
    if args.input is None:
        validate_endpoint(args.endpoint, args.allow_loopback_http)
    fetcher = lambda endpoint: fetch_scores(endpoint, allow_loopback_http=args.allow_loopback_http)
    if args.input is not None:
        def fetcher(_endpoint):
            with args.input.open(encoding="utf-8") as stream:
                return json.load(stream)
    controller = ScoreController(args.state_file, endpoint=args.endpoint,
                                 mode=args.mode, visible=not args.hidden,
                                 fetcher=fetcher, automatic=args.automatic,
                                 fetch_seconds=args.poll_seconds)
    controller.tick(force_publish=True)
    if args.once:
        if controller.last_error:
            print("Feed unavailable: " + controller.last_error, file=sys.stderr)
            return 1
        print("Wrote " + str(args.state_file))
        return 0
    print("Controls: auto | preview | compact | expanded | hide | show | toggle | quit", flush=True)
    print("Local state: " + str(args.state_file), flush=True)
    commands = queue.Queue()
    if not args.no_console:
        threading.Thread(target=_read_console, args=(commands,), daemon=True).start()
    try:
        while True:
            try:
                command = commands.get(timeout=0.5)
                try:
                    if not controller.apply_command(command):
                        break
                    if command.strip().lower() == "preview":
                        print("Showing current-score preview for five seconds.", flush=True)
                except ValueError as error:
                    print(str(error), file=sys.stderr, flush=True)
            except queue.Empty:
                pass
            controller.tick()
    except KeyboardInterrupt:
        controller.visible = False
        controller.shutdown = True
        controller.publish_current()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
