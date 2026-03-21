"""APScheduler integration — reminders and scheduled tasks."""
import re
import json
import time
import asyncio
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from src.config import MEMORY_DIR
from src.claude import run_claude_sync

logger = logging.getLogger(__name__)

_app = None

scheduler = AsyncIOScheduler(jobstores={
    'default': SQLAlchemyJobStore(
        url=f'sqlite:///{MEMORY_DIR / "scheduler.db"}'
    )
})

SCHEDULE_TRIGGERS = [
    "каждый день", "каждую ночь", "каждое утро", "каждый час", "каждую минуту",
    "каждый понедельник", "каждый вторник", "каждую среду", "каждый четверг",
    "каждую пятницу", "каждую субботу", "каждое воскресенье",
    "напоминай", "напомни через", "напомни мне", "напомни",
    "присылай каждый", "проверяй каждый",
    "every day", "every hour", "remind me every", "remind me",
]

def is_schedule_request(text: str) -> bool:
    text_lower = text.lower()
    if any(t in text_lower for t in SCHEDULE_TRIGGERS):
        return True
    # Catch "через N минут/часов" without explicit keyword
    if re.search(r'через\s+\d+\s*(минут|минуты|мин|часов|часа|час|секунд|сек)', text_lower):
        return True
    return False

async def handle_schedule_request(chat_id: int, text: str) -> str:
    parse_prompt = f"""Ты парсер расписаний. Отвечай ТОЛЬКО валидным JSON без комментариев и markdown.

Пользователь хочет создать запланированную задачу: "{text}"

Ответь JSON строго в этом формате:
{{
  "cron": "0 9 * * 1",
  "task": "краткое описание что нужно сделать",
  "human_schedule": "каждый понедельник в 9:00",
  "one_time_seconds": null
}}

Правила:
- cron: стандартное 5-польное выражение (минуты часы день месяц день_недели)
- task: короткое описание действия на русском
- human_schedule: человекочитаемое расписание на русском
- one_time_seconds: целое число секунд если задача одноразовая ("через 30 минут" = 1800), иначе null
- Если one_time_seconds задан — поле cron игнорируется"""

    try:
        raw = await asyncio.to_thread(run_claude_sync, parse_prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.split("\n")[:-1])
        data = json.loads(raw.strip())

        job_id_base = f"{chat_id}_{int(time.time())}"

        if data.get("one_time_seconds"):
            run_date = datetime.now() + timedelta(seconds=int(data["one_time_seconds"]))
            job_id = f"once_{job_id_base}"
            scheduler.add_job(
                send_scheduled_message, 'date',
                run_date=run_date,
                args=[chat_id, data["task"]],
                id=job_id
            )
            return f"Ладно, Морти, поставил напоминание — {data['human_schedule']}. Не облажайся."
        else:
            trigger = CronTrigger.from_crontab(data["cron"])
            job_id = f"repeat_{job_id_base}"
            scheduler.add_job(
                send_scheduled_message, trigger,
                args=[chat_id, data["task"]],
                id=job_id
            )
            return f"ырп Поставил: {data['task']} — {data['human_schedule']}. Не мешай."
    except Exception as e:
        logger.error(f"Schedule parse error: {e}")
        return "Не смог распарсить расписание. Скажи точнее когда и что делать."

async def send_scheduled_message(chat_id: int, task: str):
    """Выполняет запланированную задачу — вызывается APScheduler"""
    from src.bot import ask_rick
    try:
        response, files = await ask_rick(chat_id, f"[Scheduled task] {task}")
        await _app.bot.send_message(chat_id=chat_id, text=response)
        # files silently dropped — no interactive context for scheduled tasks
    except Exception as e:
        logger.error(f"Scheduled task error for chat {chat_id}: {e}")
