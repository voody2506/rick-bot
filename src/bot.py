#!/usr/bin/env python3
"""Rick Sanchez Bot v10 — modular entry point."""

from dotenv import load_dotenv
load_dotenv()

import json
import os
import re
import time
import asyncio
import logging
import tempfile
import uuid
from collections import defaultdict, deque
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

from src.config import BOT_TOKEN, OWNER_ID, MAX_HISTORY, MAX_FACTS, MEMORY_DIR, WORK_DIR, SKILLS_DIR, TOKENS_DIR

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
from src.prompts import RICK_SYSTEM, EXTRACT_FACTS_PROMPT, SUMMARIZE_PROMPT, PROFILE_PROMPT
from src.memory import (chat_histories, group_context, group_members, group_recent_photos,
                        PHOTO_QUESTION_KEYWORDS, init_chat, save_history,
                        load_facts, save_facts, load_summaries, save_summary,
                        load_profile, save_profile)
from src.claude import run_claude
from src.media import (transcribe_audio, web_search,
                       find_created_files, find_new_workdir_files, cleanup_work_dir)
from src.groups import should_respond_in_group, build_group_response
from src.parallel import try_parallel
from src.scheduler import scheduler, is_schedule_request, handle_schedule_request
from src.skills import load_skills_for_chat, search_clawhub, install_clawhub_skill
from src.tts import generate_voice
from src.memes import maybe_get_meme
from src.reactions import pick_reaction, set_reaction
from src.stickers import pick_sticker

import src.scheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

FILE_INTENT_KEYWORDS = ["вот файл", "скидываю", "держи файл"]

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
    prompt = RICK_SYSTEM + "\n\n"

    # Time awareness
    now = datetime.now()
    prompt += f"Current date/time: {now.strftime('%Y-%m-%d %H:%M, %A')}\n\n"

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
    prompt += f"User: {user_message}\nRick:"
    return prompt

async def ask_rick(chat_id, user_message, image_path=None):
    init_chat(chat_id)
    start_time = time.time()

    if image_path:
        prompt = user_message or "Что на этом фото? Опиши по-рикски."
        response = await run_claude(prompt, 90, image_path=image_path)
    else:
        # Web search only for longer messages with explicit search intent
        search_keywords = ["найди", "поищи", "что такое", "расскажи о", "расскажи про",
                           "где найти", "сколько стоит", "как найти",
                           "find", "search", "look up", "what is"]
        msg_lower = (user_message or "").lower()
        augmented_message = user_message
        if len(user_message) > 15 and any(kw in msg_lower for kw in search_keywords):
            search_results = await web_search(user_message)
            if search_results:
                augmented_message = f"{user_message}\n\n[Search results]:\n{search_results}"
                logger.info(f"Search results injected for: {user_message[:60]}")

        # Parallel only for complex messages (long + contains list/comparison markers)
        parallel_markers = ["и ", "а также", "плюс", "сравни", "vs", "versus",
                            "and also", "compare", "list", "перечисли"]
        if len(augmented_message) > 60 and any(m in msg_lower for m in parallel_markers):
            response = await try_parallel(chat_id, augmented_message)
        else:
            response = None
        if not response:
            response = await run_claude(build_prompt(chat_id, augmented_message), 120)

    if not response:
        return "*burp* ...can't hear you. Say again, Morty.", []

    # Объединяем regex-файлы и новые файлы из WORK_DIR
    files = list(set(find_created_files(response) + find_new_workdir_files(start_time)))

    chat_histories[chat_id].append(user_message or "[фото]")
    chat_histories[chat_id].append(response)
    save_history(chat_id, chat_histories[chat_id])
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
                "date": datetime.now().strftime("%Y-%m-%d"),
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

# ─── HANDLERS ─────────────────────────────────────────────

async def send_response(msg, response, files, context):
    """Send text OR voice, plus any created files."""
    # TTS — send voice instead of text if triggered
    voice = await generate_voice(response)
    if voice:
        try:
            await context.bot.send_voice(chat_id=msg.chat_id, voice=voice)
        except Exception as e:
            logger.warning(f"TTS send error: {e}")
            await msg.reply_text(response)  # fallback to text
    else:
        await msg.reply_text(response)

    # Meme GIF or sticker — occasionally send one
    meme_result = await maybe_get_meme(response)
    if meme_result:
        meme_buf, mood = meme_result
        try:
            await context.bot.send_animation(chat_id=msg.chat_id, animation=meme_buf)
        except Exception as e:
            logger.warning(f"Meme send error: {e}")
    else:
        sticker_id = pick_sticker(response)
        if sticker_id:
            try:
                await context.bot.send_sticker(chat_id=msg.chat_id, sticker=sticker_id)
            except Exception as e:
                logger.warning(f"Sticker send error: {e}")

    if not files and any(kw in response.lower() for kw in FILE_INTENT_KEYWORDS):
        await msg.reply_text("📎 [File sending in development]")
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
        bot_username = context.bot.username or ""
        reply_to_bot = (msg.reply_to_message and msg.reply_to_message.from_user
                       and msg.reply_to_message.from_user.username == bot_username)
        if not should_respond_in_group(f"[голосовое от {username}]", bot_username, reply_to_bot, chat_id, username):
            group_context[chat_id].append(f"{username}: [голосовое сообщение]")
            return

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
            response = await build_group_response(chat_id, username, f"[голосовое]: {text}")
            if response:
                group_context[chat_id].append(f"Рик: {response[:100]}")
            else:
                response = "burp What did you say?"
        else:
            init_chat(chat_id)
            response, files = await ask_rick(chat_id, f"[голосовое сообщение]: {text}")

        await msg.reply_text(response)

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
        bot_username = context.bot.username or ""
        reply_to_bot = (msg.reply_to_message and msg.reply_to_message.from_user
                       and msg.reply_to_message.from_user.username == bot_username)
        if not should_respond_in_group(user_message, bot_username, reply_to_bot, chat_id, username):
            group_context[chat_id].append(f"{username}: [прислал файл: {filename}]")
            return
        group_context[chat_id].append(f"{username}: [прислал файл: {filename}]")
        response = await build_group_response(chat_id, username, user_message)
        if not response:
            response = "Burp, sent a file. Interesting."
        group_context[chat_id].append(f"Рик: {response[:100]}")
        await msg.reply_text(response)
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

        if not has_rick_in_caption and not should_respond_in_group(
                caption or "[фото]", bot_username, reply_to_bot, chat_id, username):
            return  # Фото сохранено для follow-up, но не отвечаем сразу

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

    # Inject reply context (#7)
    if msg.reply_to_message and msg.reply_to_message.text and not msg.reply_to_message.photo:
        quoted = msg.reply_to_message.text[:200]
        reply_user = msg.reply_to_message.from_user
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
        reply_to_bot = (msg.reply_to_message and msg.reply_to_message.from_user
                       and msg.reply_to_message.from_user.username == bot_username)
        tl_pre = user_text.lower()
        is_skill_cmd = any(t in tl_pre for t in [
            "найди skill", "найди скилл", "есть ли skill", "есть ли скилл",
            "поищи skill", "поищи скилл", "skill search", "search skill",
            "установи skill", "установи скилл", "install skill",
            "skill install", "поставь skill", "поставь скилл"
        ])
        if not is_skill_cmd and not should_respond_in_group(user_text, bot_username, reply_to_bot, chat_id, username): return
        if bot_username:
            user_text = user_text.replace(f"@{bot_username}", "").strip()

    async def keep_typing():
        for _ in range(20):
            await asyncio.sleep(4)
            try: await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            except: break

    init_chat(chat_id)

    # Детект запросов на поиск/установку skill по естественному языку
    tl = user_text.lower()
    skill_search_triggers = ["найди skill", "найди скилл", "есть ли skill", "есть ли скилл",
                              "поищи skill", "поищи скилл", "skill search", "search skill"]
    skill_install_triggers = ["установи skill", "установи скилл", "install skill",
                               "skill install", "поставь skill", "поставь скилл"]
    for trigger in skill_search_triggers:
        if trigger in tl:
            query = re.sub(r'.*(?:' + re.escape(trigger) + r')\s*', '', user_text, flags=re.IGNORECASE).strip()
            if not query:
                query = user_text
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            result = await search_clawhub(query)
            try:
                await msg.reply_text(result, parse_mode="Markdown")
            except Exception:
                await msg.reply_text(result)
            return
    for trigger in skill_install_triggers:
        if trigger in tl:
            slug = re.sub(r'.*(?:' + re.escape(trigger) + r')\s*', '', user_text, flags=re.IGNORECASE).strip().split()[0] if re.sub(r'.*(?:' + re.escape(trigger) + r')\s*', '', user_text, flags=re.IGNORECASE).strip() else ""
            if slug:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                result = await install_clawhub_skill(slug, chat_id)
                try:
                    await msg.reply_text(result, parse_mode="Markdown")
                except Exception:
                    await msg.reply_text(result)
                return

    # Детект запросов на создание расписания
    if is_schedule_request(user_text):
        result = await handle_schedule_request(chat_id, user_text)
        await msg.reply_text(result, parse_mode="Markdown")
        return

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
            msg_lower_check = user_text.lower()
            is_photo_question = ("?" in user_text or
                                 any(kw in msg_lower_check for kw in PHOTO_QUESTION_KEYWORDS))
            if has_recent_photo and is_photo_question and os.path.exists(photo_info["path"]):
                recent_photo_path = photo_info["path"]

        if recent_photo_path:
            context_lines = list(group_context.get(chat_id, []))
            context_str = "\n".join(context_lines[-6:]) if context_lines else "(начало беседы)"
            vision_prompt = f"Контекст чата:\n{context_str}\n\n{username} спрашивает про фото выше: {user_text}"
            group_response = await run_claude(vision_prompt, 90, image_path=recent_photo_path)
            try:
                os.unlink(recent_photo_path)
                del group_recent_photos[chat_id]
            except Exception:
                pass
            response, files = group_response or "burp Can't see the photo, Morty", []
            group_context[chat_id].append(f"Рик: {response[:100]}")
        else:
            group_response = await build_group_response(chat_id, username, user_text)
            if group_response:
                response, files = group_response, []
                # Сохраняем ответ Рика в контекст группы
                group_context[chat_id].append(f"Рик: {group_response[:100]}")
            else:
                response, files = await ask_rick(chat_id, user_text)
    else:
        response, files = await ask_rick(chat_id, user_text)
    typing.cancel()

    await send_response(msg, response, files, context)

# ─── COMMANDS ─────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_histories[chat_id].clear()
    save_history(chat_id, chat_histories[chat_id])
    facts = load_facts(chat_id)
    note = " Кстати, я тебя помню." if facts else ""
    response, files = await ask_rick(chat_id, f"Открыли чат.{note} Поприветствуй коротко. Скажи что умеешь: отвечать на вопросы, писать код, искать в интернете, анализировать фото, принимать голосовые сообщения, создавать и присылать файлы.")
    await send_response(update.message, response, files, context)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_histories[chat_id].clear()
    save_history(chat_id, chat_histories[chat_id])
    response, _ = await ask_rick(chat_id, "Провал в памяти. Коротко.")
    await update.message.reply_text(response)

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
    me = await application.bot.get_me()
    logger.info(f"@{me.username} — Rick v10.1 online (scheduler started, per-chat skills, OWNER_ID)")
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
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("v10 started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
