import json

import redis
import structlog

from .settings import REDIS_URL

log = structlog.get_logger()
_client = redis.Redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None


def cached(key: str, ttl: int, compute):
    """Return cached JSON for key, else compute(), store it, return it."""
    if _client is not None:
        try:
            hit = _client.get(key)
            if hit:
                return json.loads(hit)
        except Exception as exc:
            log.warning("cache_read_failed", error=str(exc))
    value = compute()
    if _client is not None:
        try:
            _client.setex(key, ttl, json.dumps(value))
        except Exception as exc:
            log.warning("cache_write_failed", error=str(exc))
    return value
