import os
from datetime import datetime

from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine

from app.config import get_settings
from app.models import User

settings = get_settings()
db_file = os.path.join(settings.data_path, "bot.db")

engine = create_engine(
    f"sqlite:///{db_file}",
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    os.makedirs(settings.data_path, exist_ok=True)
    SQLModel.metadata.create_all(engine)

    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        # migrate: add columns if missing
        for stmt in (
            "ALTER TABLE messages ADD COLUMN group_id INTEGER",
            "ALTER TABLE messages ADD COLUMN bundle_id TEXT",
            "ALTER TABLE groups ADD COLUMN icon TEXT DEFAULT '📁'",
        ):
            try:
                conn.execute(text(stmt))
            except Exception:
                pass
        conn.commit()

    with Session(engine) as session:
        owner = session.get(User, settings.bot_owner_id)
        if not owner:
            session.add(
                User(
                    id=settings.bot_owner_id,
                    allowed=True,
                    notes="owner (auto-created)",
                    added_at=datetime.utcnow(),
                )
            )
            session.commit()


def get_session():
    with Session(engine) as session:
        yield session
