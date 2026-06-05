from fastapi import APIRouter, Depends

from app.web.auth import require_auth

router = APIRouter(prefix="/logs", dependencies=[Depends(require_auth)])


@router.get("")
async def view_logs():
    return {"status": "logs route placeholder"}
