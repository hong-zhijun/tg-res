from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.db import get_session
from app.models import Message
from app.web.auth import require_auth
from app.web.routes.api import _delete_message

router = APIRouter(prefix="/messages", dependencies=[Depends(require_auth)])
templates = Jinja2Templates(directory="app/web/templates")


@router.get("")
async def list_messages(request: Request):
    return templates.TemplateResponse("messages_list.html", {"request": request})


@router.get("/{msg_id}")
async def detail(msg_id: int, request: Request, db: Session = Depends(get_session)):
    msg = db.get(Message, msg_id)
    if not msg:
        return {"status": "not found"}
    return templates.TemplateResponse("messages_detail.html", {"request": request})


@router.post("/{msg_id}/delete")
async def delete_message(msg_id: int, db: Session = Depends(get_session)):
    _delete_message(msg_id, db)
    return RedirectResponse("/messages", status_code=303)
