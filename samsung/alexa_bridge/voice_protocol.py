"""Small, versioned protocol shared by the Mac and Alexa-hosted skill."""

import hashlib
import hmac
import json
import re

MAX_BODY_BYTES = 1024
MAX_AGE_SECONDS = 30
MAX_FUTURE_SECONDS = 5
REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}\Z")
FIELDS = frozenset(("version", "timestamp", "requestId", "action"))


class InvalidRequest(ValueError):
    pass


def secret_bytes(secret_hex):
    if not isinstance(secret_hex, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", secret_hex):
        raise ValueError("Configure a 32-byte secret as 64 hexadecimal characters")
    return bytes.fromhex(secret_hex)


def canonical(request):
    return ("v1\n%d\n%s\n%s" % (request["timestamp"], request["requestId"],
                                  request["action"])).encode("ascii")


def signature(request, secret):
    return "v1=" + hmac.new(secret, canonical(request), hashlib.sha256).hexdigest()


def make_request(request_id, timestamp):
    request = dict(version=1, timestamp=timestamp, requestId=request_id, action="preview")
    validate_fields(request, timestamp)
    return request


def encode_request(request):
    return json.dumps(request, separators=(",", ":"), allow_nan=False).encode("utf-8")


def validate_fields(request, now):
    if not isinstance(request, dict) or frozenset(request) != FIELDS:
        raise InvalidRequest("Invalid fields")
    if type(request["version"]) is not int or request["version"] != 1:
        raise InvalidRequest("Unsupported version")
    if type(request["timestamp"]) is not int:
        raise InvalidRequest("Invalid timestamp")
    if not isinstance(request["requestId"], str) or not REQUEST_ID.fullmatch(request["requestId"]):
        raise InvalidRequest("Invalid request ID")
    if request["action"] != "preview":
        raise InvalidRequest("Only preview is supported")
    if request["timestamp"] < now - MAX_AGE_SECONDS:
        raise InvalidRequest("Expired request")
    if request["timestamp"] > now + MAX_FUTURE_SECONDS:
        raise InvalidRequest("Future request")


def verify(body, supplied_signature, secret, now):
    if not isinstance(body, bytes) or not 0 < len(body) <= MAX_BODY_BYTES:
        raise InvalidRequest("Invalid body size")
    try:
        request = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError):
        raise InvalidRequest("Invalid JSON")
    validate_fields(request, now)
    if not isinstance(supplied_signature, str) or not re.fullmatch(r"v1=[0-9a-f]{64}", supplied_signature):
        raise InvalidRequest("Invalid authentication")
    if not hmac.compare_digest(signature(request, secret), supplied_signature):
        raise InvalidRequest("Invalid authentication")
    return request


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result
