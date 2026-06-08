from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings
from app.web.auth import require_auth

router = APIRouter(prefix="/media", dependencies=[Depends(require_auth)])


@router.get("/{path:path}")
async def serve(path: str):
    settings = get_settings()
    base = Path(settings.save_path).resolve()
    target = (base / path).resolve()
    if base not in target.parents and target != base:
        raise HTTPException(403)
    if not target.exists() or not target.is_file():
        raise HTTPException(404)
    return FileResponse(target)
