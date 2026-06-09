import asyncio
import logging

import uvicorn

from app.bot.main import build_application
from app.config import get_settings
from app.db import init_db
from app.utils.logging_setup import setup_logging
from app.web.main import build_app


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    settings = get_settings()

    logger.info("Initializing database...")
    init_db()

    logger.info("Building bot...")
    bot_app = build_application()

    logger.info("Building web...")
    web_app = build_app()

    web_config = uvicorn.Config(
        web_app,
        host="0.0.0.0",
        port=settings.web_port,
        log_level=settings.log_level.lower(),
    )
    web_server = uvicorn.Server(web_config)

    await bot_app.initialize()
    await bot_app.start()
    if bot_app.post_init:
        await bot_app.post_init(bot_app)
    await bot_app.updater.start_polling()

    logger.info("Bot running, web at :%s", settings.web_port)

    try:
        await web_server.serve()
    finally:
        logger.info("Shutting down...")
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
