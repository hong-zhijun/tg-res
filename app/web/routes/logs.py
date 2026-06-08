from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.web.auth import require_auth

router = APIRouter(prefix="/logs", dependencies=[Depends(require_auth)])
templates = Jinja2Templates(directory="app/web/templates")


@router.get("")
async def view_logs(request: Request):
    return templates.TemplateResponse("logs.html", {"request": request})
