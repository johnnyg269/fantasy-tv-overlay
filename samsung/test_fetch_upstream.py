"""Pinned release extraction rejects traversal, links and unbounded archives."""
import importlib.util
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('fantasy_fetch_upstream',
                                             Path(__file__).parent / 'tools/fetch_upstream.py')
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


class UpstreamFetchTests(unittest.TestCase):
    def archive(self, member):
        return Mock(getmembers=lambda: [member])

    def test_traversal_and_absolute_paths_are_rejected(self):
        for name in ('../elsewhere', '/tmp/elsewhere', 'folder/../../elsewhere', 'folder\\elsewhere'):
            member = tarfile.TarInfo(name); member.size = 1
            with self.subTest(name=name), self.assertRaises(ValueError):
                fetch.safe_members(self.archive(member))

    def test_symlinks_hardlinks_and_device_nodes_are_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE):
            member = tarfile.TarInfo('release/entry'); member.type = kind
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                fetch.safe_members(self.archive(member))

    def test_ordinary_relative_file_is_allowed_but_size_is_bounded(self):
        member = tarfile.TarInfo('release/source/file.py'); member.size = 20
        self.assertEqual(fetch.safe_members(self.archive(member)), [member])
        member.size = fetch.MAX_UNPACKED + 1
        with self.assertRaises(ValueError): fetch.safe_members(self.archive(member))

    def test_unpinned_installed_module_is_rejected_without_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source/src/samsung_tv_root/sdb.py'
            source.parent.mkdir(parents=True)
            source.write_text('raise RuntimeError("must not execute")')
            (root / 'samsung-tv-root').write_text('not executable')
            with self.assertRaises(ValueError): fetch.check_install(root)


if __name__ == '__main__': unittest.main()
