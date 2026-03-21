"""Group chat logic — response decisions, member formatting, group responses."""
import random
from src.config import GROUP_RANDOM_CHANCE
from src.memory import group_context, group_members, load_facts
from src.prompts import GROUP_SYSTEM, GROUP_RESPONSE_PROMPT
from src.claude import run_claude


def should_respond_in_group(text: str, bot_username: str = "", reply_to_bot: bool = False, chat_id: int = None, username: str = None) -> bool:
    """Rick отвечает в группе ТОЛЬКО если к нему обращаются, очень релевантно, или изредка сам."""
    text_lower = text.lower()

    # 0. Прямой ответ боту — всегда отвечаем
    if reply_to_bot:
        return True

    # 1. Прямое обращение по имени
    direct_mentions = ["рик", "rick", "@rickbot", "рика", "рику", "риком"]
    if any(m in text_lower for m in direct_mentions):
        return True

    # 2. Вопрос + тема Рика
    is_question = (text.strip().endswith("?") or
                   any(w in text_lower for w in ["как ", "что ", "почему ", "зачем ", "когда ", "где ", "кто "]))
    rick_topics = ["наука", "физика", "химия", "технологи", "портал", "вселен",
                   "робот", "искусствен", "программ", "код", "алгоритм", "квант",
                   "плазм", "нейрон", "днк", "геном", "ии ", "ai "]
    if is_question and any(t in text_lower for t in rick_topics):
        return True

    # 3. Команды боту
    bot_commands = ["найди skill", "установи скилл", "поищи скил", "напомни", "remind", "/skill"]
    if any(c in text_lower for c in bot_commands):
        return True

    # 4. Рик изредка вмешивается сам — ~7% шанс, только на содержательные сообщения
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
