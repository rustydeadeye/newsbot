from fastapi import APIRouter, Depends

from app.api.security import ViewerContext, get_current_viewer

router = APIRouter()


@router.get("/me")
def get_auth_me(viewer: ViewerContext = Depends(get_current_viewer)) -> dict:
    return {"viewer": viewer.to_dict()}
