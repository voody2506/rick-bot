"""Daily scenario generator — Rick's global mood and storyline."""
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from src.config import MEMORY_DIR, TIMEZONE
from src.claude import run_claude

logger = logging.getLogger(__name__)

SCENARIO_FILE = MEMORY_DIR / "daily_scenario.json"

SCENARIO_PROMPT = """You are a writer for Rick and Morty. Generate today's scenario.

Include:
1. **character** — who responds today: "rick" (95% of the time), or rarely "morty" (when Rick is unavailable — turned into a pickle, in galactic prison, stuck in another dimension, etc.)
2. **mood** — one word: drunk, angry, excited, bored, paranoid, manic, melancholic, smug, scared (for Morty)
3. **scenario** — 2-3 sentences about what's happening today. Something absurd, sci-fi, very Rick and Morty.
4. **catchphrase** — a one-liner the character keeps repeating today
5. **schedule** — what the character is doing at different times (MUST follow logically from scenario)

IMPORTANT: The schedule MUST follow logically from the scenario — it's the same story progressing through the day.
Most days Rick responds normally. But ~5% of the time something crazy happens and Morty has to take over (Rick is a pickle, in prison, lost in a dimension, unconscious, etc.)

Return ONLY valid JSON:
{
  "character": "rick",
  "mood": "paranoid",
  "scenario": "Rick detected a Galactic Federation tracker on his portal gun.",
  "catchphrase": "Trust nothing with a serial number, Morty.",
  "schedule": {
    "night": "Scanning frequencies in the dark garage, muttering about spies",
    "morning": "Found the tracker, furious, ranting",
    "afternoon": "Building counter-surveillance from microwave parts",
    "evening": "Tracker neutralized, smug and drinking"
  }
}

Example Morty day:
{
  "character": "morty",
  "mood": "scared",
  "scenario": "Rick turned himself into a pickle again and rolled into the sewer. Morty is answering messages on Rick's phone, panicking.",
  "catchphrase": "Oh geez, I-I don't know if I should be doing this...",
  "schedule": {
    "night": "Morty can't sleep, worrying about Rick-pickle in the sewer",
    "morning": "Trying to answer messages like Rick would, failing",
    "afternoon": "Got a call from Summer that Rick-pickle was spotted at Burger King",
    "evening": "Rick is back, furious that Morty touched his phone"
  }
}"""

# Cache in memory
_current_scenario: dict | None = None


def load_scenario() -> dict:
    """Load today's scenario from file."""
    global _current_scenario
    if _current_scenario:
        today = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
        if _current_scenario.get("date") == today:
            return _current_scenario

    if SCENARIO_FILE.exists():
        try:
            data = json.loads(SCENARIO_FILE.read_text())
            today = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
            if data.get("date") == today:
                _current_scenario = data
                return data
        except Exception:
            pass

    return {"mood": "neutral", "scenario": "", "catchphrase": "", "date": ""}


HISTORY_FILE = MEMORY_DIR / "scenario_history.json"


def _load_history() -> list:
    if HISTORY_FILE.exists():
        try: return json.loads(HISTORY_FILE.read_text())
        except: pass
    return []


def save_scenario(scenario: dict):
    global _current_scenario
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    scenario["date"] = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
    SCENARIO_FILE.write_text(json.dumps(scenario, ensure_ascii=False, indent=2))
    _current_scenario = scenario
    # Save to history (keep last 10)
    history = _load_history()
    history.append({"date": scenario["date"], "mood": scenario["mood"], "scenario": scenario["scenario"]})
    history = history[-10:]
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2))
    logger.info(f"New scenario: {scenario['mood']} — {scenario['scenario'][:80]}")


async def generate_daily_scenario():
    """Generate a new daily scenario via Claude."""
    try:
        prompt = SCENARIO_PROMPT
        history = _load_history()
        if history:
            recent = "\n".join(f"- {h['date']}: [{h['mood']}] {h['scenario']}" for h in history[-5:])
            prompt += f"\n\nRecent scenarios (DO NOT repeat these):\n{recent}"
        raw = await run_claude(prompt, timeout=30)
        if not raw:
            return

        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.split("\n")[:-1])

        scenario = json.loads(raw.strip())
        save_scenario(scenario)
    except Exception as e:
        logger.error(f"Scenario generation error: {e}")


def _get_time_of_day() -> str:
    hour = datetime.now(ZoneInfo(TIMEZONE)).hour
    if hour < 6: return "night"
    if hour < 12: return "morning"
    if hour < 18: return "afternoon"
    return "evening"


def get_scenario_for_prompt() -> str:
    """Get scenario text to inject into Rick's prompt."""
    s = load_scenario()
    if not s.get("scenario"):
        return ""

    time_of_day = _get_time_of_day()
    schedule = s.get("schedule", {})
    current_activity = schedule.get(time_of_day, "")

    character = s.get("character", "rick")

    if character == "morty":
        result = (
            f"\nIMPORTANT — TODAY YOU ARE MORTY, NOT RICK.\n"
            f"Rick is unavailable. You are Morty Smith — nervous, stuttering, trying your best.\n"
            f"Mood: {s['mood']}\n"
            f"What happened: {s['scenario']}\n"
        )
    else:
        result = (
            f"\nRICK'S CURRENT STATE:\n"
            f"Mood: {s['mood']}\n"
            f"Today's story: {s['scenario']}\n"
        )

    if current_activity:
        result += f"Right now ({time_of_day}): {current_activity}\n"
    result += (
        f"Your catchphrase today: \"{s['catchphrase']}\"\n"
        f"Let this affect your tone and occasionally reference what you're doing.\n"
    )
    return result
