"""Shared rate-limiter singleton (audit F-05).

Pulled out of ``app/main.py`` so any router can ``from app.core.rate_limit
import limiter`` and decorate endpoints without circular imports.

Authenticated requests are keyed by the user UUID (so two users behind the
same NAT don't share a bucket). Anonymous requests fall back to the source
IP via ``slowapi.util.get_remote_address``.

Two ways to apply the limiter:

1. ``@limiter.limit("10/minute")`` — slowapi's classic decorator. Works only
   on endpoints **without** ``from __future__ import annotations`` AND
   without ForwardRef-shaped Path params (a known pydantic-2 / slowapi
   incompatibility — see audit_ai follow-up).
2. ``Depends(rate_limit("10/minute"))`` — wraps the limit in a FastAPI
   dependency so we sidestep the decorator's signature mutation entirely.
   Prefer this on routes annotated with ``from __future__ import annotations``.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _key(request: Request) -> str:
    """Per-user key when authenticated, IP otherwise."""
    user = getattr(request.state, "user", None)
    if user is not None and getattr(user, "id", None):
        return f"user:{user.id}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_key, default_limits=["200/minute"])


def rate_limit(rate: str) -> Callable:
    """FastAPI ``Depends``-able rate limit.

    Use it on endpoints that ``from __future__ import annotations`` so the
    classic ``@limiter.limit`` decorator (which rewrites the function
    signature) does not collide with Pydantic v2's ForwardRef resolution
    for Path/Query params.

    Example::

        @router.post("/{job_id}/analyze",
                     dependencies=[Depends(rate_limit("10/minute"))])
        async def analyze(...): ...
    """

    def _dep(request: Request) -> None:
        # slowapi's Limiter.limit returns a decorator; we replicate its
        # check by calling the underlying limiter for this request and rate.
        # The limiter raises RateLimitExceeded when over the budget; the
        # SlowAPIMiddleware already handles converting that to HTTP 429.
        from limits import parse
        from slowapi.errors import RateLimitExceeded

        # Honour the global enable flag so tests (and any kill-switch) can
        # disable limiting in one place — mirrors slowapi's own .limit() guard.
        if not limiter.enabled:
            return

        item = parse(rate)
        key = _key(request)
        # slowapi internally uses _limiter as a `limits` MovingWindowRateLimiter
        # via Limiter.enabled — re-use its store and strategy.
        if not limiter.limiter.hit(item, key):  # type: ignore[attr-defined]
            raise RateLimitExceeded(item)

    return _dep
