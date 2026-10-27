"""The optional metadata subprocess is parent-owned and never auto-restarted."""
from pathlib import Path
import os
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from context_session import ContextSession


class ContextSessionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = Path(self.folder.name)
        self.session = ContextSession(self.app, seconds=60)

    def tearDown(self):
        self.session.close()
        self.folder.cleanup()

    def provision(self):
        for name in ('.local/apple-tv-venv/bin/python', '.local/apple-tv-storage.json',
                     'apple_tv_context.py'):
            path = self.app / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        config = self.app / '.local/apple-tv.json'
        config.write_text(json.dumps({'host': '192.0.2.60', 'name': 'Example Apple TV'}))
        os.chmod(config, 0o600)

    def test_missing_optional_runtime_starts_no_process(self):
        with patch('context_session.subprocess.Popen') as launch:
            self.assertFalse(self.session.start())
            launch.assert_not_called()
        self.assertEqual(self.session.current(), {'available': False})

    def test_exited_helper_is_not_restarted_and_cannot_replay_cache(self):
        self.provision()
        process = Mock()
        process.poll.return_value = 0
        with patch('context_session.subprocess.Popen', return_value=process) as launch:
            self.assertTrue(self.session.start())
            self.assertIn('--active-session', launch.call_args.args[0])
            self.assertEqual(self.session.current(), {'available': False})
            self.assertEqual(self.session.current(), {'available': False})
            self.assertEqual(launch.call_count, 1)

    def test_close_terminates_owned_process_and_invalidates_metadata(self):
        self.provision()
        process = Mock()
        process.poll.return_value = None
        with patch('context_session.subprocess.Popen', return_value=process):
            self.assertTrue(self.session.start())
            self.session.close()
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=25)
        self.assertFalse(self.session.current()['available'])
        process.poll.return_value = 0


if __name__ == '__main__':
    unittest.main()
