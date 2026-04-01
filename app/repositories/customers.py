from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import CustomerProfile


class CustomerProfileRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_workspace_user_id(self, workspace_user_id: int) -> CustomerProfile | None:
        stmt = select(CustomerProfile).where(CustomerProfile.workspace_user_id == workspace_user_id)
        return self.db.scalar(stmt)

    def get_or_create_for_workspace_user(self, workspace_user_id: int, default_display_name: str | None = None) -> CustomerProfile:
        profile = self.get_by_workspace_user_id(workspace_user_id)
        if profile:
            return profile
        profile = CustomerProfile(
            workspace_user_id=workspace_user_id,
            display_name=default_display_name,
        )
        self.db.add(profile)
        self.db.flush()
        return profile

    def update(self, profile: CustomerProfile, payload: dict) -> CustomerProfile:
        for key, value in payload.items():
            setattr(profile, key, value)
        self.db.flush()
        return profile

    def mark_onboarding_complete(self, profile: CustomerProfile) -> CustomerProfile:
        profile.onboarding_completed_at = datetime.now(timezone.utc)
        self.db.flush()
        return profile

    def mark_last_seen(self, profile: CustomerProfile) -> CustomerProfile:
        profile.last_seen_at = datetime.now(timezone.utc)
        self.db.flush()
        return profile

    def list_eligible_for_background_generation(self) -> list[CustomerProfile]:
        stmt = select(CustomerProfile).where(
            CustomerProfile.onboarding_completed_at.is_not(None),
            CustomerProfile.automation_mode != "manual_review_only",
        )
        return list(self.db.scalars(stmt))

    def has_active_autopost_customer(self) -> bool:
        stmt = select(CustomerProfile).where(CustomerProfile.auto_post_enabled.is_(True))
        profiles = list(self.db.scalars(stmt))
        return any(bool((profile.token_store or {}).get("x_access_token")) for profile in profiles)
