import json
import mimetypes
import os
import shutil
from datetime import timezone
from pathlib import Path

from sqlmodel import Session

from app.config import get_settings
from app.db import engine
from app.models import Message
from app.utils.storage import build_save_path, ensure_disk_space


class IncompleteDownloadError(Exception):
    """Downloaded file is smaller than expected."""


def guess_ext(file_path: str | None, mime_type: str | None, fallback: str) -> str:
    if file_path:
        suffix = Path(file_path).suffix
        if suffix:
            return suffix
    if mime_type:
        guessed = mimetypes.guess_extension(mime_type)
        if guessed:
            return guessed
    return fallback


async def save_telegram_file(
    bot,
    file_id: str,
    msg,
    type_: str,
    ext: str,
    original_name: str | None = None,
    group_path: str | None = None,
) -> tuple[str, int | None]:
    settings = get_settings()
    telegram_file = await bot.get_file(file_id)
    rel_path = build_save_path(
        type_=type_,
        msg_id=msg.message_id,
        unique_id=telegram_file.file_unique_id,
        ext=ext,
        original_name=original_name,
        group_path=group_path,
    )
    abs_path = os.path.join(settings.save_path, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    ensure_disk_space(os.path.dirname(abs_path), telegram_file.file_size or 0)

    src = telegram_file.file_path
    if src and os.path.isabs(src) and os.path.exists(src):
        shutil.move(src, abs_path)
    else:
        await telegram_file.download_to_drive(abs_path)

    actual_on_disk = os.path.getsize(abs_path)
    if telegram_file.file_size and actual_on_disk < telegram_file.file_size:
        try:
            os.remove(abs_path)
        except OSError:
            pass
        raise IncompleteDownloadError(
            f"Expected {telegram_file.file_size} bytes, got {actual_on_disk}"
        )

    return rel_path, actual_on_disk


async def save_message_record(msg, type_: str, group_id: int | None = None, bundle_id: str | None = None, **fields) -> int:
    msg_date = msg.date
    if msg_date.tzinfo is not None:
        msg_date = msg_date.astimezone(timezone.utc).replace(tzinfo=None)

    record = Message(
        telegram_message_id=msg.message_id,
        user_id=msg.from_user.id,
        chat_id=msg.chat.id,
        type=type_,
        text=msg.text or msg.caption,
        raw_json=json.dumps(msg.to_dict(), ensure_ascii=False, default=str),
        created_at=msg_date,
        forwarded_from=_extract_forward_origin(msg),
        group_id=group_id,
        bundle_id=bundle_id,
        **fields,
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
        return int(record.id)


def _extract_forward_origin(msg) -> str | None:
    forward_origin = getattr(msg, "forward_origin", None)
    if forward_origin:
        return str(forward_origin)
    forward_from = getattr(msg, "forward_from", None)
    if forward_from:
        return str(forward_from)
    forward_sender_name = getattr(msg, "forward_sender_name", None)
    if forward_sender_name:
        return str(forward_sender_name)
    return None
