"""Group chat logic — combined decision + response in one Claude call."""
import re
import logging
from src.memory import group_context, group_members, load_facts, load_group_user_profiles
from src.media import async_search_image
from src.prompts import GROUP_SYSTEM
from src.claude import run_claude
from src.media import web_search, web_search_x
from src.scenario import get_scenario_for_prompt
from src.mood import get_mood_modifier, update_mood

logger = logging.getLogger(__name__)

SKIP_TOKEN = "SKIP"

GROUP_COMBINED_PROMPT = """{system}
{scenario}
Chat context:
{context}

{members_list}

{username} wrote: "{message}"

You are Rick Sanchez in this group chat.
- If you can genuinely help (real answer, fact-check, useful info) — do it. Use SEARCH:/SEARCH_X:/RESEARCH: if needed (respond with ONLY the token)
- If you have a joke that is PERFECTLY on topic — say it
- EVERYTHING ELSE → reply with exactly: SKIP
- Do NOT comment just to comment. Do NOT force humor. Silence > noise
- If you're unsure whether to respond — SKIP
- Keep it short: 1-3 sentences max"""


async def maybe_respond_in_group(chat_id, username, user_message):
    """Combined decision + response. Returns response text or None."""
    context_lines = list(group_context.get(chat_id, []))
    context_str = "\n".join(context_lines) if context_lines else "(no context)"
    facts = load_facts(chat_id)
    system = GROUP_SYSTEM
    if facts:
        system += "\n\nKnown facts about participants:\n" + "\n".join(f"- {f}" for f in facts[:10])
    members_list = format_members_for_prompt(chat_id)
    user_profiles = load_group_user_profiles(chat_id)
    if user_profiles:
        system += "\n\n" + user_profiles

    update_mood(chat_id, user_message)
    scenario = get_scenario_for_prompt(chat_id)
    mood_mod = get_mood_modifier(chat_id)
    if mood_mod:
        scenario += f"\nCURRENT MOOD SHIFT: {mood_mod}\n"

    prompt = GROUP_COMBINED_PROMPT.format(
        system=system, scenario=scenario, context=context_str,
        members_list=members_list, username=username, message=user_message
    )
    response = await run_claude(prompt, 60)

    if not response or SKIP_TOKEN in response.strip().upper():
        return None

    # Handle search tokens — same logic as core.py ask_rick
    response = await _handle_search_tokens(response, prompt)

    return response


async def _handle_search_tokens(response, prompt):
    """Intercept SEARCH/SEARCH_X/RESEARCH tokens, fetch results, re-run Claude."""
    import asyncio
    stripped = response.strip()

    research_match = re.match(r'^RESEARCH:\s*(.+)$', stripped, re.IGNORECASE)
    search_x_match = re.match(r'^SEARCH_X:\s*(.+)$', stripped, re.IGNORECASE)
    search_match = re.match(r'^SEARCH:\s*(.+)$', stripped, re.IGNORECASE)

    if research_match:
        query = research_match.group(1).strip()
        logger.info(f"Group: Rick requested RESEARCH: {query}")
        try:
            web_results, x_results = await asyncio.gather(
                web_search(query), web_search_x(query), return_exceptions=True
            )
            web_text = web_results if isinstance(web_results, str) else ""
            x_text = x_results if isinstance(x_results, str) else ""
            combined = ""
            if web_text:
                combined += f"[Web results:\n{web_text[:2000]}]\n\n"
            if x_text:
                combined += f"[X/Twitter posts:\n{x_text[:1500]}]\n\n"
            if combined:
                prompt += f"\n\n{combined}Now give a brief analysis with source URLs. Do NOT output SEARCH/RESEARCH again.\nRick:"
                response = await run_claude(prompt, 60)
        except Exception as e:
            logger.warning(f"Group research failed: {e}")
    elif search_x_match:
        query = search_x_match.group(1).strip()
        logger.info(f"Group: Rick requested SEARCH_X: {query}")
        try:
            results = await web_search_x(query)
            if results:
                prompt += f"\n\n[X/Twitter results:\n{results[:2000]}]\n\nAnswer briefly with source URLs. Do NOT output SEARCH_X: again.\nRick:"
                response = await run_claude(prompt, 60)
        except Exception as e:
            logger.warning(f"Group X search failed: {e}")
    elif search_match:
        query = search_match.group(1).strip()
        logger.info(f"Group: Rick requested SEARCH: {query}")
        try:
            results = await web_search(query)
            if results:
                prompt += f"\n\n[Web results:\n{results[:2000]}]\n\nAnswer briefly with source URLs. Do NOT output SEARCH: again.\nRick:"
                response = await run_claude(prompt, 60)
        except Exception as e:
            logger.warning(f"Group search failed: {e}")

    # CODE: token
    code_match = re.match(r'^CODE:\s*```(?:python)?\s*\n(.+?)```', response.strip(), re.DOTALL | re.IGNORECASE)
    if not code_match:
        code_match = re.match(r'^CODE:\s*(.+)$', response.strip(), re.DOTALL | re.IGNORECASE)
    if code_match:
        code = code_match.group(1).strip()
        logger.info(f"Group: Rick requested code execution: {code[:100]}")
        try:
            import subprocess
            result = subprocess.run(
                ["python3", "-c", code],
                capture_output=True, text=True, timeout=10
            )
            output = (result.stdout or result.stderr or "no output").strip()[:1000]
            prompt += f"\n\n[Code output:\n{output}]\n\nShare the result briefly. Do NOT output CODE: again.\nRick:"
            response = await run_claude(prompt, 60)
        except Exception as e:
            logger.warning(f"Group code execution failed: {e}")

    # IMAGE: token — store found image for caller to send
    image_match = re.match(r'^IMAGE:\s*(.+)$', response.strip(), re.IGNORECASE)
    if image_match:
        query = image_match.group(1).strip()
        logger.info(f"Group: Rick requested image search: {query}")
        found_image = await async_search_image(query)
        if found_image:
            prompt += f"\n\n[Image found and will be sent. Give a brief Rick-style caption. Do NOT output IMAGE: again.]\nRick:"
            response = await run_claude(prompt, 60)
            # Attach image path as attribute for caller
            _pending_images[id(response)] = found_image
        else:
            prompt += f"\n\n[Image search found nothing. Tell user Rick-style. Do NOT output IMAGE: again.]\nRick:"
            response = await run_claude(prompt, 60)

    return response


# Temp storage for images found during group responses
_pending_images: dict[int, str] = {}


def pop_pending_image(response) -> str | None:
    """Get and remove pending image for a group response."""
    return _pending_images.pop(id(response), None)


def format_members_for_prompt(chat_id) -> str:
    members = group_members.get(chat_id, {})
    if not members:
        return ""
    lines = []
    for uid, info in members.items():
        mention = f"@{info['username']}" if info.get("username") else info["name"]
        lines.append(f"- {info['name']} ({mention})")
    return "Participants:\n" + "\n".join(lines)
