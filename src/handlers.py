"""Telegram message handlers — text, voice, photo, document."""

import os
import time
import asyncio
import logging
import tempfile
import uuid

from telegram import Update
from telegram.ext import ContextTypes

import random
from src.config import WORK_DIR, RICK_NAMES, GROUP_RANDOM_CHANCE
from src.memory import (group_context, group_members,
                        group_recent_photos, init_chat)
from src.claude import run_claude
from src.media import transcribe_audio
from src.groups import maybe_respond_in_group
from src.reactions import pick_reaction, set_reaction
from src.core import ask_rick, send_response, send_text, is_rate_limited

logger = logging.getLogger(__name__)


def _get_forward_source(origin) -> str:
    """Extract source name from a MessageOrigin object (v21+ API)."""
    if hasattr(origin, "chat"):  # MessageOriginChannel
        return origin.chat.title or "channel"
    if hasattr(origin, "sender_chat"):  # MessageOriginChat
        return origin.sender_chat.title or "chat"
    if hasattr(origin, "sender_user"):  # MessageOriginUser
        return origin.sender_user.first_name or "someone"
    if hasattr(origin, "sender_user_name"):  # MessageOriginHiddenUser
        return origin.sender_user_name or "someone"
    return "someone"


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages via Whisper."""
    msg = update.message
    if not msg:
        return
    chat_id = update.effective_chat.id
    user = update.effective_user
    is_group = update.effective_chat.type in ["group", "supergroup"]
    username = user.first_name if user else "Morty"

    if user and is_group:
        group_members[chat_id][user.id] = {
            "name": user.first_name or user.username or "Morty",
            "username": user.username
        }

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

        # Handle both group and private via send_response (fixes missing voice/sticker/gif)
        if is_group:
            group_context[chat_id].append(f"{username}: [voice]: {text[:100]}")
            response = await maybe_respond_in_group(chat_id, username, f"[voice]: {text}")
            if not response:
                return
            group_context[chat_id].append(f"Rick: {response[:300]}")
            await send_response(msg, response, [], context)
        else:
            init_chat(chat_id)
            response, files = await ask_rick(chat_id, f"[voice message]: {text}")
            await send_response(msg, response, files, context)

    finally:
        try:
            os.unlink(ogg_path)
        except Exception:
            pass


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming documents."""
    msg = update.message
    if not msg:
        return
    chat_id = update.effective_chat.id
    user = update.effective_user
    is_group = update.effective_chat.type in ["group", "supergroup"]
    username = user.first_name if user else "Morty"

    if user and is_group:
        group_members[chat_id][user.id] = {
            "name": user.first_name or user.username or "Morty",
            "username": user.username
        }

    filename = msg.document.file_name or "unknown file"
    user_message = f"User sent a file: {filename}. What do you think?"

    if is_group:
        group_context[chat_id].append(f"{username}: [sent file: {filename}]")
        response = await maybe_respond_in_group(chat_id, username, user_message)
        if not response:
            return
        group_context[chat_id].append(f"Rick: {response[:300]}")
        await send_text(msg, response)
    else:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        init_chat(chat_id)
        response, files = await ask_rick(chat_id, user_message)
        await send_response(msg, response, files, context)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming photos via Claude vision."""
    msg = update.message
    if not msg:
        return
    chat_id = update.effective_chat.id
    chat_type = msg.chat.type
    user = update.effective_user
    username = user.first_name if user else "Someone"

    if user and chat_type in ("group", "supergroup"):
        group_members[chat_id][user.id] = {
            "name": user.first_name or user.username or "Morty",
            "username": user.username
        }

    if chat_type in ("group", "supergroup"):
        group_context[chat_id].append(f"{username}: [photo]")

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
        has_rick_in_caption = "рик" in caption_lower or "rick" in caption_lower or bool(
            bot_username and f"@{bot_username.lower()}" in caption_lower)

        if not has_rick_in_caption and not reply_to_bot:
            return

        user_text = caption if caption else "What's in this photo? Describe it Rick-style."
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        async def keep_typing():
            for _ in range(20):
                await asyncio.sleep(4)
                try: await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                except Exception: break

        init_chat(chat_id)
        typing = asyncio.create_task(keep_typing())
        context_lines = list(group_context.get(chat_id, []))
        context_str = "\n".join(context_lines[-8:]) if context_lines else "(start of chat)"
        vision_prompt = f"Chat context:\n{context_str}\n\n{username} sent a photo. {user_text}"
        response = await run_claude(vision_prompt, 90, image_path=image_path)
        group_context[chat_id].append(f"Rick: {response[:300]}")
        typing.cancel()
        await send_response(msg, response, [], context)
        return

    # Private chat
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

    caption = msg.caption or ""
    rate_keywords = ["rate", "оцени", "оценка", "оценить", "/rate"]
    if any(kw in caption.lower() for kw in rate_keywords):
        user_text = f"Rate this image X/10 with a brutal Rick-style review. User says: {caption}"
    else:
        user_text = caption or "What's in this photo? Describe it, Rick-style."

    async def keep_typing():
        for _ in range(20):
            await asyncio.sleep(4)
            try: await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            except Exception: break

    init_chat(chat_id)
    typing = asyncio.create_task(keep_typing())
    try:
        # ask_rick now includes full context even with image_path
        response, files = await ask_rick(chat_id, user_text, image_path=image_path)
    finally:
        typing.cancel()
        try: os.unlink(image_path)
        except Exception: pass

    await send_response(msg, response, files, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages."""
    msg = update.message
    if not msg or not msg.text:
        return
    chat_id = update.effective_chat.id
    user_text = msg.text
    user = update.effective_user
    username = user.first_name if user else "Someone"

    # Rate limiting with feedback
    if user and is_rate_limited(user.id):
        await msg.reply_text("Morty, shut up for a minute. You're spamming.")
        return

    # React to user's message
    emoji = pick_reaction(user_text)
    if emoji:
        await set_reaction(context.bot, chat_id, msg.message_id, emoji)

    # Inject forwarded message content (python-telegram-bot v21+ uses forward_origin)
    if msg.forward_origin:
        fwd_text = msg.text or msg.caption or ""
        fwd_source = _get_forward_source(msg.forward_origin)
        user_text = f"[Forwarded from {fwd_source}]: {fwd_text}"

    # Inject reply context
    if msg.reply_to_message:
        reply_msg = msg.reply_to_message
        quoted = ""
        if reply_msg.text:
            quoted = reply_msg.text[:500]
        elif reply_msg.caption:
            quoted = reply_msg.caption[:500]
        if reply_msg.forward_origin:
            fwd_source = _get_forward_source(reply_msg.forward_origin)
            quoted = f"[Forwarded from {fwd_source}]: {quoted}"
        if quoted and not reply_msg.photo:
            reply_user = reply_msg.from_user
            reply_name = reply_user.first_name if reply_user else "Someone"
            user_text = f"[Replying to {reply_name}: \"{quoted}\"]\n\n{user_text}"

    if msg.chat.type in ("group", "supergroup"):
        if user:
            group_members[chat_id][user.id] = {
                "name": user.first_name or user.username or "Morty",
                "username": user.username
            }
        group_context[chat_id].append(f"{username}: {user_text[:300]}")

        bot_username = context.bot.username or ""
        text_lower = user_text.lower()

        # Determine if Rick is directly addressed
        is_mentioned = bot_username and f"@{bot_username.lower()}" in text_lower
        is_reply_to_bot = (msg.reply_to_message and msg.reply_to_message.from_user
                           and msg.reply_to_message.from_user.username == bot_username)
        is_name_called = any(name in text_lower for name in RICK_NAMES)
        directly_addressed = is_mentioned or is_reply_to_bot or is_name_called

        # Pre-filter: only call Claude if directly addressed or random chance hits
        if not directly_addressed and random.random() > GROUP_RANDOM_CHANCE:
            return  # silently skip — save API call

        if bot_username:
            user_text = user_text.replace(f"@{bot_username}", "").strip()

    async def keep_typing():
        for _ in range(20):
            await asyncio.sleep(4)
            try: await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            except Exception: break

    init_chat(chat_id)

    # Check: user replying to a photo message?
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
            context_str = "\n".join(context_lines[-8:]) if context_lines else "(start of chat)"
            vision_prompt = f"Chat context:\n{context_str}\n\n{username} replies to a photo and asks: {user_text}"
        else:
            vision_prompt = user_text
        response = await run_claude(vision_prompt, 90, image_path=reply_photo_path)
        try:
            os.unlink(reply_photo_path)
        except Exception:
            pass
        if msg.chat.type in ("group", "supergroup"):
            group_context[chat_id].append(f"Rick: {response[:300]}")
        typing.cancel()
        await send_response(msg, response, [], context)
        return

    # Group messages
    if msg.chat.type in ("group", "supergroup"):
        photo_info = group_recent_photos.get(chat_id)
        recent_photo_path = None
        if photo_info and (time.time() - photo_info["ts"]) < 300:
            recent_context = list(group_context.get(chat_id, []))[-4:]
            has_recent_photo = any("[photo]" in str(m) or "[фото]" in str(m) for m in recent_context)
            if has_recent_photo and os.path.exists(photo_info["path"]):
                recent_photo_path = photo_info["path"]

        if recent_photo_path:
            context_lines = list(group_context.get(chat_id, []))
            context_str = "\n".join(context_lines[-8:]) if context_lines else "(no context)"
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
            group_context[chat_id].append(f"Rick: {response[:300]}")
        elif directly_addressed:
            # Directly addressed — full prompt with file creation support
            ctx_lines = list(group_context.get(chat_id, []))[-8:]
            response, files = await ask_rick(chat_id, user_text, group_context_lines=ctx_lines)
            group_context[chat_id].append(f"Rick: {response[:300]}")
        else:
            # Random interjection — lightweight prompt
            group_response = await maybe_respond_in_group(chat_id, username, user_text)
            if group_response:
                response, files = group_response, []
                group_context[chat_id].append(f"Rick: {group_response[:100]}")
            else:
                typing.cancel()
                return  # Rick decided to SKIP
    else:
        response, files = await ask_rick(chat_id, user_text)
    typing.cancel()

    await send_response(msg, response, files, context)
