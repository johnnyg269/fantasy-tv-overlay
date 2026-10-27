#!/usr/bin/env python3
"""Run the bounded TV overlay session and deliver atomic score updates.

The renderer and its .NET runtime configuration must already be staged on the
owner's TV. This runner does not install applications or alter Home/startup.
"""

import argparse
import base64
from collections import deque
import fcntl
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import queue
import re
import shlex
import subprocess
import struct
import stat
import sys
import threading
import time
import uuid

from controller import DEFAULT_ENDPOINT, ScoreController, atomic_write
from feed_client import fetch_scores, validate_endpoint
from alexa_bridge.private_config import load_private_json
from send_control import take_request
from nfl_live import NflLiveWorker


HERE = Path(__file__).resolve().parent
WORK = HERE.parent
PINNED_SDB_SHA256 = "77c89d9a9f38566dfb2c5ef6a9fd371e54b9e3ca52a0feb3c05fd7cdd60ab153"
STAGE = "/home/owner/share/tmp/sdk_tools/fantasy-overlay"
SCORE_FONT_NAME = "BebasNeue-Regular.ttf"
FONT_NAMES = (SCORE_FONT_NAME, "QuietInter-Medium.ttf", "QuietInter-Semibold.ttf")
UI_ASSET_NAMES = ('button-matchup-focus.png', 'button-matchup-idle.png',
                  'popup-corner-shade.png')


class ConfigurationError(RuntimeError):
    """An operator/configuration problem that watching must not retry."""


class StopRequested(Exception):
    pass


def load_sdb_client(source):
    # Load only the pinned dependency-free transport, not a source-tree plugin.
    source = Path(source).expanduser().resolve(strict=True)
    if hashlib.sha256(source.read_bytes()).hexdigest() != PINNED_SDB_SHA256:
        raise ConfigurationError("SDB transport does not match pinned samsung-tv-root v0.0.12")
    spec = importlib.util.spec_from_file_location("fantasy_overlay_sdb", source)
    if spec is None or spec.loader is None:
        raise ConfigurationError("Cannot load the pinned SDB transport")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.SdbClient


class TVTransport:
    """One SDK operation at a time, with verified atomic state replacement."""

    def __init__(self, client, callback_host, state_basename="state.json"):
        if not re.fullmatch(r"[A-Za-z0-9.-]{1,32}", state_basename):
            raise ConfigurationError("Invalid session state basename")
        self.client = client
        self.callback_host = callback_host
        self.state_basename = state_basename
        self.lock = threading.Lock()
        # This TV reliably executes short inline captures. The SDK's automatic
        # oversized-command staging times out here; refuse that route so callers
        # split their operations instead of leaving an inaccessible staged script.
        self.client._stage_script = self._reject_script_staging

    @staticmethod
    def _reject_script_staging(_command):
        raise ConfigurationError('TV capture exceeds the safe inline limit; split it into shorter commands')

    def capture(self, command, timeout=15, allowed_exits=(0,)):
        with self.lock:
            result = self.client.capture(command, callback_host=self.callback_host,
                                         timeout=timeout)
        matches = re.findall(r"(?m)^\[exit:([0-9]+)\]\s*$", result.output)
        if not matches or int(matches[-1]) not in allowed_exits:
            raise RuntimeError("TV command did not report an allowed exit code: "
                               + result.output.strip()[-1000:])
        return result.output

    def publish(self, path, _state):
        with self.lock:
            self.client.push(Path(path), Path(STAGE + "/" + self.state_basename + ".next"))
            result = self.client.capture(
                "cd " + shlex.quote(STAGE) + " && mv "
                + shlex.quote(self.state_basename + ".next") + " "
                + shlex.quote(self.state_basename),
                callback_host=self.callback_host, timeout=15)
        matches = re.findall(r"(?m)^\[exit:([0-9]+)\]\s*$", result.output)
        if not matches or matches[-1] != "0":
            raise RuntimeError("TV state rename did not report exit 0: "
                               + result.output.strip()[-1000:])


def verify_model(client, expected_model):
    client.connect()
    client.require_device()
    result = client.run(("devices",), check=True)
    matching = [line.split() for line in result.stdout.splitlines()
                if line.split() and line.split()[0] == client.serial]
    if (len(matching) != 1 or len(matching[0]) < 3
            or matching[0][1] != "device"
            or matching[0][2] != expected_model):
        raise ConfigurationError("Expected " + expected_model + " at " + client.serial
                                 + "; SDB reported: " + result.stdout.strip())


def renderer_command(seconds, marker, state_basename="state.json"):
    # Only terminate a previous instance whose numeric PID and exact managed
    # assembly argument both match. No unrelated dotnet/application is touched.
    script = ("cd " + shlex.quote(STAGE) + " || exit 1\n"
              + "for f in " + ' '.join(FONT_NAMES + UI_ASSET_NAMES) + "; do\n"
              + " test -r \"$f\" || exit 1\n"
              + " chmod 0644 \"$f\" || exit 1\n"
              + " chsmack -a 'User::App::Shared' \"$f\" || exit 1\n"
              + "done\n"
              + "if [ -r active.pid ]; then\n"
              + " p=$(cat active.pid)\n"
              + " case \"$p\" in ''|*[!0-9]*) p=;; esac\n"
              + " if [ -n \"$p\" ] && [ -r /proc/\"$p\"/cmdline ] "
              + "&& tr '\\000' '\\n' < /proc/\"$p\"/cmdline | grep -Fx "
              + shlex.quote(STAGE + "/FantasyOverlay.dll") + " >/dev/null; then\n"
              + "  kill -TERM \"$p\" || exit 1\n"
              + "  n=0; while kill -0 \"$p\" 2>/dev/null; do "
              + "n=$((n+1)); [ \"$n\" -ge 5 ] && exit 1; sleep 1; done\n"
              + " fi\nfi\n"
              # Close inherited SDK callback descriptors as well as redirecting
              # stdio; otherwise the child holds the root capture channel open.
              + "(\n for f in /proc/self/fd/*; do\n"
              + "  n=${f##*/}\n"
              + "  case \"$n\" in 0|1|2|*[!0-9]*) ;; *) eval \"exec $n>&-\" ;; esac\n"
              + " done\n exec /usr/bin/dotnet "
              + shlex.quote(STAGE + "/FantasyOverlay.dll")
              + " --seconds " + str(seconds)
              + " --state " + shlex.quote(STAGE + "/" + state_basename)
              + " --stale-seconds 30\n) > "
              + shlex.quote(marker.replace(".pid", ".log"))
              + " 2>&1 < /dev/null & p=$!\n"
              + "printf '%s\\n' \"$p\" > active.pid\n"
              + "printf '%s\\n' \"$p\" > " + shlex.quote(marker) + "\n"
              + "printf 'renderer_pid=%s\\n' \"$p\"")
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    return "printf %s " + shlex.quote(encoded) + " | base64 -d | /bin/sh"


def stage_binary_asset(client, transport, source, remote_name, content):
    expected = hashlib.sha256(content).hexdigest()
    command = 'cd ' + shlex.quote(STAGE) + ' && sha256sum ' + remote_name
    output = transport.capture(command, allowed_exits=(0, 1))
    if expected + '  ' + remote_name not in output:
        with transport.lock:
            client.push(source, Path(STAGE + '/' + remote_name))
        output = transport.capture(command)
        if expected + '  ' + remote_name not in output:
            raise RuntimeError('TV asset checksum did not match: ' + remote_name)


def stage_score_font(client, transport):
    """Stage the licensed, self-contained UI and score fonts."""
    for name in FONT_NAMES:
        source = HERE / "assets/fonts" / name
        if not source.is_file():
            raise ConfigurationError("Missing bundled font: " + name)
        content = source.read_bytes()
        if not 1000 <= len(content) <= 2 * 1024 * 1024 or content[:4] != b"\x00\x01\x00\x00":
            raise ConfigurationError("Bundled font is not a bounded TrueType asset")
        stage_binary_asset(client, transport, source, name, content)
    print("UI and score fonts staged and checksum verified.", flush=True)


def stage_ui_assets(client, transport):
    for name in UI_ASSET_NAMES:
        source = HERE / 'assets/ui' / name
        if not source.is_file():
            raise ConfigurationError('Missing bundled overlay artwork: ' + str(source))
        content = source.read_bytes()
        if (not 24 <= len(content) <= 1024 * 1024
                or content[:8] != b'\x89PNG\r\n\x1a\n'):
            raise ConfigurationError('Overlay artwork must be a bounded PNG: ' + name)
        width, height = struct.unpack('>II', content[16:24])
        max_width, max_height = (1000, 650) if name == 'popup-corner-shade.png' else (2048, 512)
        if not 1 <= width <= max_width or not 1 <= height <= max_height:
            raise ConfigurationError('Unexpected overlay artwork dimensions: ' + name)
        stage_binary_asset(client, transport, source, name, content)
    print('Overlay artwork staged and checksums verified.', flush=True)


def read_console(commands, stop_event):
    for line in sys.stdin:
        command = line.strip()
        if command.lower() in ("quit", "exit", "q"):
            stop_event.set()
            return
        commands.put(command)
    # Closing the visible console ends the watch rather than creating an
    # unattended process. --no-console deliberately does not start this reader.
    stop_event.set()


def poll_control_file(request_path, launched_at_ns, commands, stop_event):
    """One local control-file reader for the entire visible app lifetime."""
    seen = deque(maxlen=128)
    while not stop_event.is_set():
        try:
            request = take_request(request_path, launched_at_ns)
        except OSError as error:
            print("Local overlay control unavailable: " + str(error),
                  file=sys.stderr, flush=True)
            request = None
        if request is not None and request["nonce"] not in seen:
            seen.append(request["nonce"])
            if request["command"] == "quit":
                print("Stop requested from local overlay control.", flush=True)
                stop_event.set()
                break
            commands.put(request["command"])
        stop_event.wait(0.5)


def hidden_exit_state():
    return {"visible": False, "mode": "compact", "exit": True}


def report_receipt(path, returncode):
    try:
        receipt = load_private_json(path, max_bytes=2 * 1024 * 1024)
    except (OSError, ValueError):
        print("Root session ended with code " + str(returncode)
              + ". Inspect " + str(path), flush=True)
        return False
    identity_ok = (receipt.get("authenticated") is True
                   and receipt.get("uid") == 0 and receipt.get("euid") == 0)
    cleanup_ok = (receipt.get("staging_cleaned") is True
                  and receipt.get("system_files_unchanged") is True)
    command_results = receipt.get("commands", [])
    command_ok = bool(command_results) and all(
        item.get("exit_code") == 0 and not item.get("timed_out")
        for item in command_results)
    if returncode == 0 and identity_ok and cleanup_ok and command_ok:
        print("Temporary root command completed; authenticated cleanup and system-file "
              "checks passed. Receipt: " + str(path), flush=True)
        return True
    print("Root session ended, but its command or cleanup checks did not all "
          "pass. Inspect " + str(path), file=sys.stderr, flush=True)
    return False


def receipt_renderer_pid(path):
    receipt = load_private_json(path, max_bytes=2 * 1024 * 1024)
    output = "\n".join(item.get("stdout", "")
                       for item in receipt.get("commands", []))
    matches = re.findall(r"(?m)^renderer_pid=([0-9]{1,10})\s*$", output)
    if len(matches) != 1 or int(matches[0]) < 2:
        raise RuntimeError("Root receipt did not contain one valid renderer PID")
    return int(matches[0])


def renderer_running(transport, pid):
    pid = str(int(pid))
    command = ("test -d /proc/" + pid + " && tr '\\000' '\\n' < /proc/"
               + pid + "/cmdline | grep -Fx "
               + shlex.quote(STAGE + "/FantasyOverlay.dll") + " >/dev/null")
    output = transport.capture(command, allowed_exits=(0, 1))
    return re.search(r"(?m)^\[exit:0\]\s*$", output) is not None


def wait_root_process(process, stop_event, seconds=120):
    """Never use SDK concurrently with the root command's held SDB shell."""
    deadline = time.monotonic() + seconds
    while process.poll() is None:
        if time.monotonic() >= deadline:
            raise RuntimeError("Root acquisition/cleanup exceeded " + str(seconds)
                               + " seconds")
        try:
            time.sleep(min(0.5, max(0, deadline - time.monotonic())))
        except KeyboardInterrupt:
            stop_event.set()
            print("Stop requested; waiting for the root command to finish cleanup…",
                  flush=True)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tv", default=os.environ.get("FANTASY_TV_IP"))
    parser.add_argument("--model", default=os.environ.get("FANTASY_TV_MODEL"),
                        help="Exact model from About This TV; checked against SDB")
    parser.add_argument("--firmware", default=os.environ.get("FANTASY_TV_FIRMWARE"),
                        help="Exact firmware read by you from About This TV (operator declaration)")
    parser.add_argument("--root-receipt", type=Path,
                        help="Fresh successful upstream archive-root probe JSON for this TV")
    parser.add_argument("--acknowledge-root-risk", action="store_true",
                        help="Confirm this is your authorized TV and temporary root has been validated")
    parser.add_argument("--callback-host", default=os.environ.get("FANTASY_HOST_IP"))
    parser.add_argument("--seconds", type=int, default=28800,
                        help="Bounded renderer lifetime, 1..86400 seconds")
    parser.add_argument("--sdb", type=Path)
    parser.add_argument("--sdb-module", type=Path, help="Pinned upstream src/samsung_tv_root/sdb.py")
    parser.add_argument("--root-tool", type=Path)
    parser.add_argument("--endpoint", default=os.environ.get("FANTASY_ENDPOINT"))
    parser.add_argument("--allow-loopback-http", action="store_true", help="Synthetic demo at a numeric loopback HTTP address only")
    parser.add_argument("--mode", choices=("compact", "expanded"), default="compact")
    parser.add_argument("--preview", action="store_true",
                        help="Display the current feed for five seconds after startup")
    parser.add_argument("--no-console", action="store_true",
                        help="Run until interrupted or the bounded lifetime ends")
    parser.add_argument("--watch", action="store_true",
                        help="Reconnect after TV loss and renew bounded sessions "
                             "while this visible app remains open")
    parser.add_argument("--no-tv-context", action="store_true",
                        help="Skip the optional paired Apple TV program metadata session")
    return parser


def validate_configuration(args, require_endpoint=True):
    # No connection, subprocess or root operation occurs until these checks pass.
    for name in ("tv", "callback_host"):
        try:
            address = ipaddress.IPv4Address(getattr(args, name))
        except (ipaddress.AddressValueError, TypeError):
            raise ConfigurationError("Set an explicit IPv4 address for --" + name.replace("_", "-")) from None
        if address.is_loopback or address.is_multicast or address.is_unspecified:
            raise ConfigurationError("TV and callback addresses must identify your authorized LAN devices")
    if args.tv == args.callback_host:
        raise ConfigurationError("The TV and host callback address must differ")
    if not args.acknowledge_root_risk:
        raise ConfigurationError("Read ROOT_SETUP.md and pass --acknowledge-root-risk for your own validated TV")
    if not isinstance(args.model, str) or not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", args.model):
        raise ConfigurationError("Set the exact --model from About This TV")
    if not isinstance(args.firmware, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,128}", args.firmware):
        raise ConfigurationError("Set the exact --firmware from About This TV; it is an operator declaration")
    if not 1 <= args.seconds <= 86400:
        raise ConfigurationError("--seconds must be from 1 through 86400")
    for executable in (args.sdb, args.root_tool):
        if executable is None or not executable.is_file() or not os.access(str(executable), os.X_OK):
            raise ConfigurationError("Provide existing --sdb and --root-tool executables")
    if args.sdb_module is None or not args.sdb_module.is_file():
        raise ConfigurationError("Provide --sdb-module from pinned upstream v0.0.12")
    if hashlib.sha256(args.sdb_module.read_bytes()).hexdigest() != PINNED_SDB_SHA256:
        raise ConfigurationError("SDB module does not match the pinned upstream source")
    validate_root_receipt(args.root_receipt, args.tv)
    if require_endpoint:
        validate_endpoint(args.endpoint, args.allow_loopback_http)


def validate_root_receipt(path, tv, now=None):
    """Require recent authenticated cleanup evidence for the named target."""
    now = time.time() if now is None else now
    if path is None:
        raise ConfigurationError("Run the explicit root probe in ROOT_SETUP.md first; provide --root-receipt")
    path = Path(path)
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            raise ValueError("private file")
        if not 0 <= now - path.stat().st_mtime <= 7 * 86400:
            raise ValueError("stale")
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("oversize")
        receipt = load_private_json(path, max_bytes=2 * 1024 * 1024)
        runtime = receipt.get("runtime")
        runtime_major = int(str(runtime).split(".")[0])
        valid = (receipt.get("host") == tv and receipt.get("authenticated") is True
                 and type(receipt.get("uid")) is int and receipt.get("uid") == 0
                 and type(receipt.get("euid")) is int and receipt.get("euid") == 0
                 and receipt.get("staging_cleaned") is True
                 and receipt.get("system_files_unchanged") is True
                 and runtime_major >= 6)
        if not valid:
            raise ValueError("identity or cleanup")
    except (OSError, ValueError, TypeError, AttributeError):
        raise ConfigurationError("Root receipt must be fresh authenticated UID/EUID 0, .NET >=6, cleaned and system-unchanged for this exact TV") from None
    return receipt


def acquire_runner_lock():
    local = HERE / ".local"
    local.mkdir(exist_ok=True, mode=0o700)
    if local.is_symlink() or local.stat().st_uid != os.getuid():
        raise ConfigurationError("Private state directory must be owned by this user and not a symlink")
    os.chmod(str(local), 0o700)
    lock_stream = (local / "runner.lock").open("a+")
    try:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_stream.close()
        raise ConfigurationError("Another overlay runner is already active in this folder")
    return lock_stream


def run(args, stop_event=None, commands=None, runner_lock=None, context_provider=None):
    validate_configuration(args)
    stop_event = stop_event if stop_event is not None else threading.Event()
    commands = commands if commands is not None else queue.Queue()
    owns_lock = runner_lock is None
    lock_stream = acquire_runner_lock() if owns_lock else runner_lock
    local = HERE / ".local"
    session = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    token = uuid.uuid4().hex[:8]
    state_basename = "s-" + token + ".json"
    state_file = local / (session + "-state.json")
    receipt_path = local / (session + "-root.json")
    marker = "p-" + token + ".pid"
    process = None
    receipt_stream = None
    transport = None
    receipt_ok = False
    native_pid = None
    renderer_ended = False
    live_worker = None
    try:
        if stop_event.is_set():
            raise StopRequested()
        client = load_sdb_client(args.sdb_module)(args.sdb.resolve(), args.tv, timeout=15)
        print("Checking the identified TV over SDB…", flush=True)
        verify_model(client, args.model)
        if stop_event.is_set():
            raise StopRequested()
        transport = TVTransport(client, args.callback_host, state_basename)
        transport.capture("cd " + shlex.quote(STAGE)
                          + " && test -f FantasyOverlay.dll -a -f FantasyOverlay.runtimeconfig.json")
        stage_score_font(client, transport)
        stage_ui_assets(client, transport)
        atomic_write(state_file, {"visible": False, "mode": args.mode})
        transport.publish(state_file, None)
        if stop_event.is_set():
            raise StopRequested()
        command = [str(args.root_tool.resolve()), "--sdb", str(args.sdb.resolve()),
                   "-o", "json", "archive-root", "root", args.tv,
                   "--callback-host", args.callback_host, "--command",
                   renderer_command(args.seconds, marker, state_basename),
                   "--command-timeout", "30"]
        receipt_stream = receipt_path.open("w", encoding="utf-8")
        os.chmod(str(receipt_path), 0o600)
        process = subprocess.Popen(command, stdout=receipt_stream,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   start_new_session=True)
        print("Acquiring temporary root, starting a bounded renderer, and waiting "
              "for root cleanup before SDK updates…", flush=True)
        wait_root_process(process, stop_event)
        receipt_stream.close()
        receipt_stream = None
        receipt_ok = report_receipt(receipt_path, process.returncode)
        if not receipt_ok:
            raise RuntimeError("Root launch or cleanup was not verified; inspect "
                               + str(receipt_path))
        native_pid = receipt_renderer_pid(receipt_path)
        if stop_event.is_set():
            raise StopRequested()
        if not renderer_running(transport, native_pid):
            raise RuntimeError("The launched renderer PID/assembly is not running; "
                               "inspect TV log " + STAGE + "/"
                               + marker.replace(".pid", ".log"))
        print("Renderer process started; root cleanup is complete. Visual output "
              "still needs on-TV verification.", flush=True)
        live_worker = NflLiveWorker()
        controller = ScoreController(state_file, endpoint=args.endpoint,
                                     mode=args.mode, visible=False,
                                     publish=transport.publish,
                                     fetcher=lambda endpoint: fetch_scores(endpoint, allow_loopback_http=args.allow_loopback_http),
                                     fetch_seconds=5,
                                     heartbeat_seconds=10, live_enricher=live_worker,
                                     context_provider=context_provider)
        controller.tick(force_publish=True)
        last_feed_error = controller.last_error
        if last_feed_error:
            print("Score feed unavailable: " + last_feed_error, file=sys.stderr,
                  flush=True)
        if args.preview:
            print("Showing current-score preview for five seconds.", flush=True)
            controller.apply_command("preview")
        last_seen_alert = controller.alert_id
        print("Controls: auto | preview | show | hide | toggle | compact | expanded | quit",
              flush=True)
        next_probe = time.monotonic() + 10
        native_deadline = time.monotonic() + args.seconds + 15
        while not stop_event.is_set() and time.monotonic() < native_deadline:
            try:
                command = commands.get(timeout=0.5)
                if command.lower() in ("quit", "exit", "q"):
                    stop_event.set()
                    break
                if command.lower() == "fontcheck":
                    # Developer diagnostic runs in this same SDK-owning loop,
                    # so it cannot race the score publisher's callback channel.
                    font_log = transport.capture('cd ' + shlex.quote(STAGE)
                        + " && grep -m 3 '^font_file_metrics' "
                        + shlex.quote(marker.replace('.pid', '.log')),
                        allowed_exits=(0, 1))
                    (local / (session + '-fonts.log')).write_text(font_log, encoding='utf-8')
                    print(font_log, flush=True)
                    continue
                try:
                    if command.lower() == "preview":
                        print("Showing current-score preview for five seconds.", flush=True)
                    controller.apply_command(command)
                    last_seen_alert = controller.alert_id
                except ValueError as error:
                    print(str(error), file=sys.stderr, flush=True)
            except queue.Empty:
                pass
            controller.tick()
            if controller.alert_id is not None and controller.alert_id != last_seen_alert:
                print("Score change detected; displaying scores for five seconds.",
                      flush=True)
            last_seen_alert = controller.alert_id
            if controller.last_error != last_feed_error:
                last_feed_error = controller.last_error
                print("Score feed recovered." if last_feed_error is None else
                      "Score feed unavailable: " + last_feed_error, flush=True)
            if time.monotonic() >= next_probe:
                if not renderer_running(transport, native_pid):
                    renderer_ended = True
                    break
                next_probe = time.monotonic() + 10
    except KeyboardInterrupt:
        stop_event.set()
        print("Stopping the overlay…", flush=True)
    except StopRequested:
        print("Stopping the overlay…", flush=True)
    finally:
        # Finish or terminate the old host root tool before any more SDK calls.
        if process is not None and process.poll() is None:
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                print("Root cleanup did not finish within 30 seconds; stopping "
                      "the host tool. TV-side cleanup is unverified. Receipt: "
                      + str(receipt_path), file=sys.stderr, flush=True)
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        if receipt_stream is not None:
            receipt_stream.close()
        if live_worker is not None:
            live_worker.close(timeout=1)
        if native_pid is not None and not renderer_ended and transport is not None:
            try:
                atomic_write(state_file, hidden_exit_state())
                transport.publish(state_file, None)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if not renderer_running(transport, native_pid):
                        renderer_ended = True
                        break
                    time.sleep(0.5)
                if not renderer_ended:
                    print("Renderer exit was not confirmed within 10 seconds; "
                          "its heartbeat and bounded lifetime still apply.",
                          file=sys.stderr, flush=True)
            except Exception as error:
                print("Could not confirm renderer shutdown: " + str(error)
                      + ". The renderer hides after 30 seconds without a heartbeat "
                      "and retains its bounded lifetime.", file=sys.stderr, flush=True)
        if renderer_ended and transport is not None:
            try:
                log_output = transport.capture("cd " + shlex.quote(STAGE)
                                               + " && tail -n 12 "
                                               + shlex.quote(marker.replace(".pid", ".log")))
                (local / (session + "-renderer.log")).write_text(log_output, encoding="utf-8")
                print("Renderer PID has exited. Log: "
                      + str(local / (session + "-renderer.log")), flush=True)
                transport.capture("cd " + shlex.quote(STAGE) + " && rm -f "
                                  + shlex.quote(marker) + " "
                                  + shlex.quote(state_basename) + " "
                                  + shlex.quote(state_basename + ".next"))
            except Exception as error:
                print("Renderer log or session-file cleanup failed: " + str(error),
                      file=sys.stderr, flush=True)
        if owns_lock:
            lock_stream.close()
    return 0 if receipt_ok and renderer_ended or process is None and stop_event.is_set() else 1


def main(argv=None):
    os.umask(0o077)
    launched_at_ns = time.time_ns()
    stop_event = threading.Event()
    commands = queue.Queue()
    runner_lock = None
    control_thread = None
    context_session = None
    voice_session = None
    try:
        args = build_parser().parse_args(argv)
        validate_configuration(args)
        # Keep ownership across reconnect delays too. A duplicate Start exits
        # before it can consume the active companion's control requests.
        runner_lock = acquire_runner_lock()
        from alexa_bridge.relay_session import RelaySession
        voice_session = RelaySession(HERE / ".local/alexa/mac.json")
        if voice_session.start():
            print("Fantasy voice preview bridge is active for this watching session.", flush=True)
        elif voice_session.status != "disabled":
            print("Fantasy voice preview bridge is unavailable; fantasy scores remain active.", flush=True)
        if not args.no_tv_context:
            try:
                from context_session import ContextSession
                context_session = ContextSession(HERE, seconds=86400 if args.watch else args.seconds)
                if context_session.start():
                    print("Starting paired Apple TV program metadata for this watching session…", flush=True)
            except (OSError, ValueError):
                context_session = None
                print("Apple TV metadata is unavailable; fantasy scores remain active.", flush=True)
        control_thread = threading.Thread(
            target=poll_control_file,
            args=(HERE / ".local/control-request.json", launched_at_ns, commands, stop_event),
            daemon=True)
        control_thread.start()
        if not args.no_console:
            threading.Thread(target=read_console, args=(commands, stop_event),
                             daemon=True).start()
        if args.watch:
            print("Watch mode is active in this window. Keep this host awake and "
                  "on the TV's network. Type quit or press Ctrl-C to stop.", flush=True)
        backoff = 10
        while not stop_event.is_set():
            try:
                result = run(args, stop_event, commands, runner_lock,
                             context_session.current if context_session is not None else None)
            except ConfigurationError:
                raise
            except (OSError, RuntimeError, ValueError) as error:
                print("Overlay runner: " + str(error), file=sys.stderr, flush=True)
                result = 1
            if stop_event.is_set() or not args.watch:
                return result
            if result == 0:
                print("Bounded session completed. Renewing the overlay session…",
                      flush=True)
                backoff = 10
                delay = 1
            else:
                delay = backoff
                backoff = min(60, backoff * 2)
                print("TV session unavailable or ended with an error. Retrying "
                      "only " + args.tv + " in " + str(delay)
                      + " seconds. Type quit or press Ctrl-C to stop.", flush=True)
            deadline = time.monotonic() + delay
            while not stop_event.is_set() and time.monotonic() < deadline:
                stop_event.wait(min(1, max(0, deadline - time.monotonic())))
        return 0
    except KeyboardInterrupt:
        stop_event.set()
        print("Overlay watch stopped.", flush=True)
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print("Overlay runner: " + str(error), file=sys.stderr, flush=True)
        return 1
    finally:
        stop_event.set()
        if voice_session is not None:
            try:
                voice_session.close()
            except OSError:
                pass
        if context_session is not None:
            try:
                context_session.close()
            except OSError:
                pass
        if control_thread is not None:
            control_thread.join(timeout=1)
        if runner_lock is not None:
            runner_lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
