import json
import logging
import os
import time
import uuid
from datetime import datetime

import httpx
import redis
import structlog
from fastapi import FastAPI, Request
from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Float, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

# ---------------- settings ----------------
_raw = os.getenv("DATABASE_URL", "")
# Neon and Render give "postgresql://..." but SQLAlchemy needs the psycopg driver name.
DATABASE_URL = _raw.replace("postgresql://", "postgresql+psycopg://", 1)
REDIS_URL = os.getenv("REDIS_URL", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
EMBED_DIM = 768
# Same demo tenants as your README. Override with TENANT_KEYS='{"acme":"secret"}'.
TENANT_KEYS = json.loads(
    os.getenv("TENANT_KEYS", '{"demo_corp":"demo-key-123","test_inc":"test-key-456"}')
)

log = structlog.get_logger()


# ---------------- database ----------------
class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(engine, expire_on_commit=False) if engine else None


def get_session():
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not set")
    with SessionLocal() as session:
        yield session


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    service: Mapped[str] = mapped_column(String(128))
    error: Mapped[str] = mapped_column(Text)
    logs: Mapped[str] = mapped_column(Text, default="")
    root_cause: Mapped[str] = mapped_column(String(256))
    confidence: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(32))
    result: Mapped[dict] = mapped_column(JSON)
    embedding = mapped_column(Vector(EMBED_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------- embeddings (Gemini) ----------------
_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-embedding-001:embedContent"
)


def embed(text: str):
    """Return a vector, or None when there is no key or the call fails."""
    if not GEMINI_API_KEY:
        return None
    try:
        r = httpx.post(
            _EMBED_URL,
            headers={"x-goog-api-key": GEMINI_API_KEY},
            json={
                "model": "models/gemini-embedding-001",
                "content": {"parts": [{"text": text[:8000]}]},
                "outputDimensionality": EMBED_DIM,
            },
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["embedding"]["values"]
    except Exception as exc:
        log.warning("embedding_failed", error=str(exc))
        return None


# ---------------- redis cache (optional) ----------------
_redis = redis.Redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None


def cached(key: str, ttl: int, compute):
    if _redis is not None:
        try:
            hit = _redis.get(key)
            if hit:
                return json.loads(hit)
        except Exception as exc:
            log.warning("cache_read_failed", error=str(exc))
    value = compute()
    if _redis is not None:
        try:
            _redis.setex(key, ttl, json.dumps(value))
        except Exception as exc:
            log.warning("cache_write_failed", error=str(exc))
    return value


# ---------------- structured logging ----------------
def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )


def add_request_logging(app: FastAPI) -> None:
    @app.middleware("http")
    async def _log_requests(request: Request, call_next):
        request_id = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
        start = time.perf_counter()
        response = await call_next(request)
        log.info(
            "request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            ms=round((time.perf_counter() - start) * 1000, 1),
        )
        response.headers["x-request-id"] = request_id
        return response
