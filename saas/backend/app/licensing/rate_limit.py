"""Best-effort machine API rate limiting (Phase 7).

IMPORTANT LIMITATION:
This is an in-process, thread-safe sliding-window limiter. It is suitable for
tests and single-worker deployments. It is NOT a production-grade distributed
rate limiter across multiple Gunicorn/Railway workers. Prefer edge/API-gateway
limits (or Redis) for multi-worker production — documented as non-blocking
hardening. Unknown-key activate attempts still count against IP buckets here.

Phase 7A also uses this limiter for trial creation (per-user and per-IP hourly
buckets). The same in-process / non-distributed limitation applies.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from fastapi import HTTPException, status

from app.licensing.constants import (
    LICENSE_API_RATE_LIMIT_PER_MINUTE,
    MACHINE_ERR_RATE_LIMITED,
)

_LOCK = threading.Lock()
_BUCKETS: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)


def clear_rate_limit_buckets() -> None:
    """Test helper."""
    with _LOCK:
        _BUCKETS.clear()


def _prune(q: Deque[float], *, now: float, window_s: float) -> None:
    while q and (now - q[0]) > window_s:
        q.popleft()


def check_rate_limit(
    *,
    scope: str,
    key: str,
    limit: int,
    window_seconds: int = 60,
) -> None:
    """Raise 429 when more than `limit` events occur in the sliding window."""
    if limit <= 0:
        return
    now = time.monotonic()
    bucket_key = (scope, key)
    with _LOCK:
        q = _BUCKETS[bucket_key]
        _prune(q, now=now, window_s=float(window_seconds))
        if len(q) >= int(limit):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": MACHINE_ERR_RATE_LIMITED, "message": "Rate limit exceeded"},
            )
        q.append(now)


def default_machine_limit() -> int:
    return int(LICENSE_API_RATE_LIMIT_PER_MINUTE)
