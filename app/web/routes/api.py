import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlmodel import Session, func, select

from app.config import get_settings
from app.db import get_session
from app.models import Group, Message, User
from app.web.auth import require_api_auth, verify_password

router = APIRouter(prefix="/api")

MESSAGE_TYPES = {"text", "photo", "video", "document", "voice", "audio", "animation", "sticker"}


class LoginRequest(BaseModel):
    password: str


class NoteRequest(BaseModel):
    notes: str = ""


GROUP_ICONS = ["📁", "📂", "📦", "📋", "⭐", "❤️", "🔥", "💎"]


class GroupCreate(BaseModel):
    name: str
    parent_id: int | None = None
    icon: str = "📁"


class GroupUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None


@router.post("/auth/login")
async def api_login(payload: LoginRequest, request: Request):
    settings = get_settings()
    if not verify_password(payload.password, settings.admin_password):
        raise HTTPException(status_code=401, detail="Invalid password")
    request.session["authenticated"] = True
    return {"ok": True}


@router.post("/auth/logout", dependencies=[Depends(require_api_auth)])
async def api_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/auth/session")
async def api_session(request: Request):
    return {"authenticated": bool(request.session.get("authenticated"))}


@router.get("/dashboard", dependencies=[Depends(require_api_auth)])
async def api_dashboard(db: Session = Depends(get_session)):
    settings = get_settings()
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = datetime(now.year, now.month, 1)

    type_rows = db.exec(
        select(Message.type, func.count()).group_by(Message.type).order_by(Message.type)
    ).all()
    recent = db.exec(select(Message).order_by(Message.created_at.desc()).limit(10)).all()
    return {
        "stats": {
            "today": _count_since(db, today_start),
            "week": _count_since(db, week_start),
            "month": _count_since(db, month_start),
            "total": db.exec(select(func.count()).select_from(Message)).one(),
            "storage_bytes": _dir_size(settings.save_path),
        },
        "type_distribution": [{"type": type_, "count": count} for type_, count in type_rows],
        "recent_messages": [_message_summary(item) for item in recent],
    }


@router.get("/messages", dependencies=[Depends(require_api_auth)])
async def api_list_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    type: str | None = None,
    user_id: int | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_session),
):
    if type and type not in MESSAGE_TYPES:
        raise HTTPException(status_code=422, detail="Invalid message type")

    query = select(Message).order_by(Message.created_at.desc())
    if type:
        query = query.where(Message.type == type)
    if user_id:
        query = query.where(Message.user_id == user_id)
    if q:
        query = query.where(Message.text.contains(q))
    start = _parse_date(date_from)
    end = _parse_date(date_to)
    if start:
        query = query.where(Message.created_at >= start)
    if end:
        query = query.where(Message.created_at < end.replace(hour=23, minute=59, second=59))

    items = db.exec(query.offset((page - 1) * page_size).limit(page_size + 1)).all()
    has_next = len(items) > page_size
    items = items[:page_size]
    groups = _groups_for_messages(db, items)
    return {
        "items": [_message_summary(item, groups.get(item.group_id)) for item in items],
        "page": page,
        "page_size": page_size,
        "has_next": has_next,
    }


@router.get("/messages/{message_id}", dependencies=[Depends(require_api_auth)])
async def api_message_detail(message_id: int, db: Session = Depends(get_session)):
    msg = db.get(Message, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    user = db.get(User, msg.user_id)
    group = db.get(Group, msg.group_id) if msg.group_id else None
    data = _message_detail(msg, group)
    data["user"] = _user_dict(user) if user else None
    return data


@router.delete("/messages/{message_id}", dependencies=[Depends(require_api_auth)])
async def api_delete_message(message_id: int, db: Session = Depends(get_session)):
    deleted = _delete_message(message_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True, "deleted": True}


@router.post("/messages/{message_id}/delete", dependencies=[Depends(require_api_auth)])
async def api_delete_message_post(message_id: int, db: Session = Depends(get_session)):
    deleted = _delete_message(message_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True, "deleted": True}


@router.get("/users", dependencies=[Depends(require_api_auth)])
async def api_list_users(db: Session = Depends(get_session)):
    users = db.exec(select(User).order_by(User.allowed.desc(), User.last_seen_at.desc())).all()
    counts = dict(db.exec(select(Message.user_id, func.count()).group_by(Message.user_id)).all())
    return {"items": [{**_user_dict(user), "message_count": counts.get(user.id, 0)} for user in users]}


@router.post("/users/{user_id}/toggle", dependencies=[Depends(require_api_auth)])
async def api_toggle_user(user_id: int, db: Session = Depends(get_session)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.allowed = not user.allowed
    user.last_seen_at = user.last_seen_at or datetime.utcnow()
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_dict(user)


@router.patch("/users/{user_id}/note", dependencies=[Depends(require_api_auth)])
async def api_update_user_note(
    user_id: int,
    payload: NoteRequest,
    db: Session = Depends(get_session),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.notes = payload.notes.strip() or None
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_dict(user)


@router.post("/users/{user_id}/note", dependencies=[Depends(require_api_auth)])
async def api_update_user_note_post(
    user_id: int,
    payload: NoteRequest,
    db: Session = Depends(get_session),
):
    return await api_update_user_note(user_id, payload, db)


@router.get("/groups", dependencies=[Depends(require_api_auth)])
async def api_list_groups(db: Session = Depends(get_session)):
    groups = db.exec(select(Group).order_by(Group.path)).all()
    counts = dict(
        db.exec(
            select(Message.group_id, func.count())
            .where(Message.group_id.isnot(None))
            .group_by(Message.group_id)
        ).all()
    )
    return {
        "items": [
            {
                "id": g.id, "name": g.name, "icon": g.icon or "📁",
                "parent_id": g.parent_id,
                "path": g.path, "message_count": counts.get(g.id, 0),
            }
            for g in groups
        ]
    }


@router.post("/groups", dependencies=[Depends(require_api_auth)])
async def api_create_group(payload: GroupCreate, db: Session = Depends(get_session)):
    if payload.parent_id:
        parent = db.get(Group, payload.parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent group not found")
        path = f"{parent.path}/{payload.name}"
    else:
        path = f"/{payload.name}"
    existing = db.exec(select(Group).where(Group.path == path)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Group already exists at this path")
    icon = payload.icon if payload.icon in GROUP_ICONS else "📁"
    group = Group(name=payload.name, icon=icon, parent_id=payload.parent_id, path=path, created_at=datetime.utcnow())
    db.add(group)
    db.commit()
    db.refresh(group)
    return {"id": group.id, "name": group.name, "icon": group.icon, "path": group.path}


@router.patch("/groups/{group_id}", dependencies=[Depends(require_api_auth)])
async def api_update_group(group_id: int, payload: GroupUpdate, db: Session = Depends(get_session)):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if payload.icon and payload.icon in GROUP_ICONS:
        group.icon = payload.icon
    if payload.name and payload.name != group.name:
        old_path = group.path
        if group.parent_id:
            parent = db.get(Group, group.parent_id)
            new_path = f"{parent.path}/{payload.name}" if parent else f"/{payload.name}"
        else:
            new_path = f"/{payload.name}"
        group.name = payload.name
        group.path = new_path
        for d in db.exec(select(Group).where(Group.path.startswith(old_path + "/"))).all():
            d.path = new_path + d.path[len(old_path):]
    db.commit()
    return {"ok": True}


@router.get("/groups/icons", dependencies=[Depends(require_api_auth)])
async def api_group_icons():
    return {"icons": GROUP_ICONS}


@router.delete("/groups/{group_id}", dependencies=[Depends(require_api_auth)])
async def api_delete_group(group_id: int, db: Session = Depends(get_session)):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    parent_id = group.parent_id
    for child in db.exec(select(Group).where(Group.parent_id == group_id)).all():
        child.parent_id = parent_id
    for msg in db.exec(select(Message).where(Message.group_id == group_id)).all():
        msg.group_id = parent_id
    db.delete(group)
    db.commit()
    _rebuild_group_paths(db)
    return {"ok": True}


def _rebuild_group_paths(db: Session):
    groups = db.exec(select(Group)).all()
    gmap = {g.id: g for g in groups}

    def _path(g):
        if g.parent_id and g.parent_id in gmap:
            return f"{_path(gmap[g.parent_id])}/{g.name}"
        return f"/{g.name}"

    for g in groups:
        g.path = _path(g)
    db.commit()


@router.get("/logs", dependencies=[Depends(require_api_auth)])
async def api_logs(
    level: str | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
):
    settings = get_settings()
    log_file = os.path.join(settings.data_path, "logs", "bot.log")
    lines = _tail(log_file, limit)
    if level:
        needle = f"[{level.upper()}]"
        lines = [line for line in lines if needle in line]
    return {"log_file": log_file, "lines": lines}


@router.get("/settings", dependencies=[Depends(require_api_auth)])
async def api_settings():
    settings = get_settings()
    return {
        "BOT_TOKEN": _mask(settings.bot_token),
        "BOT_OWNER_ID": settings.bot_owner_id,
        "TG_API_ID": settings.tg_api_id,
        "TG_API_HASH": _mask(settings.tg_api_hash),
        "TGAPI_PORT": settings.tgapi_port,
        "SSH_USER": settings.ssh_user,
        "SSH_HOST": settings.ssh_host,
        "SSH_PORT": settings.ssh_port,
        "SOCKS_PORT": settings.socks_port,
        "SAVE_PATH": settings.save_path,
        "DATA_PATH": settings.data_path,
        "SSH_KEY_PATH": settings.ssh_key_path,
        "WEB_PORT": settings.web_port,
        "ADMIN_PASSWORD": _mask(settings.admin_password),
        "LOG_LEVEL": settings.log_level,
        "TIMEZONE": settings.timezone,
    }


def _count_since(db: Session, dt: datetime) -> int:
    return db.exec(select(func.count()).select_from(Message).where(Message.created_at >= dt)).one()


def _message_summary(msg: Message, group: Group | None = None) -> dict:
    return jsonable_encoder(
        {
            "id": msg.id,
            "telegram_message_id": msg.telegram_message_id,
            "user_id": msg.user_id,
            "chat_id": msg.chat_id,
            "type": msg.type,
            "text": msg.text,
            "file_path": msg.file_path,
            "file_size": msg.file_size,
            "mime_type": msg.mime_type,
            "group_id": msg.group_id,
            "group_name": group.name if group else None,
            "group_icon": group.icon if group else None,
            "group_path": group.path if group else None,
            "created_at": msg.created_at,
            "media_url": f"/media/{msg.file_path}" if msg.file_path else None,
        }
    )


def _message_detail(msg: Message, group: Group | None = None) -> dict:
    data = _message_summary(msg, group)
    data.update(
        jsonable_encoder(
            {
                "duration": msg.duration,
                "width": msg.width,
                "height": msg.height,
                "forwarded_from": msg.forwarded_from,
                "raw_json": _parse_raw_json(msg.raw_json),
            }
        )
    )
    return data


def _groups_for_messages(db: Session, messages: list[Message]) -> dict[int, Group]:
    group_ids = {msg.group_id for msg in messages if msg.group_id}
    if not group_ids:
        return {}
    groups = db.exec(select(Group).where(Group.id.in_(group_ids))).all()
    return {group.id: group for group in groups if group.id is not None}


def _user_dict(user: User) -> dict:
    return jsonable_encoder(
        {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "allowed": user.allowed,
            "notes": user.notes,
            "added_at": user.added_at,
            "last_seen_at": user.last_seen_at,
        }
    )


def _delete_message(message_id: int, db: Session) -> bool:
    settings = get_settings()
    msg = db.get(Message, message_id)
    if not msg:
        return False
    if msg.file_path:
        base = Path(settings.save_path).resolve()
        target = (base / msg.file_path).resolve()
        if (base in target.parents or target == base) and target.is_file():
            try:
                os.remove(target)
            except OSError:
                pass
    db.delete(msg)
    db.commit()
    return True


def _parse_raw_json(raw: str) -> dict | str:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid date format, expected YYYY-MM-DD") from exc


def _dir_size(path: str) -> int:
    total = 0
    if not os.path.exists(path):
        return 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _tail(path: str, count: int) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as file:
        return [line.rstrip("\n") for line in file.readlines()[-count:]]


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"
