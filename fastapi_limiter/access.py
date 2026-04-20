"""IP whitelist and blacklist support for FastAPI rate limiting."""

from typing import Callable

from fastapi import Request, HTTPException


def _extract_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class IPWhitelist:
    """FastAPI dependency that blocks requests from IPs not in the allowed list.

    Use alongside RateLimiter to skip rate limiting for trusted IPs, or as a
    standalone guard for internal-only endpoints.

    Usage::

        from fastapi import Depends
        from fastapi_limiter.access import IPWhitelist

        whitelist = IPWhitelist(["10.0.0.1", "10.0.0.2"])

        @app.get("/admin", dependencies=[Depends(whitelist)])
        async def admin():
            ...

    Args:
        allowed_ips: List of allowed IP addresses.
    """

    def __init__(self, allowed_ips: list[str]) -> None:
        self._allowed = set(allowed_ips)

    def __call__(self, request: Request) -> None:
        ip = _extract_ip(request)
        if ip not in self._allowed:
            raise HTTPException(status_code=403, detail="Access denied.")


class IPBlocklist:
    """FastAPI dependency that blocks requests from specific IPs.

    Usage::

        from fastapi import Depends
        from fastapi_limiter.access import IPBlocklist

        blocklist = IPBlocklist(["1.2.3.4", "5.6.7.8"])

        @app.get("/api", dependencies=[Depends(blocklist)])
        async def api():
            ...

    Args:
        blocked_ips: List of blocked IP addresses.
    """

    def __init__(self, blocked_ips: list[str]) -> None:
        self._blocked = set(blocked_ips)

    def __call__(self, request: Request) -> None:
        ip = _extract_ip(request)
        if ip in self._blocked:
            raise HTTPException(status_code=403, detail="Access denied.")


def whitelist_key_func(
    allowed_ips: list[str],
    fallback_key_func: Callable[[Request], str] | None = None,
) -> Callable[[Request], str]:
    """Return a key_func that skips rate limiting for whitelisted IPs.

    When the request comes from an IP in ``allowed_ips`` it returns a static
    key that will never hit the limit (by using a unique per-IP key with a
    limit high enough to never trigger). In practice, pass this as the
    ``key_func`` to ``RateLimiter`` and set ``limit`` high for whitelisted
    traffic — or combine with ``IPWhitelist`` to skip the limiter entirely.

    The simpler pattern is to use ``IPWhitelist`` as a separate dependency
    on routes you want to fully bypass. This helper is for when you want
    soft-bypass (rate limited but at a much higher cap).

    Args:
        allowed_ips: IPs that receive the bypass key.
        fallback_key_func: Key function for non-whitelisted requests.
                           Defaults to IP + path.
    """
    from fastapi_limiter.limiter import _default_key

    _allowed = set(allowed_ips)
    _fallback = fallback_key_func or _default_key

    def key_func(request: Request) -> str:
        ip = _extract_ip(request)
        if ip in _allowed:
            return f"__whitelist__:{ip}"
        return _fallback(request)

    return key_func
