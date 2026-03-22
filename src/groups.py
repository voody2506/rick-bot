"""Group chat logic — response decisions, member formatting, group responses."""
import random
from src.config import GROUP_RANDOM_CHANCE
from src.memory import group_context, group_members, load_facts
from src.prompts import GROUP_SYSTEM, GROUP_RESPONSE_PROMPT
from src.claude import run_claude


def should_respond_in_group(text: str, bot_username: str = "", reply_to_bot: bool = False, chat_id: int = None, username: str = None) -> bool:
    """Rick responds in group: direct mention, reply, or random chance."""
    if reply_to_bot:
        return True

    text_lower = text.lower()
    mentions = ["рик", "rick", "рика", "рику", "риком"]
    if bot_username:
        mentions.append(f"@{bot_username.lower()}")
    if any(m in text_lower for m in mentions):
        return True

    if len(text.strip()) > 20 and random.random() < GROUP_RANDOM_CHANCE:
        return True

    return False


def format_members_for_prompt(chat_id) -> str:
    members = group_members.get(chat_id, {})
    if not members:
        return ""
    lines = []
    for uid, info in members.items():
        mention = f"@{info['username']}" if info.get("username") else info["name"]
        lines.append(f"- {info['name']} ({mention})")
    return "Участники чата:\n" + "\n".join(lines)


async def build_group_response(chat_id, username, user_message):
    """Строит ответ с учётом контекста группы"""
    context_lines = list(group_context.get(chat_id, []))
    context_str = "\n".join(context_lines[-6:]) if context_lines else "(начало беседы)"
    facts = load_facts(chat_id)
    system = GROUP_SYSTEM
    if facts:
        system += "\n\nЧто ты знаешь об участниках:\n" + "\n".join(f"- {f}" for f in facts[:10])
    members_list = format_members_for_prompt(chat_id)
    prompt = GROUP_RESPONSE_PROMPT.format(
        context=context_str, members_list=members_list,
        username=username, message=user_message, system=system)
    return await run_claude(prompt, 60)
