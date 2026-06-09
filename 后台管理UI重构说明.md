# 后台管理 UI 重构说明

> 本文档面向 UI 重做，描述后台管理系统的全部功能点和交互行为。
> 风格不在此规范，由设计方自定。
> **要求：所有弹出层（Modal）和 Toast 提示的表现必须统一一套视觉规范。**

---

## 全局结构

### 布局

- **不使用左侧菜单栏**，改为**顶部导航切换**
- 顶部导航包含以下页签（Tab）：仪表盘、消息列表、用户白名单、分组管理、日志查看
- **设置页不做**（暂不需要）
- 顶部右侧放置：全局搜索框、刷新按钮、退出按钮
- 单页应用，通过 hash 路由切换视图（`#dashboard` `#messages` `#users` `#groups` `#logs`）

### 登录页

- 独立页面，不含顶部导航
- 内容：标题、密码输入框、登录按钮
- 登录失败：在表单内显示错误提示文字
- 登录成功：跳转到仪表盘
- API：`POST /api/auth/login` body `{"password": "xxx"}`

### 退出

- 点击退出按钮调用 `POST /api/auth/logout`，跳转回登录页

### Session 检查

- 页面加载时调用 `GET /api/auth/session` 检查是否已登录
- 任何 API 返回 401 时自动跳转登录页

---

## 通用组件

### Modal（弹出层）

所有需要弹窗的场景使用同一个 Modal 组件，行为统一：

- 带遮罩层（点击遮罩关闭）
- 标题栏 + 关闭按钮（×）
- 内容区
- 底部按钮区（操作按钮 + 取消按钮）
- ESC 键关闭
- 支持 `small` 模式（窄宽弹窗，用于简单确认和表单）

用到 Modal 的场景：

| 场景 | 标题 | 内容 | 底部按钮 |
|---|---|---|---|
| 消息详情 | `消息 #ID` | 详情字段 + 媒体预览 + 原始 JSON | 关闭、删除 |
| 删除消息确认 | 删除消息 | 确认提示文字（small） | 取消、删除 |
| 编辑用户备注 | 编辑备注 | 用户名（disabled）+ 备注 textarea（small） | 取消、保存 |
| 新建分组 | 新建根分组 / 新建子分组 | 名称输入框 + 图标选择器（small） | 取消、创建 |
| 重命名分组 | 重命名分组 | 名称输入框（small） | 取消、保存 |
| 更换分组图标 | 更换图标 | 图标选择器（small） | 取消、保存 |
| 删除分组确认 | 删除分组 | 确认提示 + 说明文字（small） | 取消、删除 |

### Toast 提示

操作反馈统一使用 Toast，行为一致：

- 固定在页面右下角堆叠
- 自动消失（约 3 秒）
- 淡出动画
- 三种类型：成功（success）、错误（error）、普通（无类型）

用到 Toast 的场景：

| 操作 | 类型 | 文案 |
|---|---|---|
| 刷新数据 | success | 已刷新 |
| 删除消息 | success | 消息已删除 |
| 切换用户权限 | success | 用户权限已更新 |
| 保存备注 | success | 备注已保存 |
| 创建分组 | success | 分组已创建 |
| 重命名分组 | success | 已重命名 |
| 更换图标 | success | 图标已更新 |
| 删除分组 | success | 分组已删除 |
| 任何 API 错误 | error | 错误信息（来自 API response） |
| 表单校验失败 | error | 如「名称不能为空」 |

---

## 页面功能明细

### 1. 仪表盘（#dashboard）

**数据来源**：`GET /api/dashboard`

#### 统计卡片区

4 个指标卡片，一行排列：

| 卡片 | 数据字段 | 副标签 |
|---|---|---|
| 今日消息 | `stats.today` | 今日新增 |
| 本周消息 | `stats.week` | 滚动统计 |
| 本月消息 | `stats.month` | 本月归档 |
| 存储占用 | `stats.storage_bytes`（格式化为 KB/MB/GB） | 媒体目录 |

#### 主提示区

一段摘要文字：`累计归档 {total} 条，本月新增 {month} 条，媒体目录占用 {storage}`。

附带两个操作：「查看消息」（跳转 #messages）、「手动刷新」。

#### 最近消息

列表展示 `recent_messages`（最多 10 条），每条显示：

- 消息 ID
- 类型名（中文：文本/图片/视频/文档/语音/音频/动画/贴纸）
- 文本摘要（text 或 file_path，超长截断）
- 时间

#### 类型分布

列表展示 `type_distribution`，每项显示：类型名 + 数量。

---

### 2. 消息列表（#messages）

**数据来源**：`GET /api/messages`

#### 筛选栏

- 搜索框：按正文或 caption 模糊搜索（参数 `q`），输入防抖 300ms
- 类型下拉：全部类型 / 文本 / 图片 / 视频 / 文档 / 语音 / 音频 / 动画 / 贴纸
- 日期范围：起始日期 + 结束日期（date input）
- 翻页按钮：上一页、下一页

#### 消息表格

| 列 | 内容 |
|---|---|
| 消息 | 消息 ID + 文本摘要（两行：ID 加粗，摘要灰色） |
| 类型 | 中文类型标签（pill 样式） |
| 用户 | user_id |
| 时间 | 格式化日期时间 |
| 大小 | 文件大小（格式化），无文件显示 `-` |
| 操作 | 查看详情按钮、删除按钮 |

空状态：显示「没有匹配的消息」。

#### 消息详情弹窗

点击「查看详情」打开 Modal：

**数据来源**：`GET /api/messages/{id}`

内容：
- 详情网格（2列布局）：Telegram ID、类型、用户、时间、文件路径、文件大小
- 消息正文区：`text` 或 「无文字内容」
- 媒体预览区（根据类型）：
  - photo / sticker → `<img>`
  - video / animation → `<video controls>`
  - audio / voice → `<audio controls>`
  - document → 下载链接按钮
  - 媒体 URL 格式：`/media/{file_path}`
- 原始 JSON 区：`<pre>` 格式化展示 `raw_json`

底部按钮：关闭、删除

#### 删除消息

点击删除弹出确认 Modal（small）：

- 提示：`确定删除消息 #ID？这会同时删除数据库记录和已保存的媒体文件。`
- 按钮：取消、删除（danger 样式）
- API：`DELETE /api/messages/{id}`
- 成功后刷新消息列表和仪表盘数据

---

### 3. 用户白名单（#users）

**数据来源**：`GET /api/users`

#### 筛选栏

- 搜索框：按用户名、昵称、备注搜索（前端过滤，防抖 200ms）
- 权限下拉：全部权限 / 已允许 / 未允许

#### 用户表格

| 列 | 内容 |
|---|---|
| 用户 | 头像首字母 + 昵称或@username + user_id |
| 权限 | pill 标签：已允许（success）/ 未允许（warn） |
| 消息数 | message_count |
| 最后活跃 | 格式化日期时间 |
| 备注 | notes 或 `-` |
| 操作 | 权限切换按钮、编辑备注按钮 |

空状态：显示「没有匹配的用户」。

#### 权限切换

- 点击切换按钮调用 `POST /api/users/{id}/toggle`
- 成功后 Toast「用户权限已更新」并刷新列表

#### 编辑备注

点击编辑按钮打开 Modal（small）：

- 用户名输入框（disabled，仅展示）
- 备注 textarea
- 按钮：取消、保存
- API：`PATCH /api/users/{id}/note` body `{"notes": "xxx"}`
- 保存成功后 Toast「备注已保存」并刷新列表

---

### 4. 分组管理（#groups）

**数据来源**：`GET /api/groups`

#### 顶部操作

- 「+ 新建根分组」按钮

#### 分组树

树形列表展示所有分组，按 path 排序，通过路径深度计算缩进：

每行内容：
- **图标**（可点击，点击弹出更换图标弹窗）：显示该分组的 icon 字段
- **分组名**（加粗）
- **消息数**（pill 标签：`N 条`）
- **路径**（灰色小字，如 `/旅行/日本`）
- **操作按钮**：新建子分组（+）、重命名（编辑图标）、删除（删除图标）

空状态：显示「还没有分组。点击上方按钮创建第一个分组。」

#### 新建分组

点击「+ 新建根分组」或某分组的「+」按钮，打开 Modal（small）：

- 标题：新建根分组 / 新建子分组
- 名称输入框（placeholder：「例：旅行」）
- **图标选择器**：一排 emoji 按钮，可选图标为 📁 📂 📦 📋 ⭐ ❤️ 🔥 💎，默认选中 📁，点击切换（同时只能选一个）
- 按钮：取消、创建
- 回车键触发创建
- API：`POST /api/groups` body `{"name": "xxx", "parent_id": null|id, "icon": "📁"}`
- 名称为空时 Toast「名称不能为空」

#### 重命名分组

点击重命名按钮，打开 Modal（small）：

- 名称输入框（预填当前名称，自动全选）
- 按钮：取消、保存
- 回车键触发保存
- API：`PATCH /api/groups/{id}` body `{"name": "新名称"}`

#### 更换图标

点击分组行的图标，打开 Modal（small）：

- 图标选择器（同新建分组的图标选择器）
- 按钮：取消、保存
- API：`PATCH /api/groups/{id}` body `{"icon": "📦"}`

可用图标列表也可从 `GET /api/groups/icons` 获取。

#### 删除分组

点击删除按钮，打开确认 Modal（small）：

- 提示：`确定删除分组「xxx」？`
- 补充说明（灰色）：`子分组会移到上级，分组内消息不会被删除。`
- 按钮：取消、删除（danger 样式）
- API：`DELETE /api/groups/{id}`

---

### 5. 日志查看（#logs）

**数据来源**：`GET /api/logs`

#### 筛选栏

- 级别下拉：全部 level / INFO / WARNING / ERROR
- 搜索框：按日志内容搜索（前端过滤，防抖 250ms）
- 刷新日志按钮

#### 日志列表

每条日志显示：
- 级别标签（pill 样式）：INFO=success / WARNING/WARN=warn / ERROR=danger
- 时间（从日志行解析 `YYYY-MM-DD HH:MM:SS`）
- 日志原文（`<code>` 样式）

空状态：显示「暂无日志」。

---

## API 汇总

以下是前端需要对接的全部 API：

### 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/login` | 登录，body `{"password":""}` |
| POST | `/api/auth/logout` | 退出 |
| GET | `/api/auth/session` | 检查登录状态 |

### 仪表盘

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/dashboard` | 统计数据 + 最近消息 + 类型分布 |

### 消息

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/messages` | 列表，支持 page/page_size/type/q/date_from/date_to |
| GET | `/api/messages/{id}` | 单条详情 |
| DELETE | `/api/messages/{id}` | 删除 |
| POST | `/api/messages/{id}/delete` | 删除（POST 兼容） |

### 用户

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/users` | 用户列表 |
| POST | `/api/users/{id}/toggle` | 切换权限 |
| PATCH | `/api/users/{id}/note` | 更新备注，body `{"notes":""}` |
| POST | `/api/users/{id}/note` | 更新备注（POST 兼容） |

### 分组

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/groups` | 分组列表（含 icon/path/message_count） |
| GET | `/api/groups/icons` | 可用图标列表 |
| POST | `/api/groups` | 新建分组，body `{"name":"","parent_id":null,"icon":"📁"}` |
| PATCH | `/api/groups/{id}` | 更新分组，body `{"name":"","icon":""}` 均可选 |
| DELETE | `/api/groups/{id}` | 删除分组 |

### 日志

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/logs` | 日志，支持 level/limit 参数 |

### 媒体文件

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/media/{path}` | 读取已保存媒体文件，需已登录 |

---

## 注意事项

1. **弹出层和 Toast 必须统一规范**：所有 Modal 使用同一组件，所有 Toast 使用同一组件，视觉表现保持一致
2. 所有 API 返回 401 时统一跳转登录页
3. 消息类型中文映射：text=文本 / photo=图片 / video=视频 / document=文档 / voice=语音 / audio=音频 / animation=动画 / sticker=贴纸
4. 文件大小格式化：B → KB → MB → GB → TB
5. 日期格式：中文 locale，24 小时制
6. 搜索框均带防抖（200-300ms）
7. 分页：上一页 / 下一页按钮，第一页禁用上一页，无下一页时禁用下一页
8. 空状态均需要友好文案提示
