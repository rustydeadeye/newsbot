import base64
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.schemas import CreatorSettingsUpdate
from app.api.security import ViewerContext, get_current_viewer
from app.core.config import get_settings
from app.db.session import get_db
from app.repositories.creators import CreatorSettingsRepository
from app.repositories.customers import CustomerProfileRepository
from app.repositories.wire_feed import WireJobRepository

router = APIRouter()

# In-memory PKCE state store: { state: { code_verifier, created_at, workspace_user_id, target, next_path } }
# Short-lived — only valid for one OAuth round-trip (~10 minutes).
_pkce_store: dict[str, dict] = {}
_PKCE_TTL_SECONDS = 600
_X_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
_X_SCOPES = "tweet.read tweet.write users.read offline.access"


def _prune_pkce_store() -> None:
    now = time.monotonic()
    stale = [k for k, v in _pkce_store.items() if now - v["created_at"] > _PKCE_TTL_SECONDS]
    for k in stale:
        del _pkce_store[k]


def _autopost_status(profile: dict, recent_failed: int) -> str:
    if not profile.get("x_connected") or not profile.get("display_name"):
        return "setup_required"
    if recent_failed > 0 and profile.get("auto_post_enabled"):
        return "needs_attention"
    return "active" if profile.get("auto_post_enabled") else "paused"


def _autopost_dashboard_payload(db: Session, viewer: ViewerContext) -> dict:
    profile = CustomerProfileRepository(db).get_or_create_for_workspace_user(
        viewer.workspace_user_id,
        default_display_name=viewer.display_name,
    )
    job_repo = WireJobRepository(db)
    now = datetime.now(timezone.utc)
    profile_payload = profile.to_dict()
    next_posts = [
        {
            "id": job.id,
            "status": job.status,
            "scheduled_for": job.scheduled_for.isoformat() if job.scheduled_for else None,
            "tweet_text": candidate.draft_text,
            "source_title": candidate.title,
            "ticker": candidate.ticker,
        }
        for candidate, job in job_repo.list_upcoming(limit=3)
    ]
    recent_posts = [
        {
            "id": log.id,
            "platform_post_id": log.platform_post_id,
            "posted_at": log.posted_at.isoformat() if log.posted_at else None,
            "tweet_text": candidate.draft_text if candidate else None,
            "source_title": candidate.title if candidate else None,
            "ticker": candidate.ticker if candidate else None,
            "x_url": f"https://x.com/i/web/status/{log.platform_post_id}" if log.platform_post_id else None,
        }
        for log, _job, candidate in job_repo.list_logs_with_candidates_recent(limit=10)
    ]
    recent_failed = job_repo.count_recent_failed(now - timedelta(hours=24))
    return {
        "display_name": profile_payload.get("display_name"),
        "x_connected": profile_payload.get("x_connected"),
        "autopost_enabled": profile.auto_post_enabled,
        "status": _autopost_status(profile_payload, recent_failed),
        "posting_window": {"start_hour": 0, "end_hour": 0, "timezone": "Asia/Kolkata"},
        "quiet_hours": {"start_hour": 23, "end_hour": 7, "timezone": "Asia/Kolkata"},
        "scan_interval_minutes": max(1, get_settings().wire_feed_interval_sec // 60),
        "next_posts": next_posts,
        "recent_posts": recent_posts,
    }


@router.get("/creator")
def get_creator_settings(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    if viewer.is_customer:
        profile = CustomerProfileRepository(db).get_or_create_for_workspace_user(
            viewer.workspace_user_id,
            default_display_name=viewer.display_name,
        )
        db.commit()
        return profile.to_dict()
    settings = CreatorSettingsRepository(db).get_or_create_default()
    db.commit()
    return settings.to_dict()


@router.get("/autopost")
def get_autopost_dashboard(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    if not viewer.is_customer:
        raise HTTPException(status_code=403, detail="Customer access required")
    payload = _autopost_dashboard_payload(db, viewer)
    db.commit()
    return payload


@router.post("/autopost/pause")
def pause_autopost(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    if not viewer.is_customer:
        raise HTTPException(status_code=403, detail="Customer access required")
    repo = CustomerProfileRepository(db)
    profile = repo.get_or_create_for_workspace_user(viewer.workspace_user_id, default_display_name=viewer.display_name)
    profile.auto_post_enabled = False
    db.commit()
    return _autopost_dashboard_payload(db, viewer)


@router.post("/autopost/resume")
def resume_autopost(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    if not viewer.is_customer:
        raise HTTPException(status_code=403, detail="Customer access required")
    repo = CustomerProfileRepository(db)
    profile = repo.get_or_create_for_workspace_user(viewer.workspace_user_id, default_display_name=viewer.display_name)
    if not profile.display_name or not (profile.token_store or {}).get("x_access_token"):
        raise HTTPException(status_code=409, detail="Complete setup before starting autoposting")
    profile.auto_post_enabled = True
    db.commit()
    return _autopost_dashboard_payload(db, viewer)


@router.put("/creator")
def update_creator_settings(
    payload: CreatorSettingsUpdate,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> JSONResponse:
    update_payload = payload.model_dump(exclude_none=True)
    if viewer.is_customer:
        repo = CustomerProfileRepository(db)
        settings = repo.get_or_create_for_workspace_user(
            viewer.workspace_user_id,
            default_display_name=viewer.display_name,
        )
        allowed_keys = {
            "display_name",
            "tone",
            "language",
            "watchlist",
            "blocked_phrases",
            "openai_api_key",
            "automation_mode",
            "freshness_window_hours",
            "max_posts_per_hour",
            "timezone",
            "posting_window_start",
            "posting_window_end",
            "auto_post_enabled",
            "auto_post_threshold",
        }
        update_payload = {key: value for key, value in update_payload.items() if key in allowed_keys}
        if "openai_api_key" in update_payload:
            token_store = dict(settings.token_store or {})
            token_store["openai_api_key"] = update_payload.pop("openai_api_key")
            update_payload["token_store"] = token_store
    else:
        repo = CreatorSettingsRepository(db)
        settings = repo.get_or_create_default()
        if "openai_api_key" in update_payload:
            token_store = dict(settings.token_store or {})
            token_store["openai_api_key"] = update_payload.pop("openai_api_key")
            update_payload["token_store"] = token_store

    if "timezone" in update_payload:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(update_payload["timezone"])
        except (ZoneInfoNotFoundError, KeyError):
            return JSONResponse(
                status_code=422,
                content={"detail": [{"loc": ["body", "timezone"], "msg": "Unknown timezone identifier. Use a valid tz name such as Asia/Kolkata."}]},
            )

    # openai_api_key is a secret — store in token_store, not as a plain column
    openai_api_key = update_payload.pop("openai_api_key", None)
    if openai_api_key is not None:
        store = dict(settings.token_store or {})
        if openai_api_key == "":
            store.pop("openai_api_key", None)
        else:
            store["openai_api_key"] = openai_api_key
        settings.token_store = store

    updated = repo.update(settings, update_payload)
    db.commit()
    return JSONResponse(content=updated.to_dict())


@router.get("/x/connect")
def x_oauth_connect(
    next_path: str = "/settings",
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    """Return a X OAuth 2.0 authorization URL for the viewer to redirect to."""
    cfg = get_settings()
    if not cfg.x_client_id:
        raise HTTPException(status_code=400, detail="X_CLIENT_ID is not configured")

    _prune_pkce_store()
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    _pkce_store[state] = {
        "code_verifier": code_verifier,
        "created_at": time.monotonic(),
        "workspace_user_id": viewer.workspace_user_id,
        "target": "customer" if viewer.is_customer else "workspace",
        "next_path": next_path,
    }

    params = {
        "response_type": "code",
        "client_id": cfg.x_client_id,
        "redirect_uri": cfg.x_redirect_uri,
        "scope": _X_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{_X_AUTH_URL}?{urlencode(params)}"
    return {"auth_url": auth_url}


@router.post("/x/disconnect")
def x_disconnect(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    if viewer.is_customer:
        repo = CustomerProfileRepository(db)
        profile = repo.get_or_create_for_workspace_user(viewer.workspace_user_id, default_display_name=viewer.display_name)
        store = dict(profile.token_store or {})
        store.pop("x_access_token", None)
        store.pop("x_refresh_token", None)
        profile.token_store = store
        profile.auto_post_enabled = False
        db.commit()
        return {"x_connected": False, "autopost_enabled": False}

    repo = CreatorSettingsRepository(db)
    creator = repo.get_or_create_default()
    store = dict(creator.token_store or {})
    store.pop("x_access_token", None)
    store.pop("x_refresh_token", None)
    creator.token_store = store
    db.commit()
    return {"x_connected": False}


@router.get("/x/callback")
def x_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """X OAuth 2.0 callback — exchanges code for tokens, stores them, redirects to frontend."""
    cfg = get_settings()
    frontend_settings = f"{cfg.frontend_url.rstrip('/')}/settings"

    if error:
        return RedirectResponse(url=f"{frontend_settings}?x_error={error}")

    if not code or not state:
        return RedirectResponse(url=f"{frontend_settings}?x_error=missing_params")

    pkce = _pkce_store.pop(state, None)
    if not pkce:
        return RedirectResponse(url=f"{frontend_settings}?x_error=invalid_state")
    frontend_settings = f"{cfg.frontend_url.rstrip('/')}{pkce.get('next_path', '/settings')}"

    # Exchange authorization code for tokens
    auth_header = base64.b64encode(
        f"{cfg.x_client_id}:{cfg.x_client_secret}".encode()
    ).decode() if cfg.x_client_secret else None

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if auth_header:
        headers["Authorization"] = f"Basic {auth_header}"

    try:
        response = httpx.post(
            cfg.x_token_url,
            headers=headers,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": cfg.x_redirect_uri,
                "code_verifier": pkce["code_verifier"],
                "client_id": cfg.x_client_id,
            },
            timeout=20.0,
        )
        response.raise_for_status()
    except Exception:
        return RedirectResponse(url=f"{frontend_settings}?x_error=token_exchange_failed")

    payload = response.json()
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if not access_token:
        return RedirectResponse(url=f"{frontend_settings}?x_error=no_access_token")

    if pkce.get("target") == "customer":
        repo = CustomerProfileRepository(db)
        profile = repo.get_or_create_for_workspace_user(pkce["workspace_user_id"])
        store = dict(profile.token_store or {})
        store["x_access_token"] = access_token
        if refresh_token:
            store["x_refresh_token"] = refresh_token
        profile.token_store = store
    else:
        repo = CreatorSettingsRepository(db)
        creator = repo.get_or_create_default()
        store = dict(creator.token_store or {})
        store["x_access_token"] = access_token
        if refresh_token:
            store["x_refresh_token"] = refresh_token
        creator.token_store = store
    db.commit()

    return RedirectResponse(url=f"{frontend_settings}?x_connected=1")
