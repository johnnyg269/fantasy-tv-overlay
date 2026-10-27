"""Parent-owned optional Apple TV metadata process for one watching session."""
import os
from pathlib import Path
import subprocess
import time

from controller import atomic_write
from tv_context import read_context_cache
from alexa_bridge.private_config import load_private_json
import ipaddress


class ContextSession:
    def __init__(self, app_folder, seconds=28800):
        self.folder = Path(app_folder)
        self.local = self.folder / '.local'
        self.cache = self.local / 'tv-context.json'
        self.seconds = seconds
        self.process = None
        self.log = None

    def start(self):
        python = self.local / 'apple-tv-venv/bin/python'
        storage = self.local / 'apple-tv-storage.json'
        helper = self.folder / 'apple_tv_context.py'
        config_path = self.local / 'apple-tv.json'
        if not all(path.is_file() for path in (python, storage, helper, config_path)):
            return False
        config = load_private_json(config_path)
        host = str(ipaddress.IPv4Address(config.get('host')))
        name = config.get('name')
        if (set(config) != {'host', 'name'} or not isinstance(name, str)
                or not 1 <= len(name) <= 100 or not name.isprintable()):
            raise ValueError('Apple TV configuration requires your own host and exact device name')
        self.local.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._clear('starting')
        self.log = (self.local / 'apple-tv-context.log').open('a', encoding='utf-8')
        os.chmod(str(self.local / 'apple-tv-context.log'), 0o600)
        try:
            self.process = subprocess.Popen(
                [str(python), str(helper), '--storage', str(storage),
                 '--cache', str(self.cache), '--host', host,
                 '--name', name, '--seconds', str(self.seconds), '--active-session'],
                stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT,
                start_new_session=True)
        except OSError:
            self.log.close()
            self.log = None
            self._clear('unavailable')
            return False
        return True

    def current(self):
        # No automatic process restart: reconnecting can wake an Apple TV.
        if self.process is None or self.process.poll() is not None:
            return {'available': False}
        return read_context_cache(self.cache)

    def _clear(self, status):
        atomic_write(self.cache, {'available': False, 'capturedAt': time.time(),
                                 'status': status, 'app': None, 'title': None,
                                 'matchedGameId': None, 'confidence': 'unknown'})
        os.chmod(str(self.cache), 0o600)

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if self.log is not None:
            self.log.close()
            self.log = None
        if self.local.exists():
            self._clear('stopped')
