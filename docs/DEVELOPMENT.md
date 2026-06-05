# Telegram NAS 剪藏机器人 - 开发文档

> 配套文档：[REQUIREMENTS.md](./REQUIREMENTS.md)
> 目标读者：开发者 / AI 编码代理（Codex 等）
> 原则：本文档之外**不要做额外发挥**，需求不明确时优先选择"简单且可逆"的实现

---

## 1. 技术栈与版本

| 类别 | 选型 | 版本 | 说明 |
|------|------|------|------|
| 运行时 | Python | 3.12 | 用 `python:3.12-slim` 基础镜像 |
| Bot 框架 | python-telegram-bot | ~= 21.0 | 必须带 `[socks]` extra |
| Web 框架 | FastAPI | ~= 0.115 | |
| ASGI 服务器 | Uvicorn | ~= 0.32 | |
| ORM | SQLModel | ~= 0.0.22 | 基于 SQLAlchemy + Pydantic |
| 模板 | Jinja2 | ~= 3.1 | FastAPI 自带集成 |
| 表单 | python-multipart | ~= 0.0.12 | FastAPI 表单依赖 |
| 配置 | python-dotenv | ~= 1.0 | |
| 异步文件 IO | aiofiles | ~= 24.1 | |
| 时区 | zoneinfo（标准库） | - | |
| 系统包 | openssh-client, autossh | 系统版本 | 在 Dockerfile 装 |
| Telegram API 接入 | telegram-bot-api (C++ server) | 从 aiogram/telegram-bot-api 镜像拷贝二进制 | 本地模式运行，突破 20MB 下载限制 |

**注意**：python-telegram-bot 21.x 是 async-only 的，所有 handler 都是 `async def`。不要使用旧版同步 API。

---

## 2. 项目结构

```
tgbot-saver/
├── README.md
├── REQUIREMENTS.md
├── DEVELOPMENT.md
├── .gitignore
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── config.py              # 配置加载（从 env）
│   ├── db.py                  # 数据库引擎、session、init
│   ├── models.py              # SQLModel 表定义
│   ├── run.py                 # 主入口：并发跑 bot + web
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── main.py            # Application 构建、启动
│   │   ├── handlers.py        # 各消息类型的 handler
│   │   ├── commands.py        # /start /stats /search 等命令 handler
│   │   ├── saver.py           # 文件下载与落盘逻辑
│   │   └── notify.py          # 错误推送给 owner
│   ├── web/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI app 构建
│   │   ├── auth.py            # 登录、session 中间件
│   │   ├── deps.py            # 依赖注入（db session、当前用户）
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py        # /login /logout
│   │   │   ├── dashboard.py   # /
│   │   │   ├── messages.py    # /messages
│   │   │   ├── users.py       # /users
│   │   │   ├── logs.py        # /logs
│   │   │   ├── settings.py    # /settings
│   │   │   └── media.py       # /media/* 静态文件代理
│   │   ├── templates/
│   │   │   ├── base.html
│   │   │   ├── login.html
│   │   │   ├── dashboard.html
│   │   │   ├── messages_list.html
│   │   │   ├── messages_detail.html
│   │   │   ├── users.html
│   │   │   ├── logs.html
│   │   │   └── settings.html
│   │   └── static/
│   │       └── style.css      # 极简自定义样式
│   └── utils/
│       ├── __init__.py
│       ├── storage.py         # 路径生成、目录创建、磁盘空间检查
│       ├── logging_setup.py   # 日志配置
│       └── time.py            # 时区工具
└── scripts/
    ├── init_db.py             # 手动初始化数据库
    └── manual_test.md         # 手动测试清单
```

---

## 3. 配置与环境变量

### 3.1 `.env.example`

```dotenv
# ===== Bot 配置 =====
BOT_TOKEN=                          # 从 @BotFather 获得
BOT_OWNER_ID=                       # 你自己的 Telegram user ID（数字）

# ===== 自建 telegram-bot-api server =====
TG_API_ID=                          # 从 my.telegram.org 申请，绑普通账号
TG_API_HASH=                        # 同上
TGAPI_PORT=8081                     # 容器内本地监听端口，一般不动

# ===== 网络（SSH SOCKS 隧道）=====
SSH_USER=ubuntu                     # 美国服务器登录用户名
SSH_HOST=                           # 美国服务器 IP 或域名
SSH_PORT=22
SOCKS_PORT=1080                     # 容器内本地监听端口，一般不动

# ===== 路径（宿主机侧）=====
# 这些路径会被 docker-compose 挂载到容器
SAVE_PATH=/vol1/1000/tgbot/saved    # 媒体文件保存根目录
DATA_PATH=/vol1/1000/tgbot/data     # 数据库、日志、bot-api 工作目录

# ===== Web 后台 =====
WEB_PORT=8080                       # NAS 上对外暴露的端口
ADMIN_PASSWORD=                     # 管理页密码，首次部署时设置

# ===== 其它 =====
LOG_LEVEL=INFO                      # DEBUG / INFO / WARNING / ERROR
TIMEZONE=Asia/Shanghai
```

### 3.2 `app/config.py`

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    bot_token: str
    bot_owner_id: int

    # 自建 telegram-bot-api server
    tg_api_id: int
    tg_api_hash: str
    tgapi_port: int = 8081
    tgapi_dir: str = "/var/lib/telegram-bot-api"

    ssh_user: str
    ssh_host: str
    ssh_port: int = 22
    socks_port: int = 1080

    save_path: str = "/app/saved"       # 容器内路径
    data_path: str = "/app/data"
    ssh_key_path: str = "/app/data/ssh"

    web_port: int = 8080
    admin_password: str

    log_level: str = "INFO"
    timezone: str = "Asia/Shanghai"

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**注意路径转换**：`.env` 里的 `SAVE_PATH` / `DATA_PATH` 是宿主机路径，只给 docker-compose 挂载卷使用。容器内程序统一使用固定路径：`/app/saved`、`/app/data`、`/app/data/ssh`、`/var/lib/telegram-bot-api`，不感知宿主机路径。

---

## 4. 数据库设计

### 4.1 `app/models.py`

```python
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int = Field(primary_key=True)           # Telegram user ID（不自增）
    username: Optional[str] = None
    display_name: Optional[str] = None          # first_name + last_name
    allowed: bool = Field(default=False)
    notes: Optional[str] = None
    added_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: Optional[datetime] = None

class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_message_id: int = Field(index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    chat_id: int

    type: str = Field(index=True)
    # 枚举值: text, photo, video, document, voice, audio, animation, sticker

    text: Optional[str] = None                  # 文字内容或 caption
    file_path: Optional[str] = None             # 相对 SAVE_PATH 的路径
    file_size: Optional[int] = None             # 字节
    mime_type: Optional[str] = None
    duration: Optional[int] = None              # 秒，仅音视频
    width: Optional[int] = None
    height: Optional[int] = None

    forwarded_from: Optional[str] = None        # 原始发送者（字符串描述）

    raw_json: str = Field(default="{}")         # 原始 Telegram Message 对象 JSON

    created_at: datetime = Field(
        default_factory=datetime.utcnow, index=True
    )

class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class MessageTag(SQLModel, table=True):
    __tablename__ = "message_tags"

    message_id: int = Field(foreign_key="messages.id", primary_key=True)
    tag_id: int = Field(foreign_key="tags.id", primary_key=True)
```

### 4.2 `app/db.py`

```python
from sqlmodel import SQLModel, Session, create_engine
from app.config import get_settings
import os

settings = get_settings()
db_file = os.path.join(settings.data_path, "bot.db")

# 启用 WAL 模式，允许 bot 进程和 web 进程并发读写
engine = create_engine(
    f"sqlite:///{db_file}",
    connect_args={"check_same_thread": False},
)

def init_db():
    """创建表 + 启用 WAL + 写入 owner 用户"""
    os.makedirs(settings.data_path, exist_ok=True)
    SQLModel.metadata.create_all(engine)

    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()

    from app.models import User
    from datetime import datetime
    with Session(engine) as s:
        owner = s.get(User, settings.bot_owner_id)
        if not owner:
            s.add(User(
                id=settings.bot_owner_id,
                allowed=True,
                notes="owner (auto-created)",
                added_at=datetime.utcnow(),
            ))
            s.commit()

def get_session():
    """FastAPI 依赖注入用"""
    with Session(engine) as session:
        yield session
```

### 4.3 索引策略
- `messages.telegram_message_id` 索引（按 TG ID 查重/查找）
- `messages.user_id` 索引（按用户筛选）
- `messages.type` 索引（按类型筛选）
- `messages.created_at` 索引（时间排序）
- `tags.name` 唯一索引

不做复合索引，单用户数据量不需要。

---

## 5. Bot 模块

### 5.1 入口：`app/bot/main.py`

```python
import logging
from telegram import Update
from telegram.ext import (
    Application, MessageHandler, CommandHandler, filters
)
from telegram.request import HTTPXRequest

from app.config import get_settings
from app.bot.handlers import (
    handle_text, handle_photo, handle_video, handle_document,
    handle_voice, handle_audio, handle_animation, handle_sticker,
)
from app.bot.commands import (
    cmd_start, cmd_id, cmd_stats, cmd_search, cmd_help,
)
from app.bot.notify import error_handler, register_commands

logger = logging.getLogger(__name__)

async def post_init(app: Application):
    await register_commands(app)
    logger.info("Bot started, commands registered")

def build_application() -> Application:
    settings = get_settings()

    # 走容器内本地 telegram-bot-api server，不再需要代理（代理由 server 自己用）
    base_url = f"http://127.0.0.1:{settings.tgapi_port}/bot"
    base_file_url = f"http://127.0.0.1:{settings.tgapi_port}/file/bot"

    # 大文件下载耗时长，read_timeout 必须足够大
    request = HTTPXRequest(connect_timeout=30, read_timeout=600)
    get_updates_request = HTTPXRequest(connect_timeout=30, read_timeout=60)

    app = (
        Application.builder()
        .token(settings.bot_token)
        .base_url(base_url)
        .base_file_url(base_file_url)
        .local_mode(True)               # 关键：本地模式下 file_path 是绝对路径
        .request(request)
        .get_updates_request(get_updates_request)
        .post_init(post_init)
        .build()
    )

    # 命令
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("help", cmd_help))

    # 消息（顺序重要：specific → general）
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
```

### 5.2 白名单装饰器（`app/bot/handlers.py` 内）

```python
from functools import wraps
from datetime import datetime
from sqlmodel import Session, select
from app.db import engine
from app.models import User

def require_allowed(func):
    """白名单装饰器：非允许用户首次回拒绝消息，后续静默"""
    @wraps(func)
    async def wrapper(update, context):
        user = update.effective_user
        if not user:
            return

        with Session(engine) as s:
            db_user = s.get(User, user.id)
            now = datetime.utcnow()

            if not db_user:
                # 首次见到，记录并拒绝
                s.add(User(
                    id=user.id,
                    username=user.username,
                    display_name=f"{user.first_name or ''} {user.last_name or ''}".strip(),
                    allowed=False,
                    added_at=now,
                    last_seen_at=now,
                ))
                s.commit()
                await update.message.reply_text(
                    "抱歉，本 bot 不对外开放。"
                )
                return

            if not db_user.allowed:
                # 已知用户但被拒，静默
                db_user.last_seen_at = now
                s.commit()
                return

            # 通过
            db_user.last_seen_at = now
            db_user.username = user.username  # 更新最新信息
            s.commit()

        return await func(update, context)
    return wrapper
```

### 5.3 Handler 模板

每种消息类型的 handler 都遵循同样模板：

```python
@require_allowed
async def handle_photo(update, context):
    msg = update.message
    photo = msg.photo[-1]  # 最大尺寸

    # 1. 大文件先回执"下载中"，下载完再编辑
    is_large = photo.file_size and photo.file_size > 50 * 1024 * 1024
    notice = None
    if is_large:
        notice = await msg.reply_text("⏳ 下载中...")

    # 2. 下载（本地模式下其实是 shutil.move）
    file_path = await save_telegram_file(
        context.bot, photo.file_id, msg, type_="photo", ext=".jpg"
    )

    # 3. 写数据库
    db_id = await save_message_record(
        msg, type_="photo",
        file_path=file_path,
        file_size=photo.file_size,
        width=photo.width, height=photo.height,
    )

    # 4. 回执（大文件编辑 notice，小文件新发）
    done = f"✅ 已保存 photo → `{file_path}`（消息 #{db_id}）"
    if notice:
        await notice.edit_text(done, parse_mode="Markdown")
    else:
        await msg.reply_text(done, parse_mode="Markdown")
```

> 视频/文档等 handler 同理，把 `is_large` 阈值（50MB）作为"是否要回执下载中"的开关。

### 5.4 文件下载：`app/bot/saver.py`

```python
import os
import json
import shutil
from datetime import datetime
from sqlmodel import Session
from app.config import get_settings
from app.db import engine
from app.models import Message
from app.utils.storage import build_save_path, ensure_disk_space

settings = get_settings()

async def save_telegram_file(bot, file_id: str, msg, type_: str, ext: str) -> str:
    """在本地 bot-api server 模式下取文件，返回相对 SAVE_PATH 的路径。

    本地模式：`bot.get_file()` 返回的 file.file_path 是 telegram-bot-api 已经写好的
    容器内绝对路径，我们只需要把它移动到 SAVE_PATH 对应位置即可（同一文件系统
    走 rename，零拷贝）。
    """
    file = await bot.get_file(file_id)

    # 构造目标路径：{type}/{msg_id}_{file_unique_id}{ext}
    rel_path = build_save_path(type_, msg.message_id, file.file_unique_id, ext)
    abs_path = os.path.join(settings.save_path, rel_path)

    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    ensure_disk_space(os.path.dirname(abs_path), file.file_size or 0)

    src = file.file_path
    if src and os.path.isabs(src) and os.path.exists(src):
        # 本地模式正常路径
        shutil.move(src, abs_path)
    else:
        # 兜底（理论上不会进这里）：走旧的 HTTP 下载
        await file.download_to_drive(abs_path)

    return rel_path

async def save_message_record(msg, type_: str, **fields) -> int:
    """写消息到数据库，返回 message.id"""
    record = Message(
        telegram_message_id=msg.message_id,
        user_id=msg.from_user.id,
        chat_id=msg.chat.id,
        type=type_,
        text=msg.text or msg.caption,
        raw_json=json.dumps(msg.to_dict(), ensure_ascii=False, default=str),
        created_at=msg.date.replace(tzinfo=None),
        forwarded_from=_extract_forward_origin(msg),
        **fields,
    )
    with Session(engine) as s:
        s.add(record)
        s.commit()
        s.refresh(record)
        return record.id

def _extract_forward_origin(msg) -> str | None:
    if msg.forward_origin:
        return str(msg.forward_origin)
    return None

async def save_metadata_only(msg, type_: str) -> int:
    """仅记录元数据（用于超大文件）"""
    return await save_message_record(msg, type_=type_)
```

### 5.5 路径生成：`app/utils/storage.py`

```python
import os
import shutil
from app.config import get_settings

settings = get_settings()

def build_save_path(
    type_: str, msg_id: int, unique_id: str, ext: str
) -> str:
    """返回相对 SAVE_PATH 的路径"""
    safe_unique = "".join(c for c in unique_id if c.isalnum() or c in "-_")[:32]
    filename = f"{msg_id}_{safe_unique}{ext}"
    return os.path.join(type_, filename)

def ensure_disk_space(path: str, needed_bytes: int, buffer_mb: int = 100):
    """检查磁盘剩余空间，不足则抛 IOError"""
    stat = shutil.disk_usage(path)
    if stat.free < needed_bytes + buffer_mb * 1024 * 1024:
        raise IOError(
            f"Insufficient disk space: need {needed_bytes} bytes + {buffer_mb}MB buffer, "
            f"have {stat.free} bytes"
        )
```

### 5.6 命令实现：`app/bot/commands.py`

```python
from datetime import datetime, timedelta
from sqlmodel import Session, select, func
from app.db import engine
from app.models import Message
from app.bot.handlers import require_allowed
import os
from app.config import get_settings

settings = get_settings()

async def cmd_start(update, context):
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"👋 你好！你的 user_id 是 `{user_id}`。\n"
        f"使用 /help 查看可用命令。",
        parse_mode="Markdown",
    )

async def cmd_id(update, context):
    await update.message.reply_text(
        f"你的 user_id: `{update.effective_user.id}`",
        parse_mode="Markdown",
    )

@require_allowed
async def cmd_stats(update, context):
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    month_start = datetime(now.year, now.month, 1)

    with Session(engine) as s:
        today = s.exec(
            select(func.count()).select_from(Message)
            .where(Message.created_at >= today_start)
        ).one()
        month = s.exec(
            select(func.count()).select_from(Message)
            .where(Message.created_at >= month_start)
        ).one()
        total = s.exec(select(func.count()).select_from(Message)).one()

    # 计算存储占用
    storage_bytes = _dir_size(settings.save_path)
    storage_mb = storage_bytes / 1024 / 1024

    await update.message.reply_text(
        f"📊 统计\n"
        f"今日：{today}\n"
        f"本月：{month}\n"
        f"总计：{total}\n"
        f"存储：{storage_mb:.1f} MB"
    )

@require_allowed
async def cmd_search(update, context):
    if not context.args:
        await update.message.reply_text("用法：/search 关键词")
        return
    keyword = " ".join(context.args)

    with Session(engine) as s:
        results = s.exec(
            select(Message)
            .where(Message.text.like(f"%{keyword}%"))
            .order_by(Message.created_at.desc())
            .limit(10)
        ).all()

    if not results:
        await update.message.reply_text(f"未找到包含 `{keyword}` 的消息。",
                                        parse_mode="Markdown")
        return

    lines = [f"🔍 找到 {len(results)} 条："]
    for m in results:
        snippet = (m.text or "")[:50].replace("\n", " ")
        lines.append(f"#{m.id} [{m.type}] {m.created_at:%Y-%m-%d} {snippet}")
    await update.message.reply_text("\n".join(lines))

async def cmd_help(update, context):
    await update.message.reply_text(
        "📖 命令列表：\n"
        "/start - 开始使用\n"
        "/id - 查看我的 user_id\n"
        "/stats - 统计信息\n"
        "/search 关键词 - 搜索历史\n"
        "/help - 显示此帮助"
    )

def _dir_size(path: str) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total
```

### 5.7 错误处理与命令注册：`app/bot/notify.py`

```python
import logging
import traceback
from telegram import BotCommand
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

async def register_commands(app):
    await app.bot.set_my_commands([
        BotCommand("start", "开始使用"),
        BotCommand("id", "查看我的 user ID"),
        BotCommand("stats", "查看统计信息"),
        BotCommand("search", "搜索历史消息"),
        BotCommand("help", "查看命令列表"),
    ])

async def error_handler(update, context):
    err = context.error
    logger.error("Unhandled error", exc_info=err)

    tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    tb_short = tb[-3000:]  # Telegram 单条消息长度限制

    try:
        await context.bot.send_message(
            chat_id=settings.bot_owner_id,
            text=(
                f"⚠️ Bot 错误\n"
                f"```\n{tb_short}\n```"
            ),
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Failed to send error notification to owner")
```

---

## 6. Web 后台模块

### 6.1 入口：`app/web/main.py`

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from app.config import get_settings
from app.web.routes import auth, dashboard, messages, users, logs, settings as settings_route, media

settings = get_settings()

def build_app() -> FastAPI:
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
```

### 6.2 认证：`app/web/auth.py`

最简单的方案：
- 登录页只提交管理页密码 → 比对 `.env` 中的 `ADMIN_PASSWORD` → 设置 session
- 中间件检查 session，未登录跳 `/login`
- 路由 `/login` `/logout` `/static/*` `/media/*`（可选）不需要鉴权

```python
from fastapi import Request, HTTPException

# 公开路由白名单
PUBLIC_PATHS = {"/login", "/static", "/favicon.ico"}

async def require_auth(request: Request):
    if any(request.url.path.startswith(p) for p in PUBLIC_PATHS):
        return
    if not request.session.get("authenticated"):
        # 不抛 401，重定向到 /login
        from fastapi.responses import RedirectResponse
        raise HTTPException(
            status_code=307,
            headers={"Location": "/login"},
        )

def verify_password(submitted_password: str, expected_password: str) -> bool:
    # 简化：直接比对明文（.env 里就是明文）。
    return submitted_password == expected_password
```

### 6.3 路由示例：`app/web/routes/messages.py`

```python
from fastapi import APIRouter, Request, Depends, Query
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from typing import Optional
from datetime import datetime
from app.db import get_session
from app.models import Message, User
from app.web.auth import require_auth

router = APIRouter(prefix="/messages", dependencies=[Depends(require_auth)])
templates = Jinja2Templates(directory="app/web/templates")

@router.get("")
async def list_messages(
    request: Request,
    page: int = 1,
    type: Optional[str] = None,
    user_id: Optional[int] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_session),
):
    PAGE_SIZE = 50
    query = select(Message).order_by(Message.created_at.desc())
    if type:
        query = query.where(Message.type == type)
    if user_id:
        query = query.where(Message.user_id == user_id)
    if q:
        query = query.where(Message.text.like(f"%{q}%"))
    query = query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    items = db.exec(query).all()

    return templates.TemplateResponse("messages_list.html", {
        "request": request,
        "items": items,
        "page": page,
        "type": type,
        "q": q,
    })

@router.get("/{msg_id}")
async def detail(
    msg_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    msg = db.get(Message, msg_id)
    if not msg:
        from fastapi import HTTPException
        raise HTTPException(404)
    user = db.get(User, msg.user_id)
    return templates.TemplateResponse("messages_detail.html", {
        "request": request,
        "msg": msg,
        "user": user,
    })

@router.post("/{msg_id}/delete")
async def delete(msg_id: int, db: Session = Depends(get_session)):
    import os
    from app.config import get_settings
    settings = get_settings()
    msg = db.get(Message, msg_id)
    if msg:
        if msg.file_path:
            try:
                os.remove(os.path.join(settings.save_path, msg.file_path))
            except OSError:
                pass
        db.delete(msg)
        db.commit()
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/messages", status_code=303)
```

### 6.4 媒体文件路由：`app/web/routes/media.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import os
from app.config import get_settings
from app.web.auth import require_auth

router = APIRouter(prefix="/media", dependencies=[Depends(require_auth)])
settings = get_settings()

@router.get("/{path:path}")
async def serve(path: str):
    # 防 path traversal
    base = Path(settings.save_path).resolve()
    target = (base / path).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(403)
    if not target.exists() or not target.is_file():
        raise HTTPException(404)
    return FileResponse(target)
```

### 6.5 模板（`base.html` 简版示例）

```html
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>{% block title %}tgbot admin{% endblock %}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <nav>
        <a href="/">仪表盘</a> |
        <a href="/messages">消息</a> |
        <a href="/users">用户</a> |
        <a href="/logs">日志</a> |
        <a href="/settings">配置</a> |
        <form method="post" action="/logout" style="display:inline">
            <button type="submit">登出</button>
        </form>
    </nav>
    <main>
        {% block content %}{% endblock %}
    </main>
</body>
</html>
```

样式追求**够用**即可，全局一个 `style.css`，几十行 CSS 把表格、表单、卡片样式写一下。不引外部 UI 框架。

---

## 7. 并发运行：`app/run.py`

bot 和 web 在同一个容器内并发跑，使用 asyncio：

```python
import asyncio
import logging
import uvicorn

from app.utils.logging_setup import setup_logging
from app.config import get_settings
from app.db import init_db
from app.bot.main import build_application
from app.web.main import build_app

async def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    settings = get_settings()

    logger.info("Initializing database...")
    init_db()

    logger.info("Building bot...")
    bot_app = build_application()

    logger.info("Building web...")
    web_app = build_app()

    # Web 服务器
    web_config = uvicorn.Config(
        web_app,
        host="0.0.0.0",
        port=settings.web_port,
        log_level=settings.log_level.lower(),
    )
    web_server = uvicorn.Server(web_config)

    # Bot 初始化
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()

    logger.info(f"Bot running, web at :{settings.web_port}")

    try:
        await web_server.serve()  # 阻塞直到 web 退出
    finally:
        logger.info("Shutting down...")
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. 日志配置：`app/utils/logging_setup.py`

```python
import logging
import logging.handlers
import os
from app.config import get_settings

def setup_logging():
    settings = get_settings()
    log_dir = os.path.join(settings.data_path, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "bot.log")

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件（10MB 滚动，保留 5 份）
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)

    # stdout
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(settings.log_level)
    root.addHandler(fh)
    root.addHandler(sh)

    # 降噪
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
```

---

## 9. 容器化

### 9.1 `requirements.txt`

```
python-telegram-bot[socks]==21.6
fastapi==0.115.0
uvicorn[standard]==0.32.0
sqlmodel==0.0.22
jinja2==3.1.4
python-multipart==0.0.12
python-dotenv==1.0.1
aiofiles==24.1.0
pydantic-settings==2.6.0
itsdangerous==2.2.0
```

### 9.2 `Dockerfile`

多阶段构建：从 aiogram 官方镜像拷贝预编译的 `telegram-bot-api` 二进制（自己编译需要 ~30 分钟和几 GB 依赖）。

```dockerfile
# ---------- 第一阶段：从 aiogram 镜像拿 telegram-bot-api 二进制 ----------
FROM aiogram/telegram-bot-api:latest AS tgapi

# ---------- 第二阶段：Python 运行时 ----------
FROM python:3.12-slim

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-client \
        autossh \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 拷贝 telegram-bot-api 二进制
COPY --from=tgapi /usr/bin/telegram-bot-api /usr/local/bin/telegram-bot-api

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

# 容器内默认路径
ENV SAVE_PATH=/app/saved
ENV DATA_PATH=/app/data
ENV SSH_KEY_PATH=/app/data/ssh
ENV TGAPI_DIR=/var/lib/telegram-bot-api
ENV PYTHONUNBUFFERED=1

RUN mkdir -p ${TGAPI_DIR}

HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -sf http://127.0.0.1:${TGAPI_PORT:-8081}/ > /dev/null 2>&1 \
        || curl -sf --socks5 127.0.0.1:${SOCKS_PORT:-1080} \
            --max-time 8 https://api.telegram.org > /dev/null \
        || exit 1

CMD ["./entrypoint.sh"]
```

> 健康检查改成 "本地 bot-api server 在跑" 为主，SOCKS 出口为兜底。`start-period` 从 30s 调到 60s，给 bot-api 启动留时间。

### 9.3 `entrypoint.sh`

启动顺序：autossh → 等隧道 → telegram-bot-api → 等 server → python bot/web。任一关键进程退出则容器退出。

```bash
#!/bin/bash
set -e

# ---------- 1. SSH SOCKS 隧道 ----------
echo "[entrypoint] Starting SSH SOCKS tunnel..."
autossh -M 0 -N -D 127.0.0.1:${SOCKS_PORT:-1080} \
  -o "ServerAliveInterval=30" \
  -o "ServerAliveCountMax=3" \
  -o "ExitOnForwardFailure=yes" \
  -o "StrictHostKeyChecking=accept-new" \
  -o "UserKnownHostsFile=${SSH_KEY_PATH}/known_hosts" \
  -i ${SSH_KEY_PATH}/id_ed25519 \
  -p ${SSH_PORT:-22} \
  ${SSH_USER}@${SSH_HOST} &
TUNNEL_PID=$!

echo "[entrypoint] Waiting for tunnel..."
for i in {1..15}; do
    if curl -sf --socks5 127.0.0.1:${SOCKS_PORT:-1080} \
        --max-time 5 https://api.telegram.org > /dev/null; then
        echo "[entrypoint] Tunnel is up."
        break
    fi
    sleep 2
done

# ---------- 2. telegram-bot-api server（本地模式）----------
echo "[entrypoint] Starting telegram-bot-api server..."
mkdir -p ${TGAPI_DIR} ${DATA_PATH}/logs
telegram-bot-api \
  --local \
  --api-id="${TG_API_ID}" \
  --api-hash="${TG_API_HASH}" \
  --http-port=${TGAPI_PORT:-8081} \
  --dir="${TGAPI_DIR}" \
  --proxy="socks5://127.0.0.1:${SOCKS_PORT:-1080}" \
  --log="${DATA_PATH}/logs/tgapi.log" \
  --verbosity=2 &
TGAPI_PID=$!

echo "[entrypoint] Waiting for bot-api server..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:${TGAPI_PORT:-8081}/ > /dev/null 2>&1; then
        echo "[entrypoint] bot-api server is up."
        break
    fi
    sleep 1
done

# ---------- 3. Python bot + web ----------
echo "[entrypoint] Starting bot + web..."
python -m app.run &
APP_PID=$!

# 任一进程退出则容器退出，由 Docker 重启策略接管
trap "kill $TUNNEL_PID $TGAPI_PID $APP_PID 2>/dev/null" EXIT
wait -n $TUNNEL_PID $TGAPI_PID $APP_PID
EXIT_CODE=$?
echo "[entrypoint] One process exited (code=$EXIT_CODE), shutting down."
exit $EXIT_CODE
```

### 9.4 `docker-compose.yml`

```yaml
services:
  tgbot:
    build: .
    container_name: tgbot-saver
    restart: unless-stopped
    env_file: .env
    ports:
      - "${WEB_PORT}:${WEB_PORT}"
    volumes:
      - ${SAVE_PATH}:/app/saved
      - ${DATA_PATH}:/app/data
      - ${DATA_PATH}/tgapi:/var/lib/telegram-bot-api  # bot-api server 工作目录
    environment:
      - TZ=${TIMEZONE}
      - SAVE_PATH=/app/saved
      - DATA_PATH=/app/data
      - SSH_KEY_PATH=/app/data/ssh
      - TGAPI_DIR=/var/lib/telegram-bot-api
```

> `tgapi` 卷持久化的是 bot 会话状态（含未消费完的 update）。重启容器不丢，避免重复处理或漏消息。

### 9.5 `.gitignore`

```
.env
*.pyc
__pycache__/
.venv/
data/
saved/
*.db
*.db-wal
*.db-shm
logs/
```

---

## 10. 部署步骤（运维清单）

```bash
# 1. NAS 准备目录
sudo mkdir -p /vol1/1000/tgbot/saved /vol1/1000/tgbot/data/ssh /vol1/1000/tgbot/data/tgapi
sudo chown -R $(id -u):$(id -g) /vol1/1000/tgbot

# 2. 生成 SSH 密钥并部署到美国服务器
ssh-keygen -t ed25519 -f /vol1/1000/tgbot/data/ssh/id_ed25519 -N ""
ssh-copy-id -i /vol1/1000/tgbot/data/ssh/id_ed25519.pub user@us-server
# 测试免密
ssh -i /vol1/1000/tgbot/data/ssh/id_ed25519 user@us-server "echo ok"
# 把 host key 写入 known_hosts（避免首次启动 prompt）
ssh-keyscan -p 22 us-server.ip >> /vol1/1000/tgbot/data/ssh/known_hosts

# 3. 申请 Telegram api_id / api_hash
# - 登录 https://my.telegram.org（用任意普通账号，不绑 bot）
# - "API development tools" → 创建一个 application
# - 记下 api_id（数字）和 api_hash（字符串）
# 注意：api_id/hash 与 bot 身份无关，谁的账号申请都能用；
# 但一旦 bot 用本地 server 跑起来，就不能再切回云端 Bot API（除非先 /logOut）。

# 4. 克隆代码
cd /vol1/1000/tgbot
git clone <repo-url> app  # 或者把代码放进去

# 5. 复制并填写 .env
cp .env.example .env
nano .env
# 必填：BOT_TOKEN, BOT_OWNER_ID, TG_API_ID, TG_API_HASH, SSH_USER, SSH_HOST, ADMIN_PASSWORD

# 6. 启动
docker compose up -d --build

# 7. 看日志
docker compose logs -f
# 重点观察 telegram-bot-api 启动日志，确认 api_id/hash 没报错
```

---

## 11. 手动测试清单（scripts/manual_test.md）

按顺序跑一遍，全部 ✅ 即可上线：

```
[ ] docker compose ps 显示 healthy
[ ] docker compose logs 无 ERROR
[ ] 进容器：docker exec tgbot-saver curl --socks5 127.0.0.1:1080 https://api.telegram.org
    → 返回 {"ok":false,"error_code":404,...}（正常，没带 token）
[ ] 进容器：docker exec tgbot-saver curl http://127.0.0.1:8081/
    → 有响应（即使是 404 也说明 bot-api server 在跑）
[ ] tail -f ${DATA_PATH}/logs/tgapi.log（宿主机）或 docker exec tgbot-saver tail -f /app/data/logs/tgapi.log
    看 telegram-bot-api 日志，无 "API ID invalid" 等错误
[ ] Telegram 找到 bot，发 /start → 收到欢迎消息和 user_id
[ ] 发 /id → 返回 user_id
[ ] 发文字消息 "测试" → 收到 ✅，DB 中有记录
[ ] 发图片 → 收到 ✅，NAS 文件管理器看到 saved/photo/xxx.jpg
[ ] 发小视频（< 50MB）→ 直接 ✅，不显示"下载中"
[ ] 发文档 → 同上
[ ] 发语音消息（按住录音）→ 同上
[ ] 发动画（GIF）→ 同上
[ ] 发贴纸 → 同上
[ ] 发 100MB 视频 → 先收到"⏳ 下载中"，几十秒后编辑为"✅ 已保存"，文件落盘
[ ] 发 500MB 视频 → 同上，下载时间 1-3 分钟
[ ] docker exec tgbot-saver find /var/lib/telegram-bot-api/ -type f -size +1M
    应该为空或只剩 server 自己的会话文件（验证 shutil.move 把媒体搬走了）
[ ] 用小号给 bot 发消息 → 收到"不对外开放"，DB users 表有新行 allowed=false
[ ] 发 /stats → 数字正确
[ ] 发 /search 测试 → 找到刚才的文字消息
[ ] 浏览器访问 http://nas-ip:8080 → 跳转 /login
[ ] 登录 → 进仪表盘
[ ] /messages 列表正常
[ ] 点详情 → 图片/视频内联预览正常
[ ] 删除某条 → 文件和 DB 行都消失
[ ] /users 列表正常，切换小号 allowed → 切换后小号能发消息成功
[ ] /logs 显示日志尾部
[ ] docker compose restart → 服务恢复，bot 可用，bot-api server 重新起来
[ ] 在美国服务器 kill sshd 或 sudo systemctl restart sshd → 30s 内隧道自动恢复，bot-api server 跟着恢复
[ ] 触发一个故意的异常（比如临时把 SAVE_PATH 权限改为 000）→ Owner 收到错误私信
```

---

## 12. 编码规范

- **格式化**：black（line length 100）
- **导入排序**：isort
- **类型注解**：所有公开函数加 type hints
- **异步优先**：所有 I/O 操作用 `async def`
- **错误处理**：handler 顶层用 try/except 兜底，并交给 `error_handler`；不在业务代码里吞异常
- **日志**：用模块级 `logger = logging.getLogger(__name__)`，不要 `print`
- **数据库**：所有数据库操作走 SQLModel session，session 用上下文管理器
- **常量**：路径、超时等常量定义在 `app/config.py` 或对应模块顶部
- **不要**：写注释解释"这行做什么"——代码本身要可读；只在解释"为什么这么写"时写注释

---

## 13. 重要陷阱（务必注意）

1. **PTB 21.x 是纯异步**：所有 handler 必须 `async def`，不能写同步 handler
2. **SQLite 并发**：bot 和 web 是两个 asyncio 任务在同一进程，但都用同一个 engine；务必启用 WAL 模式
3. **autossh 退出条件**：必须加 `-o ExitOnForwardFailure=yes`，否则隧道转发失败时进程会卡住不退出
4. **known_hosts**：首次连接会要求确认 host key。生产环境用 `ssh-keyscan` 预填，或用 `StrictHostKeyChecking=accept-new`（首次自动接受，之后严格校验）
5. **时区**：Telegram 返回的 `msg.date` 是 timezone-aware（UTC），存数据库前 `.replace(tzinfo=None)`，前端显示时再转 TIMEZONE
6. **path traversal**：`/media/{path}` 路由必须做 `resolve()` 后的前缀校验，否则用户能用 `../` 读任意文件
7. **文件名安全**：Telegram 的 `file_unique_id` 可能包含特殊字符，构造文件名时只保留 alnum + `-_`
8. **Telegram 消息编辑**：用户编辑已发送消息会触发 `edited_message`，**v1 不处理**（明确忽略）
9. **media group（一次发多张图）**：每张图是独立 update，按顺序到达；v1 当成多条独立消息存即可，不做聚合
10. **bot 启动顺序**：必须先 `await bot_app.initialize()` 再 `start()` 再 `start_polling()`，顺序错会卡死
11. **本地 bot-api server 是单向门**：一旦 bot 用本地 server 跑过，就不能再切回云端 Bot API（除非先调 `/logOut`）。**bot token 不要在云端和本地之间来回切换**
12. **本地模式下 `file.file_path` 是绝对路径不是 URL**：`saver.py` 必须用 `shutil.move`，不能再 `download_to_drive` 走 HTTP；同时 `/var/lib/telegram-bot-api` 和 `/app/saved` 必须在容器同一文件系统，才能走 rename 零拷贝
13. **SOCKS 代理参数格式**：telegram-bot-api 只认 `socks5://host:port`，**不要写 `socks5h://`** —— 它不认这个 scheme，会启动失败
14. **bot-api server 启动慢**：需要 ~3-5 秒才能接受连接。entrypoint 必须用 curl 轮询等它起来，否则 bot 第一个请求会 connection refused
15. **大文件下载超时**：PTB 的 `read_timeout` 必须设到 600s 以上，否则 500MB+ 文件下载到一半被 PTB 主动断开。`get_updates_request` 不需要，那个还是短超时
16. **`api_id` / `api_hash` 尽量不换**：换了之后 telegram-bot-api server 会重新初始化，期间 bot 短暂不可用。bot 历史消息的 `file_id` 仍可用（绑 bot token，不绑 api_id）。如果换后 server 启动异常，清空 `${TGAPI_DIR}/<bot_id>/` 再启动即可
17. **`bot token` 也不能换**：所有数据库里存的 `file_id` 都和 bot token 绑定，换 token 后老的 `file_id` 全失效，无法 backfill 历史大文件

---

## 14. 不确定时的默认决策

如果实现过程中遇到本文档没明确说明的情况，按以下原则决策：

1. **优先简单**：能用 10 行代码解决就别写 50 行
2. **优先可逆**：选择以后好改的方案，比如先存原始 JSON 再说，别急着做 schema 优化
3. **优先用户感知**：用户能在 Telegram 立刻看到的反馈最重要，比如出错要回执
4. **不引入新依赖**：除 requirements.txt 已列出的，不要装新库；除非必要再写到本文档更新
5. **不暴露公网**：所有端口默认监听 NAS 内网，不要主动开放

文档之外的功能请求：**不要做**。

---

## 15. 第一次跑通后的下一步

完成 MVP 并跑通验收清单之后，推荐迭代顺序：

1. URL 抓取（最高 ROI）
2. yt-dlp 集成
3. FTS5 全文检索
4. 标签系统 UI
5. LLM 自动整理

每个都写独立的需求文档再做，本文档保持 MVP 范围。
