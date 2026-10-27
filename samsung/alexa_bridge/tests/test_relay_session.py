import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from relay_session import READY_MESSAGE, RelaySession


class RelaySessionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.config = self.root / "fixture.json"
        self.config.write_text(json.dumps({"fixture": True}))
        self.config.chmod(0o600)

    def tearDown(self):
        self.folder.cleanup()

    def child_script(self, source):
        script = self.root / "fixture_child.py"
        script.write_text(source)
        return script

    def test_missing_configuration_does_not_launch_anything(self):
        session = RelaySession(self.root / "missing.json")
        with patch("relay_session.subprocess.Popen") as popen:
            self.assertFalse(session.start())
        self.assertEqual(session.status, "disabled")
        popen.assert_not_called()

    def test_public_configuration_is_rejected_without_launch(self):
        self.config.chmod(0o644)
        session = RelaySession(self.config)
        with patch("relay_session.subprocess.Popen") as popen:
            self.assertFalse(session.start())
        self.assertEqual(session.status, "start_failed")
        popen.assert_not_called()

    def test_one_child_across_renewals_and_bounded_cleanup(self):
        script = self.child_script("import time\nprint(%r, flush=True)\nwhile True: time.sleep(.1)\n" % READY_MESSAGE.decode())
        session = RelaySession(self.config, relay_script=script)
        try:
            self.assertTrue(session.start())
            child = session.process
            self.assertEqual(child.args[0], "/usr/bin/python3")
            self.assertTrue(session.start())
            self.assertIs(session.process, child)
            self.assertNotIn("funnel", child.args)
        finally:
            session.close()
        self.assertIsNotNone(child.poll())
        self.assertFalse(session.start())
        self.assertEqual(session.status, "stopped")

    def test_startup_timeout_cleans_child_without_logging_output(self):
        script = self.child_script("import time\ntime.sleep(20)\n")
        session = RelaySession(self.config, relay_script=script, startup_timeout=.15)
        start = time.monotonic()
        self.assertFalse(session.start())
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual(session.status, "start_timeout")
        self.assertIsNone(session.process)

    def test_early_child_failure_does_not_restart_during_watch(self):
        script = self.child_script("raise SystemExit(2)\n")
        session = RelaySession(self.config, relay_script=script)
        self.assertFalse(session.start())
        self.assertEqual(session.status, "start_failed")
        with patch("relay_session.subprocess.Popen") as popen:
            self.assertFalse(session.start())
        popen.assert_not_called()

    def test_context_exit_closes_only_owned_child(self):
        script = self.child_script("import time\nprint(%r, flush=True)\ntime.sleep(20)\n" % READY_MESSAGE.decode())
        with RelaySession(self.config, relay_script=script) as session:
            child = session.process
            self.assertEqual(session.status, "ready")
        self.assertIsNotNone(child.poll())
        self.assertEqual(session.status, "stopped")


if __name__ == "__main__":
    unittest.main()
