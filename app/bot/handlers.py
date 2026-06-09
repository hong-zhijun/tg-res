import asyncio
import logging
import os
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
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
MEDIA_GROUP_WAIT = 1.0

_download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
_claimed_files: set[str] = set()

_TYPE_LABELS = {
    "video": "视频", "audio": "音频", "document": "文件",
    "voice": "语音", "animation": "动图", "photo": "图片", "sticker": "贴纸",
}


# ---- Download queue tracking ----

@dataclass
class _DownloadEntry:
    display_name: str
    file_size: int
    status: str  # "queued" | "downloading"


_active_downloads: list[_DownloadEntry] = []


def get_queue_status() -> str:
    """Build queue status string for /queue command."""
    if not _active_downloads and not _media_group_buffer:
        return "当前没有下载任务。"

    lines = ["📥 下载队列："]

    for i, entry in enumerate(_active_downloads, 1):
        icon = "⬇️" if entry.status == "downloading" else "⏳"
        status_text = "下载中" if entry.status == "downloading" else "排队中"
        lines.append(f"{icon} {i}. {entry.display_name} ({_format_size(entry.file_size)}) - {status_text}")

    for items in _media_group_buffer.values():
        total = sum(it.fields.get("file_size", 0) for it in items)
        lines.append(f"📦 媒体组（{len(items)} 个文件，{_format_size(total)}）- 等待中")

    downloading = sum(1 for d in _active_downloads if d.status == "downloading")
    queued = sum(1 for d in _active_downloads if d.status == "queued")
    lines.append(f"\n活跃 {downloading}/{MAX_CONCURRENT_DOWNLOADS} | 排队 {queued}")
    return "\n".join(lines)


# ---- Media group batching ----

@dataclass
class _PendingMedia:
    update: Any
    context: Any
    type_: str
    file_id: str
    fallback_ext: str
    original_name: str | None
    fields: dict


_media_group_buffer: dict[str, list[_PendingMedia]] = {}
_media_group_tasks: dict[str, asyncio.Task] = {}


async def _buffer_media_group(
    update, context, group_id, *,
    type_, file_id, fallback_ext, original_name, fields,
):
    """Buffer a media item; start a timer to batch-process the group."""
    item = _PendingMedia(
        update=update, context=context,
        type_=type_, file_id=file_id, fallback_ext=fallback_ext,
        original_name=original_name, fields=fields,
    )
    _media_group_buffer.setdefault(group_id, []).append(item)

    existing = _media_group_tasks.get(group_id)
    if not existing or existing.done():
        _media_group_tasks[group_id] = asyncio.create_task(
            _process_media_group(group_id)
        )


async def _process_media_group(group_id: str):
    """Wait for all items, then download with a single notification."""
    await asyncio.sleep(MEDIA_GROUP_WAIT)

    items = _media_group_buffer.pop(group_id, [])
    _media_group_tasks.pop(group_id, None)
    if not items:
        return

    count = len(items)
    total_size = sum(it.fields.get("file_size", 0) for it in items)

    type_counts: dict[str, int] = {}
    for it in items:
        label = _TYPE_LABELS.get(it.type_, it.type_)
        type_counts[label] = type_counts.get(label, 0) + 1
    type_desc = "、".join(f"{v}{k}" for k, v in type_counts.items())

    first_msg = items[0].update.message
    notice = await first_msg.reply_text(
        f"📦 媒体组（{type_desc}，共 {_format_size(total_size)}）\n"
        f"准备下载 {count} 个文件..."
    )

    saved_ids: list[int] = []
    failed_count = 0

    for i, item in enumerate(items, 1):
        msg = item.update.message
        file_size = item.fields.get("file_size", 0)
        is_large = file_size > LARGE_FILE_BYTES
        display_name = _media_display_name(item.type_, item.original_name, file_size)
        prefix = f"📦 [{i}/{count}] "

        entry: _DownloadEntry | None = None
        try:
            if is_large:
                ahead = len(_active_downloads)
                entry = _DownloadEntry(display_name, file_size, "queued")
                _active_downloads.append(entry)

                if _download_semaphore.locked():
                    try:
                        await notice.edit_text(
                            f"{prefix}{display_name} 排队中（前方 {ahead} 个任务）"
                        )
                    except Exception:
                        pass

                async with _download_semaphore:
                    entry.status = "downloading"
                    try:
                        await notice.edit_text(
                            f"{prefix}{display_name} 下载中\n"
                            f"{_progress_bar(0)} 0%\n"
                            f"0.0 MB / {_format_size(file_size)}"
                        )
                    except Exception:
                        pass
                    rel_path, actual_size = await _download_with_progress(
                        item.context.bot, item.file_id, msg,
                        item.type_, item.fallback_ext, item.original_name,
                        notice, file_size, display_name, prefix=prefix,
                    )
            else:
                try:
                    await notice.edit_text(f"{prefix}{display_name} 下载中...")
                except Exception:
                    pass
                rel_path, actual_size = await save_telegram_file(
                    item.context.bot,
                    file_id=item.file_id, msg=msg,
                    type_=item.type_, ext=item.fallback_ext,
                    original_name=item.original_name,
                )

            fields = dict(item.fields)
            if actual_size is not None:
                fields["file_size"] = actual_size
            db_id = await save_message_record(
                msg, type_=item.type_, file_path=rel_path, **fields
            )
            saved_ids.append(db_id)

        except Exception as exc:
            failed_count += 1
            logger.error("Media group item failed [%s]: %s", display_name, exc)
        finally:
            if entry and entry in _active_downloads:
                _active_downloads.remove(entry)

    if failed_count == 0:
        id_list = ", ".join(f"#{d}" for d in saved_ids)
        await notice.edit_text(f"📦 媒体组（{count} 个文件）已全部保存\n{id_list}")
    else:
        await notice.edit_text(
            f"📦 媒体组完成：✅ {len(saved_ids)} 已保存，❌ {failed_count} 失败"
        )


# ---- User management ----

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


# ---- Media handlers ----

@require_allowed
async def handle_text(update, context) -> None:
    db_id = await save_message_record(update.message, type_="text")
    await update.message.reply_text(f"已保存（消息 #{db_id}）")


@require_allowed
async def handle_photo(update, context) -> None:
    photo = update.message.photo[-1]
    await _save_media(
        update, context, type_="photo",
        file_id=photo.file_id, fallback_ext=".jpg",
        file_size=photo.file_size,
        width=photo.width, height=photo.height,
    )


@require_allowed
async def handle_video(update, context) -> None:
    video = update.message.video
    await _save_media(
        update, context, type_="video",
        file_id=video.file_id,
        fallback_ext=guess_ext(getattr(video, "file_name", None), video.mime_type, ".mp4"),
        original_name=getattr(video, "file_name", None),
        file_size=video.file_size, mime_type=video.mime_type,
        duration=video.duration, width=video.width, height=video.height,
    )


@require_allowed
async def handle_document(update, context) -> None:
    document = update.message.document
    ext = guess_ext(document.file_name, document.mime_type, "")
    await _save_media(
        update, context, type_="document",
        file_id=document.file_id, fallback_ext=ext,
        original_name=document.file_name,
        file_size=document.file_size, mime_type=document.mime_type,
    )


@require_allowed
async def handle_voice(update, context) -> None:
    voice = update.message.voice
    await _save_media(
        update, context, type_="voice",
        file_id=voice.file_id, fallback_ext=".ogg",
        file_size=voice.file_size, mime_type=voice.mime_type,
        duration=voice.duration,
    )


@require_allowed
async def handle_audio(update, context) -> None:
    audio = update.message.audio
    await _save_media(
        update, context, type_="audio",
        file_id=audio.file_id,
        fallback_ext=guess_ext(getattr(audio, "file_name", None), audio.mime_type, ".mp3"),
        original_name=getattr(audio, "file_name", None),
        file_size=audio.file_size, mime_type=audio.mime_type,
        duration=audio.duration,
    )


@require_allowed
async def handle_animation(update, context) -> None:
    animation = update.message.animation
    await _save_media(
        update, context, type_="animation",
        file_id=animation.file_id,
        fallback_ext=guess_ext(getattr(animation, "file_name", None), animation.mime_type, ".mp4"),
        original_name=getattr(animation, "file_name", None),
        file_size=animation.file_size, mime_type=animation.mime_type,
        duration=animation.duration,
        width=animation.width, height=animation.height,
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
        update, context, type_="sticker",
        file_id=sticker.file_id, fallback_ext=ext,
        file_size=sticker.file_size,
        width=sticker.width, height=sticker.height,
    )


# ---- Helpers ----

def _media_display_name(type_: str, original_name: str | None, file_size: int) -> str:
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


# ---- Download with progress ----

async def _download_with_progress(
    bot, file_id, msg, type_, ext, original_name,
    notice, expected_size, display_name, prefix="",
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

    api_url = f"https://api.telegram.org/bot{settings.bot_token}/editMessageText"
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
            text = f"{prefix}{display_name} 下载中\n{_progress_bar(percent)} {percent}%\n"
            text += f"{_format_size(current_size)} / {_format_size(expected_size)}"
            if speed > 0:
                eta = int((expected_size - current_size) / speed)
                text += f" | {_format_size(int(speed))}/s | ~{eta}s"

            try:
                await progress_client.post(api_url, json={**edit_base, "text": text})
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


# ---- Single file save ----

async def _save_media(
    update, context, type_, file_id, fallback_ext,
    original_name=None, **fields,
) -> None:
    msg = update.message

    # Media group: buffer for batch processing
    group_id = getattr(msg, "media_group_id", None)
    if group_id:
        await _buffer_media_group(
            update, context, group_id,
            type_=type_, file_id=file_id, fallback_ext=fallback_ext,
            original_name=original_name, fields=fields,
        )
        return

    # Single file processing
    file_size = fields.get("file_size") or 0
    is_large = file_size > LARGE_FILE_BYTES
    display_name = _media_display_name(type_, original_name, file_size)

    notice = None
    queued = False
    entry: _DownloadEntry | None = None

    if is_large:
        ahead = len(_active_downloads)
        if _download_semaphore.locked():
            queued = True
            entry = _DownloadEntry(display_name, file_size, "queued")
            _active_downloads.append(entry)
            notice = await msg.reply_text(
                f"{display_name} 排队中（前方 {ahead} 个任务）"
            )
        else:
            entry = _DownloadEntry(display_name, file_size, "downloading")
            _active_downloads.append(entry)
            notice = await msg.reply_text(
                f"{display_name} 下载中\n"
                f"{_progress_bar(0)} 0%\n"
                f"0.0 MB / {_format_size(file_size)}"
            )

    try:
        if is_large:
            async with _download_semaphore:
                if entry:
                    entry.status = "downloading"
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
                context.bot, file_id=file_id, msg=msg,
                type_=type_, ext=fallback_ext, original_name=original_name,
            )
    except Exception as exc:
        error_text = (
            "NAS 存储空间不足或文件写入失败"
            if isinstance(exc, OSError)
            else "下载失败，请检查网络或稍后重试"
        )
        if notice:
            await notice.edit_text(f"{display_name} {error_text}")
        else:
            await msg.reply_text(error_text)
        logger.error("Save media failed [%s]: %s", display_name, exc)
        return
    finally:
        if entry and entry in _active_downloads:
            _active_downloads.remove(entry)

    if actual_size is not None:
        fields["file_size"] = actual_size
    db_id = await save_message_record(msg, type_=type_, file_path=rel_path, **fields)
    done = f"{display_name} 已保存（#{db_id}）"
    if notice:
        await notice.edit_text(done)
    else:
        await msg.reply_text(done)
