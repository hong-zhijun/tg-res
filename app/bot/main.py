import logging

from telegram.ext import Application, CommandHandler
from telegram.request import HTTPXRequest

from app.bot.commands import cmd_help, cmd_id, cmd_search, cmd_start, cmd_stats
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

    request = HTTPXRequest(connect_timeout=30, read_timeout=600)
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
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_error_handler(error_handler)
    return app
