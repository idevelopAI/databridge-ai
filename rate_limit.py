import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException

from config import get_rate_limit_per_minute

_requests_by_key: dict[str, deque[float]] = defaultdict(deque)
_rate_limit_lock = Lock()


def enforce_rate_limit(api_key: str) -> None:
    limit = get_rate_limit_per_minute()
    now = time.monotonic()
    window_start = now - 60

    with _rate_limit_lock:
        request_times = _requests_by_key[api_key]

        while request_times and request_times[0] < window_start:
            request_times.popleft()

        if len(request_times) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
            )

        request_times.append(now)
