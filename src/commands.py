"""Bot command handlers — /start, /reset, /forget, /skill, /schedule, /news, /quiet."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from src.config import OWNER_ID, SKILLS_DIR
from src.memory import chat_histories, save_history, load_facts, save_facts
from src.quiet import cycle_mode, MODE_OFF, MODE_LISTEN, MODE_SILENT
from src.skills import search_clawhub, install_clawhub_skill
from src.scheduler import scheduler
from src.news import load_news_config, save_news_config, send_daily_news
from src.core import ask_rick, send_response, send_text

logger = logging.getLogger(__name__)


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/news HH:MM [topic] — schedule daily news, /news off — disable, /news now — send now"""
    args = context.args or []
    chat_id = str(update.effective_chat.id)
    config = load_news_config()

    if not args:
        current = config.get(chat_id)
        if current:
            await send_text(update.message, f"News: daily at {current['time']}, topic: {current.get('topic', 'not set')}\nUse `/news off` to disable.")
        else:
            await send_text(update.message, "Usage:\n`/news 14:30 AI startups` — daily news at 14:30\n`/news now quantum physics` — send now\n`/news off` — disable")
        return

    if args[0] == "off":
        config.pop(chat_id, None)
        save_news_config(config)
        try: scheduler.remove_job(f"news_{chat_id}")
        except Exception: pass
        await send_text(update.message, "Daily news disabled.")
        return

    if args[0] == "now":
        topic = " ".join(args[1:]) if len(args) > 1 else config.get(chat_id, {}).get("topic", "")
        if not topic:
            await send_text(update.message, "Specify topic: `/news now AI startups`")
            return
        await send_daily_news(int(chat_id), topic)
        return

    time_str = args[0]
    try:
        hour, minute = map(int, time_str.split(":"))
        assert 0 <= hour <= 23 and 0 <= minute <= 59
    except Exception:
        await send_text(update.message, "Wrong format. Use: `/news 14:30`")
        return

    if len(args) < 2:
        await send_text(update.message, "Specify topic: `/news 14:30 AI startups`")
        return
    topic = " ".join(args[1:])
    config[chat_id] = {"time": time_str, "topic": topic}
    save_news_config(config)

    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(
        send_daily_news, CronTrigger(hour=hour, minute=minute),
        args=[int(chat_id), topic],
        id=f"news_{chat_id}", replace_existing=True
    )
    await send_text(update.message, f"Daily news at {time_str}, topic: {topic}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_histories[chat_id].clear()
    save_history(chat_id, chat_histories[chat_id])
    facts = load_facts(chat_id)
    note = " By the way, I remember you." if facts else ""
    response, files = await ask_rick(chat_id, f"Chat opened.{note} Greet briefly, Rick-style. Say what you can do: answer questions, write and run code, search the web, browse websites, analyze photos, understand voice messages, create and send files (code, presentations, documents), sometimes reply with voice.")
    await send_response(update.message, response, files, context)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_histories[chat_id].clear()
    save_history(chat_id, chat_histories[chat_id])
    response, _ = await ask_rick(chat_id, "Memory gap. Be brief.")
    await send_text(update.message, response)


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_histories[chat_id].clear()
    save_history(chat_id, chat_histories[chat_id])
    save_facts(chat_id, [])
    await update.message.reply_text("burp Who are you? Starting from scratch.")


async def skill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/skill search|install|list"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage:\n"
            "  `/skill search <query>` — search ClawHub\n"
            "  `/skill install <slug>` — install a skill\n"
            "  `/skill list` — list installed skills",
            parse_mode="Markdown"
        )
        return

    subcmd = args[0].lower()
    rest = " ".join(args[1:]).strip()
    chat_id = update.effective_chat.id

    if subcmd == "list":
        chat_skills_dir = SKILLS_DIR / str(chat_id)
        if not chat_skills_dir.exists():
            await update.message.reply_text("No skills installed. Try `/skill search <something>`", parse_mode="Markdown")
            return
        installed = [d.name for d in sorted(chat_skills_dir.iterdir()) if d.is_dir() and (d / "SKILL.md").exists()]
        if not installed:
            await update.message.reply_text("No skills installed.")
            return
        msg_text = "Installed skills:\n" + "\n".join(f"\u2022 `{s}`" for s in installed)
        await update.message.reply_text(msg_text, parse_mode="Markdown")

    elif subcmd == "search":
        if not rest:
            await update.message.reply_text("Specify a query: `/skill search <query>`", parse_mode="Markdown")
            return
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        result = await search_clawhub(rest)
        await update.message.reply_text(result, parse_mode="Markdown")

    elif subcmd == "install":
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("This isn't for you, Morty.")
            return
        if not rest:
            await update.message.reply_text("Specify slug: `/skill install <slug>`", parse_mode="Markdown")
            return
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        result = await install_clawhub_skill(rest, chat_id)
        await update.message.reply_text(result, parse_mode="Markdown")

    else:
        await update.message.reply_text(f"Unknown subcommand '{subcmd}'. Use: search, install, list")


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/schedule list | cancel <id>"""
    args = context.args or []
    chat_id = update.effective_chat.id

    if not args:
        await update.message.reply_text(
            "Usage:\n"
            "  `/schedule list` — tasks for this chat\n"
            "  `/schedule cancel <id>` — cancel a task",
            parse_mode="Markdown"
        )
        return

    subcmd = args[0].lower()

    if subcmd == "list":
        prefix_once = f"once_{chat_id}_"
        prefix_repeat = f"repeat_{chat_id}_"
        jobs = [j for j in scheduler.get_jobs()
                if j.id.startswith(prefix_once) or j.id.startswith(prefix_repeat)]
        if not jobs:
            await update.message.reply_text("No active tasks for this chat.")
            return
        lines = ["Scheduled tasks:"]
        for j in jobs:
            task_desc = j.args[1] if len(j.args) > 1 else "?"
            lines.append(f"\u2022 `{j.id}`\n  {task_desc}\n  {j.trigger}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif subcmd == "cancel":
        if len(args) < 2:
            await update.message.reply_text("Specify ID: `/schedule cancel <id>`", parse_mode="Markdown")
            return
        job_id = args[1]
        prefix_once = f"once_{chat_id}_"
        prefix_repeat = f"repeat_{chat_id}_"
        if not (job_id.startswith(prefix_once) or job_id.startswith(prefix_repeat)):
            await update.message.reply_text("That's not your task, Morty.")
            return
        try:
            scheduler.remove_job(job_id)
            await update.message.reply_text(f"Cancelled. `{job_id}`", parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(f"Task `{job_id}` not found.", parse_mode="Markdown")

    else:
        await update.message.reply_text(f"Unknown command '{subcmd}'. Use: list, cancel")


_MODE_LABELS = {
    MODE_OFF: "Обычный режим. Рик снова в деле.",
    MODE_LISTEN: "Режим прослушки. Читаю, но молчу. Отвечаю только на @ или по имени.",
    MODE_SILENT: "Полная тишина. Не читаю, не отвечаю. Только на @ или по имени.",
}


async def quiet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/quiet — cycle: off → listen → silent → off."""
    chat_id = update.effective_chat.id
    new_mode = cycle_mode(chat_id)
    await update.message.reply_text(_MODE_LABELS[new_mode])
