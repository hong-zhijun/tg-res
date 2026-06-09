import os
import shutil
from datetime import datetime, timedelta

from sqlmodel import Session, func, select

from app.bot.groups import get_all_groups_tree, get_or_create_by_path
from app.bot.handlers import get_queue_status, record_user_seen, require_allowed
from app.config import get_settings
from app.db import engine
from app.models import Message


async def cmd_start(update, context) -> None:
    user_id = update.effective_user.id if update.effective_user else "unknown"
    if update.effective_user:
        record_user_seen(update.effective_user)
    await update.message.reply_text(f"你好！你的 user_id 是 {user_id}。使用 /help 查看命令。")


async def cmd_id(update, context) -> None:
    user_id = update.effective_user.id if update.effective_user else "unknown"
    if update.effective_user:
        record_user_seen(update.effective_user)
    await update.message.reply_text(f"你的 user_id: {user_id}")


@require_allowed
async def cmd_stats(update, context) -> None:
    settings = get_settings()
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    month_start = datetime(now.year, now.month, 1)

    with Session(engine) as session:
        total = session.exec(select(func.count()).select_from(Message)).one()
        today = session.exec(
            select(func.count()).select_from(Message).where(Message.created_at >= today_start)
        ).one()
        month = session.exec(
            select(func.count()).select_from(Message).where(Message.created_at >= month_start)
        ).one()

    await update.message.reply_text(
        "统计\n"
        f"今日：{today} 条\n"
        f"本月：{month} 条\n"
        f"总计：{total} 条\n"
        f"存储占用：{_format_bytes(_dir_size(settings.save_path))}"
    )


@require_allowed
async def cmd_search(update, context) -> None:
    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.message.reply_text("用法：/search 关键词")
        return

    with Session(engine) as session:
        items = session.exec(
            select(Message)
            .where(Message.text.contains(keyword))
            .order_by(Message.created_at.desc())
            .limit(10)
        ).all()

    if not items:
        await update.message.reply_text("没有找到匹配消息。")
        return

    lines = ["搜索结果："]
    for item in items:
        text = (item.text or item.file_path or "").replace("\n", " ")
        if len(text) > 50:
            text = text[:47] + "..."
        lines.append(f"#{item.id} {item.created_at:%Y-%m-%d} [{item.type}] {text}")
    await update.message.reply_text("\n".join(lines))


@require_allowed
async def cmd_queue(update, context) -> None:
    await update.message.reply_text(get_queue_status())


@require_allowed
async def cmd_groups(update, context) -> None:
    await update.message.reply_text(get_all_groups_tree())


@require_allowed
async def cmd_newgroup(update, context) -> None:
    path = " ".join(context.args).strip() if context.args else ""
    if not path:
        await update.message.reply_text("用法：/newgroup 分组路径\n例：/newgroup 旅行/日本/东京")
        return
    grp = get_or_create_by_path(path)
    icon = grp.icon or "📁"
    await update.message.reply_text(f"✅ {icon} 分组「{grp.path.strip('/')}」已创建")


@require_allowed
async def cmd_mv(update, context) -> None:
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("用法：/mv 消息ID 分组路径\n例：/mv 123 旅行/大阪")
        return
    try:
        msg_id = int(args[0])
    except ValueError:
        await update.message.reply_text("消息 ID 必须是数字。")
        return
    group_path = " ".join(args[1:])
    grp = get_or_create_by_path(group_path)
    settings = get_settings()
    with Session(engine) as session:
        record = session.get(Message, msg_id)
        if not record:
            await update.message.reply_text(f"消息 #{msg_id} 不存在。")
            return
        old_path = record.file_path
        if old_path:
            filename = os.path.basename(old_path)
            new_rel = os.path.join(grp.path.strip("/"), filename)
            old_abs = os.path.join(settings.save_path, old_path)
            new_abs = os.path.join(settings.save_path, new_rel)
            if os.path.exists(old_abs):
                os.makedirs(os.path.dirname(new_abs), exist_ok=True)
                shutil.move(old_abs, new_abs)
            record.file_path = new_rel
        record.group_id = grp.id
        session.commit()
    await update.message.reply_text(f"✅ #{msg_id} 已移到「{grp.path.strip('/')}」")


async def cmd_help(update, context) -> None:
    if update.effective_user:
        record_user_seen(update.effective_user)
    await update.message.reply_text(
        "/start - 开始使用\n"
        "/id - 查看我的 user_id\n"
        "/stats - 统计信息\n"
        "/search 关键词 - 搜索历史\n"
        "/queue - 查看下载队列\n"
        "/groups - 查看分组列表\n"
        "/newgroup 路径 - 创建分组\n"
        "/mv ID 路径 - 移动消息到分组\n"
        "/help - 显示此帮助"
    )


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


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
