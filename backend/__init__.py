from fastapi import FastAPI

from .logging_conf import add_request_logging, configure_logging
from .router import build_router


def mount(app: FastAPI, analyze_fn) -> None:
    """Attach logging, request middleware and the /api/v2 routes to an app."""
    configure_logging()
    add_request_logging(app)
    app.include_router(build_router(analyze_fn))
