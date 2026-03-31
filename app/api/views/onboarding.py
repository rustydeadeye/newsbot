from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import CustomerOpenAIUpdate, CustomerProfileUpdate
from app.api.security import ViewerContext, get_current_viewer
from app.db.session import get_db
from app.repositories.customers import CustomerProfileRepository

router = APIRouter()


def _get_customer_profile(db: Session, viewer: ViewerContext):
    if not viewer.is_customer:
        raise HTTPException(status_code=403, detail="Customer onboarding only")
    repo = CustomerProfileRepository(db)
    profile = repo.get_or_create_for_workspace_user(
        viewer.workspace_user_id,
        default_display_name=viewer.display_name,
    )
    db.commit()
    return repo, profile


@router.get("/status")
def get_onboarding_status(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    repo, profile = _get_customer_profile(db, viewer)
    payload = profile.to_dict()
    payload["required"] = not payload["onboarding_completed"]
    payload["missing"] = [
        name
        for name, is_ready in (
            ("display_name", bool(payload["display_name"])),
            ("openai_api_key", bool(payload["openai_configured"])),
        )
        if not is_ready
    ]
    return payload


@router.put("/profile")
def update_onboarding_profile(
    payload: CustomerProfileUpdate,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    repo, profile = _get_customer_profile(db, viewer)
    update_payload = payload.model_dump(exclude_none=True)
    repo.update(profile, update_payload)
    db.commit()
    return profile.to_dict()


@router.put("/openai")
def update_onboarding_openai(
    payload: CustomerOpenAIUpdate,
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    repo, profile = _get_customer_profile(db, viewer)
    token_store = dict(profile.token_store or {})
    token_store["openai_api_key"] = payload.openai_api_key.strip()
    repo.update(profile, {"token_store": token_store})
    db.commit()
    return profile.to_dict()


@router.post("/complete")
def complete_onboarding(
    db: Session = Depends(get_db),
    viewer: ViewerContext = Depends(get_current_viewer),
) -> dict:
    repo, profile = _get_customer_profile(db, viewer)
    payload = profile.to_dict()
    if not payload["display_name"]:
        raise HTTPException(status_code=409, detail="Display name is required")
    if not payload["openai_configured"]:
        raise HTTPException(status_code=409, detail="OpenAI key is required")
    repo.mark_onboarding_complete(profile)
    db.commit()
    return profile.to_dict()
