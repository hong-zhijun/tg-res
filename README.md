# Telegram NAS Saver

私人 Telegram NAS 剪藏机器人。把文字、图片、视频、文件、语音等内容发给自己的 Telegram bot，服务会把内容保存到家里的 NAS，并提供一个内网 Web 后台用于浏览、搜索和管理。

## 功能

### Bot 端

- **消息接收**：支持文字、图片、视频、文档、语音、音频、动画、贴纸
- **大文件下载**：通过本地 telegram-bot-api server 支持超 20MB 文件，带进度条、速度和 ETA 显示
- **下载稳定性**：自动重试（3次指数退避）、文件完整性校验、按文件大小动态超时
- **并发控制**：信号量限制最多 3 个大文件同时下载，排队时显示位置
- **媒体组合并**：同一 media_group 的多个文件打包处理，一条通知跟踪整组进度
- **多级资源分组**：树形分组结构，转发消息后弹出 InlineKeyboard 选择分组
- **分组图标**：每个分组可自定义图标（📁📂📦📋⭐❤️🔥💎）
- **Bundle 关联**：media_group 和频道转发消息通过 bundle_id 关联存储
- **白名单**：仅授权用户可使用，未知用户首次拒绝后静默

### Bot 命令

| 命令 | 说明 |
|---|---|
| `/start` | 开始使用 |
| `/id` | 查看 user ID |
| `/stats` | 统计信息（今日/本月/总数/存储占用） |
| `/search <关键词>` | 搜索历史消息 |
| `/queue` | 查看下载队列 |
| `/groups` | 查看分组列表 |
| `/newgroup <路径>` | 创建分组（支持多级，如 `旅行/日本/东京`） |
| `/mv <ID> <路径>` | 移动消息到分组 |
| `/help` | 查看命令列表 |

### Web 后台

- **仪表盘**：今日/本周/本月消息数、存储占用、最近消息、类型分布
- **消息管理**：搜索、类型筛选、日期筛选、分页、详情查看（含媒体预览）、删除
- **用户白名单**：搜索、权限切换、备注编辑
- **分组管理**：树形展示、新建（含图标选择）、重命名、更换图标、删除（子分组自动上移）
- **日志查看**：按级别筛选、关键词搜索
- **登录**：管理页密码认证，session cookie

## 架构

```text
Telegram 客户端
    |
    v
Telegram API
    |
    v
美国服务器 SSH SOCKS 出口
    |
    v
NAS Docker 容器
    |-- autossh 隧道进程
    |-- telegram-bot-api server (本地模式，MTProto 经 proxychains 走隧道)
    |-- Python Bot (python-telegram-bot 21.x)
    |-- FastAPI Web 后台
    |
    v
/vol1/1000/tgbot/
    |-- saved/  媒体文件（按分组或类型目录存放）
    |-- data/   SQLite、日志、SSH 密钥、telegram-bot-api 状态
```

## 技术栈

- Python 3.12
- python-telegram-bot 21.x（HTTPXRequest, connection_pool_size=16）
- FastAPI + Jinja2 + Starlette Session
- SQLModel + SQLite（WAL 模式）
- Docker + docker-compose
- telegram-bot-api server 本地模式
- autossh + SSH SOCKS 隧道
- proxychains-ng（MTProto 代理）
- httpx（独立 SOCKS 连接，进度消息编辑）

## 目录结构

```text
app/
  bot/
    main.py           Bot Application 构建和 handler 注册
    handlers.py       消息处理、下载进度、分组选择、媒体组合并
    commands.py       /start /stats /search /groups /newgroup /mv 等
    groups.py         分组 CRUD、InlineKeyboard 构建
    saver.py          文件下载保存、完整性校验
    notify.py         BotFather 命令注册、错误通知
  web/
    main.py           FastAPI 应用构建
    auth.py           密码验证、session 鉴权
    routes/
      api.py          JSON API（仪表盘/消息/用户/分组/日志/配置）
      dashboard.py    仪表盘页面路由
      messages.py     消息列表/详情页面路由
      users.py        用户管理页面路由
      logs.py         日志页面路由
      settings.py     配置页面路由
      media.py        媒体文件静态服务
      auth.py         登录页面路由
    templates/        Jinja2 HTML 模板
    static/
      admin.js        SPA 路由、API 调用、弹窗、图标选择器
      style.css       全量样式
  utils/
    storage.py        文件路径生成（支持分组路径）
    logging_setup.py  日志配置
    time.py           时间工具
  config.py           环境变量配置（Pydantic Settings）
  db.py               SQLite 初始化 + 自动迁移
  models.py           数据模型（User / Group / Message / Tag / MessageTag）
  run.py              Bot + Web 并发启动入口
docs/
  REQUIREMENTS.md     需求文档
  DEVELOPMENT.md      开发文档
  API.md              后台接口文档
  UI-design/          Web UI 设计稿
scripts/
  init_db.py          手动初始化数据库
```

## 数据模型

### User
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int (PK) | Telegram user ID |
| username | str? | @username |
| display_name | str? | 昵称 |
| allowed | bool | 是否允许使用 |
| notes | str? | 备注 |
| added_at | datetime | 首次出现时间 |
| last_seen_at | datetime? | 最后活跃时间 |

### Group
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int (PK) | 自增 |
| name | str | 分组名 |
| icon | str | 图标 emoji，默认 📁 |
| parent_id | int? (FK→groups.id) | 父分组 |
| path | str | 物化路径，如 `/旅行/日本` |
| created_at | datetime | 创建时间 |

### Message
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int (PK) | 自增 |
| telegram_message_id | int | Telegram 消息 ID |
| user_id | int (FK→users.id) | 发送者 |
| chat_id | int | 聊天 ID |
| type | str | text/photo/video/document/voice/audio/animation/sticker |
| text | str? | 文本内容或 caption |
| file_path | str? | 媒体文件相对路径 |
| file_size | int? | 文件字节数 |
| mime_type | str? | MIME 类型 |
| duration | int? | 时长（秒） |
| width | int? | 宽度 |
| height | int? | 高度 |
| forwarded_from | str? | 转发来源 |
| group_id | int? (FK→groups.id) | 所属分组 |
| bundle_id | str? | 关联标识（mg_xxx / fwd_xxx） |
| raw_json | str | 原始消息 JSON |
| created_at | datetime | 保存时间 |

## 配置

复制 `.env.example` 为 `.env` 并填写：

```dotenv
BOT_TOKEN=
BOT_OWNER_ID=

TG_API_ID=
TG_API_HASH=
TGAPI_PORT=8081

SSH_USER=ubuntu
SSH_HOST=
SSH_PORT=22
SOCKS_PORT=1080

SAVE_PATH=/vol1/1000/tgbot/saved
DATA_PATH=/vol1/1000/tgbot/data

WEB_PORT=8080
ADMIN_PASSWORD=

LOG_LEVEL=INFO
TIMEZONE=Asia/Shanghai
```

`TG_API_ID` 和 `TG_API_HASH` 来自 `my.telegram.org`。它们用于本地 `telegram-bot-api server`，bot 身份仍由 `BOT_TOKEN` 决定。

## NAS 目录

```bash
sudo mkdir -p /vol1/1000/tgbot/saved /vol1/1000/tgbot/data/ssh /vol1/1000/tgbot/data/tgapi
sudo chown -R $(id -u):$(id -g) /vol1/1000/tgbot
```

SSH 私钥放在：

```text
/vol1/1000/tgbot/data/ssh/id_ed25519
/vol1/1000/tgbot/data/ssh/known_hosts
```

## 启动

### Docker / NAS

```bash
docker compose up -d --build
docker compose logs -f
```

Web 后台默认访问：

```text
http://nas-ip:8080
```

### 本地开发（uv）

```powershell
$env:BOT_TOKEN='123:ABC'
$env:BOT_OWNER_ID='1'
$env:TG_API_ID='1'
$env:TG_API_HASH='hash'
$env:SSH_USER='user'
$env:SSH_HOST='host'
$env:ADMIN_PASSWORD='pass'
$env:SAVE_PATH="$PWD\.tmp_saved"
$env:DATA_PATH="$PWD\.tmp_data"
$env:WEB_PORT='8080'
uv run --with-requirements requirements.txt uvicorn app.web.main:build_app --factory --host 127.0.0.1 --port 8080
```

## 文档

- 需求：[docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)
- 开发：[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
- 接口：[docs/API.md](docs/API.md)
- UI 重构说明：[后台管理UI重构说明.md](后台管理UI重构说明.md)
