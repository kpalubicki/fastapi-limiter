"""Built-in key functions for common per-user rate limiting patterns."""

from __future__ import annotations

import base64
import json
from typing import Callable

from fastapi import Request
from fastapi_limiter.limiter import _default_key


def jwt_key_func(claim: str = "sub", header: str = "Authorization") -> Callable[[Request], str]:
    """Return a key_func that uses a JWT claim as the rate limit key.

    Decodes the JWT payload without signature verification — suitable for
    rate limiting where trust is already established by upstream auth middleware.
    Falls back to IP + path if the token is missing or the claim is absent.

    Usage::

        from fastapi_limiter import RateLimiter
        from fastapi_limiter.keys import jwt_key_func

        limiter = RateLimiter(limit=20, window=60, key_func=jwt_key_func())

        @app.get("/api", dependencies=[Depends(limiter)])
        def api():
            ...

    Args:
        claim: JWT payload field to use as the key. Defaults to ``"sub"``.
        header: HTTP header containing the token. Defaults to ``"Authorization"``.
    """
    def key_func(request: Request) -> str:
        auth = request.headers.get(header, "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            try:
                parts = token.split(".")
                if len(parts) == 3:
                    padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(padded))
                    user_id = payload.get(claim)
                    if user_id:
                        return f"jwt:{user_id}:{request.url.path}"
            except Exception:
                pass
        return _default_key(request)

    return key_func
