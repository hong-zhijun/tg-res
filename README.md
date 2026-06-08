# Telegram NAS Saver

私人 Telegram NAS 剪藏机器人。把文字、图片、视频、文件、语音等内容发给自己的 Telegram bot，服务会把内容保存到家里的 NAS，并提供一个内网 Web 后台用于浏览、搜索和管理。

> 当前仓库已经完成第一版可运行实现：Bot 收存链路、后台 API、Web 管理页面、Docker 编排和文档均已接通。

## 目标

- 私人使用，不做多租户和公开发布。
- Telegram bot 负责接收内容并保存到 NAS。
- 媒体文件按类型保存，例如 `photo/`、`video/`、`document/`。
- Web 后台只在家庭局域网访问，登录只需要管理页密码。
- 通过自建 `telegram-bot-api server` 本地模式支持大文件保存。
- NAS 通过 SSH SOCKS 隧道使用美国服务器访问 Telegram。

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
    |-- telegram-bot-api server
    |-- Python Telegram bot
    |-- FastAPI Web 后台
    |
    v
/vol1/1000/tgbot/
    |-- saved/  媒体文件
    |-- data/   SQLite、日志、SSH 密钥、telegram-bot-api 状态
```

## 技术栈

- Python 3.12
- python-telegram-bot 21.x
- FastAPI + Jinja2
- SQLModel + SQLite
- Docker + docker-compose
- telegram-bot-api server 本地模式
- autossh + SSH SOCKS 隧道

## 当前目录

```text
app/
  bot/              Telegram bot 入口、命令、通知、消息 handler
  web/              FastAPI 后台、路由、模板、静态资源
  utils/            日志、存储、时间工具
  config.py         环境变量配置
  db.py             SQLite 初始化
  models.py         SQLModel 表定义
  run.py            bot + web 主入口
docs/
  REQUIREMENTS.md   需求文档
  DEVELOPMENT.md    开发文档
  API.md            后台接口文档
  PHASE1_PLAN.md    第一期开发计划
  UI-design/        Web UI 设计稿
scripts/
  init_db.py        手动初始化数据库
  manual_test.md    手动测试清单入口
```

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

本地只跑 Web 后台时，可以用测试环境变量启动：

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

访问：

```text
http://127.0.0.1:8080
```

登录密码就是上面设置的 `ADMIN_PASSWORD`。

完整 Bot + Web 运行仍建议走 Docker，因为它依赖 `telegram-bot-api server` 和 SSH SOCKS 隧道。

## 开发状态

已完成：

- 基础 Python 包结构
- 配置模型
- SQLite 表结构
- Bot 白名单、命令、消息接收和媒体保存
- Web 登录、仪表盘、消息、用户、日志、配置页面
- 后台 JSON API
- Dockerfile、docker-compose、entrypoint
- 文档和手动测试入口

待实现：

- NAS / Telegram 真实环境联调
- 大文件 100MB / 500MB 手动验收
- 后续 Phase 2 功能：URL 抓取、全文检索、标签 UI 等

## 文档

详细需求见 [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)。

开发说明见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。
