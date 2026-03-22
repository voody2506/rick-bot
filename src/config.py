import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "sonnet")
CLAUDE_TIMEOUT = int(os.getenv("CLAUDE_TIMEOUT", "90"))

MAX_HISTORY = int(os.getenv("MAX_HISTORY", "20"))
MAX_FACTS = int(os.getenv("MAX_FACTS", "50"))
GROUP_RANDOM_CHANCE = float(os.getenv("GROUP_RANDOM_CHANCE", "0.07"))
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
TIMEZONE = os.getenv("TIMEZONE", "America/New_York")

# TTS (Fish Audio)
TTS_ENABLED = os.getenv("TTS_ENABLED", "false").lower() == "true"
FISH_AUDIO_API_KEY = os.getenv("FISH_AUDIO_API_KEY", "")
FISH_AUDIO_VOICE_ID = os.getenv("FISH_AUDIO_VOICE_ID", "d2e75a3e3fd6419893057c02a375a113")

# Web Search (Tavily)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

BASE_DIR = Path(os.getenv("BASE_DIR", str(Path(__file__).resolve().parent.parent)))
MEMORY_DIR = BASE_DIR / "memory"
WORK_DIR = BASE_DIR / "work"
SKILLS_DIR = BASE_DIR / "skills"
TOKENS_DIR = BASE_DIR / "tokens"

RICK_NAMES = ["рик", "rick", "санчез", "sanchez", "рика", "рику", "риком"]

CLAWHUB_SEARCH_URL = "https://clawhub.ai/api/search"
CLAWHUB_DOWNLOAD_URL = "https://wry-manatee-359.convex.site/api/v1/download"
