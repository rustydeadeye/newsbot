from dataclasses import dataclass
import logging
from typing import Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.workspace_users import WorkspaceUserRepository

_log = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ViewerContext:
    workspace_user_id: int
    user_id: str
    email: str
    role: str
    display_name: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_customer(self) -> bool:
        return self.role == "customer"

    @property
    def actor_name(self) -> str:
        return self.display_name or self.email

    def to_dict(self) -> dict[str, str | None]:
        return {
            "workspace_user_id": self.workspace_user_id,
            "user_id": self.user_id,
            "email": self.email,
            "role": self.role,
            "display_name": self.display_name,
        }


def _verify_token_with_supabase(token: str, supabase_url: str, anon_key: str) -> dict[str, Any]:
    """Validate the JWT by calling Supabase's own /auth/v1/user endpoint.
    This is always correct regardless of how the JWT secret is configured."""
    url = f"{supabase_url.rstrip('/')}/auth/v1/user"
    try:
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {token}", "apikey": anon_key},
            timeout=5.0,
        )
    except httpx.RequestError as exc:
        _log.error("Supabase auth request failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth service unreachable")

    if response.status_code == 401:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token")
    if not response.is_success:
        _log.warning("Supabase /auth/v1/user returned %d", response.status_code)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token")

    data = response.json()
    return {
        "sub": data.get("id"),
        "email": data.get("email"),
        "user_metadata": data.get("user_metadata", {}),
    }


def _extract_display_name(claims: dict[str, Any]) -> str | None:
    user_metadata = claims.get("user_metadata") or {}
    if not isinstance(user_metadata, dict):
        return None
    for key in ("display_name", "full_name", "name"):
        value = user_metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def get_current_viewer(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ViewerContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Supabase auth is not configured")

    claims = _verify_token_with_supabase(credentials.credentials, settings.supabase_url, settings.supabase_publishable_key)

    user_id = claims.get("sub")
    email = claims.get("email")
    if not isinstance(user_id, str) or not isinstance(email, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token")

    display_name = _extract_display_name(claims)
    repo = WorkspaceUserRepository(db)
    workspace_user = repo.get_by_auth_user_id(user_id)
    if workspace_user is None:
        if not settings.auth_auto_provision_users:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access not provisioned")
        default_role = "admin" if email.lower() in settings.auth_admin_email_set else "customer"
        workspace_user = repo.provision(
            auth_user_id=user_id,
            email=email,
            display_name=display_name,
            role=default_role,
        )
        db.commit()
    else:
        repo.touch(workspace_user, email=email, display_name=display_name)
        db.commit()

    if not workspace_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access disabled")

    return ViewerContext(
        workspace_user_id=workspace_user.id,
        user_id=workspace_user.auth_user_id,
        email=workspace_user.email,
        role=workspace_user.role,
        display_name=workspace_user.display_name,
    )


def require_admin(viewer: ViewerContext = Depends(get_current_viewer)) -> ViewerContext:
    if not viewer.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return viewer
