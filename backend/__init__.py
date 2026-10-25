from fastapi import FastAPI

from .core import add_request_logging, configure_logging
from .router import build_router


def mount(app: FastAPI, analyze_fn) -> None:
    """Attach structured logging and the /api/v2 routes to a FastAPI app."""
    configure_logging()
    add_request_logging(app)
    app.include_router(build_router(analyze_fn))
