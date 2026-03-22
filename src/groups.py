"""Group chat logic — combined decision + response in one Claude call."""
from src.memory import group_context, group_members, load_facts
from src.prompts import GROUP_SYSTEM
from src.claude import run_claude
from src.scenario import get_scenario_for_prompt
from src.mood import get_mood_modifier, update_mood

SKIP_TOKEN = "SKIP"

GROUP_COMBINED_PROMPT = """{system}
{scenario}
Chat context:
{context}

{members_list}

{username} wrote: "{message}"

You are Rick Sanchez in this group chat. If you want to say something — say it (short, 1-3 sentences max). If this message doesn't need a response from Rick — reply with exactly: SKIP"""


async def maybe_respond_in_group(chat_id, username, user_message):
    """Combined decision + response. Returns response text or None."""
    context_lines = list(group_context.get(chat_id, []))
    context_str = "\n".join(context_lines[-6:]) if context_lines else "(no context)"
    facts = load_facts(chat_id)
    system = GROUP_SYSTEM
    if facts:
        system += "\n\nKnown facts about participants:\n" + "\n".join(f"- {f}" for f in facts[:10])
    members_list = format_members_for_prompt(chat_id)

    update_mood(user_message)
    scenario = get_scenario_for_prompt()
    mood_mod = get_mood_modifier()
    if mood_mod:
        scenario += f"\nCURRENT MOOD SHIFT: {mood_mod}\n"
    response = await run_claude(
        GROUP_COMBINED_PROMPT.format(
            system=system, scenario=scenario, context=context_str,
            members_list=members_list, username=username, message=user_message
        ), 60
    )

    if not response or SKIP_TOKEN in response.strip().upper():
        return None
    return response


def format_members_for_prompt(chat_id) -> str:
    members = group_members.get(chat_id, {})
    if not members:
        return ""
    lines = []
    for uid, info in members.items():
        mention = f"@{info['username']}" if info.get("username") else info["name"]
        lines.append(f"- {info['name']} ({mention})")
    return "Participants:\n" + "\n".join(lines)
