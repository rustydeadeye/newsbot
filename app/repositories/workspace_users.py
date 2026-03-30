from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.access import WorkspaceUser


class WorkspaceUserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_auth_user_id(self, auth_user_id: str) -> WorkspaceUser | None:
        stmt = select(WorkspaceUser).where(WorkspaceUser.auth_user_id == auth_user_id)
        return self.db.scalar(stmt)

    def get_by_email(self, email: str) -> WorkspaceUser | None:
        stmt = select(WorkspaceUser).where(WorkspaceUser.email == email)
        return self.db.scalar(stmt)

    def provision(
        self,
        *,
        auth_user_id: str,
        email: str,
        display_name: str | None,
        role: str,
    ) -> WorkspaceUser:
        user = WorkspaceUser(
            auth_user_id=auth_user_id,
            email=email,
            display_name=display_name,
            role=role,
            is_active=True,
            last_seen_at=datetime.now(timezone.utc),
        )
        self.db.add(user)
        self.db.flush()
        return user

    def touch(self, user: WorkspaceUser, *, email: str, display_name: str | None) -> WorkspaceUser:
        user.email = email
        user.display_name = display_name
        user.last_seen_at = datetime.now(timezone.utc)
        self.db.flush()
        return user
