"""Parallel task decomposition and execution."""
import asyncio
from src.claude import run_claude
from src.memory import load_facts
from src.prompts import RICK_SYSTEM, PARALLEL_CHECK, MERGE_PROMPT


async def try_parallel(chat_id, message):
    check = await run_claude(PARALLEL_CHECK.format(message=message), timeout=15)
    if not check or "НЕТ" in check.upper() or not check.strip().startswith("-"):
        return None
    subtasks = [l.lstrip("- ").strip() for l in check.split("\n") if l.strip().startswith("-")]
    if len(subtasks) < 2: return None
    facts = load_facts(chat_id)
    facts_str = "\n".join(facts) if facts else "нет"
    prompts = [f"{RICK_SYSTEM}\n\nФакты: {facts_str}\n\nПодзадача: {t}\nРезультат:" for t in subtasks]
    results = await asyncio.gather(*[run_claude(p, 60) for p in prompts])
    results_str = "\n\n".join(f"[{subtasks[i]}]\n{results[i]}" for i in range(len(subtasks)))
    return await run_claude(MERGE_PROMPT.format(original=message, results=results_str), 30) or None
