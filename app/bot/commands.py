async def cmd_start(update, context) -> None:
    user_id = update.effective_user.id if update.effective_user else "unknown"
    await update.message.reply_text(f"你好！你的 user_id 是 `{user_id}`。", parse_mode="Markdown")


async def cmd_id(update, context) -> None:
    user_id = update.effective_user.id if update.effective_user else "unknown"
    await update.message.reply_text(f"你的 user_id: `{user_id}`", parse_mode="Markdown")


async def cmd_stats(update, context) -> None:
    await update.message.reply_text("统计功能尚未实现。")


async def cmd_search(update, context) -> None:
    await update.message.reply_text("搜索功能尚未实现。")


async def cmd_help(update, context) -> None:
    await update.message.reply_text(
        "/start - 开始使用\n"
        "/id - 查看我的 user_id\n"
        "/stats - 统计信息\n"
        "/search 关键词 - 搜索历史\n"
        "/help - 显示此帮助"
    )
