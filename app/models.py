from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int = Field(primary_key=True)
    username: Optional[str] = None
    display_name: Optional[str] = None
    allowed: bool = Field(default=False)
    notes: Optional[str] = None
    added_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: Optional[datetime] = None


class Group(SQLModel, table=True):
    __tablename__ = "groups"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    icon: str = Field(default="📁")
    parent_id: Optional[int] = Field(default=None, foreign_key="groups.id", index=True)
    path: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_message_id: int = Field(index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    chat_id: int

    type: str = Field(index=True)
    text: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    duration: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    forwarded_from: Optional[str] = None
    group_id: Optional[int] = Field(default=None, foreign_key="groups.id", index=True)
    bundle_id: Optional[str] = Field(default=None, index=True)
    raw_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MessageTag(SQLModel, table=True):
    __tablename__ = "message_tags"

    message_id: int = Field(foreign_key="messages.id", primary_key=True)
    tag_id: int = Field(foreign_key="tags.id", primary_key=True)
