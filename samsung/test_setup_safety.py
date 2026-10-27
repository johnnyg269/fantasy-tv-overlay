"""Root prerequisites and staging guardrails; no TV is contacted."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import run_tv
import stage


class SetupSafetyTests(unittest.TestCase):
    def receipt(self):
        return {"host": "192.0.2.50", "authenticated": True, "uid": 0, "euid": 0,
                "runtime": "6.0.9", "staging_cleaned": True, "system_files_unchanged": True}

    def test_missing_configuration_stops_before_connection(self):
        args = run_tv.build_parser().parse_args([])
        with patch("run_tv.load_sdb_client") as loader, self.assertRaises(run_tv.ConfigurationError):
            run_tv.run(args)
        loader.assert_not_called()

    def test_no_default_household_target(self):
        with patch.dict(os.environ, {}, clear=True):
            args = run_tv.build_parser().parse_args([])
        self.assertIsNone(args.tv)
        self.assertIsNone(args.callback_host)
        self.assertIsNone(args.model)
        self.assertIsNone(args.endpoint)
        self.assertFalse(args.acknowledge_root_risk)

    def test_authenticated_receipt_requires_target_runtime_and_cleanups(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "root.json"
            path.write_text(json.dumps(self.receipt())); path.chmod(0o600)
            self.assertTrue(run_tv.validate_root_receipt(path, "192.0.2.50")["authenticated"])
            for field, value in (("host", "192.0.2.51"), ("authenticated", False),
                                 ("uid", 1), ("euid", 1), ("runtime", "3.1"),
                                 ("staging_cleaned", False), ("system_files_unchanged", False)):
                receipt = self.receipt(); receipt[field] = value
                path.write_text(json.dumps(receipt))
                with self.subTest(field=field), self.assertRaises(run_tv.ConfigurationError):
                    run_tv.validate_root_receipt(path, "192.0.2.50")

    def test_public_or_symlink_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "root.json"; path.write_text(json.dumps(self.receipt()))
            path.chmod(0o644)
            with self.assertRaises(run_tv.ConfigurationError):
                run_tv.validate_root_receipt(path, "192.0.2.50")
            path.chmod(0o600)
            link = Path(folder) / "alias.json"; link.symlink_to(path)
            with self.assertRaises(run_tv.ConfigurationError):
                run_tv.validate_root_receipt(link, "192.0.2.50")

    def test_boolean_zero_is_not_integer_root_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "root.json"
            receipt = self.receipt(); receipt["uid"] = False
            path.write_text(json.dumps(receipt)); path.chmod(0o600)
            with self.assertRaises(run_tv.ConfigurationError):
                run_tv.validate_root_receipt(path, "192.0.2.50")

    def test_stale_future_and_oversized_receipts_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "root.json"; path.write_text(json.dumps(self.receipt())); path.chmod(0o600)
            now = time.time()
            for mtime in (now - 8 * 86400, now + 60):
                os.utime(path, (mtime, mtime))
                with self.assertRaises(run_tv.ConfigurationError):
                    run_tv.validate_root_receipt(path, "192.0.2.50", now)
            path.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
            with self.assertRaises(run_tv.ConfigurationError):
                run_tv.validate_root_receipt(path, "192.0.2.50")

    def test_model_mismatch_stops_without_a_root_command(self):
        client = Mock(serial="192.0.2.50:26101")
        client.run.return_value.stdout = "192.0.2.50:26101 device DIFFERENTMODEL\n"
        with self.assertRaises(run_tv.ConfigurationError):
            run_tv.verify_model(client, "EXPECTEDMODEL")
        client.capture.assert_not_called()
        client.push.assert_not_called()

    def test_unpinned_transport_is_never_imported(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "sdb.py"
            source.write_text("raise RuntimeError('executed')")
            with self.assertRaises(run_tv.ConfigurationError):
                run_tv.load_sdb_client(source)

    def test_stage_requires_managed_local_build(self):
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder)
            for name in stage.BUILD_NAMES: (build / name).write_bytes(b"wrong")
            with self.assertRaises(ValueError): stage.verify_build(build)

    def test_root_start_and_kill_are_specific_to_overlay_assembly(self):
        import base64
        import shlex
        command = run_tv.renderer_command(30, "p-test.pid", "s-test.json")
        script = base64.b64decode(shlex.split(command)[2]).decode()
        self.assertIn("grep -Fx", script)
        self.assertIn(run_tv.STAGE + "/FantasyOverlay.dll", script)
        self.assertNotIn("killall", script)
        self.assertNotIn("systemctl", script)
        self.assertNotIn("/etc/passwd", script)
        self.assertIn("--stale-seconds 30", script)
        for font in run_tv.FONT_NAMES: self.assertIn(font, script)


if __name__ == "__main__":
    unittest.main()
