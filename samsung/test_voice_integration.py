"""Voice child follows the entire watch, including renewal and failure cleanup."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_tv


class VoiceIntegrationTests(unittest.TestCase):
    def test_one_voice_session_across_renderer_renewal_and_stop(self):
        calls = []

        def renderer(args, stop_event, *unused):
            calls.append(True)
            if len(calls) == 2:
                stop_event.set()
            return 0

        with tempfile.TemporaryDirectory() as folder, \
                patch.object(run_tv, "HERE", Path(folder)), \
                patch.object(run_tv, "validate_configuration"), \
                patch.object(run_tv, "run", side_effect=renderer), \
                patch("alexa_bridge.relay_session.RelaySession") as voice, \
                contextlib.redirect_stdout(io.StringIO()):
            voice.return_value.start.return_value = True
            self.assertEqual(run_tv.main(["--watch", "--no-console", "--no-tv-context"]), 0)
        self.assertEqual(len(calls), 2)
        voice.assert_called_once_with(Path(folder) / ".local/alexa/mac.json")
        voice.return_value.start.assert_called_once_with()
        voice.return_value.close.assert_called_once_with()

    def test_configuration_failure_closes_started_voice_child(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(run_tv, "HERE", Path(folder)), \
                patch.object(run_tv, "validate_configuration"), \
                patch.object(run_tv, "run", side_effect=run_tv.ConfigurationError("fixture")), \
                patch("alexa_bridge.relay_session.RelaySession") as voice, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            voice.return_value.start.return_value = True
            self.assertEqual(run_tv.main(["--no-console", "--no-tv-context"]), 1)
        voice.return_value.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
