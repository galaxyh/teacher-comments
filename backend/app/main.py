"""FastAPI app entrypoint.

Per ARCH-001 §2.1, this module is intentionally thin: it composes lifespan + routers
+ exception handlers, and exposes `app` for `uvicorn app.main:app`.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.exceptions import AppError
from app.core.lifespan import lifespan
from app.routers import auth, system

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(
        title="teacher-comments",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        """Map AppError subclasses to HTTP responses (ARCH-001 §6.3)."""
        status_code = _status_for(exc)
        return JSONResponse(
            status_code=status_code,
            content={
                "error": type(exc).__name__,
                "message": str(exc),
                "context": exc.context,
                "terminal": exc.is_terminal(),
            },
        )

    app.include_router(system.router)
    app.include_router(auth.router)  # /auth/login, /auth/callback, /auth/logout, /me
    # Future: app.include_router(drive.router, prefix="/drive")
    # Future: app.include_router(batch.router, prefix="/batch")
    # Future: app.include_router(evaluation.router, prefix="/eval")
    # Future: app.include_router(settings_router.router, prefix="/settings")

    return app


def _status_for(exc: AppError) -> int:
    """Coarse HTTP code mapping. Per-error fine-tuning lives here as the table grows."""
    from app.core.exceptions import (
        AttestationRequiredError,
        AuthError,
        ConfigError,
        DriveFileNotFoundError,
        OAuthRevokedError,
        PIILeakageError,
        UnsupportedFormatError,
    )

    if isinstance(exc, OAuthRevokedError):
        return 401
    if isinstance(exc, AttestationRequiredError):
        return 403
    if isinstance(exc, AuthError):
        return 401
    if isinstance(exc, DriveFileNotFoundError):
        return 404
    if isinstance(exc, UnsupportedFormatError):
        return 415
    if isinstance(exc, PIILeakageError):
        return 500   # boundary trip = system bug, not user error
    if isinstance(exc, ConfigError):
        return 500
    return 500


app = create_app()
