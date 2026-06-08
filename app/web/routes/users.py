from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.db import get_session
from app.models import User
from app.web.auth import require_auth

router = APIRouter(prefix="/users", dependencies=[Depends(require_auth)])
templates = Jinja2Templates(directory="app/web/templates")


@router.get("")
async def list_users(request: Request):
    return templates.TemplateResponse("users.html", {"request": request})


@router.post("/{user_id}/toggle")
async def toggle_user(user_id: int, db: Session = Depends(get_session)):
    user = db.get(User, user_id)
    if user:
        user.allowed = not user.allowed
        db.add(user)
        db.commit()
    return RedirectResponse("/users", status_code=303)


@router.post("/{user_id}/note")
async def update_note(
    user_id: int,
    notes: str = Form(""),
    db: Session = Depends(get_session),
):
    user = db.get(User, user_id)
    if user:
        user.notes = notes.strip() or None
        db.add(user)
        db.commit()
    return RedirectResponse("/users", status_code=303)
