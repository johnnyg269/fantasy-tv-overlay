import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location("install_ci_sdk", Path(__file__).with_name("install_ci_sdk.py"))
sdk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdk)


class AndroidCiBootstrapTests(unittest.TestCase):
    def archive(self, directory, malicious=None):
        archive = Path(directory) / "tools.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("cmdline-tools/bin/sdkmanager", "#!/bin/sh\nexit 0\n")
            if malicious is not None:
                bundle.writestr(malicious, "invalid")
        return archive

    def test_checksum_rejects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.archive(directory)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            sdk.verify_archive(archive, archive.stat().st_size, digest)
            with self.assertRaises(ValueError):
                sdk.verify_archive(archive, archive.stat().st_size, "0" * 64)

    def test_safe_extraction_and_executable_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.archive(directory)
            target = Path(directory) / "output"
            sdk.safe_extract(archive, target)
            self.assertTrue((target / "cmdline-tools/bin/sdkmanager").stat().st_mode & 0o100)

    def test_path_traversal_absolute_and_foreign_roots_rejected(self):
        for name in ("../escaped", "/escaped", "cmdline-tools/../../escaped", "other/file", "C:/escaped", "cmdline-tools/..\\escaped"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    sdk.safe_extract(self.archive(directory, name), Path(directory) / "output")

    def test_license_flag_required_before_download(self):
        with patch.object(sdk, "download") as download, self.assertRaises(SystemExit):
            sdk.main([])
        download.assert_not_called()

    def test_export_only_expected_ci_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            env, path = Path(directory) / "env", Path(directory) / "path"
            root = Path(directory) / "sdk"
            with patch.dict(os.environ, {"GITHUB_ENV": str(env), "GITHUB_PATH": str(path)}):
                sdk.export_environment(root)
            self.assertIn("ANDROID_HOME=" + str(root), env.read_text())
            self.assertIn("ANDROID_SDK_ROOT=" + str(root), env.read_text())
            self.assertIn(str(root / "platform-tools"), path.read_text())


if __name__ == "__main__":
    unittest.main()
