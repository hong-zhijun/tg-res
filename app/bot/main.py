import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

from app.bot.commands import cmd_groups, cmd_help, cmd_id, cmd_mv, cmd_newgroup, cmd_queue, cmd_search, cmd_start, cmd_stats
from app.bot.handlers import (
    handle_animation,
    handle_audio,
    handle_document,
    handle_group_callback,
    handle_photo,
    handle_sticker,
    handle_text,
    handle_video,
    handle_voice,
)
from app.bot.notify import error_handler, register_commands
from app.config import get_settings

logger = logging.getLogger(__name__)


async def post_init(app: Application) -> None:
    await register_commands(app)
    logger.info("Bot started, commands registered")


def build_application() -> Application:
    settings = get_settings()
    base_url = f"http://127.0.0.1:{settings.tgapi_port}/bot"
    base_file_url = f"http://127.0.0.1:{settings.tgapi_port}/file/bot"

    request = HTTPXRequest(
        connect_timeout=30, read_timeout=600,
        connection_pool_size=16, pool_timeout=30,
    )
    get_updates_request = HTTPXRequest(connect_timeout=30, read_timeout=60)

    app = (
        Application.builder()
        .token(settings.bot_token)
        .base_url(base_url)
        .base_file_url(base_file_url)
        .local_mode(True)
        .request(request)
        .get_updates_request(get_updates_request)
        .post_init(post_init)
        .concurrent_updates(True)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(CommandHandler("groups", cmd_groups))
    app.add_handler(CommandHandler("newgroup", cmd_newgroup))
    app.add_handler(CommandHandler("mv", cmd_mv))

    app.add_handler(CallbackQueryHandler(handle_group_callback, pattern=r"^g[sbni]?:"))

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.ANIMATION, handle_animation))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_error_handler(error_handler)
    return app
