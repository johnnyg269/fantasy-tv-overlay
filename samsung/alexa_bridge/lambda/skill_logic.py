"""Alexa behavior and signed HTTPS call; no cloud credentials or TV controls."""

from datetime import datetime, timezone
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from voice_protocol import encode_request, make_request, secret_bytes, signature

QUEUED = "Your fantasy score popup was requested."
UNCONFIRMED = "I couldn't confirm the request. Check that your Mac and fantasy overlay are running."
SETUP = "The fantasy voice connection needs setup."
UNAUTHORIZED = "This fantasy overlay isn't enabled for this Alexa account."


def validate_config(config):
    required = {"expected_skill_id", "allowed_user_id", "relay_url", "secret_hex"}
    if not isinstance(config, dict) or set(config) != required:
        raise ValueError("Invalid private configuration")
    if not str(config["expected_skill_id"]).startswith("amzn1.ask.skill."):
        raise ValueError("Configure the expected skill ID")
    if not str(config["allowed_user_id"]).startswith("amzn1.ask.account."):
        raise ValueError("Configure the allowed household account ID")
    secret_bytes(config["secret_hex"])
    url = urllib.parse.urlsplit(config["relay_url"])
    if (url.scheme != "https" or not url.hostname or not url.hostname.endswith(".ts.net")
            or url.port not in (None, 443) or url.username or url.password
            or url.path != "/fantasy/preview" or url.query or url.fragment):
        raise ValueError("Configure the HTTPS Funnel preview URL on port 443")
    return config


def authorized(event, config):
    try:
        system = event["context"]["System"]
        if (system["application"]["applicationId"] != config["expected_skill_id"]
                or system["user"]["userId"] != config["allowed_user_id"]):
            return False
        session = event.get("session")
        if session is not None:
            if (session["application"]["applicationId"] != config["expected_skill_id"]
                    or session["user"]["userId"] != config["allowed_user_id"]):
                return False
        return True
    except (KeyError, TypeError):
        return False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the signed request to a different service or URL.
        return None


def request_preview(event, config, opener=None, clock=time.time):
    if not authorized(event, config):
        return UNAUTHORIZED
    now = int(clock())
    try:
        request = event["request"]
        received = datetime.fromisoformat(request["timestamp"].replace("Z", "+00:00"))
        if received.tzinfo is None or not -5 <= now - received.timestamp() <= 150:
            return UNCONFIRMED
        payload = make_request(request["requestId"], now)
        body = encode_request(payload)
        headers = {"Content-Type": "application/json",
                   "X-Fantasy-Signature": signature(payload, secret_bytes(config["secret_hex"]))}
        http_request = urllib.request.Request(config["relay_url"], data=body,
                                              headers=headers, method="POST")
        opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(http_request, timeout=4) as response:
            raw = response.read(1025)
            if len(raw) > 1024:
                return UNCONFIRMED
            reply = json.loads(raw.decode("utf-8"))
            if (response.status, reply.get("status")) in ((202, "queued"), (200, "duplicate")):
                return QUEUED
            return UNCONFIRMED
    except urllib.error.HTTPError as error:
        return SETUP if error.code in (400, 401, 403, 404) else UNCONFIRMED
    except (OSError, ValueError, KeyError, TypeError):
        return UNCONFIRMED


def response(speech=None):
    result = {"shouldEndSession": True}
    if speech:
        result["outputSpeech"] = {"type": "PlainText", "text": speech}
    return {"version": "1.0", "response": result}
