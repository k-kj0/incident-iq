from fastapi import FastAPI

from .core import add_request_logging, configure_logging
from .gtm import build_gtm_router
from .router import build_router


def mount(app: FastAPI, analyze_fn) -> None:
    """Attach structured logging, the /api/v2 routes and the /api/v3/gtm routes."""
    configure_logging()
    add_request_logging(app)
    app.include_router(build_router(analyze_fn))
    app.include_router(build_gtm_router())
