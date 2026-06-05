from fastapi import APIRouter, Depends

from app.web.auth import require_auth

router = APIRouter(prefix="/messages", dependencies=[Depends(require_auth)])


@router.get("")
async def list_messages():
    return {"status": "messages route placeholder"}
