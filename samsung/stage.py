#!/usr/bin/env python3
"""Stage only this project's locally built renderer/assets on one explicit TV."""

import hashlib
from pathlib import Path
import re
import shlex
import sys

import run_tv


BUILD_NAMES = ("FantasyOverlay.dll", "FantasyOverlay.runtimeconfig.json",
               "FantasyOverlay.deps.json")


def verify_build(build):
    build = Path(build).expanduser().resolve(strict=True)
    files = []
    for name in BUILD_NAMES:
        path = build / name
        if not path.is_file() or not 1 <= path.stat().st_size <= 8 * 1024 * 1024:
            raise ValueError("Build the renderer locally before staging: missing/oversized " + name)
        files.append((name, path, path.read_bytes()))
    if files[0][2][:2] != b"MZ":
        raise ValueError("Renderer DLL is not a managed PE assembly")
    return files


def main(argv=None):
    parser = run_tv.build_parser()
    parser.description = __doc__
    parser.add_argument("--build", type=Path, default=run_tv.HERE / ".local/build")
    args = parser.parse_args(argv)
    try:
        run_tv.validate_configuration(args, require_endpoint=False)
        files = verify_build(args.build)
        client = run_tv.load_sdb_client(args.sdb_module)(args.sdb.resolve(), args.tv, timeout=15)
        run_tv.verify_model(client, args.model)
        transport = run_tv.TVTransport(client, args.callback_host)
        stage = shlex.quote(run_tv.STAGE)
        # Refuse an in-use assembly rather than replacing the active process.
        output = transport.capture(
            "mkdir -p " + stage + " && cd " + stage + " && "
            "if [ -r active.pid ]; then p=$(cat active.pid); "
            "case \"$p\" in ''|*[!0-9]*) p=;; esac; "
            "if [ -n \"$p\" ] && [ -r /proc/\"$p\"/cmdline ] && "
            "tr '\\000' '\\n' < /proc/\"$p\"/cmdline | grep -Fx "
            + shlex.quote(run_tv.STAGE + "/FantasyOverlay.dll")
            + " >/dev/null; then echo renderer_still_running; exit 1; fi; fi")
        for name, source, content in files:
            # Deterministic file names, fixed directory, checksum after each push.
            with transport.lock:
                client.push(source, Path(run_tv.STAGE + "/" + name + ".next"))
            digest = hashlib.sha256(content).hexdigest()
            output = transport.capture("cd " + stage + " && sha256sum " + name + ".next")
            if not re.search(r"(?m)^" + digest + r"  " + re.escape(name) + r"\.next$", output):
                raise ValueError("TV checksum did not match " + name)
            transport.capture("cd " + stage + " && mv " + name + ".next " + name)
        run_tv.stage_score_font(client, transport)
        run_tv.stage_ui_assets(client, transport)
        print("Renderer and licensed assets staged; no Home/startup or system files changed.")
        print("Start run_tv.py for a bounded visible session, then verify HDMI/apps, sound and remote on this TV.")
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print("Staging stopped: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
