"""Entry point for an Alexa-hosted Python custom skill. Handler: lambda_handler."""

import json
from pathlib import Path

from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.serialize import DefaultSerializer
from ask_sdk_core.skill_builder import SkillBuilder

from skill_logic import (SETUP, UNAUTHORIZED, authorized, request_preview,
                         response, validate_config)

_handler = None
_config = None


class VoiceHandler(AbstractRequestHandler):
    def __init__(self, config):
        self.config = config

    def can_handle(self, handler_input):
        return True

    def handle(self, handler_input):
        envelope = DefaultSerializer().serialize(handler_input.request_envelope)
        request = envelope["request"]
        request_type = request["type"]
        intent = request.get("intent", {}).get("name")
        if request_type == "LaunchRequest" or (request_type == "IntentRequest" and intent == "ShowScoreIntent"):
            speech = request_preview(envelope, self.config)
        elif request_type == "SessionEndedRequest":
            return handler_input.response_builder.set_should_end_session(True).response
        elif intent in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
            speech = "Okay."
        else:
            speech = "Say show my score to request the fantasy score popup on your TV."
        return handler_input.response_builder.speak(speech).set_should_end_session(True).response


def build_handler(config):
    validate_config(config)
    builder = SkillBuilder()
    # ASK SDK enforces the application ID before dispatching any request handler.
    builder.skill_id = config["expected_skill_id"]
    builder.add_request_handler(VoiceHandler(config))
    return builder.lambda_handler()


def lambda_handler(event, context):
    global _handler, _config
    try:
        if _config is None:
            with (Path(__file__).parent / "private_config.json").open("r", encoding="utf-8") as stream:
                _config = validate_config(json.load(stream))
        if not authorized(event, _config):
            return response(UNAUTHORIZED)
        if _handler is None:
            _handler = build_handler(_config)
        return _handler(event, context)
    except Exception:
        # Do not log the request envelope: it contains account IDs and API tokens.
        # This also avoids claiming that the TV displayed anything after a timeout.
        return response(SETUP)
