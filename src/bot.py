#!/usr/bin/env python3
"""Rick Sanchez Bot v11 — modular entry point."""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters

from src.config import BOT_TOKEN, MEMORY_DIR, WORK_DIR, SKILLS_DIR, TOKENS_DIR
from src.handlers import handle_message, handle_voice, handle_photo, handle_video, handle_document
from src.commands import (start_command, reset_command, forget_command,
                          skill_command, schedule_command, news_command,
                          quiet_command)
from src.scheduler import scheduler
from src.scenario import load_scenario, generate_daily_scenario
from src.news import load_news_config, send_daily_news
from src.media import cleanup_work_dir

import src.scheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application):
    src.scheduler._app = application
    scheduler.start()

    s = load_scenario()
    if not s.get("scenario"):
        asyncio.create_task(generate_daily_scenario())

    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from src.pages import cleanup_old_pages
    scheduler.add_job(
        generate_daily_scenario, CronTrigger(hour=8, minute=0),
        id="daily_scenario", replace_existing=True
    )
    scheduler.add_job(
        cleanup_old_pages, IntervalTrigger(hours=6),
        id="cleanup_pages", replace_existing=True
    )

    news_config = load_news_config()
    for cid, cfg in news_config.items():
        try:
            h, m = map(int, cfg["time"].split(":"))
            scheduler.add_job(
                send_daily_news, CronTrigger(hour=h, minute=m),
                args=[int(cid), cfg.get("topic", "science technology AI")],
                id=f"news_{cid}", replace_existing=True
            )
            logger.info(f"News job registered: chat {cid} at {h:02d}:{m:02d}")
        except Exception as e:
            logger.error(f"Failed to register news job for chat {cid}: {e}")

    from telegram import BotCommand
    await application.bot.set_my_commands([
        BotCommand("quiet", "Режимы: обычный / прослушка / тишина"),
    ])

    me = await application.bot.get_me()
    logger.info(f"@{me.username} — Rick v11 online (scheduler started, daily scenario)")
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    cleanup_work_dir()


def main():
    print("Rick Sanchez Bot v11 — modular architecture")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(CommandHandler("skill", skill_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("quiet", quiet_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, handle_video))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("v11 started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
