from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.web.routes import auth, dashboard, logs, media, messages, settings as settings_route, users


def build_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="tgbot-saver admin", docs_url=None, redoc_url=None)
    app.add_middleware(SessionMiddleware, secret_key=settings.admin_password)

    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(messages.router)
    app.include_router(users.router)
    app.include_router(logs.router)
    app.include_router(settings_route.router)
    app.include_router(media.router)

    app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
    return app
