from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.web.auth import require_auth

router = APIRouter(prefix="/settings", dependencies=[Depends(require_auth)])
templates = Jinja2Templates(directory="app/web/templates")


@router.get("")
async def view_settings(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})
