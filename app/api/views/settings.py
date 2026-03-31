import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode
from zoneinfo import ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.schemas import CreatorSettingsUpdate
from app.api.security import ViewerContext, get_current_viewer, require_admin
from app.core.config import get_settings
from app.db.session import get_db
from app.repositories.creators import CreatorSettingsRepository

router = APIRouter()

# In-memory PKCE state store: { state: { code_verifier, created_at } }
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


@router.get("/creator")
def get_creator_settings(
    db: Session = Depends(get_db),
    _viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    settings = CreatorSettingsRepository(db).get_or_create_default()
    db.commit()
    return settings.to_dict()


@router.put("/creator")
def update_creator_settings(
    payload: CreatorSettingsUpdate,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> JSONResponse:
    repo = CreatorSettingsRepository(db)
    settings = repo.get_or_create_default()
    update_payload = payload.model_dump(exclude_none=True)
    if viewer.is_customer:
        allowed_keys = {"display_name", "tone", "language", "watchlist", "blocked_phrases", "timezone", "posting_window_start", "posting_window_end"}
        update_payload = {key: value for key, value in update_payload.items() if key in allowed_keys}

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


@router.get("/x/connect", dependencies=[Depends(require_admin)])
def x_oauth_connect() -> dict:
    """Return a X OAuth 2.0 authorization URL for the admin to redirect to."""
    cfg = get_settings()
    if not cfg.x_client_id:
        raise HTTPException(status_code=400, detail="X_CLIENT_ID is not configured")

    _prune_pkce_store()
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    _pkce_store[state] = {"code_verifier": code_verifier, "created_at": time.monotonic()}

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

    repo = CreatorSettingsRepository(db)
    creator = repo.get_or_create_default()
    store = dict(creator.token_store or {})
    store["x_access_token"] = access_token
    if refresh_token:
        store["x_refresh_token"] = refresh_token
    creator.token_store = store
    db.commit()

    return RedirectResponse(url=f"{frontend_settings}?x_connected=1")
