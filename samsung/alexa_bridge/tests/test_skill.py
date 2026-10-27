from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import time
import unittest
import urllib.error
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "lambda"))

import lambda_function
from skill_logic import (QUEUED, SETUP, UNAUTHORIZED, UNCONFIRMED,
                         request_preview, validate_config)
from voice_protocol import verify

NOW = int(time.time())
CONFIG = {"expected_skill_id": "amzn1.ask.skill.unit-test", "allowed_user_id": "amzn1.ask.account.unit-test",
          "relay_url": "https://fixture.example.ts.net/fantasy/preview", "secret_hex": "a1" * 32}


def event(request_type="LaunchRequest", intent=None):
    application = {"applicationId": CONFIG["expected_skill_id"]}
    user = {"userId": CONFIG["allowed_user_id"]}
    request = {"type": request_type, "requestId": "request-12345678", "locale": "en-US",
               "timestamp": datetime.fromtimestamp(NOW, timezone.utc).isoformat()}
    if intent:
        request["intent"] = {"name": intent, "confirmationStatus": "NONE", "slots": {}}
    return {"version": "1.0", "session": {"new": True, "sessionId": "session.unit-test",
            "application": dict(application), "user": dict(user), "attributes": {}},
            "context": {"System": {"application": dict(application), "user": dict(user),
                        "device": {"deviceId": "fixture", "supportedInterfaces": {}}}},
            "request": request}


class FakeResponse(io.BytesIO):
    def __init__(self, code=202, status="queued"):
        super().__init__(json.dumps({"status": status}).encode())
        self.status = code


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.opener = Mock()
        self.opener.open.return_value = FakeResponse()
        lambda_function._config = dict(CONFIG)
        lambda_function._handler = None

    def tearDown(self):
        lambda_function._config = None
        lambda_function._handler = None

    def test_sdk_launch_queues_signed_fixed_preview(self):
        with patch("skill_logic.urllib.request.build_opener", return_value=self.opener):
            result = lambda_function.lambda_handler(event(), None)
        self.assertIn(QUEUED, result["response"]["outputSpeech"]["ssml"])
        self.assertTrue(result["response"]["shouldEndSession"])
        request = self.opener.open.call_args[0][0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, CONFIG["relay_url"])
        signed = request.get_header("X-fantasy-signature")
        payload = verify(request.data, signed, bytes.fromhex(CONFIG["secret_hex"]), int(time.time()))
        self.assertEqual(payload["action"], "preview")
        self.assertEqual(self.opener.open.call_args[1]["timeout"], 4)

    def test_show_score_intent_queues(self):
        with patch("skill_logic.urllib.request.build_opener", return_value=self.opener):
            result = lambda_function.lambda_handler(event("IntentRequest", "ShowScoreIntent"), None)
        self.assertIn(QUEUED, result["response"]["outputSpeech"]["ssml"])
        self.opener.open.assert_called_once()

    def test_wrong_skill_and_household_are_rejected_before_http(self):
        for section, field in (("application", "applicationId"), ("user", "userId")):
            envelope = event()
            envelope["context"]["System"][section][field] = "not-authorized"
            with patch("skill_logic.urllib.request.build_opener", return_value=self.opener):
                result = lambda_function.lambda_handler(envelope, None)
            self.assertEqual(result["response"]["outputSpeech"]["text"], UNAUTHORIZED)
        self.opener.open.assert_not_called()

    def test_mismatched_session_identity_is_also_rejected(self):
        envelope = event()
        envelope["session"]["user"]["userId"] = "other-user"
        self.assertEqual(request_preview(envelope, CONFIG, self.opener, lambda: NOW), UNAUTHORIZED)
        self.opener.open.assert_not_called()

    def test_ask_sdk_itself_enforces_expected_skill_id(self):
        envelope = event()
        envelope["session"]["application"]["applicationId"] = "amzn1.ask.skill.other"
        envelope["context"]["System"]["application"]["applicationId"] = "amzn1.ask.skill.other"
        with self.assertRaises(Exception):
            lambda_function.build_handler(CONFIG)(envelope, None)
        self.opener.open.assert_not_called()

    def test_help_stop_and_fallback_never_call_relay(self):
        with patch("skill_logic.urllib.request.build_opener", return_value=self.opener):
            for intent in ("AMAZON.HelpIntent", "AMAZON.StopIntent", "AMAZON.FallbackIntent"):
                result = lambda_function.lambda_handler(event("IntentRequest", intent), None)
                self.assertTrue(result["response"]["shouldEndSession"])
        self.opener.open.assert_not_called()

    def test_old_alexa_envelope_is_not_resigned_and_sent(self):
        envelope = event()
        envelope["request"]["timestamp"] = "2000-01-01T00:00:00Z"
        self.assertEqual(request_preview(envelope, CONFIG, self.opener, lambda: NOW), UNCONFIRMED)
        self.opener.open.assert_not_called()

    def test_offline_timeout_and_ambiguous_ack_never_claim_tv_success(self):
        self.opener.open.side_effect = TimeoutError()
        self.assertEqual(request_preview(event(), CONFIG, self.opener, lambda: NOW), UNCONFIRMED)
        self.opener.open.side_effect = None
        self.opener.open.return_value = FakeResponse(202, "anything_else")
        self.assertEqual(request_preview(event(), CONFIG, self.opener, lambda: NOW), UNCONFIRMED)

    def test_auth_failure_reports_setup_and_duplicate_ack_reports_request_only(self):
        self.opener.open.side_effect = urllib.error.HTTPError(CONFIG["relay_url"], 401, "rejected", {}, None)
        self.assertEqual(request_preview(event(), CONFIG, self.opener, lambda: NOW), SETUP)
        self.opener.open.side_effect = None
        self.opener.open.return_value = FakeResponse(200, "duplicate")
        self.assertEqual(request_preview(event(), CONFIG, self.opener, lambda: NOW), QUEUED)

    def test_private_configuration_requires_https_exact_path_and_identity(self):
        for changes in ({"relay_url": "http://fixture.example.ts.net/fantasy/preview"},
                        {"relay_url": "https://example.com/fantasy/preview"},
                        {"relay_url": "https://fixture.example.ts.net:8443/fantasy/preview"},
                        {"relay_url": "https://fixture.example.ts.net/fantasy/preview?key=x"},
                        {"secret_hex": ""}, {"allowed_user_id": ""}):
            with self.assertRaises(ValueError):
                validate_config(dict(CONFIG, **changes))


if __name__ == "__main__":
    unittest.main()
