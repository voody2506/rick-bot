#!/usr/bin/env python3
"""Rick Sanchez Bot v10 — modular entry point."""

from dotenv import load_dotenv
load_dotenv()

import json
import os
import time
import asyncio
import logging
import tempfile
import uuid
from collections import defaultdict, deque
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

from src.config import BOT_TOKEN, OWNER_ID, MAX_HISTORY, MAX_FACTS, MEMORY_DIR, WORK_DIR, SKILLS_DIR, TOKENS_DIR, TIMEZONE

# ─── RATE LIMITING ───────────────────────────────────────
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 10     # max messages per window
_user_timestamps: dict[int, deque] = defaultdict(lambda: deque(maxlen=RATE_LIMIT_MAX))


def is_rate_limited(user_id: int) -> bool:
    now = time.time()
    timestamps = _user_timestamps[user_id]
    # Remove old timestamps
    while timestamps and now - timestamps[0] > RATE_LIMIT_WINDOW:
        timestamps.popleft()
    if len(timestamps) >= RATE_LIMIT_MAX:
        return True
    timestamps.append(now)
    return False
from datetime import datetime
from zoneinfo import ZoneInfo
from src.prompts import RICK_SYSTEM, EXTRACT_FACTS_PROMPT, SUMMARIZE_PROMPT, PROFILE_PROMPT
from src.memory import (chat_histories, group_context, group_members, group_recent_photos,
                        init_chat, save_history,
                        load_facts, save_facts, load_summaries, save_summary,
                        load_profile, save_profile)
from src.claude import run_claude
from src.media import (transcribe_audio, find_created_files, find_new_workdir_files, cleanup_work_dir)
from src.groups import maybe_respond_in_group
from src.scheduler import scheduler
from src.skills import load_skills_for_chat, search_clawhub, install_clawhub_skill
from src.tts import generate_voice
from src.memes import maybe_send_gif
from src.reactions import pick_reaction, set_reaction
from src.stickers import pick_sticker
from src.scenario import get_scenario_for_prompt, generate_daily_scenario, load_scenario
from src.mood import update_mood, get_mood_modifier
from src.news import load_news_config, save_news_config, send_daily_news

import src.scheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─── ФАКТЫ ────────────────────────────────────────────────

async def extract_and_save_facts(chat_id, user_msg, rick_response):
    try:
        current = load_facts(chat_id)
        raw = await run_claude(EXTRACT_FACTS_PROMPT.format(
            user=user_msg, response=rick_response,
            current_facts="\n".join(current) if current else "нет"), timeout=15)
        if not raw or "НЕТ" in raw.upper(): return
        new_facts = [l.lstrip("- ").strip() for l in raw.split("\n") if l.strip().startswith("-")]
        if new_facts:
            updated = current + new_facts
            if len(updated) > MAX_FACTS:
                pruned = await run_claude(
                    f"Оставь {MAX_FACTS} важнейших фактов:\n" + "\n".join(f"- {f}" for f in updated) +
                    "\nФорматируй каждый с '- '", 15)
                updated = [l.lstrip("- ").strip() for l in pruned.split("\n") if l.strip().startswith("-")]
            save_facts(chat_id, updated)
    except Exception as e:
        logger.error(f"Ошибка фактов: {e}")

# ─── ОСНОВНАЯ ЛОГИКА ──────────────────────────────────────

def build_prompt(chat_id, user_message):
    history = list(chat_histories[chat_id])
    facts = load_facts(chat_id)
    summaries = load_summaries(chat_id)
    profile = load_profile(chat_id)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    prompt = RICK_SYSTEM.format(work_dir=str(WORK_DIR)) + "\n\n"

    # Time awareness
    now = datetime.now(ZoneInfo(TIMEZONE))
    prompt += f"Current date/time: {now.strftime('%Y-%m-%d %H:%M, %A')}\n"

    # Daily scenario — global mood and storyline
    prompt += get_scenario_for_prompt() + "\n"

    # Dynamic mood from interactions
    mood_mod = get_mood_modifier()
    if mood_mod:
        prompt += f"CURRENT MOOD SHIFT: {mood_mod}\n\n"

    # User profile
    if profile:
        prompt += "User profile:\n"
        for k, v in profile.items():
            if v and v != "null":
                prompt += f"- {k}: {v}\n"
        prompt += "\n"

    # Past conversation summaries
    if summaries:
        prompt += "Past conversations:\n"
        for s in summaries[-5:]:  # last 5 summaries
            prompt += f"- [{s.get('date', '?')}]: {s.get('summary', '')}\n"
        prompt += "\n"

    skills = load_skills_for_chat(chat_id)
    if skills:
        prompt += f"Installed skills:\n{skills}\n\n"
    if facts:
        prompt += "Known facts:\n" + "\n".join(f"- {f}" for f in facts) + "\n\n"
    if history:
        prompt += "Recent conversation:\n"
        for i in range(0, len(history), 2):
            if i < len(history): prompt += f"User: {history[i]}\n"
            if i+1 < len(history): prompt += f"Rick: {history[i+1]}\n"
        prompt += "\n"
    prompt += f"[chat_id: {chat_id}]\nUser: {user_message}\nRick:"
    return prompt

async def ask_rick(chat_id, user_message, image_path=None):
    init_chat(chat_id)
    start_time = time.time()
    update_mood(user_message or "")

    if image_path:
        prompt = user_message or "Что на этом фото? Опиши по-рикски."
        response = await run_claude(prompt, 90, image_path=image_path)
    else:
        response = await run_claude(build_prompt(chat_id, user_message), 120)

    if not response:
        return "*burp* ...can't hear you. Say again, Morty.", []

    # Объединяем regex-файлы и новые файлы из WORK_DIR
    files = list(set(find_created_files(response) + find_new_workdir_files(start_time)))

    chat_histories[chat_id].append(user_message or "[фото]")
    chat_histories[chat_id].append(response)
    save_history(chat_id, chat_histories[chat_id])

    # Extract facts every 5 messages instead of every message
    if len(chat_histories[chat_id]) % 10 == 0:  # 10 entries = 5 message pairs
        asyncio.create_task(extract_and_save_facts(chat_id, user_message or "[фото]", response))

    # Summarize when history is full — before next truncation loses data
    if len(chat_histories[chat_id]) >= MAX_HISTORY * 2:
        asyncio.create_task(summarize_and_update_profile(chat_id))

    return response, files


async def summarize_and_update_profile(chat_id):
    """Summarize current conversation and update user profile. Runs in background."""
    try:
        history = list(chat_histories[chat_id])
        if not history:
            return

        # Build conversation text for summarization
        conv_lines = []
        for i in range(0, len(history), 2):
            if i < len(history): conv_lines.append(f"User: {history[i]}")
            if i+1 < len(history): conv_lines.append(f"Rick: {history[i+1]}")
        conv_text = "\n".join(conv_lines)

        # Summarize
        summary_raw = await run_claude(
            SUMMARIZE_PROMPT.format(conversation=conv_text), timeout=15)
        if summary_raw:
            save_summary(chat_id, {
                "date": datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d"),
                "summary": summary_raw.strip()
            })
            logger.info(f"Saved conversation summary for chat {chat_id}")

        # Update profile
        current_profile = load_profile(chat_id)
        profile_raw = await run_claude(
            PROFILE_PROMPT.format(
                current_profile=json.dumps(current_profile, ensure_ascii=False) if current_profile else "{}",
                conversation=conv_text[-2000:]  # last 2000 chars
            ), timeout=15)
        if profile_raw:
            # Extract JSON from response
            profile_raw = profile_raw.strip()
            if profile_raw.startswith("```"):
                profile_raw = "\n".join(profile_raw.split("\n")[1:])
            if profile_raw.endswith("```"):
                profile_raw = "\n".join(profile_raw.split("\n")[:-1])
            try:
                new_profile = json.loads(profile_raw.strip())
                save_profile(chat_id, new_profile)
                logger.info(f"Updated profile for chat {chat_id}")
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse profile JSON for chat {chat_id}")
    except Exception as e:
        logger.error(f"Summarize/profile error: {e}")

# ─── HELPERS ──────────────────────────────────────────────

async def send_text(msg, text):
    """Send text with Markdown formatting, fallback to plain text."""
    try:
        await msg.reply_text(text, parse_mode="Markdown")
    except Exception:
        try:
            await msg.reply_text(text, parse_mode=None)
        except Exception as e:
            logger.error(f"Send text error: {e}")


# ─── HANDLERS ─────────────────────────────────────────────

async def send_response(msg, response, files, context):
    """Send text OR voice, plus any created files. Supports multi-message via ---."""
    # Split multi-messages
    parts = [p.strip() for p in response.split("---") if p.strip()]

    if len(parts) > 1:
        # Multi-message mode — send each part with delay
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # Last part — maybe voice
                voice = await generate_voice(part)
                if voice:
                    try:
                        await context.bot.send_voice(chat_id=msg.chat_id, voice=voice)
                    except Exception:
                        await send_text(msg, part)
                else:
                    await send_text(msg, part)
            else:
                await send_text(msg, part)
                await asyncio.sleep(1)  # delay between messages
    else:
        # Single message
        voice = await generate_voice(response)
        if voice:
            try:
                await context.bot.send_voice(chat_id=msg.chat_id, voice=voice)
            except Exception as e:
                logger.warning(f"TTS send error: {e}")
                await send_text(msg, response)
        else:
            await send_text(msg, response)

    # GIF or sticker — occasionally send one by mood
    gif_sent = await maybe_send_gif(response, context.bot, msg.chat_id)
    sticker_id = pick_sticker(response) if not gif_sent else None
    if sticker_id:
        try:
            await context.bot.send_sticker(chat_id=msg.chat_id, sticker=sticker_id)
        except Exception as e:
            logger.warning(f"Sticker send error: {e}")

    for file_path in files:
        try:
            with open(file_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=msg.chat_id,
                    document=f,
                    filename=os.path.basename(file_path),
                    caption=f"📎 {os.path.basename(file_path)}"
                )
            logger.info(f"Sent file: {file_path}")
            if str(WORK_DIR) in file_path:
                os.unlink(file_path)
        except Exception as e:
            logger.error(f"File send error {file_path}: {e}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка голосовых сообщений через Whisper"""
    msg = update.message
    if not msg: return
    chat_id = update.effective_chat.id
    user = update.effective_user
    is_group = update.effective_chat.type in ["group", "supergroup"]
    username = user.first_name if user else "Morty"

    if user and is_group:
        group_members[chat_id][user.id] = {
            "name": user.first_name or user.username or "Morty",
            "username": user.username
        }

    if is_group:
        pass  # Combined decision handles voice in group

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    voice = msg.voice
    voice_file = await context.bot.get_file(voice.file_id)

    with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp:
        ogg_path = tmp.name

    await voice_file.download_to_drive(ogg_path)

    try:
        text = await transcribe_audio(ogg_path)

        if not text:
            await msg.reply_text("Burp... couldn't make that out, Morty.")
            return

        logger.info(f"Voice transcribed: {text[:100]}")

        # Process like a text message
        if is_group:
            group_context[chat_id].append(f"{username}: [голосовое]: {text[:100]}")
            response = await maybe_respond_in_group(chat_id, username, f"[voice]: {text}")
            if not response:
                return
            group_context[chat_id].append(f"Рик: {response[:100]}")
        else:
            init_chat(chat_id)
            response, files = await ask_rick(chat_id, f"[голосовое сообщение]: {text}")

        await send_text(msg, response)

    finally:
        try:
            os.unlink(ogg_path)
        except Exception:
            pass

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка входящих документов — передаёт Рику имя файла как контекст"""
    msg = update.message
    if not msg: return
    chat_id = update.effective_chat.id
    user = update.effective_user
    is_group = update.effective_chat.type in ["group", "supergroup"]
    username = user.first_name if user else "Morty"

    if user and is_group:
        group_members[chat_id][user.id] = {
            "name": user.first_name or user.username or "Morty",
            "username": user.username
        }

    filename = msg.document.file_name or "неизвестный файл"
    user_message = f"Пользователь прислал файл: {filename}. Что ты думаешь?"

    if is_group:
        group_context[chat_id].append(f"{username}: [sent file: {filename}]")
        response = await maybe_respond_in_group(chat_id, username, user_message)
        if not response:
            return
        group_context[chat_id].append(f"Рик: {response[:100]}")
        await send_text(msg, response)
    else:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        init_chat(chat_id)
        response, files = await ask_rick(chat_id, user_message)
        await send_response(msg, response, files, context)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка входящих фотографий через CLI stream-json"""
    msg = update.message
    if not msg: return
    chat_id = update.effective_chat.id
    chat_type = msg.chat.type
    user = update.effective_user

    username = user.first_name if user else "Кто-то"

    if user and chat_type in ("group", "supergroup"):
        group_members[chat_id][user.id] = {
            "name": user.first_name or user.username or "Morty",
            "username": user.username
        }

    if chat_type in ("group", "supergroup"):
        group_context[chat_id].append(f"{username}: [фото]")

        # ВСЕГДА скачиваем фото в группе — нужно для follow-up вопросов
        photo = msg.photo[-1]
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        image_path = str(WORK_DIR / f"photo_{chat_id}_{uuid.uuid4().hex[:8]}.jpg")
        try:
            file = await context.bot.get_file(photo.file_id)
            await file.download_to_drive(image_path)
        except Exception as e:
            await msg.reply_text(f"burp Couldn't download the photo: {e}")
            return
        group_recent_photos[chat_id] = {"path": image_path, "ts": time.time()}

        bot_username = context.bot.username or ""
        reply_to_bot = (msg.reply_to_message and msg.reply_to_message.from_user
                       and msg.reply_to_message.from_user.username == bot_username)
        caption = msg.caption or ""
        caption_lower = caption.lower()
        has_rick_in_caption = "рик" in caption_lower or bool(
            bot_username and f"@{bot_username.lower()}" in caption_lower)

        if not has_rick_in_caption and not reply_to_bot:
            return  # Photo saved for follow-up, but don't respond now

        # Отвечаем на фото сразу
        user_text = caption if caption else "Что на этом фото? Опиши по-рикски."
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        async def keep_typing():
            for _ in range(20):
                await asyncio.sleep(4)
                try: await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                except: break

        init_chat(chat_id)
        typing = asyncio.create_task(keep_typing())
        context_lines = list(group_context.get(chat_id, []))
        context_str = "\n".join(context_lines[-6:]) if context_lines else "(начало беседы)"
        vision_prompt = f"Контекст чата:\n{context_str}\n\n{username} прислал фото. {user_text}"
        response = await run_claude(vision_prompt, 90, image_path=image_path)
        group_context[chat_id].append(f"Рик: {response[:100]}")
        typing.cancel()
        await send_response(msg, response, [], context)
        return

    # Личная переписка
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    photo = msg.photo[-1]
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    image_path = str(WORK_DIR / f"photo_{chat_id}_{uuid.uuid4().hex[:8]}.jpg")

    try:
        file = await context.bot.get_file(photo.file_id)
        await file.download_to_drive(image_path)
    except Exception as e:
        await msg.reply_text(f"burp Couldn't download the photo: {e}")
        return

    user_text = msg.caption or "What's in this photo? Describe it, Rick-style."

    async def keep_typing():
        for _ in range(20):
            await asyncio.sleep(4)
            try: await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            except: break

    init_chat(chat_id)
    typing = asyncio.create_task(keep_typing())
    try:
        response, files = await ask_rick(chat_id, user_text, image_path=image_path)
    finally:
        typing.cancel()
        try: os.unlink(image_path)
        except Exception: pass

    await send_response(msg, response, files, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text: return
    chat_id = update.effective_chat.id
    user_text = msg.text
    user = update.effective_user
    username = user.first_name if user else "Someone"

    # Rate limiting
    if user and is_rate_limited(user.id):
        return

    # React to user's message
    emoji = pick_reaction(user_text)
    if emoji:
        await set_reaction(context.bot, chat_id, msg.message_id, emoji)

    # Inject forwarded message content
    if msg.forward_from_chat or msg.forward_from:
        fwd_text = msg.text or msg.caption or ""
        fwd_source = ""
        if msg.forward_from_chat:
            fwd_source = msg.forward_from_chat.title or "channel"
        elif msg.forward_from:
            fwd_source = msg.forward_from.first_name or "someone"
        user_text = f"[Forwarded from {fwd_source}]: {fwd_text}"

    # Inject reply context — including forwarded posts in replies
    if msg.reply_to_message:
        reply_msg = msg.reply_to_message
        quoted = ""
        if reply_msg.text:
            quoted = reply_msg.text[:500]
        elif reply_msg.caption:
            quoted = reply_msg.caption[:500]
        if reply_msg.forward_from_chat:
            fwd_source = reply_msg.forward_from_chat.title or "channel"
            quoted = f"[Forwarded from {fwd_source}]: {quoted}"
        if quoted and not reply_msg.photo:
            reply_user = reply_msg.from_user
            reply_name = reply_user.first_name if reply_user else "Someone"
            user_text = f"[Replying to {reply_name}: \"{quoted}\"]\n\n{user_text}"

    if msg.chat.type in ("group", "supergroup"):
        # Сохраняем участника
        if user:
            group_members[chat_id][user.id] = {
                "name": user.first_name or user.username or "Morty",
                "username": user.username
            }
        # Сохраняем все сообщения в буфер контекста группы
        group_context[chat_id].append(f"{username}: {user_text[:100]}")

        bot_username = context.bot.username or ""
        if bot_username:
            user_text = user_text.replace(f"@{bot_username}", "").strip()

    async def keep_typing():
        for _ in range(20):
            await asyncio.sleep(4)
            try: await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            except: break

    init_chat(chat_id)

    # External services — no auto-detection, let Rick handle naturally via Claude

    # Проверяем: пользователь отвечает на фото-сообщение?
    reply_photo_path = None
    if msg.reply_to_message and msg.reply_to_message.photo:
        try:
            reply_photo = msg.reply_to_message.photo[-1]
            WORK_DIR.mkdir(parents=True, exist_ok=True)
            reply_photo_path = str(WORK_DIR / f"reply_photo_{chat_id}_{reply_photo.file_id[:8]}.jpg")
            rp_file = await context.bot.get_file(reply_photo.file_id)
            await rp_file.download_to_drive(reply_photo_path)
        except Exception as e:
            logger.warning(f"reply photo download failed: {e}")
            reply_photo_path = None

    typing = asyncio.create_task(keep_typing())

    if reply_photo_path:
        if msg.chat.type in ("group", "supergroup"):
            context_lines = list(group_context.get(chat_id, []))
            context_str = "\n".join(context_lines[-6:]) if context_lines else "(начало беседы)"
            vision_prompt = f"Контекст чата:\n{context_str}\n\n{username} отвечает на фото и спрашивает: {user_text}"
        else:
            vision_prompt = user_text
        response = await run_claude(vision_prompt, 90, image_path=reply_photo_path)
        try:
            os.unlink(reply_photo_path)
        except Exception:
            pass
        if msg.chat.type in ("group", "supergroup"):
            group_context[chat_id].append(f"Рик: {response[:100]}")
        typing.cancel()
        await send_response(msg, response, [], context)
        return
    # В группах используем специальный промпт с контекстом
    if msg.chat.type in ("group", "supergroup"):
        # Проверяем: есть ли недавнее фото и текущий вопрос относится к нему?
        photo_info = group_recent_photos.get(chat_id)
        recent_photo_path = None
        if photo_info and (time.time() - photo_info["ts"]) < 300:
            recent_context = list(group_context.get(chat_id, []))[-4:]
            has_recent_photo = any("[фото]" in str(m) for m in recent_context)
            if has_recent_photo and os.path.exists(photo_info["path"]):
                recent_photo_path = photo_info["path"]

        if recent_photo_path:
            context_lines = list(group_context.get(chat_id, []))
            context_str = "\n".join(context_lines[-6:]) if context_lines else "(no context)"
            vision_prompt = f"Chat context:\n{context_str}\n\n{username} asks about the photo: {user_text}"
            response = await run_claude(vision_prompt, 90, image_path=recent_photo_path)
            try:
                os.unlink(recent_photo_path)
                del group_recent_photos[chat_id]
            except Exception:
                pass
            if not response:
                response = "burp Can't see the photo, Morty"
            files = []
            group_context[chat_id].append(f"Рик: {response[:100]}")
        else:
            # Combined decision + response in one Claude call
            group_response = await maybe_respond_in_group(chat_id, username, user_text)
            if group_response:
                response, files = group_response, []
                group_context[chat_id].append(f"Рик: {group_response[:100]}")
            else:
                typing.cancel()
                return  # Rick decided to SKIP
    else:
        response, files = await ask_rick(chat_id, user_text)
    typing.cancel()

    await send_response(msg, response, files, context)

# ─── COMMANDS ─────────────────────────────────────────────

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
            await send_text(update.message, "Usage:\n`/news 14:30 AI startups` — daily news at 14:30 about AI startups\n`/news now quantum physics` — send now\n`/news off` — disable")
        return

    if args[0] == "off":
        config.pop(chat_id, None)
        save_news_config(config)
        # Remove scheduler job
        try: scheduler.remove_job(f"news_{chat_id}")
        except: pass
        await send_text(update.message, "Daily news disabled.")
        return

    if args[0] == "now":
        topic = " ".join(args[1:]) if len(args) > 1 else config.get(chat_id, {}).get("topic", "")
        if not topic:
            await send_text(update.message, "Specify topic: `/news now AI startups`")
            return
        await send_daily_news(context.bot, int(chat_id), topic)
        return

    # Parse time HH:MM
    time_str = args[0]
    try:
        hour, minute = map(int, time_str.split(":"))
        assert 0 <= hour <= 23 and 0 <= minute <= 59
    except:
        await send_text(update.message, "Wrong format. Use: `/news 14:30`")
        return

    if len(args) < 2:
        await send_text(update.message, "Specify topic: `/news 14:30 AI startups`")
        return
    topic = " ".join(args[1:])
    config[chat_id] = {"time": time_str, "topic": topic}
    save_news_config(config)

    # Add scheduler job
    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(
        send_daily_news, CronTrigger(hour=hour, minute=minute),
        args=[context.bot, int(chat_id), topic],
        id=f"news_{chat_id}", replace_existing=True
    )
    await send_text(update.message, f"Daily news at {time_str}, topic: {topic}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_histories[chat_id].clear()
    save_history(chat_id, chat_histories[chat_id])
    facts = load_facts(chat_id)
    note = " Кстати, я тебя помню." if facts else ""
    response, files = await ask_rick(chat_id, f"Открыли чат.{note} Поприветствуй коротко по-рикски. Скажи что умеешь: отвечать на вопросы, писать и запускать код, искать в интернете, открывать сайты через браузер, анализировать фото, понимать голосовые сообщения, создавать и присылать файлы (код, презентации, документы), иногда отвечать голосом.")
    await send_response(update.message, response, files, context)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_histories[chat_id].clear()
    save_history(chat_id, chat_histories[chat_id])
    response, _ = await ask_rick(chat_id, "Провал в памяти. Коротко.")
    await send_text(update.message, response)

async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_histories[chat_id].clear()
    save_history(chat_id, chat_histories[chat_id])
    save_facts(chat_id, [])
    await update.message.reply_text("burp Who are you? Starting from scratch.")

async def skill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /skill search|install|list"""
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
        msg = "📦 Установленные skills:\n" + "\n".join(f"• `{s}`" for s in installed)
        await update.message.reply_text(msg, parse_mode="Markdown")

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
        lines = ["📅 Задачи:"]
        for j in jobs:
            task_desc = j.args[1] if len(j.args) > 1 else "?"
            lines.append(f"• `{j.id}`\n  📌 {task_desc}\n  ⏰ {j.trigger}")
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

# ─── APP INIT ─────────────────────────────────────────────

async def post_init(application):
    src.scheduler._app = application
    scheduler.start()

    # Generate daily scenario on startup if not exists for today
    s = load_scenario()
    if not s.get("scenario"):
        asyncio.create_task(generate_daily_scenario())

    # Schedule daily scenario generation at random time between 6-10 AM
    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(
        generate_daily_scenario, CronTrigger(hour=8, minute=0),
        id="daily_scenario", replace_existing=True
    )

    # Restore news jobs from config
    news_config = load_news_config()
    for cid, cfg in news_config.items():
        try:
            h, m = map(int, cfg["time"].split(":"))
            scheduler.add_job(
                send_daily_news, CronTrigger(hour=h, minute=m),
                args=[application.bot, int(cid), cfg.get("topic", "science technology AI")],
                id=f"news_{cid}", replace_existing=True
            )
        except Exception:
            pass

    me = await application.bot.get_me()
    logger.info(f"@{me.username} — Rick v10.1 online (scheduler started, daily scenario)")
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    cleanup_work_dir()

def main():
    print("Rick Sanchez Bot v10 — scheduler, per-chat skills, OWNER_ID")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(CommandHandler("skill", skill_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("v10 started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
