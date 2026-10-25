import structlog
import httpx

from .settings import EMBED_DIM, GEMINI_API_KEY

log = structlog.get_logger()
URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent"


def embed(text: str) -> list[float] | None:
    """Return an embedding, or None if no key / the call fails (callers degrade)."""
    if not GEMINI_API_KEY:
        return None
    try:
        r = httpx.post(
            URL,
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
