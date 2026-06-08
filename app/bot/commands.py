import os
from datetime import datetime, timedelta

from sqlmodel import Session, func, select

from app.bot.handlers import record_user_seen, require_allowed
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


async def cmd_help(update, context) -> None:
    if update.effective_user:
        record_user_seen(update.effective_user)
    await update.message.reply_text(
        "/start - 开始使用\n"
        "/id - 查看我的 user_id\n"
        "/stats - 统计信息\n"
        "/search 关键词 - 搜索历史\n"
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
