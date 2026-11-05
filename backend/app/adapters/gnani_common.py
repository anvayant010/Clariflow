"""Shared transport for Gnani REST calls: auth, serialisation, 429 backoff, error normalisation.

Verified against docs.gnani.ai on 2026-11-03: auth is the `X-API-Key-ID` header; accounts
may allow only one active request, so all outbound calls share one lock; 429 has no
Retry-After header, so we back off ourselves.
"""
import logging
import threading
import time

import httpx

log = logging.getLogger("clariflow")
_LOCK = threading.Lock()
# Keys that answered "insufficient credit" (HTTP 402) and when. Held in memory only, and keyed by the key itself, so a
# key is never logged or stored anywhere else. After RETRY_AFTER_S the key is tried again (credit may have been added).
_OUT_OF_CREDIT: dict[str, float] = {}
RETRY_AFTER_S = 3600.0


class GnaniError(Exception):
    """Provider failure in a safe shape: no keys, headers or raw bodies."""

    def __init__(self, kind: str, message: str, status: int | None = None):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message
        self.status = status


_KIND_BY_STATUS = {
    400: "bad_request",
    401: "auth",
    402: "insufficient_credit",
    403: "scope_not_allowed",
    422: "bad_request",
    429: "rate_limited",
    503: "unavailable",
    504: "upstream_timeout",
}


def _safe_message(resp: httpx.Response) -> str:
    """Pull the provider's short message out of the known error shapes."""
    try:
        body = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}"
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return f"{err.get('type', '')} {err.get('message', '')}".strip()[:200]
        detail = body.get("detail")
        if isinstance(detail, dict):
            return f"{detail.get('error_code', '')} {detail.get('message', '')}".strip()[:200]
        if "message" in body:
            return str(body["message"])[:200]
    return f"HTTP {resp.status_code}"


def post(
    url: str,
    api_key: str,
    *,
    fallback_key: str = "",
    timeout: float = 60.0,
    retries: int = 2,
    backoff: float = 1.5,
    **kwargs,
) -> httpx.Response:
    """POST with the auth header. Raises GnaniError on any failure.

    If a second key is configured it is used ONLY when Gnani answers 402 (insufficient credit) for the first: that call is
    repeated once with the second key, and the first key is skipped for the next hour. Rate limits (429), bad keys (401),
    scope errors (403) and timeouts never switch keys: they are not a sign that credit ran out.
    """
    keys = [k for k in (api_key, fallback_key) if k]
    if not keys:
        raise GnaniError("auth", "GNANI_API_KEY_ID is not set")
    now = time.monotonic()
    fresh = [k for k in keys if now - _OUT_OF_CREDIT.get(k, -RETRY_AFTER_S - 1) > RETRY_AFTER_S]
    last: GnaniError | None = None
    for key in fresh or keys:  # when every key is marked, try them anyway: credit may have been added
        try:
            return _post_once(url, key, timeout=timeout, retries=retries, backoff=backoff, **dict(kwargs))
        except GnaniError as e:
            if e.status != 402 or len(keys) == 1:
                raise
            _OUT_OF_CREDIT[key] = time.monotonic()
            log.warning("Gnani key #%d is out of credit%s", keys.index(key) + 1, "; trying the next key" if key != keys[-1] else "")
            last = e
    raise last or GnaniError("insufficient_credit", "no usable key")


def _post_once(url: str, api_key: str, *, timeout: float, retries: int, backoff: float, **kwargs) -> httpx.Response:
    headers = {"X-API-Key-ID": api_key, **kwargs.pop("headers", {})}

    with _LOCK:  # one active request at a time
        for attempt in range(retries + 1):
            try:
                resp = httpx.post(url, headers=headers, timeout=timeout, **kwargs)
            except httpx.TimeoutException:
                raise GnaniError("timeout", "request timed out") from None
            except httpx.HTTPError:
                raise GnaniError("network", "could not reach provider") from None
            if resp.status_code == 429 and attempt < retries:
                time.sleep(backoff * (2**attempt))
                continue
            break

    if resp.status_code >= 400:
        kind = _KIND_BY_STATUS.get(resp.status_code, "provider_error")
        raise GnaniError(kind, _safe_message(resp), resp.status_code)
    return resp
