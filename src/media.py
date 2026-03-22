"""Media handling — vision, voice (Whisper), web search, file helpers."""
import os
import re
import json
import asyncio
import logging
import urllib.request
import urllib.parse
from src.config import WORK_DIR, WHISPER_MODEL, TAVILY_API_KEY

logger = logging.getLogger(__name__)

# Lazy-load whisper to avoid import cost when not needed
_whisper_model = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        logger.info(f"Loading Whisper model ({WHISPER_MODEL})...")
        _whisper_model = whisper.load_model(WHISPER_MODEL)
        logger.info("Whisper model loaded!")
    return _whisper_model

async def transcribe_audio(ogg_path: str, language: str = "ru") -> str:
    """Transcribe audio file using Whisper in executor."""
    loop = asyncio.get_event_loop()
    model = get_whisper_model()
    result = await loop.run_in_executor(
        None, lambda: model.transcribe(ogg_path, language=language)
    )
    return result["text"].strip()


def _tavily_search_sync(query: str, max_results: int = 5) -> str:
    """Search via Tavily API — returns summarized context for AI."""
    payload = json.dumps({
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic"
    }).encode()
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=payload, method="POST",
        headers={"Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read())
    results = []
    for r in data.get("results", []):
        results.append(f"[{r['title']}]: {r['content'][:300]}")
    return "\n\n".join(results)


def _ddg_search_sync(query: str) -> str:
    """Fallback: DuckDuckGo Instant Answers."""
    url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    results = []
    if data.get("AbstractText"):
        results.append(data["AbstractText"])
    for r in data.get("RelatedTopics", [])[:5]:
        if isinstance(r, dict) and r.get("Text"):
            results.append(r["Text"])
    return "\n".join(results)


async def web_search(query: str) -> str:
    """Web search — Tavily if available, DuckDuckGo fallback."""
    loop = asyncio.get_event_loop()
    try:
        if TAVILY_API_KEY:
            return await loop.run_in_executor(None, _tavily_search_sync, query)
        return await loop.run_in_executor(None, _ddg_search_sync, query)
    except Exception as e:
        logger.warning(f"web_search error: {e}")
        return ""


def find_created_files(output: str) -> list:
    """Ищет пути к файлам в ответе Claude"""
    patterns = [
        r'сохран[а-я]+\s+(?:в|как|по пути)?\s*["\']?(/[^\s"\']+\.[a-zA-Z0-9]+)',
        r'файл\s+["\']?(/[^\s"\']+\.[a-zA-Z0-9]+)',
        r'создан\s+["\']?(/[^\s"\']+\.[a-zA-Z0-9]+)',
        r'saved\s+(?:to|as)?\s*["\']?(/[^\s"\']+\.[a-zA-Z0-9]+)',
        r'(/home/rickbot/[^\s"\']+\.[a-zA-Z0-9]+)',
        r'(/tmp/[^\s"\']+\.[a-zA-Z0-9]+)',
    ]
    files = []
    for pat in patterns:
        for match in re.finditer(pat, output, re.IGNORECASE):
            path = match.group(1)
            if os.path.exists(path) and os.path.isfile(path):
                files.append(path)
    return list(set(files))


def find_new_workdir_files(since: float) -> list:
    """Ищет файлы в WORK_DIR созданные/изменённые после метки времени since"""
    if not WORK_DIR.exists():
        return []
    result = []
    for f in WORK_DIR.iterdir():
        if f.is_file() and f.stat().st_mtime >= since - 1:
            result.append(str(f))
    return result

def cleanup_work_dir():
    """Очищает временные файлы старше 1 часа"""
    if WORK_DIR.exists():
        import time
        now = time.time()
        for f in WORK_DIR.iterdir():
            if f.is_file() and (now - f.stat().st_mtime) > 3600:
                f.unlink()
                logger.info(f"Удалён временный файл: {f}")
