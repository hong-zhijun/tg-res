# 第一期接口文档

> 所有后台接口都在同一个 FastAPI 服务中。前端后续只需要对接 `/api/*` 和 `/media/*`。

## 认证

后台使用 session cookie。除 `/api/auth/login` 和 `/api/auth/session` 外，所有 `/api/*` 接口都需要先登录。

### POST `/api/auth/login`

请求：

```json
{"password": "管理页密码"}
```

响应：

```json
{"ok": true}
```

密码错误返回 `401`。

### POST `/api/auth/logout`

清空 session。

响应：

```json
{"ok": true}
```

### GET `/api/auth/session`

响应：

```json
{"authenticated": true}
```

## 仪表盘

### GET `/api/dashboard`

响应：

```json
{
  "stats": {
    "today": 1,
    "week": 5,
    "month": 20,
    "total": 100,
    "storage_bytes": 123456
  },
  "type_distribution": [
    {"type": "photo", "count": 10}
  ],
  "recent_messages": [
    {
      "id": 1,
      "telegram_message_id": 1234,
      "user_id": 10001,
      "chat_id": 10001,
      "type": "text",
      "text": "hello",
      "file_path": null,
      "file_size": null,
      "mime_type": null,
      "created_at": "2026-06-05T10:00:00",
      "media_url": null
    }
  ]
}
```

## 消息

### GET `/api/messages`

查询参数：

- `page`：默认 `1`
- `page_size`：默认 `50`，最大 `100`
- `type`：`text/photo/video/document/voice/audio/animation/sticker`
- `user_id`
- `q`：按 `text` 模糊搜索
- `date_from`：`YYYY-MM-DD`
- `date_to`：`YYYY-MM-DD`

响应：

```json
{
  "items": [],
  "page": 1,
  "page_size": 50,
  "has_next": false
}
```

### GET `/api/messages/{message_id}`

返回单条消息详情，额外包含：

- `duration`
- `width`
- `height`
- `forwarded_from`
- `raw_json`
- `user`

不存在返回 `404`。

### DELETE `/api/messages/{message_id}`

删除数据库记录；如有媒体文件，也会删除磁盘文件。

响应：

```json
{"ok": true, "deleted": true}
```

### POST `/api/messages/{message_id}/delete`

与 `DELETE /api/messages/{message_id}` 等价，给不方便发 `DELETE` 的客户端使用。

## 用户

### GET `/api/users`

响应：

```json
{
  "items": [
    {
      "id": 10001,
      "username": "name",
      "display_name": "Name",
      "allowed": true,
      "notes": "owner",
      "added_at": "2026-06-05T10:00:00",
      "last_seen_at": "2026-06-05T10:00:00",
      "message_count": 10
    }
  ]
}
```

### POST `/api/users/{user_id}/toggle`

切换 `allowed`。

响应为更新后的用户对象。

### PATCH `/api/users/{user_id}/note`

请求：

```json
{"notes": "备注"}
```

响应为更新后的用户对象。

### POST `/api/users/{user_id}/note`

与 `PATCH /api/users/{user_id}/note` 等价。

## 日志

### GET `/api/logs`

查询参数：

- `level`：可选，例如 `INFO/WARNING/ERROR`
- `limit`：默认 `500`，最大 `2000`

响应：

```json
{
  "log_file": "/app/data/logs/bot.log",
  "lines": []
}
```

## 配置

### GET `/api/settings`

返回当前配置，敏感值会脱敏。

```json
{
  "BOT_TOKEN": "1234******abcd",
  "BOT_OWNER_ID": 10001,
  "TG_API_ID": 12345,
  "TG_API_HASH": "abcd******wxyz",
  "WEB_PORT": 8080
}
```

## 媒体文件

### GET `/media/{path}`

读取已保存媒体文件。需要已登录 session。

示例：

```text
GET /media/photo/1234_AgACAg.jpg
```

服务端会限制路径必须位于 `SAVE_PATH` 下，禁止 `../` 读取任意文件。

## Bot 命令接口

Telegram 客户端侧可用命令：

- `/start`：显示欢迎信息和当前用户 ID。
- `/id`：返回当前 Telegram user ID。
- `/help`：显示命令列表。
- `/stats`：返回今日、本月、总数和存储占用。
- `/search <关键词>`：按消息文本模糊搜索最近 10 条。

Bot 支持消息类型：

- `text`
- `photo`
- `video`
- `document`
- `voice`
- `audio`
- `animation`
- `sticker`
