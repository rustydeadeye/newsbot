from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.workspace_users import WorkspaceUserRepository

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ViewerContext:
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

    def to_dict(self) -> dict[str, str | None]:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "role": self.role,
            "display_name": self.display_name,
        }


def _decode_supabase_jwt(token: str, settings: Settings) -> dict[str, Any]:
    if settings.supabase_jwt_secret:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1" if settings.supabase_url else None,
        )

    if not settings.supabase_jwks_url or not settings.supabase_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase auth is not configured",
        )

    jwk_client = PyJWKClient(settings.supabase_jwks_url)
    signing_key = jwk_client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience="authenticated",
        issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
    )


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

    try:
        claims = _decode_supabase_jwt(credentials.credentials, settings)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token") from exc

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
        user_id=workspace_user.auth_user_id,
        email=workspace_user.email,
        role=workspace_user.role,
        display_name=workspace_user.display_name,
    )


def require_admin(viewer: ViewerContext = Depends(get_current_viewer)) -> ViewerContext:
    if not viewer.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return viewer
