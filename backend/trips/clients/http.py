"""HTTP plumbing shared by the upstream API clients."""

from __future__ import annotations

import re
import threading

import requests
from urllib3.exceptions import ReadTimeoutError

USER_AGENT = "weather-aware-truck-routing/1.0"
CONNECT_TIMEOUT_S = 5.0

_local = threading.local()
_API_KEY = re.compile(r"(key=)[^&\s'\"]+")


def session() -> requests.Session:
    """A keep-alive session for the current thread.

    One server process handles several requests at once on separate threads (on Vercel too), and
    requests.Session isn't guaranteed to be thread-safe, so each thread gets its own.
    """
    current = getattr(_local, "session", None)
    if current is None:
        current = requests.Session()
        current.headers["User-Agent"] = USER_AGENT
        _local.session = current
    return current


def redact(text: str) -> str:
    """Hide API keys in URLs before text reaches a log. requests puts the full URL, query string
    included, into its error messages."""
    return _API_KEY.sub(r"\1***", text)


def is_timeout(error: requests.RequestException) -> bool:
    """Whether a request failed by waiting too long. requests reports a stall partway through a
    response body as a ConnectionError wrapping urllib3's ReadTimeoutError, not as a Timeout."""
    if isinstance(error, requests.Timeout):
        return True
    return bool(error.args) and isinstance(error.args[0], ReadTimeoutError)
