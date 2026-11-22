from fastapi import FastAPI

from .core import add_request_logging, configure_logging
from .gtm import build_gtm_router
from .quotes import build_quotes_router
from .router import build_router


def mount(app: FastAPI, analyze_fn) -> None:
    """Attach structured logging, /api/v2, /api/v3/gtm and /api/v3/quotes."""
    configure_logging()
    add_request_logging(app)
    app.include_router(build_router(analyze_fn))
    app.include_router(build_gtm_router())
    app.include_router(build_quotes_router())
