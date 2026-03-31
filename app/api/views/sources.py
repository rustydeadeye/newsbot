from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import SourceUpdate
from app.api.security import require_admin
from app.db.session import get_db
from app.repositories.sources import SourceRepository

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("")
def list_sources(db: Session = Depends(get_db)) -> list[dict]:
    return [source.to_dict() for source in SourceRepository(db).list_all()]


@router.patch("/{source_id}")
def update_source(source_id: int, payload: SourceUpdate, db: Session = Depends(get_db)) -> dict:
    source = SourceRepository(db).get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    source.enabled = payload.enabled
    db.commit()
    return source.to_dict()
