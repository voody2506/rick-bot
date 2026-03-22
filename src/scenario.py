"""Daily scenario generator — Rick's global mood and storyline with subplots."""
import json
import random
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from src.config import MEMORY_DIR, TIMEZONE
from src.claude import run_claude

logger = logging.getLogger(__name__)

SCENARIO_FILE = MEMORY_DIR / "daily_scenario.json"

SCENARIO_PROMPT = """You are a writer for Rick and Morty. Generate today's scenario.

Include:
1. **character** — who responds today. Almost always "rick" (95%). Very rarely (~5%) another character: "morty", "jerry", or any other Rick and Morty character — but this should be EXTREMELY rare and always have a funny reason.
2. **mood** — MUST be different from recent scenarios. Pick from: drunk, angry, excited, bored, paranoid, manic, melancholic, smug, scared. NEVER repeat the same mood two days in a row.
3. **scenario** — 2-3 sentences about what's happening today. MUST be a completely different TYPE of story from recent ones. Vary between: inventions gone wrong, interdimensional travel, family drama, visitors/enemies showing up, Rick's past catching up, mundane situations with sci-fi twists, body horror, time shenanigans, Rick vs bureaucracy, philosophical crises. NEVER start with "Rick reverse-engineered" or "Rick discovered" twice in a row.
4. **catchphrase** — a one-liner the character keeps repeating today
5. **schedule** — what's happening at different times. MUST follow logically from scenario. Each time slot has "who" (rick/morty/jerry) and "activity". Rick usually comes back by evening if he was absent.
6. **subplots** — 4 mini-events that can randomly happen during the day. They MUST be related to the main scenario. Each is 1-2 sentences — something unexpected, funny, or chaotic that interrupts the main story. These add unpredictability to conversations.

IMPORTANT: The schedule MUST follow logically from the scenario — it's the same story progressing through the day. Subplots are side-events within the same story — NOT separate stories.
Most days Rick responds normally. But ~5% of the time something crazy happens and Morty has to take over (Rick is a pickle, in prison, lost in a dimension, unconscious, etc.)

Return ONLY valid JSON:
{
  "character": "rick",
  "mood": "paranoid",
  "scenario": "Rick detected a Galactic Federation tracker on his portal gun.",
  "catchphrase": "Trust nothing with a serial number, Morty.",
  "schedule": {
    "night": {"who": "rick", "activity": "Scanning frequencies in the dark garage"},
    "morning": {"who": "rick", "activity": "Found the tracker, furious, ranting"},
    "afternoon": {"who": "rick", "activity": "Building counter-surveillance device"},
    "evening": {"who": "rick", "activity": "Tracker neutralized, smug and drinking"}
  },
  "subplots": [
    "A second tracker was found inside Rick's flask — he's furious and paranoid about who touched his stuff",
    "Morty accidentally broadcast Rick's location to the Galactic Federation while trying to help",
    "Birdperson sent a cryptic message: 'They know.' Rick is now questioning if Birdperson is compromised",
    "The counter-surveillance device gained sentience and is now scanning Rick back"
  ]
}

Example Morty day (Rick returns by evening):
{
  "character": "morty",
  "mood": "scared",
  "scenario": "Rick turned himself into a pickle. Morty answers his phone.",
  "catchphrase": "Oh geez, I-I don't know if I should be doing this...",
  "schedule": {
    "night": {"who": "morty", "activity": "Can't sleep, worrying about Rick-pickle"},
    "morning": {"who": "morty", "activity": "Trying to answer messages, failing"},
    "afternoon": {"who": "morty", "activity": "Summer spotted Rick-pickle at Burger King"},
    "evening": {"who": "rick", "activity": "Rick is BACK and furious. Took his phone from Morty."}
  }
}

Example Jerry day (Rick returns by evening):
{
  "character": "jerry",
  "mood": "proud",
  "scenario": "Jerry found Rick's phone. Thinks he can help. Terrible at it.",
  "catchphrase": "See? I can do science stuff too!",
  "schedule": {
    "night": {"who": "jerry", "activity": "Asleep like a normal person"},
    "morning": {"who": "jerry", "activity": "Found Rick's phone, decided to 'help'"},
    "afternoon": {"who": "jerry", "activity": "Giving terrible advice with confidence"},
    "evening": {"who": "rick", "activity": "Rick is back, took phone, called Jerry subhuman"}
  }
}"""

# Cache in memory
_current_scenario: dict | None = None
# Track used subplots per chat so they don't repeat
_used_subplots: dict[int, set[int]] = {}  # chat_id -> set of used subplot indices
_used_subplots_date: str = ""

# Per-chat scenario overrides (e.g. user woke Rick up)
_slot_overrides: dict[int, dict] = {}  # chat_id -> {"who": str, "activity": str, "slot": str}
SUBPLOT_CHANCE = 0.20  # 20% chance per message


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
        except Exception: pass
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


def set_slot_override(chat_id: int, who: str, activity: str):
    """Override current time slot for this chat."""
    _slot_overrides[chat_id] = {
        "who": who,
        "activity": activity,
        "slot": _get_time_of_day()
    }


def _get_active_override(chat_id: int) -> dict | None:
    """Get override if it's still for the current time slot."""
    override = _slot_overrides.get(chat_id)
    if not override:
        return None
    if override["slot"] != _get_time_of_day():
        del _slot_overrides[chat_id]  # expired — slot changed
        return None
    return override


def get_scenario_for_prompt(chat_id: int = 0) -> str:
    """Get scenario text to inject into Rick's prompt."""
    s = load_scenario()
    if not s.get("scenario"):
        return ""

    time_of_day = _get_time_of_day()
    schedule = s.get("schedule", {})
    slot = schedule.get(time_of_day, {})

    # Support both old format (string) and new format (dict with who/activity)
    if isinstance(slot, dict):
        current_who = slot.get("who", s.get("character", "rick"))
        current_activity = slot.get("activity", "")
    else:
        current_who = s.get("character", "rick")
        current_activity = slot

    # Apply per-chat override if active
    override = _get_active_override(chat_id)
    if override:
        current_who = override["who"]
        current_activity = override["activity"]

    if current_who != "rick":
        result = (
            f"\nIMPORTANT — RIGHT NOW YOU ARE {current_who.upper()}, NOT RICK.\n"
            f"You are {current_who} from Rick and Morty. Stay fully in character.\n"
            f"You have Rick's phone/device and can use all its tools (search, files, browser). Never admit you're a bot.\n"
            f"Mood: {s['mood']}\n"
            f"Today's story: {s['scenario']}\n"
        )
    else:
        result = (
            f"\nRICK'S CURRENT STATE:\n"
            f"Mood: {s['mood']}\n"
            f"Today's story: {s['scenario']}\n"
        )

    if current_activity:
        result += f"Default activity ({time_of_day}): {current_activity}\n"
    result += (
        f"Your catchphrase today: \"{s['catchphrase']}\"\n"
        f"This is background context — DON'T force it into every response. "
        f"Only reference it when it fits naturally, when you're bored, or when the user asks.\n"
        f"IMPORTANT: The schedule is a DEFAULT, not a rule. If the user's actions change the situation "
        f"(e.g. wakes you up, breaks something, calls someone), ADAPT — go with what happened. "
        f"Check the conversation history: if the story already changed earlier in this chat, stay consistent with that.\n"
        f"If the user's actions SIGNIFICANTLY change the current situation, add at the very END of your response "
        f"on a new line: SCENARIO_UPDATE: who=<character> activity=<brief description of new state>\n"
        f"Example: user pours water on sleeping Rick → SCENARIO_UPDATE: who=rick activity=Woke up furious, soaking wet, swearing revenge\n"
    )

    # Random subplot injection (per-chat)
    subplot = _pick_subplot(s, chat_id)
    if subplot:
        result += f"\nINTERRUPTION — something just happened: {subplot}\n"
        result += "React to this interruption naturally in your response.\n"

    return result


def _pick_subplot(scenario: dict, chat_id: int) -> str | None:
    """Pick a random unused subplot for this chat, or None."""
    global _used_subplots, _used_subplots_date

    subplots = scenario.get("subplots", [])
    if not subplots:
        return None

    # Reset all chats' used subplots on new day
    today = scenario.get("date", "")
    if _used_subplots_date != today:
        _used_subplots = {}
        _used_subplots_date = today

    if random.random() > SUBPLOT_CHANCE:
        return None

    # Pick from subplots not yet seen by this chat
    used = _used_subplots.get(chat_id, set())
    available = [(i, s) for i, s in enumerate(subplots) if i not in used]
    if not available:
        return None

    idx, subplot = random.choice(available)
    _used_subplots.setdefault(chat_id, set()).add(idx)
    return subplot
