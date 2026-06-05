from fastapi import APIRouter, Depends

from app.web.auth import require_auth

router = APIRouter(prefix="/settings", dependencies=[Depends(require_auth)])


@router.get("")
async def view_settings():
    return {"status": "settings route placeholder"}
