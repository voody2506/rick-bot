#!/usr/bin/env python3
"""Rick Sanchez Bot v10 — modular entry point."""

from dotenv import load_dotenv
load_dotenv()

import os
import re
import time
import asyncio
import logging
import tempfile
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

from src.config import BOT_TOKEN, OWNER_ID, MAX_FACTS, MEMORY_DIR, WORK_DIR, SKILLS_DIR, TOKENS_DIR
from src.prompts import RICK_SYSTEM, EXTRACT_FACTS_PROMPT
from src.memory import (chat_histories, group_context, group_members, group_recent_photos,
                        PHOTO_QUESTION_KEYWORDS, init_chat, save_history,
                        load_facts, save_facts)
from src.claude import run_claude
from src.media import (transcribe_audio, web_search,
                       find_created_files, find_new_workdir_files, cleanup_work_dir)
from src.groups import should_respond_in_group, build_group_response
from src.parallel import try_parallel
from src.scheduler import scheduler, is_schedule_request, handle_schedule_request
from src.skills import (load_skills_for_chat, search_clawhub, install_clawhub_skill,
                        detect_service, handle_service_request)

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
    prompt = RICK_SYSTEM + "\n\n"
    skills = load_skills_for_chat(chat_id)
    if skills:
        prompt += f"УСТАНОВЛЕННЫЕ SKILLS (инструкции из ClawHub):\n{skills}\n\n"
    if facts:
        prompt += "Факты о пользователе:\n" + "\n".join(f"- {f}" for f in facts) + "\n\n"
    if history:
        prompt += "История:\n"
        for i in range(0, len(history), 2):
            if i < len(history): prompt += f"Собеседник: {history[i]}\n"
            if i+1 < len(history): prompt += f"Рик: {history[i+1]}\n"
        prompt += "\n"
    prompt += f"Собеседник: {user_message}\nРик:"
    return prompt

async def ask_rick(chat_id, user_message, image_path=None):
    init_chat(chat_id)
    start_time = time.time()

    if image_path:
        prompt = user_message or "Что на этом фото? Опиши по-рикски."
        response = await run_claude(prompt, 90, image_path=image_path)
    else:
        # Detect search intent and inject real web results before calling Claude
        search_keywords = ["найди", "поищи", "что такое", "расскажи о", "расскажи про",
                           "где найти", "сколько стоит", "как найти", "поиск",
                           "find", "search", "look up"]
        msg_lower = (user_message or "").lower()
        augmented_message = user_message
        if any(kw in msg_lower for kw in search_keywords):
            search_results = await web_search(user_message)
            if search_results:
                augmented_message = f"{user_message}\n\n[Результаты поиска]:\n{search_results}"
                logger.info(f"Search results injected for: {user_message[:60]}")

        response = await try_parallel(chat_id, augmented_message)
        if not response:
            response = await run_claude(build_prompt(chat_id, augmented_message), 120)

    if not response:
        return "ырп ...не слышу. Повтори, Морти.", []

    # Объединяем regex-файлы и новые файлы из WORK_DIR
    files = list(set(find_created_files(response) + find_new_workdir_files(start_time)))

    chat_histories[chat_id].append(user_message or "[фото]")
    chat_histories[chat_id].append(response)
    save_history(chat_id, chat_histories[chat_id])
    asyncio.create_task(extract_and_save_facts(chat_id, user_message or "[фото]", response))

    return response, files

# ─── HANDLERS ─────────────────────────────────────────────

async def send_response(msg, response, files, context):
    """Отправляет текст и все созданные файлы"""
    await msg.reply_text(response)
    if not files and any(kw in response.lower() for kw in FILE_INTENT_KEYWORDS):
        await msg.reply_text("📎 [Функция отправки файлов в разработке — скоро Рик сможет скидывать файлы напрямую]")
    for file_path in files:
        try:
            with open(file_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=msg.chat_id,
                    document=f,
                    filename=os.path.basename(file_path),
                    caption=f"📎 {os.path.basename(file_path)}"
                )
            logger.info(f"Отправлен файл: {file_path}")
            if str(WORK_DIR) in file_path:
                os.unlink(file_path)
        except Exception as e:
            logger.error(f"Ошибка отправки файла {file_path}: {e}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка голосовых сообщений через Whisper"""
    msg = update.message
    if not msg: return
    chat_id = update.effective_chat.id
    user = update.effective_user
    is_group = update.effective_chat.type in ["group", "supergroup"]
    username = user.first_name if user else "Морти"

    if user and is_group:
        group_members[chat_id][user.id] = {
            "name": user.first_name or user.username or "Морти",
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
            await msg.reply_text("Ырп... ничего не разобрал, Морти.")
            return

        logger.info(f"Voice transcribed: {text[:100]}")

        # Process like a text message
        if is_group:
            group_context[chat_id].append(f"{username}: [голосовое]: {text[:100]}")
            response = await build_group_response(chat_id, username, f"[голосовое]: {text}")
            if response:
                group_context[chat_id].append(f"Рик: {response[:100]}")
            else:
                response = "ырп Что ты там сказал?"
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
    username = user.first_name if user else "Морти"

    if user and is_group:
        group_members[chat_id][user.id] = {
            "name": user.first_name or user.username or "Морти",
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
            response = "Ырп, файл прислал. Интересно."
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
            "name": user.first_name or user.username or "Морти",
            "username": user.username
        }

    if chat_type in ("group", "supergroup"):
        group_context[chat_id].append(f"{username}: [фото]")

        # ВСЕГДА скачиваем фото в группе — нужно для follow-up вопросов
        photo = msg.photo[-1]
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        image_path = str(WORK_DIR / f"photo_{chat_id}_{photo.file_id[:8]}.jpg")
        try:
            file = await context.bot.get_file(photo.file_id)
            await file.download_to_drive(image_path)
        except Exception as e:
            await msg.reply_text(f"ырп Не смог скачать фото: {e}")
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
    image_path = str(WORK_DIR / f"photo_{chat_id}_{photo.file_id[:8]}.jpg")

    try:
        file = await context.bot.get_file(photo.file_id)
        await file.download_to_drive(image_path)
    except Exception as e:
        await msg.reply_text(f"ырп Не смог скачать фото: {e}")
        return

    user_text = msg.caption or "Что на этом фото? Опиши по-рикски."

    async def keep_typing():
        for _ in range(20):
            await asyncio.sleep(4)
            try: await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            except: break

    init_chat(chat_id)
    typing = asyncio.create_task(keep_typing())
    response, files = await ask_rick(chat_id, user_text, image_path=image_path)
    typing.cancel()

    try: os.unlink(image_path)
    except: pass

    await send_response(msg, response, files, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text: return
    chat_id = update.effective_chat.id
    user_text = msg.text
    user = update.effective_user
    username = user.first_name if user else "Кто-то"

    if msg.chat.type in ("group", "supergroup"):
        # Сохраняем участника
        if user:
            group_members[chat_id][user.id] = {
                "name": user.first_name or user.username or "Морти",
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

    # Авто-флоу внешних сервисов
    service = detect_service(user_text)
    if service:
        handled = await handle_service_request(update, context, user.id, chat_id, service, user_text)
        if handled:
            return

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
            response, files = group_response or "ырп Не вижу фото, Морти", []
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
    await update.message.reply_text("ырп Кто ты? Начинаем с нуля.")

async def skill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /skill search|install|list"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Использование:\n"
            "  `/skill search <запрос>` — поиск на ClawHub\n"
            "  `/skill install <slug>` — установить skill\n"
            "  `/skill list` — список установленных",
            parse_mode="Markdown"
        )
        return

    subcmd = args[0].lower()
    rest = " ".join(args[1:]).strip()
    chat_id = update.effective_chat.id

    if subcmd == "list":
        chat_skills_dir = SKILLS_DIR / str(chat_id)
        if not chat_skills_dir.exists():
            await update.message.reply_text("Нет установленных skills. Попробуй `/skill search <что-нибудь>`", parse_mode="Markdown")
            return
        installed = [d.name for d in sorted(chat_skills_dir.iterdir()) if d.is_dir() and (d / "SKILL.md").exists()]
        if not installed:
            await update.message.reply_text("Нет установленных skills.")
            return
        msg = "📦 Установленные skills:\n" + "\n".join(f"• `{s}`" for s in installed)
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif subcmd == "search":
        if not rest:
            await update.message.reply_text("Укажи запрос: `/skill search <что ищешь>`", parse_mode="Markdown")
            return
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        result = await search_clawhub(rest)
        await update.message.reply_text(result, parse_mode="Markdown")

    elif subcmd == "install":
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("Морти, это не для тебя.")
            return
        if not rest:
            await update.message.reply_text("Укажи slug: `/skill install <slug>`", parse_mode="Markdown")
            return
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        result = await install_clawhub_skill(rest, chat_id)
        await update.message.reply_text(result, parse_mode="Markdown")

    else:
        await update.message.reply_text(f"Неизвестная подкоманда «{subcmd}». Используй: search, install, list")

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/schedule list | cancel <id>"""
    args = context.args or []
    chat_id = update.effective_chat.id

    if not args:
        await update.message.reply_text(
            "Использование:\n"
            "  `/schedule list` — задачи этого чата\n"
            "  `/schedule cancel <id>` — отменить задачу",
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
            await update.message.reply_text("Нет активных задач для этого чата.")
            return
        lines = ["📅 Задачи:"]
        for j in jobs:
            task_desc = j.args[1] if len(j.args) > 1 else "?"
            lines.append(f"• `{j.id}`\n  📌 {task_desc}\n  ⏰ {j.trigger}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif subcmd == "cancel":
        if len(args) < 2:
            await update.message.reply_text("Укажи ID: `/schedule cancel <id>`", parse_mode="Markdown")
            return
        job_id = args[1]
        prefix_once = f"once_{chat_id}_"
        prefix_repeat = f"repeat_{chat_id}_"
        if not (job_id.startswith(prefix_once) or job_id.startswith(prefix_repeat)):
            await update.message.reply_text("Это не твоя задача, Морти.")
            return
        try:
            scheduler.remove_job(job_id)
            await update.message.reply_text(f"Отменено. `{job_id}`", parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(f"Задача `{job_id}` не найдена.", parse_mode="Markdown")

    else:
        await update.message.reply_text(f"Неизвестная команда «{subcmd}». Используй: list, cancel")

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
