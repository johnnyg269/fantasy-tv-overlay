"""Optional one-watch relay lifetime. Never invokes Funnel or changes networking."""

import os
from pathlib import Path
import selectors
import subprocess
import time

try:
    from .private_config import load_private_json
except ImportError:
    from private_config import load_private_json

READY_MESSAGE = b"Fantasy voice relay listening on 127.0.0.1:8767; Funnel is not enabled by this program."


class RelaySession:
    """Create once outside the TV runner's renewal loop, close in its outer finally.

    Missing configuration is an ordinary disabled state. start() is idempotent;
    after one actual launch attempt, it never relaunches during the same watch.
    Failed startup does not prevent the existing overlay from running.
    """

    def __init__(self, config_path, relay_script=None, python_executable="/usr/bin/python3",
                 startup_timeout=3.0):
        self.config_path = Path(config_path)
        self.relay_script = Path(relay_script) if relay_script else Path(__file__).with_name("relay.py")
        self.python_executable = str(python_executable)
        self.startup_timeout = float(startup_timeout)
        self.process = None
        self.status = "disabled"
        self._attempted = False

    def start(self):
        if self._attempted:
            if self.process is not None and self.process.poll() is None and self.status == "ready":
                return True
            if self.status == "ready":
                self.status = "exited"
            return False
        if not self.config_path.is_file():
            self.status = "disabled"
            return False
        self._attempted = True
        try:
            load_private_json(self.config_path)
            self.process = subprocess.Popen(
                [self.python_executable, "-u", str(self.relay_script), "--config", str(self.config_path)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=0, close_fds=True, start_new_session=True)
            deadline = time.monotonic() + self.startup_timeout
            pending = b""
            with selectors.DefaultSelector() as selector:
                os.set_blocking(self.process.stdout.fileno(), False)
                selector.register(self.process.stdout, selectors.EVENT_READ)
                while time.monotonic() < deadline:
                    if self.process.poll() is not None:
                        break
                    for key, _mask in selector.select(timeout=min(.1, max(0, deadline - time.monotonic()))):
                        block = os.read(key.fileobj.fileno(), 1024)
                        pending = (pending + block)[-4096:]
                        if READY_MESSAGE + b"\n" in pending and self.process.poll() is None:
                            self.status = "ready"
                            return True
            failure = "start_failed" if self.process.poll() is not None else "start_timeout"
        except (OSError, ValueError):
            failure = "start_failed"
        self.close()
        self.status = failure
        return False

    def close(self):
        child, self.process = self.process, None
        if child is not None:
            try:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=1)
            finally:
                if child.stdout is not None:
                    child.stdout.close()
        self.status = "stopped" if self._attempted else "disabled"

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
