import asyncio
import logging
import os
import time
from collections.abc import Callable, Coroutine
from datetime import datetime
from functools import wraps
from typing import Any

import httpx
from sqlmodel import Session

from app.bot.saver import guess_ext, save_message_record, save_telegram_file
from app.config import get_settings
from app.db import engine
from app.models import User

logger = logging.getLogger(__name__)

LARGE_FILE_BYTES = 50 * 1024 * 1024
PROGRESS_INTERVAL = 5
MAX_CONCURRENT_DOWNLOADS = 3

_download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
_claimed_files: set[str] = set()

_TYPE_LABELS = {
    "video": "视频", "audio": "音频", "document": "文件",
    "voice": "语音", "animation": "动图", "photo": "图片", "sticker": "贴纸",
}


def user_display_name(user) -> str | None:
    parts = [user.first_name or "", user.last_name or ""]
    return " ".join(part for part in parts if part).strip() or None


def record_user_seen(user) -> tuple[bool, bool]:
    settings = get_settings()
    now = datetime.utcnow()
    with Session(engine) as session:
        db_user = session.get(User, user.id)
        is_new = db_user is None
        if is_new:
            db_user = User(
                id=user.id,
                username=user.username,
                display_name=user_display_name(user),
                allowed=user.id == settings.bot_owner_id,
                added_at=now,
                last_seen_at=now,
            )
            session.add(db_user)
        else:
            db_user.username = user.username
            db_user.display_name = user_display_name(user)
            db_user.last_seen_at = now
            if user.id == settings.bot_owner_id:
                db_user.allowed = True
        session.commit()
        return bool(db_user.allowed), is_new


def require_allowed(func: Callable[..., Coroutine[Any, Any, None]]):
    @wraps(func)
    async def wrapper(update, context) -> None:
        user = update.effective_user
        message = update.effective_message
        if not user or not message:
            return

        allowed, is_new = record_user_seen(user)
        if not allowed:
            if is_new:
                await message.reply_text("抱歉，本 bot 不对外开放。")
            return

        await func(update, context)

    return wrapper


@require_allowed
async def handle_text(update, context) -> None:
    db_id = await save_message_record(update.message, type_="text")
    await update.message.reply_text(f"已保存（消息 #{db_id}）")


@require_allowed
async def handle_photo(update, context) -> None:
    photo = update.message.photo[-1]
    await _save_media(
        update,
        context,
        type_="photo",
        file_id=photo.file_id,
        fallback_ext=".jpg",
        file_size=photo.file_size,
        width=photo.width,
        height=photo.height,
    )


@require_allowed
async def handle_video(update, context) -> None:
    video = update.message.video
    await _save_media(
        update,
        context,
        type_="video",
        file_id=video.file_id,
        fallback_ext=guess_ext(getattr(video, "file_name", None), video.mime_type, ".mp4"),
        original_name=getattr(video, "file_name", None),
        file_size=video.file_size,
        mime_type=video.mime_type,
        duration=video.duration,
        width=video.width,
        height=video.height,
    )


@require_allowed
async def handle_document(update, context) -> None:
    document = update.message.document
    ext = guess_ext(document.file_name, document.mime_type, "")
    await _save_media(
        update,
        context,
        type_="document",
        file_id=document.file_id,
        fallback_ext=ext,
        original_name=document.file_name,
        file_size=document.file_size,
        mime_type=document.mime_type,
    )


@require_allowed
async def handle_voice(update, context) -> None:
    voice = update.message.voice
    await _save_media(
        update,
        context,
        type_="voice",
        file_id=voice.file_id,
        fallback_ext=".ogg",
        file_size=voice.file_size,
        mime_type=voice.mime_type,
        duration=voice.duration,
    )


@require_allowed
async def handle_audio(update, context) -> None:
    audio = update.message.audio
    await _save_media(
        update,
        context,
        type_="audio",
        file_id=audio.file_id,
        fallback_ext=guess_ext(getattr(audio, "file_name", None), audio.mime_type, ".mp3"),
        original_name=getattr(audio, "file_name", None),
        file_size=audio.file_size,
        mime_type=audio.mime_type,
        duration=audio.duration,
    )


@require_allowed
async def handle_animation(update, context) -> None:
    animation = update.message.animation
    await _save_media(
        update,
        context,
        type_="animation",
        file_id=animation.file_id,
        fallback_ext=guess_ext(getattr(animation, "file_name", None), animation.mime_type, ".mp4"),
        original_name=getattr(animation, "file_name", None),
        file_size=animation.file_size,
        mime_type=animation.mime_type,
        duration=animation.duration,
        width=animation.width,
        height=animation.height,
    )


@require_allowed
async def handle_sticker(update, context) -> None:
    sticker = update.message.sticker
    if getattr(sticker, "is_animated", False):
        ext = ".tgs"
    elif getattr(sticker, "is_video", False):
        ext = ".webm"
    else:
        ext = ".webp"
    await _save_media(
        update,
        context,
        type_="sticker",
        file_id=sticker.file_id,
        fallback_ext=ext,
        file_size=sticker.file_size,
        width=sticker.width,
        height=sticker.height,
    )


def _media_display_name(
    type_: str, original_name: str | None, file_size: int,
) -> str:
    if original_name:
        return original_name
    label = _TYPE_LABELS.get(type_, type_)
    return f"{label} ({_format_size(file_size)})"


def _format_size(n: int) -> str:
    if n >= 1024 * 1024 * 1024:
        return f"{n / 1024 / 1024 / 1024:.1f} GB"
    return f"{n / 1024 / 1024:.1f} MB"


def _progress_bar(percent: int, width: int = 10) -> str:
    filled = int(width * percent / 100)
    return "█" * filled + "░" * (width - filled)


def _scan_dir_sizes(base_dir: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for root, _, files in os.walk(base_dir):
        for f in files:
            fp = os.path.join(root, f)
            try:
                result[fp] = os.path.getsize(fp)
            except OSError:
                pass
    return result


def _find_growing_file(
    before: dict[str, int],
    after: dict[str, int],
    exclude: set[str] | None = None,
) -> tuple[str | None, int]:
    best_path = None
    best_size = 0
    for path, size in after.items():
        if exclude and path in exclude:
            continue
        if size > before.get(path, 0) and size > best_size:
            best_path = path
            best_size = size
    return best_path, best_size


async def _download_with_progress(
    bot,
    file_id: str,
    msg,
    type_: str,
    ext: str,
    original_name: str | None,
    notice,
    expected_size: int,
    display_name: str,
) -> tuple[str, int | None]:
    settings = get_settings()
    tgapi_dir = settings.tgapi_dir

    before = _scan_dir_sizes(tgapi_dir)
    download_task = asyncio.create_task(
        save_telegram_file(
            bot, file_id=file_id, msg=msg, type_=type_, ext=ext,
            original_name=original_name,
        )
    )

    last_percent = -1
    start_time = time.monotonic()
    growing_file: str | None = None

    api_url = (
        f"https://api.telegram.org/bot{settings.bot_token}/editMessageText"
    )
    edit_base = {"chat_id": msg.chat.id, "message_id": notice.message_id}

    progress_client = httpx.AsyncClient(
        proxy=f"socks5://127.0.0.1:{settings.socks_port}",
        timeout=httpx.Timeout(4, connect=3),
    )

    try:
        while not download_task.done():
            done, _ = await asyncio.wait(
                {download_task}, timeout=PROGRESS_INTERVAL
            )
            if done:
                break

            current_size = 0
            if growing_file:
                try:
                    current_size = os.path.getsize(growing_file)
                except OSError:
                    growing_file = None

            if not growing_file:
                after = _scan_dir_sizes(tgapi_dir)
                growing_file, current_size = _find_growing_file(
                    before, after, exclude=_claimed_files
                )
                if growing_file:
                    _claimed_files.add(growing_file)

            if current_size <= 0 or expected_size <= 0:
                continue

            percent = min(int(current_size / expected_size * 100), 99)
            if percent <= last_percent:
                continue

            elapsed = time.monotonic() - start_time
            speed = current_size / elapsed if elapsed > 0 else 0
            text = f"{display_name} 下载中\n{_progress_bar(percent)} {percent}%\n"
            text += (
                f"{_format_size(current_size)} / {_format_size(expected_size)}"
            )
            if speed > 0:
                eta = int((expected_size - current_size) / speed)
                text += f" | {_format_size(int(speed))}/s | ~{eta}s"

            try:
                await progress_client.post(
                    api_url, json={**edit_base, "text": text}
                )
            except Exception as exc:
                logger.debug("Progress edit failed: %s", exc)

            last_percent = percent
    except Exception:
        if not download_task.done():
            download_task.cancel()
        raise
    finally:
        if growing_file:
            _claimed_files.discard(growing_file)
        await progress_client.aclose()

    return download_task.result()


async def _save_media(
    update,
    context,
    type_: str,
    file_id: str,
    fallback_ext: str,
    original_name: str | None = None,
    **fields,
) -> None:
    msg = update.message
    file_size = fields.get("file_size") or 0
    is_large = file_size > LARGE_FILE_BYTES
    display_name = _media_display_name(type_, original_name, file_size)

    notice = None
    queued = False
    if is_large:
        if _download_semaphore.locked():
            queued = True
            notice = await msg.reply_text(
                f"{display_name} 排队中，前方还有下载任务..."
            )
        else:
            notice = await msg.reply_text(
                f"{display_name} 下载中\n"
                f"{_progress_bar(0)} 0%\n"
                f"0.0 MB / {_format_size(file_size)}"
            )

    try:
        if is_large:
            async with _download_semaphore:
                if notice and queued:
                    await notice.edit_text(
                        f"{display_name} 下载中\n"
                        f"{_progress_bar(0)} 0%\n"
                        f"0.0 MB / {_format_size(file_size)}"
                    )
                rel_path, actual_size = await _download_with_progress(
                    context.bot, file_id, msg, type_, fallback_ext,
                    original_name, notice, file_size, display_name,
                )
        else:
            rel_path, actual_size = await save_telegram_file(
                context.bot,
                file_id=file_id,
                msg=msg,
                type_=type_,
                ext=fallback_ext,
                original_name=original_name,
            )
    except Exception as exc:
        error_text = "NAS 存储空间不足或文件写入失败" if isinstance(exc, OSError) else "下载失败，请检查网络或稍后重试"
        if notice:
            await notice.edit_text(f"{display_name} {error_text}")
        else:
            await msg.reply_text(error_text)
        logger.error("Save media failed [%s]: %s", display_name, exc)
        return

    if actual_size is not None:
        fields["file_size"] = actual_size
    db_id = await save_message_record(msg, type_=type_, file_path=rel_path, **fields)
    done = f"{display_name} 已保存（#{db_id}）"
    if notice:
        await notice.edit_text(done)
    else:
        await msg.reply_text(done)
