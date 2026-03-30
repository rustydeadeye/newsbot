from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import CreatorSettingsUpdate
from app.api.security import ViewerContext, get_current_viewer
from app.db.session import get_db
from app.repositories.creators import CreatorSettingsRepository

router = APIRouter()


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
) -> dict:
    repo = CreatorSettingsRepository(db)
    settings = repo.get_or_create_default()
    update_payload = payload.model_dump(exclude_none=True)
    if viewer.is_customer:
        allowed_keys = {"display_name", "tone", "language", "watchlist", "blocked_phrases"}
        update_payload = {key: value for key, value in update_payload.items() if key in allowed_keys}
    updated = repo.update(settings, update_payload)
    db.commit()
    return updated.to_dict()
