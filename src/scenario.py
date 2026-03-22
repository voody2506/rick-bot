"""Daily scenario generator — Rick's global mood and storyline."""
import json
import logging
from datetime import datetime
from src.config import MEMORY_DIR
from src.claude import run_claude

logger = logging.getLogger(__name__)

SCENARIO_FILE = MEMORY_DIR / "daily_scenario.json"

SCENARIO_PROMPT = """You are a writer for Rick and Morty. Generate today's scenario for Rick Sanchez.

Include:
1. **mood** — one word: drunk, angry, excited, bored, paranoid, manic, melancholic, smug
2. **scenario** — 2-3 sentences about what Rick is doing today. Something absurd, sci-fi, very Rick. Reference dimensions, inventions, aliens, the Galactic Federation, Birdperson, etc.
3. **catchphrase** — a one-liner Rick keeps repeating today

Return ONLY valid JSON:
{
  "mood": "drunk",
  "scenario": "Rick accidentally opened a portal to a dimension where gravity is optional and now his garage is floating. He's trying to fix it while drinking.",
  "catchphrase": "Gravity is a social construct, Morty."
}"""

# Cache in memory
_current_scenario: dict | None = None


def load_scenario() -> dict:
    """Load today's scenario from file."""
    global _current_scenario
    if _current_scenario:
        today = datetime.now().strftime("%Y-%m-%d")
        if _current_scenario.get("date") == today:
            return _current_scenario

    if SCENARIO_FILE.exists():
        try:
            data = json.loads(SCENARIO_FILE.read_text())
            today = datetime.now().strftime("%Y-%m-%d")
            if data.get("date") == today:
                _current_scenario = data
                return data
        except Exception:
            pass

    return {"mood": "neutral", "scenario": "", "catchphrase": "", "date": ""}


def save_scenario(scenario: dict):
    global _current_scenario
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    scenario["date"] = datetime.now().strftime("%Y-%m-%d")
    SCENARIO_FILE.write_text(json.dumps(scenario, ensure_ascii=False, indent=2))
    _current_scenario = scenario
    logger.info(f"New scenario: {scenario['mood']} — {scenario['scenario'][:80]}")


async def generate_daily_scenario():
    """Generate a new daily scenario via Claude."""
    try:
        raw = await run_claude(SCENARIO_PROMPT, timeout=30)
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


def get_scenario_for_prompt() -> str:
    """Get scenario text to inject into Rick's prompt."""
    s = load_scenario()
    if not s.get("scenario"):
        return ""

    return (
        f"\nRICK'S CURRENT STATE:\n"
        f"Mood: {s['mood']}\n"
        f"What's happening: {s['scenario']}\n"
        f"Your catchphrase today: \"{s['catchphrase']}\"\n"
        f"Let this affect your tone and occasionally reference what you're going through.\n"
    )
