"""Core logic — prompt building, Claude interaction, response delivery."""

import json
import os
import time
import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime
from zoneinfo import ZoneInfo

from src.config import MAX_HISTORY, MAX_FACTS, WORK_DIR, TIMEZONE
from src.prompts import RICK_SYSTEM, EXTRACT_FACTS_PROMPT, SUMMARIZE_PROMPT, PROFILE_PROMPT
from src.memory import (chat_histories, init_chat, save_history,
                        load_facts, save_facts, load_summaries, save_summary,
                        load_profile, save_profile)
from src.claude import run_claude
from src.media import find_created_files, find_new_workdir_files
from src.skills import load_skills_for_chat
from src.tts import generate_voice
from src.memes import maybe_send_gif
from src.stickers import pick_sticker
from src.scenario import get_scenario_for_prompt
from src.mood import update_mood, get_mood_modifier

logger = logging.getLogger(__name__)

# --- RATE LIMITING ---
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 10     # max messages per window
_user_timestamps: dict[int, deque] = defaultdict(lambda: deque(maxlen=RATE_LIMIT_MAX))


def is_rate_limited(user_id: int) -> bool:
    now = time.time()
    timestamps = _user_timestamps[user_id]
    while timestamps and now - timestamps[0] > RATE_LIMIT_WINDOW:
        timestamps.popleft()
    if len(timestamps) >= RATE_LIMIT_MAX:
        return True
    timestamps.append(now)
    return False


# --- FACTS ---

async def extract_and_save_facts(chat_id, user_msg, rick_response):
    try:
        current = load_facts(chat_id)
        raw = await run_claude(EXTRACT_FACTS_PROMPT.format(
            user=user_msg, response=rick_response,
            current_facts="\n".join(current) if current else "none"), timeout=15)
        if not raw or "NO" in raw.upper():
            return
        new_facts = [l.lstrip("- ").strip() for l in raw.split("\n") if l.strip().startswith("-")]
        if new_facts:
            updated = current + new_facts
            if len(updated) > MAX_FACTS:
                pruned = await run_claude(
                    f"Keep the {MAX_FACTS} most important facts:\n" + "\n".join(f"- {f}" for f in updated) +
                    "\nFormat each with '- '", 15)
                updated = [l.lstrip("- ").strip() for l in pruned.split("\n") if l.strip().startswith("-")]
            save_facts(chat_id, updated)
    except Exception as e:
        logger.error(f"Facts error: {e}")


# --- CORE LOGIC ---

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

    # Daily scenario
    prompt += get_scenario_for_prompt(chat_id) + "\n"

    # Dynamic mood (per-chat)
    mood_mod = get_mood_modifier(chat_id)
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
        for s in summaries[-5:]:
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
    update_mood(chat_id, user_message or "")

    # Build full prompt with context — even for photos (fixes missing context bug)
    prompt = build_prompt(chat_id, user_message or "What's in this photo? Describe it Rick-style.")
    response = await run_claude(prompt, 120, image_path=image_path)

    if not response:
        return "burp ...can't hear you. Say again, Morty.", []

    files = list(set(find_created_files(response) + find_new_workdir_files(start_time)))

    chat_histories[chat_id].append(user_message or "[photo]")
    chat_histories[chat_id].append(response)
    save_history(chat_id, chat_histories[chat_id])

    # Extract facts every 10 message pairs (was 5 — too expensive)
    if len(chat_histories[chat_id]) % 20 == 0:
        asyncio.create_task(extract_and_save_facts(chat_id, user_message or "[photo]", response))

    # Summarize when history is full
    if len(chat_histories[chat_id]) >= MAX_HISTORY * 2:
        asyncio.create_task(summarize_and_update_profile(chat_id))

    return response, files


async def summarize_and_update_profile(chat_id):
    """Summarize current conversation and update user profile. Runs in background."""
    try:
        history = list(chat_histories[chat_id])
        if not history:
            return

        conv_lines = []
        for i in range(0, len(history), 2):
            if i < len(history): conv_lines.append(f"User: {history[i]}")
            if i+1 < len(history): conv_lines.append(f"Rick: {history[i+1]}")
        conv_text = "\n".join(conv_lines)

        summary_raw = await run_claude(
            SUMMARIZE_PROMPT.format(conversation=conv_text), timeout=15)
        if summary_raw:
            save_summary(chat_id, {
                "date": datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d"),
                "summary": summary_raw.strip()
            })
            logger.info(f"Saved conversation summary for chat {chat_id}")

        current_profile = load_profile(chat_id)
        profile_raw = await run_claude(
            PROFILE_PROMPT.format(
                current_profile=json.dumps(current_profile, ensure_ascii=False) if current_profile else "{}",
                conversation=conv_text[-2000:]
            ), timeout=15)
        if profile_raw:
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


# --- RESPONSE HELPERS ---

async def send_text(msg, text):
    """Send text with Markdown formatting, fallback to plain text."""
    try:
        await msg.reply_text(text, parse_mode="Markdown")
    except Exception:
        try:
            await msg.reply_text(text, parse_mode=None)
        except Exception as e:
            logger.error(f"Send text error: {e}")


async def send_response(msg, response, files, context):
    """Send text OR voice, plus any created files. Supports multi-message via ---."""
    parts = [p.strip() for p in response.split("---") if p.strip()]

    if len(parts) > 1:
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
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
                await asyncio.sleep(1)
    else:
        voice = await generate_voice(response)
        if voice:
            try:
                await context.bot.send_voice(chat_id=msg.chat_id, voice=voice)
            except Exception as e:
                logger.warning(f"TTS send error: {e}")
                await send_text(msg, response)
        else:
            await send_text(msg, response)

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
                    caption=os.path.basename(file_path)
                )
            logger.info(f"Sent file: {file_path}")
            if str(WORK_DIR) in file_path:
                os.unlink(file_path)
        except Exception as e:
            logger.error(f"File send error {file_path}: {e}")
