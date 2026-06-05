from fastapi import APIRouter, Depends

from app.web.auth import require_auth

router = APIRouter(prefix="/users", dependencies=[Depends(require_auth)])


@router.get("")
async def list_users():
    return {"status": "users route placeholder"}
