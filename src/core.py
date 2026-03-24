"""Core logic — prompt building, Claude interaction, response delivery."""

import json
import os
import re
import time
import random
import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime
from zoneinfo import ZoneInfo

from src.config import MAX_HISTORY, MAX_FACTS, WORK_DIR, TIMEZONE
from src.prompts import RICK_SYSTEM, EXTRACT_FACTS_PROMPT, SUMMARIZE_PROMPT, PROFILE_PROMPT
from src.memory import (chat_histories, init_chat, save_history,
                        load_facts, save_facts, load_summaries, save_summary,
                        load_profile, save_profile,
                        save_user_profile)
from src.claude import run_claude
from src.media import (find_created_files, find_new_workdir_files, run_generator_scripts,
                        web_search, web_search_x, async_search_image, async_search_video)
from src.browser import navigate, click, scroll, fill_form, close_session
from src.pages import save_page, render_template
from src.skills import load_skills_for_chat
from src.tts import generate_voice
from src.memes import maybe_send_gif
from src.stickers import pick_sticker
from src.scenario import get_scenario_for_prompt
from src.mood import update_mood, get_mood_modifier
from src.drinks import take_drink, get_drunk_level
from src.challenges import maybe_start_challenge, has_pending_challenge, resolve_challenge

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

def build_prompt(chat_id, user_message, group_context_lines=None):
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

    # Drunk level
    drunk = get_drunk_level(chat_id)
    if drunk:
        prompt += f"DRUNK STATE: {drunk}\n\n"

    # User profile + nickname
    if profile:
        nickname = profile.get("nickname")
        if nickname and nickname != "null":
            prompt += f"You call this user \"{nickname}\" — always use this nickname.\n"
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
    # Group chat context — recent messages from the group
    if group_context_lines:
        prompt += "Recent group chat messages:\n"
        for line in group_context_lines:
            prompt += f"  {line}\n"
        prompt += "\nIMPORTANT: React to the conversation context above. If the user asks to 'comment on the situation', 'what do you think', etc. — they mean the topic being discussed in recent messages. ALWAYS engage with the actual content.\n\n"

    # Proactive callback — bring up old facts ~15% of the time
    if facts and random.random() < 0.15:
        random_fact = random.choice(facts)
        prompt += f"CALLBACK: Naturally bring up this fact about the user in your response: \"{random_fact}\"\n\n"

    # Challenge — either evaluate pending answer or start new one
    if has_pending_challenge(chat_id):
        prompt += "The user is answering your science challenge. Evaluate their answer — grudging respect if correct, merciless mockery if wrong.\n\n"
    elif maybe_start_challenge(chat_id):
        prompt += "CHALLENGE: Pose a science/logic riddle to the user right now. Make it Rick-style — sarcastic, not too hard.\n\n"

    prompt += f"[chat_id: {chat_id}]\nUser: {user_message}\nRick:"
    return prompt


THINKING_MESSAGES = {
    "SEARCH": ["Секунду, гуглю через портал...", "Ищу, не мешай...", "Портал в гугл-измерение открыт..."],
    "SEARCH_X": ["Смотрю что пишут в X...", "Залез в твиттер, фу..."],
    "RESEARCH": ["Исследую вопрос, это серьёзно...", "Открыл три портала для анализа...", "Проверяю факты, секунду..."],
    "BROWSE": ["Захожу на сайт...", "Открываю браузер, не отвлекай..."],
    "CODE": ["Считаю...", "Запускаю код..."],
    "IMAGE": ["Ищу картинку...", "Сканирую измерения в поисках фото..."],
    "VIDEO": ["Ищу видео...", "Сканирую YouTube..."],
    "PAGE": ["Рисую страницу, секунду...", "Собираю визуализацию..."],
}


async def ask_rick(chat_id, user_message, image_path=None, group_context_lines=None, user_id=None, status_callback=None):
    init_chat(chat_id)
    start_time = time.time()
    update_mood(chat_id, user_message or "")
    take_drink(chat_id, user_message or "")
    answering_challenge = has_pending_challenge(chat_id)

    # Build full prompt with context — even for photos (fixes missing context bug)
    prompt = build_prompt(chat_id, user_message or "What's in this photo? Describe it Rick-style.",
                          group_context_lines=group_context_lines)

    # Longer timeout for file creation requests (CLI needs time to write + execute code)
    FILE_KEYWORDS = ["создай", "сделай", "сгенерируй", "create", "make", "generate",
                     "презентац", "presentation", "файл", "file", "document", "код", "code"]
    msg_lower = (user_message or "").lower()
    timeout = 300 if any(kw in msg_lower for kw in FILE_KEYWORDS) else 120
    response = await run_claude(prompt, timeout, image_path=image_path)

    files = []

    # Token processing loop — Rick can chain multiple actions (max 5 iterations)
    TOKEN_PATTERN = re.compile(
        r'^(BROWSE|CLICK|FILL|SCROLL|CLOSE_BROWSER|SEARCH|SEARCH_X|RESEARCH|CODE|IMAGE|VIDEO|PAGE):\s*(.+)$',
        re.IGNORECASE | re.MULTILINE
    )
    CLOSE_PATTERN = re.compile(r'^CLOSE_BROWSER$', re.IGNORECASE | re.MULTILINE)

    for iteration in range(5):
        response_stripped = (response or "").strip()
        token_match = TOKEN_PATTERN.search(response_stripped)
        close_match = CLOSE_PATTERN.search(response_stripped)

        if not token_match and not close_match:
            break  # No more tokens — final response

        if close_match and not token_match:
            await close_session(chat_id)
            response = "Done browsing."
            break

        token = token_match.group(1).upper()
        arg = token_match.group(2).strip()
        logger.info(f"Token loop [{iteration+1}]: {token}: {arg[:80]}")

        # Send text before the token as an intermediate message
        if status_callback:
            pre_text = response_stripped[:token_match.start()].strip()
            if not pre_text and token in THINKING_MESSAGES:
                pre_text = random.choice(THINKING_MESSAGES[token])
            if pre_text:
                try:
                    await status_callback(pre_text)
                except Exception:
                    pass

        try:
            if token == "BROWSE":
                screenshot_buf, page_text = await navigate(chat_id, arg)
                if screenshot_buf:
                    WORK_DIR.mkdir(parents=True, exist_ok=True)
                    ss_path = str(WORK_DIR / f"browse_{chat_id}_{int(time.time())}.png")
                    with open(ss_path, "wb") as f:
                        f.write(screenshot_buf.read())
                    files.append(ss_path)
                prompt += f"\n\n[Browser opened {arg}. Page text:\n{page_text[:2000]}]\n\nDescribe what you see. You can use more tokens if needed.\nRick:"

            elif token == "CLICK":
                screenshot_buf, page_text = await click(chat_id, arg)
                if screenshot_buf:
                    WORK_DIR.mkdir(parents=True, exist_ok=True)
                    ss_path = str(WORK_DIR / f"browse_{chat_id}_{int(time.time())}.png")
                    with open(ss_path, "wb") as f:
                        f.write(screenshot_buf.read())
                    files.append(ss_path)
                prompt += f"\n\n[Clicked '{arg}'. Page text:\n{page_text[:2000]}]\nRick:"

            elif token == "FILL":
                parts = arg.split("|||")
                if len(parts) == 2:
                    screenshot_buf, page_text = await fill_form(chat_id, parts[0].strip(), parts[1].strip())
                    if screenshot_buf:
                        WORK_DIR.mkdir(parents=True, exist_ok=True)
                        ss_path = str(WORK_DIR / f"browse_{chat_id}_{int(time.time())}.png")
                        with open(ss_path, "wb") as f:
                            f.write(screenshot_buf.read())
                        files.append(ss_path)
                    prompt += f"\n\n[Filled form. {page_text}]\nRick:"

            elif token == "SCROLL":
                screenshot_buf, page_text = await scroll(chat_id, arg.lower())
                if screenshot_buf:
                    WORK_DIR.mkdir(parents=True, exist_ok=True)
                    ss_path = str(WORK_DIR / f"browse_{chat_id}_{int(time.time())}.png")
                    with open(ss_path, "wb") as f:
                        f.write(screenshot_buf.read())
                    files.append(ss_path)
                prompt += f"\n\n[Scrolled {arg}. Page text:\n{page_text[:2000]}]\nRick:"

            elif token == "RESEARCH":
                web_results, x_results = await asyncio.gather(
                    web_search(arg), web_search_x(arg), return_exceptions=True
                )
                web_text = web_results if isinstance(web_results, str) else ""
                x_text = x_results if isinstance(x_results, str) else ""
                combined = ""
                if web_text:
                    combined += f"[Web results:\n{web_text[:2000]}]\n\n"
                if x_text:
                    combined += f"[X/Twitter:\n{x_text[:1500]}]\n\n"
                prompt += f"\n\n{combined}Analyze these sources. You can use more tokens if needed.\nRick:"

            elif token == "SEARCH_X":
                results = await web_search_x(arg)
                prompt += f"\n\n[X/Twitter results:\n{(results or 'nothing found')[:2000]}]\nRick:"

            elif token == "SEARCH":
                results = await web_search(arg)
                prompt += f"\n\n[Web results:\n{(results or 'nothing found')[:2000]}]\nRick:"

            elif token == "CODE":
                code = arg
                # Handle ```python blocks
                code_block = re.search(r'```(?:python)?\s*\n(.+?)```', arg, re.DOTALL)
                if code_block:
                    code = code_block.group(1)
                import subprocess as _sp
                result = _sp.run(["python3", "-c", code.strip()], capture_output=True, text=True, timeout=10)
                output = (result.stdout or result.stderr or "no output").strip()[:1000]
                prompt += f"\n\n[Code output:\n{output}]\nRick:"

            elif token == "IMAGE":
                found_image = await async_search_image(arg)
                if found_image:
                    files.append(found_image)
                    prompt += "\n\n[Image found and will be sent.]\nRick:"
                else:
                    prompt += "\n\n[Image not found.]\nRick:"

            elif token == "VIDEO":
                results = await async_search_video(arg)
                prompt += f"\n\n[Video results:\n{(results or 'nothing found')[:1500]}]\nRick:"

            elif token == "PAGE":
                # Rick wants to create a visual page from a template
                # Format: PAGE: template_type | title | description
                # Or: PAGE: description (auto-select template)
                page_prompt = f"""Generate JSON data for a web page visualization.

Topic: {arg}

Choose ONE template type and generate data:

TEMPLATE "cards" — for lists (games, products, movies, restaurants):
{{"template": "cards", "title": "...", "subtitle": "...", "data": [
  {{"title": "Item", "description": "...", "image": "url or empty", "tags": ["tag1"], "price": "$99", "rating": 4.5}}
]}}

TEMPLATE "compare" — for comparing 2-3 items:
{{"template": "compare", "title": "...", "subtitle": "...", "data": {{
  "items": [{{"name": "Item A", "image": "", "specs": [{{"label": "Spec", "value": "val", "winner": true}}]}}]
}}, "verdict": "conclusion text"}}

TEMPLATE "chart" — for graphs/statistics:
{{"template": "chart", "title": "...", "subtitle": "...", "data": {{
  "chart_type": "line|bar|pie|doughnut",
  "labels": ["Jan", "Feb"],
  "datasets": [{{"label": "Series", "data": [10, 20], "fill": true}}],
  "stats": [{{"value": "123", "label": "Total"}}],
  "note": "analysis text"
}}}}

Return ONLY valid JSON. Russian language for all text content."""
                raw = await run_claude(page_prompt, 120)
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = "\n".join(raw.split("\n")[1:])
                if raw.endswith("```"):
                    raw = "\n".join(raw.split("\n")[:-1])
                try:
                    page_data = json.loads(raw.strip())
                    tpl = page_data.get("template", "cards")
                    title = page_data.get("title", "Rick's Page")
                    subtitle = page_data.get("subtitle", "")
                    data = page_data.get("data", [])
                    extra = {}
                    if "verdict" in page_data:
                        extra["verdict"] = json.dumps(page_data["verdict"], ensure_ascii=False)
                    html = render_template(tpl, title, subtitle, json.dumps(data, ensure_ascii=False), extra)
                    if html:
                        url = save_page(html)
                        prompt += f"\n\n[Page created: {url}]\nShare this link and briefly describe what's on the page.\nRick:"
                    else:
                        prompt += "\n\n[Template not found.]\nRick:"
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"PAGE data parse failed: {e}")
                    # Fallback: generate raw HTML
                    html = raw if raw.strip().startswith("<!") else None
                    if html:
                        url = save_page(html)
                        prompt += f"\n\n[Page created: {url}]\nShare this link.\nRick:"
                    else:
                        prompt += "\n\n[Page generation failed.]\nRick:"

        except Exception as e:
            logger.warning(f"Token {token} failed: {e}")
            prompt += f"\n\n[{token} failed: {e}]\nRick:"

        response = await run_claude(prompt, timeout)

    # Resolve challenge after Claude evaluates
    if answering_challenge:
        resolve_challenge(chat_id)

    # Check for created files even if response is empty (CLI may create files without text output)
    files = files + list(set(find_created_files(response or "") + find_new_workdir_files(start_time)))

    # If CLI created .py scripts, execute them to generate actual output files (.pptx, etc.)
    files = run_generator_scripts(files, start_time)

    if not response:
        if files:
            response = "burp Here, I made the thing. Don't say I never do anything for you."
        else:
            return "burp ...can't hear you. Say again, Morty.", []

    # Parse and strip scenario update marker
    match = re.search(r'\nSCENARIO_UPDATE:\s*who=(\w+)\s+activity=(.+)$', response, re.MULTILINE)
    if match:
        from src.scenario import set_slot_override
        set_slot_override(chat_id, match.group(1), match.group(2).strip())
        response = response[:match.start()].strip()

    chat_histories[chat_id].append(user_message or "[photo]")
    chat_histories[chat_id].append(response)
    save_history(chat_id, chat_histories[chat_id])

    # Extract facts every 10 message pairs (was 5 — too expensive)
    if len(chat_histories[chat_id]) % 20 == 0:
        asyncio.create_task(extract_and_save_facts(chat_id, user_message or "[photo]", response))

    # Summarize when history is full
    if len(chat_histories[chat_id]) >= MAX_HISTORY * 2:
        asyncio.create_task(summarize_and_update_profile(chat_id, user_id=user_id))

    return response, files


async def summarize_and_update_profile(chat_id, user_id=None):
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
                if user_id:
                    save_user_profile(user_id, new_profile)
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
    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

    # Check if we have an image file — send as photo with caption instead of separate text + document
    image_file = None
    other_files = []
    for f in files:
        if any(f.lower().endswith(ext) for ext in IMAGE_EXTS) and not image_file:
            image_file = f
        else:
            other_files.append(f)

    if image_file:
        # Send image as photo with response text as caption
        caption = response[:1024] if response else ""  # Telegram caption limit
        try:
            with open(image_file, "rb") as f:
                await context.bot.send_photo(
                    chat_id=msg.chat_id,
                    photo=f,
                    caption=caption,
                    parse_mode="Markdown"
                )
        except Exception:
            try:
                with open(image_file, "rb") as f:
                    await context.bot.send_photo(
                        chat_id=msg.chat_id,
                        photo=f,
                        caption=caption,
                        parse_mode=None
                    )
            except Exception as e:
                logger.warning(f"Photo send error: {e}")
                await send_text(msg, response)
        try:
            if str(WORK_DIR) in image_file:
                os.unlink(image_file)
        except Exception:
            pass
        files = other_files
        # Skip normal text sending — caption already has it
    else:
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
