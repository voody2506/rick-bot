"""Media handling — vision, voice (Whisper), video, web search, file helpers."""
import os
import re
import json
import asyncio
import logging
import subprocess
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
    loop = asyncio.get_running_loop()
    model = get_whisper_model()
    result = await loop.run_in_executor(
        None, lambda: model.transcribe(ogg_path, language=language)
    )
    return result["text"].strip()


def extract_video_frames(video_path: str, max_frames: int = 4) -> list[str]:
    """Extract key frames from video using ffmpeg. Returns list of image paths."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    base = os.path.splitext(os.path.basename(video_path))[0]
    frame_paths = []

    # Get video duration
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=10
        )
        duration = float(probe.stdout.strip() or "0")
    except Exception:
        duration = 0

    if duration <= 0:
        # Fallback: just grab first frame
        out = str(WORK_DIR / f"{base}_frame_0.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-frames:v", "1", "-q:v", "3", out],
            capture_output=True, timeout=15
        )
        if os.path.exists(out):
            frame_paths.append(out)
        return frame_paths

    # Extract evenly spaced frames
    n = min(max_frames, max(1, int(duration // 2)))
    interval = duration / (n + 1)
    for i in range(n):
        ts = interval * (i + 1)
        out = str(WORK_DIR / f"{base}_frame_{i}.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{ts:.1f}", "-i", video_path,
             "-frames:v", "1", "-q:v", "3", out],
            capture_output=True, timeout=15
        )
        if os.path.exists(out):
            frame_paths.append(out)
    return frame_paths


def extract_video_audio(video_path: str) -> str | None:
    """Extract audio track from video as ogg. Returns path or None."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    base = os.path.splitext(os.path.basename(video_path))[0]
    audio_path = str(WORK_DIR / f"{base}_audio.ogg")
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "libopus", audio_path],
            capture_output=True, timeout=30
        )
        if result.returncode == 0 and os.path.exists(audio_path):
            # Skip if audio is too small (no real audio track)
            if os.path.getsize(audio_path) > 1000:
                return audio_path
    except Exception as e:
        logger.warning(f"Video audio extraction failed: {e}")
    return None


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
        url = r.get("url", "")
        results.append(f"[{r['title']}] ({url}): {r['content'][:300]}")
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
    loop = asyncio.get_running_loop()
    try:
        if TAVILY_API_KEY:
            return await loop.run_in_executor(None, _tavily_search_sync, query)
        return await loop.run_in_executor(None, _ddg_search_sync, query)
    except Exception as e:
        logger.warning(f"web_search error: {e}")
        return ""


async def web_search_x(query: str) -> str:
    """Search X/Twitter via Tavily with site filter."""
    loop = asyncio.get_running_loop()
    try:
        x_query = f"site:x.com OR site:twitter.com {query}"
        if TAVILY_API_KEY:
            return await loop.run_in_executor(None, _tavily_search_sync, x_query, 5)
        return await loop.run_in_executor(None, _ddg_search_sync, x_query)
    except Exception as e:
        logger.warning(f"web_search_x error: {e}")
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

def run_generator_scripts(files: list, since: float) -> list:
    """If any .py scripts are in files, execute them and return generated output files instead."""
    import subprocess
    import sys

    py_scripts = [f for f in files if f.endswith('.py')]
    if not py_scripts:
        return files

    non_py = [f for f in files if not f.endswith('.py')]

    for script in py_scripts:
        try:
            subprocess.run(
                [sys.executable, script],
                cwd=str(WORK_DIR),
                timeout=30,
                capture_output=True,
            )
            logger.info(f"Executed generator script: {script}")
        except Exception as e:
            logger.warning(f"Script execution failed {script}: {e}")

        # Remove the script after execution
        try:
            os.remove(script)
        except Exception:
            pass

    # Collect new non-.py files created by the scripts
    generated = find_new_workdir_files(since)
    generated = [f for f in generated if not f.endswith('.py')]

    return list(set(non_py + generated))


def cleanup_work_dir():
    """Очищает временные файлы старше 1 часа"""
    if WORK_DIR.exists():
        import time
        now = time.time()
        for f in WORK_DIR.iterdir():
            if f.is_file() and (now - f.stat().st_mtime) > 3600:
                f.unlink()
                logger.info(f"Удалён временный файл: {f}")
