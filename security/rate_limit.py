from collections import defaultdict, deque
from time import monotonic
from typing import Deque, Dict

from fastapi import HTTPException, Request


_BUCKETS: Dict[str, Deque[float]] = defaultdict(deque)


def enforce_rate_limit(request: Request, key: str, limit: int, seconds: int) -> None:
    ip = request.client.host if request.client else "unknown"
    bucket_key = f"{key}:{ip}"
    now = monotonic()
    bucket = _BUCKETS[bucket_key]
    while bucket and now - bucket[0] > seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="تم تجاوز عدد المحاولات المسموح. حاول لاحقاً")
    bucket.append(now)
