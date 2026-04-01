from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.event import DraftPost, Event


class DraftRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, draft: DraftPost) -> DraftPost:
        self.db.add(draft)
        self.db.flush()
        return draft

    def list_publishable(self) -> list[DraftPost]:
        stmt = select(DraftPost).where(
            DraftPost.status == "approved",
            DraftPost.needs_review.is_(False),
            DraftPost.workspace_user_id.is_(None),
        )
        return list(self.db.scalars(stmt))

    def get_event(self, draft: DraftPost) -> Event | None:
        stmt = select(Event).where(Event.id == draft.event_id)
        return self.db.scalar(stmt)

    def get(self, draft_id: int) -> DraftPost | None:
        return self.db.get(DraftPost, draft_id)

    def list_needing_review(self) -> list[DraftPost]:
        stmt = select(DraftPost).where(DraftPost.needs_review.is_(True)).order_by(DraftPost.created_at.desc())
        return list(self.db.scalars(stmt))

    def list_needing_review_for_workspace_user(self, workspace_user_id: int) -> list[DraftPost]:
        stmt = (
            select(DraftPost)
            .where(DraftPost.needs_review.is_(True), DraftPost.workspace_user_id == workspace_user_id)
            .order_by(DraftPost.created_at.desc())
        )
        return list(self.db.scalars(stmt))

    def latest_for_event(self, event_id: int, workspace_user_id: int | None = None) -> DraftPost | None:
        stmt = (
            select(DraftPost)
            .where(
                DraftPost.event_id == event_id,
                DraftPost.workspace_user_id == workspace_user_id,
            )
            .order_by(DraftPost.created_at.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def list_rejected(self, limit: int = 50) -> list[DraftPost]:
        stmt = (
            select(DraftPost)
            .where(DraftPost.status == "rejected")
            .order_by(DraftPost.updated_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def list_rejected_for_workspace_user(self, workspace_user_id: int, limit: int = 50) -> list[DraftPost]:
        stmt = (
            select(DraftPost)
            .where(DraftPost.status == "rejected", DraftPost.workspace_user_id == workspace_user_id)
            .order_by(DraftPost.updated_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def list_customer_post_approval_for_workspace_user(self, workspace_user_id: int, limit: int = 50) -> list[DraftPost]:
        stmt = (
            select(DraftPost)
            .where(
                DraftPost.workspace_user_id == workspace_user_id,
                DraftPost.status.in_(("approved", "queued", "publishing", "posted", "failed")),
            )
            .order_by(DraftPost.updated_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def list_history_for_workspace_user(self, workspace_user_id: int, limit: int = 50) -> list[DraftPost]:
        stmt = (
            select(DraftPost)
            .where(
                DraftPost.workspace_user_id == workspace_user_id,
                DraftPost.status.in_(("posted", "expired", "superseded", "rejected", "failed", "cancelled")),
            )
            .order_by(DraftPost.updated_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))
