"""TV metadata is optional scene enrichment, never a fantasy scoring event."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from controller import ScoreController
from test_controller import score_payload


class ContextIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.payload = score_payload()
        for league in self.payload['leagues']:
            league['me']['players'] = [{'slot': 'QB', 'name': 'Test Starter',
                                        'bench': False, 'pts': 10, 'proj': 15}]
        self.context = {"available": True, "app": "YouTube TV",
                        "title": "Football Night in America", "matchedGameId": None,
                        "confidence": "unknown"}
        self.controller = ScoreController(
            Path(self.folder.name) / 'state.json', clock=lambda: 1000,
            fetcher=lambda _: deepcopy(self.payload),
            context_provider=lambda: deepcopy(self.context))

    def tearDown(self):
        self.folder.cleanup()

    def test_context_is_visible_in_sidebar_without_creating_score_alert(self):
        state = self.controller.tick()
        self.assertFalse(state['visible'])
        self.assertNotIn('alertId', state)
        self.assertEqual(state['tvContext'], self.context)
        texts = [obj.get('text', '') for sidebar in state['sidebarScenes']
                 for obj in sidebar['scene']['objects']]
        self.assertTrue(any('Football Night in America' in text for text in texts))
        self.assertNotIn('tvContext', self.payload)
        self.assertNotIn('tvContext', self.controller.scores)

    def test_metadata_changes_do_not_trigger_a_score_popup(self):
        self.controller.tick()
        self.context.update(title='Chiefs at Seahawks', matchedGameId='game-1',
                            confidence='exact-title-pair')
        state = self.controller.tick(force_publish=True)
        self.assertFalse(state['visible'])
        self.assertNotIn('alertId', state)
        self.assertEqual(state['tvContext']['matchedGameId'], 'game-1')

    def test_provider_failure_clears_context_and_preserves_score_health(self):
        self.controller.tick()
        def failed():
            raise OSError('metadata unavailable')
        self.controller.context_provider = failed
        state = self.controller.tick(force_publish=True)
        self.assertEqual(state['tvContext'], {'available': False})
        self.assertTrue(state['feed']['available'])
        self.assertIsNone(self.controller.last_error)
        self.assertFalse(state['visible'])


if __name__ == '__main__':
    unittest.main()
