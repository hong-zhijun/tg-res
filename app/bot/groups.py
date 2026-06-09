"""Group tree CRUD and inline-keyboard builder."""

import logging
from datetime import datetime

from sqlmodel import Session, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.db import engine
from app.models import Group

logger = logging.getLogger(__name__)

GROUP_SELECT_TIMEOUT = 60  # auto-save if no selection


# ---- Queries ----

def has_groups() -> bool:
    with Session(engine) as session:
        return session.exec(select(Group).limit(1)).first() is not None


def get_group(group_id: int) -> Group | None:
    with Session(engine) as session:
        return session.get(Group, group_id)


def get_children(parent_id: int | None) -> list[Group]:
    with Session(engine) as session:
        stmt = select(Group).where(Group.parent_id == parent_id).order_by(Group.name)
        return list(session.exec(stmt).all())


def get_all_groups_tree() -> str:
    with Session(engine) as session:
        groups = list(session.exec(select(Group).order_by(Group.path)).all())
    if not groups:
        return "还没有分组。使用 /newgroup 名称 创建第一个分组。"
    lines = ["📁 分组列表："]
    for g in groups:
        depth = g.path.count("/") - 1
        indent = "  " * depth
        lines.append(f"{indent}📁 {g.name}")
    return "\n".join(lines)


# ---- Mutations ----

def create_group(name: str, parent_id: int | None = None) -> Group:
    with Session(engine) as session:
        if parent_id:
            parent = session.get(Group, parent_id)
            path = f"{parent.path}/{name}" if parent else f"/{name}"
        else:
            path = f"/{name}"
        group = Group(name=name, parent_id=parent_id, path=path, created_at=datetime.utcnow())
        session.add(group)
        session.commit()
        session.refresh(group)
        return group


def get_or_create_by_path(path_str: str) -> Group:
    """Create group and all ancestors. '旅行/日本/东京' → 3 groups."""
    parts = [p.strip() for p in path_str.strip("/").split("/") if p.strip()]
    if not parts:
        raise ValueError("Empty group path")
    parent_id: int | None = None
    current_path = ""
    group: Group | None = None
    with Session(engine) as session:
        for part in parts:
            current_path += f"/{part}"
            stmt = select(Group).where(Group.path == current_path)
            group = session.exec(stmt).first()
            if not group:
                group = Group(name=part, parent_id=parent_id, path=current_path, created_at=datetime.utcnow())
                session.add(group)
                session.commit()
                session.refresh(group)
            parent_id = group.id
    assert group is not None
    return group


# ---- Keyboard builder ----

def build_group_keyboard(
    pending_id: str,
    parent_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    """Returns (header_text, keyboard)."""
    children = get_children(parent_id)

    # Breadcrumb header
    if parent_id:
        group = get_group(parent_id)
        header = f"📁 {group.path.strip('/')} >" if group else "选择分组："
    else:
        header = "选择分组："

    buttons: list[list[InlineKeyboardButton]] = []

    # Group buttons, 2 per row
    row: list[InlineKeyboardButton] = []
    for child in children:
        row.append(InlineKeyboardButton(
            f"📁 {child.name}",
            callback_data=f"g:{pending_id}:{child.id}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Action row
    actions: list[InlineKeyboardButton] = []
    if parent_id is not None:
        parent = get_group(parent_id)
        back_target = parent.parent_id if parent else 0
        actions.append(InlineKeyboardButton("⬅️ 返回", callback_data=f"gb:{pending_id}:{back_target or 0}"))
        actions.append(InlineKeyboardButton("✅ 存这里", callback_data=f"gs:{pending_id}:{parent_id}"))
    actions.append(InlineKeyboardButton("➕ 新建", callback_data=f"gn:{pending_id}:{parent_id or 0}"))
    buttons.append(actions)

    # Direct save
    buttons.append([InlineKeyboardButton("📥 直接保存", callback_data=f"gs:{pending_id}:0")])

    return header, InlineKeyboardMarkup(buttons)
