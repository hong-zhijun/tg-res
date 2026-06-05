from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.web.auth import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/")
@router.get("/dashboard")
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})
