from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.security import require_admin
from app.db.session import get_db
from app.repositories.sources import SourceRepository

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("")
def list_sources(db: Session = Depends(get_db)) -> list[dict]:
    return [source.to_dict() for source in SourceRepository(db).list_enabled()]
