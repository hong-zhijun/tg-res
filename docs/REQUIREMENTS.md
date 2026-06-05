# Telegram NAS 剪藏机器人 - 需求文档

> 版本：v1.0（MVP）
> 维护者：[Owner]
> 目标读者：开发者 / AI 编码代理（Codex 等）

---

## 1. 项目概述

### 1.1 目标
打造一个"个人 Telegram 剪藏箱"：用户在任何设备上把内容（文字、图片、视频、文件、语音）转发给一个私有 Telegram bot，bot 自动将内容保存到家庭 NAS 的存储池中，并提供一个 Web 管理后台用于浏览、搜索、管理这些内容。

### 1.2 使用场景
- 在外刷到一篇好文章，转发链接给 bot → NAS 永久存档
- 看到一张有用的截图，发给 bot → 自动归档进当日相册
- 录一段语音备忘 → bot 存下原始语音文件
- 朋友给你发了一段视频 → 转发给 bot → 留底
- 回家后通过 Web 后台浏览/搜索这些内容

### 1.3 用户
- **单一用户**：项目所有者本人
- 不考虑多租户、不考虑公开发布
- 白名单机制是为了**防止 bot 被陌生人骚扰**，不是为了支持多人协作

---

## 2. 架构概览

```
┌─────────────┐
│  Telegram   │
│  客户端     │ (手机 / 桌面 / 网页)
└──────┬──────┘
       │ 发消息
       ▼
┌─────────────────┐
│  Telegram API   │ (api.telegram.org)
└──────┬──────────┘
       │
       │ 国际网络（受限）
       │
       ▼
┌─────────────────────────┐
│   美国服务器（中转）    │
│   提供 SSH SOCKS 出口   │
└──────┬──────────────────┘
       │ SSH 隧道
       ▼
┌────────────────────────────────────────────┐
│              NAS（飞牛 OS）                 │
│  ┌──────────────────────────────────────┐  │
│  │  Docker 容器：tgbot-saver            │  │
│  │  ┌──────────┐  ┌─────────────────┐   │  │
│  │  │ autossh  │←─│ telegram-bot-api│   │  │
│  │  │ 隧道进程 │  │ server (本地模式)│   │  │
│  │  └──────────┘  └────────┬────────┘   │  │
│  │                         │            │  │
│  │                  ┌──────┴──────┐     │  │
│  │                  │  Bot 进程   │     │  │
│  │                  └──────┬──────┘     │  │
│  │                         │            │  │
│  │  ┌──────────────────────┴─────────┐  │  │
│  │  │  FastAPI Web 后台进程          │  │  │
│  │  └────────────────┬───────────────┘  │  │
│  └───────────────────┼──────────────────┘  │
│                      │                      │
│  ┌───────────────────┴──────────────────┐  │
│  │  /vol1/1000/tgbot/                   │  │
│  │   ├── saved/  (媒体文件)             │  │
│  │   └── data/   (SQLite+日志+SSH+TGAPI)│  │
│  └──────────────────────────────────────┘  │
└────────────────────────────────────────────┘
```

### 关键设计决策

| 决策点 | 选择 | 原因 |
|--------|------|------|
| 部署方式 | Docker + docker-compose | 自包含、易迁移、飞牛应用中心可视化管理 |
| 数据库 | SQLite | 单文件、零运维、对个人数据量足够 |
| 网络出口 | SSH SOCKS 隧道（容器内 autossh） | 美国服务器只需开 SSH，无额外攻击面 |
| Telegram API 接入 | 自建 telegram-bot-api server（本地模式） | 突破云端 Bot API 的 20MB 下载限制，最大可支持 2GB 文件 |
| Web 框架 | FastAPI + Jinja2 模板 | 后端 ORM 可与 bot 共享，无需前后端分离 |
| 进程编排 | entrypoint.sh + `wait -n` | 任一关键进程死亡触发容器重启 |
| 存储位置 | NAS 存储池下挂载到容器 | 媒体文件落到大容量盘，删容器不丢数据 |

---

## 3. 功能需求

### 3.1 Bot 核心功能

#### 3.1.1 消息接收与保存

支持以下消息类型，每种都要保存到磁盘 + 数据库：

| 类型 | Telegram API 字段 | 保存内容 |
|------|-------------------|----------|
| 文字 | `message.text` | 全文存数据库，无磁盘文件 |
| 图片 | `message.photo[-1]`（最大尺寸） | 下载到磁盘，保存路径 |
| 视频 | `message.video` | 下载到磁盘 |
| 文档（任意文件） | `message.document` | 下载到磁盘，保留原文件名 |
| 语音消息 | `message.voice` | 下载 `.ogg` 文件 |
| 音频文件 | `message.audio` | 下载，保留原文件名 |
| 动画（GIF） | `message.animation` | 下载 `.mp4` 文件 |
| 贴纸 | `message.sticker` | 下载为 `.webp` 或 `.tgs` |

**对所有非文字类型**：
- 同时保存 `caption`（如有）到数据库 `text` 字段
- 保存原始消息的完整 JSON 到 `raw_json` 字段（用于未来扩展，不丢任何元信息）

#### 3.1.2 存储路径规则

```
${SAVE_PATH}/
├── photo/
│   └── 1234_AgACAg.jpg
├── video/
│   └── 1235_BAACAg.mp4
├── document/
│   └── 1236_report.pdf
├── voice/
│   └── 1237_AwACAg.ogg
├── audio/
│   └── 1238_song.mp3
├── animation/
│   └── 1239_CgACAg.mp4
└── sticker/
    └── 1240_DAACAg.webp
```

- 直接按类型分目录：`{type}/`
- 文件名格式：`{telegram_message_id}_{原文件名或 file_unique_id}.{ext}`
- 文字消息不落盘，只进数据库

#### 3.1.3 白名单机制

- 数据库 `users` 表存储所有交互过的用户
- 字段 `allowed` 控制是否处理其消息
- 启动时自动将 `BOT_OWNER_ID` 标记为 `allowed=true`
- 非白名单用户首次发消息：
  - 在 `users` 表记录用户基本信息（id、username）
  - 回复一次："抱歉，本 bot 不对外开放"
  - 后续消息直接静默忽略（不再回复，避免被刷屏）
- 在 Web 后台可手动开关任何用户的 `allowed`

#### 3.1.4 命令列表

通过 `setMyCommands` 注册以下命令，让客户端自动补全：

| 命令 | 描述 | 行为 |
|------|------|------|
| `/start` | 开始使用 | 显示欢迎信息 + 当前用户 ID |
| `/id` | 查看我的用户 ID | 返回 `effective_user.id`，用于白名单配置 |
| `/stats` | 查看统计 | 今日条数、本月条数、总条数、存储占用 |
| `/search <关键词>` | 搜索历史 | 在 `text` 字段做 `LIKE %关键词%` 搜索，返回最近 10 条匹配（含日期、类型、摘要） |
| `/help` | 查看帮助 | 列出所有命令的说明 |

#### 3.1.5 回执消息

每条成功保存的消息，bot 回复一条消息确认：
- 文字消息："✅ 已保存（消息 #123）"
- 媒体消息："✅ 已保存 video → `video/1235_xxx.mp4`（消息 #123）"
- 包含数据库中的 `message.id` 便于在后台定位

**大文件两段式回执**（文件 > 50MB）：
- 收到消息时立刻回 "⏳ 下载中..."
- 下载并落盘后，将该回执 **编辑** 为 "✅ 已保存 ..."
- 避免用户以为 bot 卡死，同时不刷屏

#### 3.1.6 错误处理与通知

注册全局错误处理器 `application.add_error_handler`：
- 捕获所有未处理异常
- 写入日志文件（含 traceback）
- 主动 Telegram 私聊推送给 `BOT_OWNER_ID`，格式：
  ```
  ⚠️ Bot 错误
  时间：2026-06-05 14:32:11
  消息 ID：1234
  类型：video
  错误：<异常类名 + 简短描述>
  ```

#### 3.1.7 已知限制处理

- **大文件上限（2GB / 4GB）**：
  - bot 通过容器内自建的 telegram-bot-api server 下载文件，已突破云端 Bot API 的 20MB 限制
  - 仍受 Telegram 客户端上传上限：普通账号 2GB，Premium 账号 4GB（这是 Telegram 协议侧的硬限制，无法突破）
  - v1 不设置额外业务软上限，能否保存主要取决于 Telegram 自身限制、NAS 剩余空间和网络稳定性
- **大文件下载耗时**：
  - 数百 MB 起的文件下载需要数十秒到数分钟
  - bot 收到后先回执 "⏳ 下载中..."，下载完成后编辑该消息为 "✅ 已保存"
  - 避免用户以为 bot 卡死
- **磁盘空间不足**：
  - 写文件前检查可用空间
  - 不足则中止保存，回复："⚠️ NAS 存储空间不足，请清理"
  - 触发错误通知
- **Telegram API 限流**：
  - python-telegram-bot 默认会重试，无需额外处理

### 3.2 Web 管理后台

#### 3.2.1 通用

- 端口：`WEB_PORT`（默认 8080）
- 认证：简单的 session 登录，只校验 `.env` 中的管理页密码
- 仅监听 NAS 局域网，不暴露公网
- 服务端渲染（Jinja2），无前后端分离

#### 3.2.2 页面

| 路径 | 功能 |
|------|------|
| `GET /login` | 登录表单 |
| `POST /login` | 验证凭据，设置 session |
| `POST /logout` | 清 session 跳登录 |
| `GET /` 或 `/dashboard` | 仪表盘：今日/本周/本月条数、存储占用、按类型分布饼图、最近 10 条 |
| `GET /messages` | 消息列表：分页（每页 50），筛选（类型、日期范围、用户、关键词），按时间倒序 |
| `GET /messages/{id}` | 单条详情：缩略图/播放器内联预览、完整 JSON、所属用户、原始 Telegram 消息 ID |
| `POST /messages/{id}/delete` | 删除：同时删磁盘文件和数据库行 |
| `GET /users` | 用户列表：id、username、display_name、allowed 开关、备注、最后活跃时间、消息数 |
| `POST /users/{id}/toggle` | 切换 `allowed` |
| `POST /users/{id}/note` | 更新备注 |
| `GET /logs` | 日志：tail 最后 500 行，按 level 筛选 |
| `GET /settings` | 只读：当前配置（脱敏，token 部分显示星号） |

#### 3.2.3 媒体预览

- 图片：`<img src="/media/{path}">` 直接渲染
- 视频：`<video controls>` 内联播放
- 音频/语音：`<audio controls>` 内联播放
- 文档：提供下载链接，PDF 用 `<iframe>` 内嵌
- 所有 `/media/*` 路由要做 path traversal 防护

### 3.3 网络要求

- 容器启动时自动建立 SSH SOCKS 隧道至美国服务器
- 隧道断开后 autossh 自动重连
- **telegram-bot-api server** 通过 `socks5://127.0.0.1:1080` 访问 Telegram API
- **Bot 进程**不再直连 Telegram，改连本地 `http://127.0.0.1:8081`（telegram-bot-api server 监听的端口）
- Web 后台不需要走代理（监听本地端口即可）

### 3.4 telegram-bot-api 凭证

自建 telegram-bot-api server 需要 Telegram 的 `api_id` / `api_hash`：

- 从 [my.telegram.org](https://my.telegram.org) 申请，绑定到一个普通 Telegram 账号（不绑定 bot）
- 凭证只是用于 server 标识，**与 bot 身份无关**，bot 仍由 `BOT_TOKEN` 决定
- 通过 `.env` 的 `TG_API_ID` / `TG_API_HASH` 注入容器
- ⚠️ 一旦切换到本地 telegram-bot-api server，**bot 不能再走云端 Bot API**（Telegram 的硬性规定）。如需切回云端必须先调 `/logOut` 注销本地会话

---

## 4. 非功能需求

### 4.1 部署
- 平台：Debian 系 Linux（飞牛 NAS）
- 方式：Docker + docker-compose
- 重启策略：`restart: unless-stopped`
- 开机自启：依赖 Docker 自身的 daemon 自启

### 4.2 配置
- 全部敏感信息通过 `.env` 注入
- `.env.example` 列出所有变量但不含值
- `.env` 加入 `.gitignore`

### 4.3 持久化
- SQLite 数据库放在挂载卷（`DATA_PATH`）
- 媒体文件放在挂载卷（`SAVE_PATH`）
- SSH 私钥放在 `DATA_PATH/ssh/` 下，随 data 目录挂载到容器内 `/app/data/ssh/`
- telegram-bot-api server 工作目录（含会话状态、下载缓存）挂载在 `DATA_PATH/tgapi/`，容器内对应 `/var/lib/telegram-bot-api/`

### 4.4 可观测性
- Bot 行为打到 `/app/data/logs/bot.log`（容器内路径）
- 日志同时输出到 stdout（`docker logs` 可看）
- 日志级别由 `LOG_LEVEL` 控制

### 4.5 备份
- v1 不提供备份功能
- 数据库和媒体文件都放在 NAS 挂载目录中，备份由使用者自行按 NAS 方案处理

### 4.6 性能
- 单用户使用，每天预计消息量 < 100 条
- 不做性能优化设计，能正确运行即达标

---

## 5. v1 范围之外（明确不做）

为避免范围蔓延，以下功能 **v1 不实现**，但数据库和架构要为之留好扩展点：

- ❌ URL 自动抓取（解析链接 → 存网页正文/截图）
- ❌ yt-dlp 集成（下载 YouTube/B 站/X 视频）
- ❌ OCR（图片转文字）
- ❌ Whisper 语音转写
- ❌ LLM 自动打标签/摘要
- ❌ 全文检索（FTS5）——v1 只用 `LIKE` 模糊匹配
- ❌ 标签系统的 UI（数据库结构留好，UI 后续做）
- ❌ 多群组、多用户协作
- ❌ 公网暴露 Web 后台
- ❌ HTTPS（v1 仅内网 HTTP）
- ❌ 定时摘要推送
- ❌ 内置备份脚本/自动备份

---

## 6. 后续阶段预告（影响 v1 设计）

虽然 v1 不做，但这些功能在第 2/3 阶段会加：

**Phase 2**：
- URL 抓取（`message.text` 检测到 URL 自动 fetch）
- yt-dlp 视频下载
- SQLite FTS5 全文搜索
- 标签 UI

**Phase 3**：
- LLM 自动整理（标题、摘要、标签）
- Whisper 转写
- 公开 Web 浏览（带认证）
- 同步到 Obsidian/Notion

→ 因此数据库 schema 已预留 `tags` / `message_tags` 表，`raw_json` 字段保留完整原始消息，便于后续重新解析。

---

## 7. 验收标准（v1）

| # | 标准 | 验证方式 |
|---|------|----------|
| 1 | bot 在 NAS 上 Docker 容器中正常启动 | `docker compose ps` 看 status |
| 2 | 隧道建立成功 | 容器内 `curl --socks5 127.0.0.1:1080 https://api.telegram.org` 有响应 |
| 3 | Owner 发文字消息，bot 回 ✅，数据库有记录 | 发一条消息 → 看 SQLite |
| 4 | Owner 发图片，bot 回 ✅，文件落到 NAS 对应目录 | 发图片 → 在飞牛文件管理器看 |
| 5 | Owner 发视频、文档、语音、动画、贴纸，均能保存 | 逐个测试 |
| 6 | 陌生用户发消息，被拒绝，记录到 users 表 | 用小号测试 |
| 7 | 命令 `/start /id /stats /search /help` 均可用 | 客户端菜单点一遍 |
| 8 | Web 后台能登录、看消息列表、看详情、删除、切换用户白名单 | 浏览器手动操作 |
| 9 | 容器重启后服务自动恢复 | `docker compose restart` |
| 10 | NAS 重启后服务自动恢复 | 重启 NAS |
| 11 | 模拟错误（关掉美国服务器 SSH）→ 自动重试 → 恢复 | 临时阻断网络测试 |
| 12 | 容器内 telegram-bot-api server 正常运行 | `curl http://127.0.0.1:8081/` 有响应 |
| 13 | 发 100MB / 500MB 视频，bot 通过本地 server 正常下载并保存 | 发大视频测试，文件落到 NAS 对应目录 |
| 14 | 大文件下载期间，bot 先回 "⏳ 下载中"，完成后编辑为 "✅ 已保存" | 发 500MB 视频观察回执变化 |
