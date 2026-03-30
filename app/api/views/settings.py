from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import CreatorSettingsUpdate
from app.db.session import get_db
from app.repositories.creators import CreatorSettingsRepository

router = APIRouter()


@router.get("/creator")
def get_creator_settings(db: Session = Depends(get_db)) -> dict:
    settings = CreatorSettingsRepository(db).get_or_create_default()
    db.commit()
    return settings.to_dict()


@router.put("/creator")
def update_creator_settings(payload: CreatorSettingsUpdate, db: Session = Depends(get_db)) -> dict:
    repo = CreatorSettingsRepository(db)
    settings = repo.get_or_create_default()
    updated = repo.update(settings, payload.model_dump(exclude_none=True))
    db.commit()
    return updated.to_dict()
