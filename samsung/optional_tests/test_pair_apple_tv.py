"""Synthetic AirPlay pairing flow and private storage; no device or network."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pair_apple_tv as pair


class PairingTests(unittest.IsolatedAsyncioTestCase):
    def args(self, allow=True):
        return SimpleNamespace(host='192.0.2.60', name='Example Apple TV', timeout=2, allow_pairing=allow)

    async def test_pairing_requires_explicit_flag_and_interactive_hidden_pin(self):
        with patch.object(pair, 'storage_for', new_callable=AsyncMock) as storage:
            with self.assertRaises(pair.SetupError): await pair.pair_airplay(self.args(False))
            storage.assert_not_awaited()
        with patch.object(pair.sys.stdin, 'isatty', return_value=False), \
                patch.object(pair, 'storage_for', new_callable=AsyncMock) as storage:
            with self.assertRaises(pair.SetupError): await pair.pair_airplay(self.args())
            storage.assert_not_awaited()

    async def test_discovery_is_airplay_multicast_exact_target_and_never_unicast_wake(self):
        service = SimpleNamespace(credentials=None)
        config = SimpleNamespace(address='192.0.2.60', name='Example Apple TV', deep_sleep=False,
                                 get_service=lambda protocol: service)
        with patch.object(pair.pyatv, 'scan', new_callable=AsyncMock, return_value=[config]) as scan:
            found, found_service = await pair.discover_target(self.args(), Mock())
        self.assertIs(found, config)
        self.assertIs(found_service, service)
        self.assertEqual(scan.call_args.kwargs['protocol'], pair.Protocol.AirPlay)
        self.assertNotIn('hosts', scan.call_args.kwargs)
        config.deep_sleep = True
        with patch.object(pair.pyatv, 'scan', new_callable=AsyncMock, return_value=[config]):
            with self.assertRaises(pair.SetupError): await pair.discover_target(self.args(), Mock())

    async def test_pairing_saves_only_after_confirmation_and_always_closes(self):
        storage = SimpleNamespace(save=AsyncMock())
        pairing = SimpleNamespace(begin=AsyncMock(), finish=AsyncMock(), close=AsyncMock(),
                                  device_provides_pin=True, has_paired=True, pin=Mock())
        with patch.object(pair.sys.stdin, 'isatty', return_value=True), \
                patch.object(pair.sys.stderr, 'isatty', return_value=True), \
                patch.object(pair, 'storage_for', new_callable=AsyncMock, return_value=storage), \
                patch.object(pair, 'discover_target', new_callable=AsyncMock,
                             return_value=(Mock(), SimpleNamespace(credentials=None))), \
                patch.object(pair.pyatv, 'pair', new_callable=AsyncMock, return_value=pairing) as connect, \
                patch.object(pair, 'hidden_pin', return_value=1111), \
                patch.object(pair, 'save_device_config') as config:
            self.assertEqual(await pair.pair_airplay(self.args()), 0)
        self.assertEqual(connect.call_args.args[1], pair.Protocol.AirPlay)
        storage.save.assert_awaited_once()
        pairing.close.assert_awaited_once()
        config.assert_called_once()

    async def test_private_store_rejects_symlink_and_public_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            path = directory / 'storage.json'
            with patch.object(pair, 'PRIVATE_DIRECTORY', directory), patch.object(pair, 'STORAGE_PATH', path):
                store = pair.PrivateFileStorage(asyncio.get_running_loop())
                store._save_file({'fixture': True})
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(json.loads(store._read_file()), {'fixture': True})
                path.chmod(0o644)
                with self.assertRaises(pair.SetupError): store._read_file()
                target = directory / 'elsewhere.json'; target.write_text('{}')
                path.unlink(); path.symlink_to(target)
                with self.assertRaises(pair.SetupError): await store.load()

    async def test_existing_device_configuration_is_never_silently_retargeted(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(pair, 'PRIVATE_DIRECTORY', Path(folder)):
            pair.save_device_config(self.args())
            path = Path(folder) / 'apple-tv.json'
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            args = self.args(); args.host = '192.0.2.61'
            with self.assertRaises(pair.SetupError): pair.save_device_config(args)
            self.assertEqual(json.loads(path.read_text())['host'], '192.0.2.60')


if __name__ == '__main__': unittest.main()
