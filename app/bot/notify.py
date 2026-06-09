import logging
import traceback

from telegram import BotCommand

from app.config import get_settings

logger = logging.getLogger(__name__)


async def register_commands(app) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("start", "开始使用"),
            BotCommand("id", "查看我的 user ID"),
            BotCommand("stats", "查看统计信息"),
            BotCommand("search", "搜索历史消息"),
            BotCommand("queue", "查看下载队列"),
            BotCommand("groups", "查看分组列表"),
            BotCommand("newgroup", "创建分组"),
            BotCommand("mv", "移动消息到分组"),
            BotCommand("help", "查看命令列表"),
        ]
    )


async def error_handler(update, context) -> None:
    settings = get_settings()
    err = context.error
    logger.error("Unhandled error", exc_info=err)

    tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    tb_short = tb[-3000:]

    try:
        await context.bot.send_message(
            chat_id=settings.bot_owner_id,
            text=f"Bot 错误\n```\n{tb_short}\n```",
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Failed to send error notification to owner")
