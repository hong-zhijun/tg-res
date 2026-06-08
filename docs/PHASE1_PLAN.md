# 第一期开发计划

> 范围：按 v1 需求先完成 Bot 收存能力和后台 JSON API。前端页面不作为本期交付重点，后续单独做。

## 目标

第一期要先让系统具备可被验证的后端能力：

- Telegram bot 能接收 owner 的文字和媒体消息。
- 文本进 SQLite，媒体按类型落盘并写入 SQLite。
- 非白名单用户会被记录并拒绝。
- 后台提供可供前端调用的 JSON API，用于登录、看统计、查消息、删消息、管用户、看日志、看配置。
- 媒体文件通过受保护的 `/media/*` 路由读取。

## 开发顺序

1. Bot 核心链路
   - 注册 `/start /id /help /stats /search`。
   - 实现用户记录和白名单判断。
   - 实现 text/photo/video/document/voice/audio/animation/sticker handler。
   - 实现媒体文件下载、磁盘空间检查、按类型保存、数据库入库和保存回执。

2. 后台 API
   - 实现 session 登录 API。
   - 实现 dashboard 统计 API。
   - 实现 messages 列表、详情、删除 API。
   - 实现 users 列表、白名单切换、备注更新 API。
   - 实现 logs tail API。
   - 实现 settings 脱敏配置 API。
   - 保留 `/media/{path}` 文件读取接口，并做 path traversal 防护。

3. 文档和验收
   - 输出接口文档，固定路径、参数、响应形状。
   - 本地跑 Python 编译检查、导入检查、SQLite 初始化检查和 API smoke test。
   - NAS 上再做真实 Telegram、Docker、SSH 隧道、大文件验收。

## 本期不做

- 不做新前端页面和交互打磨。
- 不做 URL 抓取、OCR、语音转写、标签 UI、全文检索。
- 不做公网发布、HTTPS、自动备份。

## 验收标准

- `python -m compileall app scripts` 通过。
- 使用测试环境变量时，`init_db()`、`build_app()`、`build_application()` 能正常执行。
- API smoke test 覆盖登录、dashboard、messages、users、settings、logs。
- NAS 环境中按 `scripts/manual_test.md` 完成 Telegram 和大文件手动验收。
