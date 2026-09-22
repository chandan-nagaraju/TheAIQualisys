"""In-process rate limits for OAuth endpoints.

NON-DISTRIBUTED / STAGING-ONLY HARDENING.

These limits live in process memory (one bucket map per worker). They help for
local and single-worker staging, but are NOT production-grade for multi-worker
deployments. Production must use a distributed limiter (e.g. Redis) before
enabling desktop OAuth at scale.

Same caveats as the licensing in-process limiter.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from fastapi import HTTPException, status

from app.oauth.constants import ERR_INVALID_REQUEST

_LOCK = threading.Lock()
_BUCKETS: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)


def clear_oauth_rate_limit_buckets() -> None:
    with _LOCK:
        _BUCKETS.clear()


def check_oauth_rate_limit(*, scope: str, key: str, limit: int, window_seconds: int = 60) -> None:
    if limit <= 0:
        return
    now = time.monotonic()
    bucket_key = (scope, key)
    with _LOCK:
        q = _BUCKETS[bucket_key]
        while q and (now - q[0]) > float(window_seconds):
            q.popleft()
        if len(q) >= int(limit):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"error": ERR_INVALID_REQUEST, "error_description": "Rate limit exceeded"},
            )
        q.append(now)
