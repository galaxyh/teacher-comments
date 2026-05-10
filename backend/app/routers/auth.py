"""Auth router — /auth/login, /auth/callback, /auth/logout, /me.

Per ARCH-001 §3.1 onboarding flow steps 1-11 and DESIGN-001 §4.3 contract.

Routers stay thin: parse cookies/state, delegate to AuthService, set/clear cookies.
No business logic here.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from app.config import Settings, get_settings
from app.core.exceptions import AuthError
from app.core.session import (
    COOKIE_NAME,
    OAUTH_STATE_COOKIE,
    OAUTH_STATE_TTL,
    SESSION_TTL_SECONDS,
    issue_oauth_state,
    issue_session_cookie,
    parse_oauth_state,
    parse_session_cookie,
)
from app.db.write_queue import DBWriteQueue, get_write_queue
from app.models import Teacher
from app.schemas.auth import MeResponse
from app.services.audit_logger import AuditLogger
from app.services.auth_service import AuthService, SingleUserViolationError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


# ── Service factory (DI) ─────────────────────────────────────────────
def get_auth_service(
    settings: Settings = Depends(get_settings),
    queue: DBWriteQueue = Depends(get_write_queue),
) -> AuthService:
    return AuthService(
        settings=settings,
        db_write_queue=queue,
        audit=AuditLogger(queue),
    )


# ── Current-teacher dependency ────────────────────────────────────────
async def get_current_teacher(
    auth: AuthService = Depends(get_auth_service),
    session_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> Teacher:
    """Resolve the current teacher from the signed session cookie.

    Returns 401 with a structured body so the frontend can decide whether to
    redirect to /login vs show a session-expired toast.
    """
    if not session_cookie:
        raise HTTPException(status_code=401, detail={"reason": "no_session"})

    payload = parse_session_cookie(session_cookie)
    if payload is None:
        raise HTTPException(status_code=401, detail={"reason": "invalid_session"})
    if payload.is_expired():
        raise HTTPException(status_code=401, detail={"reason": "expired_session"})

    teacher = await auth.get_teacher(teacher_id=payload.teacher_id)
    if teacher is None:
        # Cookie signed for a teacher that no longer exists (logout in another tab,
        # DB rebuilt, etc.). Treat as anonymous.
        raise HTTPException(status_code=401, detail={"reason": "teacher_not_found"})
    return teacher


# ── Routes ────────────────────────────────────────────────────────────
@router.get("/auth/login", status_code=status.HTTP_302_FOUND)
async def login(
    return_to: str = Query(default="/", description="URL to redirect after login"),
    auth: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    """Begin OAuth flow.

    - Issues a signed state cookie (carries `return_to`)
    - Redirects to Google's authorize URL with that state
    """
    state = issue_oauth_state(return_to=return_to)
    authorize_url = auth.begin_oauth(state=state)

    response = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        max_age=OAUTH_STATE_TTL,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/auth",
    )
    return response


@router.get("/auth/callback")
async def callback(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    state_cookie: str | None = Cookie(default=None, alias=OAUTH_STATE_COOKIE),
) -> RedirectResponse:
    """OAuth callback.

    Validates state cookie matches `state` query param (CSRF protection),
    exchanges code for tokens, persists teacher, sets session cookie, redirects
    to the URL stored in state's `return_to`.
    """
    if error:
        # User denied consent or Google reported an error
        raise HTTPException(status_code=400, detail={"reason": "oauth_provider_error", "error": error})
    if not code or not state:
        raise HTTPException(status_code=400, detail={"reason": "missing_oauth_params"})
    if not state_cookie or state_cookie != state:
        # CSRF protection: state from cookie must match state from URL
        raise HTTPException(status_code=400, detail={"reason": "state_mismatch"})

    state_payload = parse_oauth_state(state)
    if state_payload is None:
        raise HTTPException(status_code=400, detail={"reason": "state_invalid_or_expired"})

    try:
        teacher = await auth.complete_oauth(code=code)
    except SingleUserViolationError as exc:
        raise HTTPException(status_code=409, detail={"reason": "single_user_violation", **exc.context}) from exc
    except AuthError as exc:
        raise HTTPException(status_code=401, detail={"reason": "oauth_failed", "message": str(exc)}) from exc

    return_to = str(state_payload.get("return_to") or "/")
    response = RedirectResponse(url=return_to, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=COOKIE_NAME,
        value=issue_session_cookie(teacher.id),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/auth")
    return response


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    auth: AuthService = Depends(get_auth_service),
    teacher: Teacher = Depends(get_current_teacher),
) -> RedirectResponse:
    await auth.logout(teacher_id=teacher.id)
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/me", response_model=MeResponse)
async def me(teacher: Teacher = Depends(get_current_teacher)) -> MeResponse:
    """Current-teacher info — used by frontend to decide post-login routing."""
    return MeResponse(
        teacher_id=teacher.id,
        email=teacher.email,
        has_drive_root=teacher.drive_root_folder_id is not None,
        has_attested=teacher.consent_attestation_at is not None,
    )
