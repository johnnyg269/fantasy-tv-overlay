"""Fixed-origin HTTPS JSON reader. No redirects, credential logging, or retries."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ProviderError(ValueError):
    """A safe category; never include upstream response bodies or credentials."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


ALLOWED_HOSTS = frozenset(("lm-api-reads.fantasy.espn.com", "api.sleeper.app"))


def get_json(url, headers=None, maximum=4 * 1024 * 1024):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.port not in (None, 443) or parsed.username or parsed.password):
        raise ProviderError("Provider origin is not allowed")
    request = Request(url, headers={"Accept": "application/json",
                                  "User-Agent": "FantasyTV/1.0", **(headers or {})})
    try:
        with build_opener(NoRedirect()).open(request, timeout=8) as response:
            body = response.read(maximum + 1)
    except HTTPError as error:
        if error.code in (401, 403):
            raise ProviderError("Provider authorization failed") from None
        if error.code == 429:
            raise ProviderError("Provider rate limit reached") from None
        raise ProviderError("Provider request failed") from None
    except (URLError, TimeoutError, OSError):
        raise ProviderError("Provider is unavailable") from None
    if len(body) > maximum:
        raise ProviderError("Provider response is too large")
    try:
        return json.loads(body.decode("utf-8"), parse_constant=lambda _: None)
    except (UnicodeError, ValueError):
        raise ProviderError("Provider did not return JSON") from None
