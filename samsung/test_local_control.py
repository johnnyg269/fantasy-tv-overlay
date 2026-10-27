"""Local companion-control checks; no TV, network, or subprocess is started."""

import json
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import run_tv
import send_control


class LocalControlTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "control-request.json"

    def tearDown(self):
        self.folder.cleanup()

    def test_atomic_allowlisted_request_is_consumed_and_deleted(self):
        launched = time.time_ns()
        request = send_control.write_request("quit", self.path)
        self.assertEqual(json.loads(self.path.read_text()), request)
        self.assertGreaterEqual(request["issuedAtNS"], launched)
        self.assertEqual(send_control.take_request(self.path, launched), request)
        self.assertFalse(self.path.exists())
        self.assertEqual(list(Path(self.folder.name).iterdir()), [])

    def test_earlier_launch_quit_is_never_executed(self):
        request = send_control.write_request("quit", self.path)
        self.assertIsNone(send_control.take_request(self.path, request["issuedAtNS"] + 1))
        self.assertFalse(self.path.exists())

    def test_unknown_or_malformed_commands_are_not_executed(self):
        with self.assertRaises(ValueError):
            send_control.write_request("quit; anything", self.path)
        for request in (
            {"command": ["quit"], "nonce": "a", "issuedAtNS": 20},
            {"command": "quit", "nonce": "a", "issuedAtNS": True},
            {"command": "quit", "nonce": "", "issuedAtNS": 20},
            {"command": "unlisted", "nonce": "a", "issuedAtNS": 20},
        ):
            self.path.write_text(json.dumps(request))
            self.assertIsNone(send_control.take_request(self.path, 10))

    def test_newer_atomic_request_is_not_deleted_with_claimed_older_one(self):
        send_control.write_request("show", self.path)
        real_loads = json.loads

        def load_and_replace(content):
            send_control.write_request("quit", self.path)
            return real_loads(content)

        with patch.object(send_control.json, "loads", load_and_replace):
            self.assertEqual(send_control.take_request(self.path, 0)["command"], "show")
        self.assertTrue(self.path.exists())
        self.assertEqual(send_control.take_request(self.path, 0)["command"], "quit")

    def test_poll_thread_quit_sets_shared_stop_without_enqueuing_shell(self):
        launched = time.time_ns()
        send_control.write_request("quit", self.path)
        commands, stop = queue.Queue(), threading.Event()
        worker = threading.Thread(target=run_tv.poll_control_file,
                                  args=(self.path, launched, commands, stop))
        worker.start()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertTrue(stop.is_set())
        self.assertTrue(commands.empty())

    def test_nonquit_request_is_delivered_once_to_existing_command_queue(self):
        launched = time.time_ns()
        send_control.write_request("preview", self.path)
        commands, stop = queue.Queue(), threading.Event()
        worker = threading.Thread(target=run_tv.poll_control_file,
                                  args=(self.path, launched, commands, stop))
        worker.start()
        try:
            self.assertEqual(commands.get(timeout=2), "preview")
            self.assertTrue(commands.empty())
        finally:
            stop.set()
            worker.join(timeout=2)

    def test_an_existing_runner_lock_is_fatal_without_creating_control_threads(self):
        with patch.object(run_tv, "HERE", Path(self.folder.name)):
            existing = run_tv.acquire_runner_lock()
            try:
                with self.assertRaises(run_tv.ConfigurationError):
                    run_tv.acquire_runner_lock()
                with patch.object(run_tv, "validate_configuration"), \
                        patch.object(run_tv.threading, "Thread") as thread:
                    self.assertEqual(run_tv.main(["--watch", "--no-console"]), 1)
                    thread.assert_not_called()
            finally:
                existing.close()


if __name__ == "__main__":
    unittest.main()
