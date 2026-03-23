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


def extract_document_text(file_path: str, max_chars: int = 4000) -> str:
    """Extract text from PDF, DOCX, or plain text files."""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".pdf":
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            text = "\n".join(page.extract_text() or "" for page in reader.pages[:20])
        elif ext in (".docx", ".doc"):
            from docx import Document
            doc = Document(file_path)
            text = "\n".join(p.text for p in doc.paragraphs)
        elif ext in (".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".css", ".log"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        else:
            return ""
        return text[:max_chars].strip() if text else ""
    except Exception as e:
        logger.warning(f"Document extract failed for {file_path}: {e}")
        return ""


def search_and_download_image(query: str) -> str | None:
    """Search for an image via Tavily and download it. Returns local path or None."""
    if not TAVILY_API_KEY:
        return None
    try:
        payload = json.dumps({
            "api_key": TAVILY_API_KEY,
            "query": query,
            "max_results": 5,
            "search_depth": "basic",
            "include_images": True
        }).encode()
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload, method="POST",
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        image_urls = data.get("images", [])
        if not image_urls:
            # Fallback: look for image URLs in results
            for r in data.get("results", []):
                url = r.get("url", "")
                if any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    image_urls.append(url)
        if not image_urls:
            return None
        # Download first valid image
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        for img_url in image_urls[:3]:
            try:
                img_req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(img_req, timeout=10) as img_resp:
                    img_data = img_resp.read()
                if len(img_data) < 1000:
                    continue
                ext = ".jpg"
                if ".png" in img_url.lower():
                    ext = ".png"
                path = str(WORK_DIR / f"img_search_{hash(query) % 100000}{ext}")
                with open(path, "wb") as f:
                    f.write(img_data)
                return path
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"Image search failed: {e}")
    return None


async def async_search_image(query: str) -> str | None:
    """Async wrapper for image search."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, search_and_download_image, query)


def search_video_sync(query: str) -> str:
    """Search for videos via Tavily. Returns formatted results with URLs."""
    if not TAVILY_API_KEY:
        return ""
    try:
        video_query = f"site:youtube.com {query}"
        payload = json.dumps({
            "api_key": TAVILY_API_KEY,
            "query": video_query,
            "max_results": 3,
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
            results.append(f"[{r['title']}] ({url}): {r['content'][:200]}")
        return "\n\n".join(results) if results else ""
    except Exception as e:
        logger.warning(f"Video search failed: {e}")
        return ""


async def async_search_video(query: str) -> str:
    """Async wrapper for video search."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, search_video_sync, query)


def fetch_url_content(url: str, max_chars: int = 3000) -> str:
    """Fetch text content from a URL. Falls back to Tavily then Playwright for JS-heavy pages."""
    text = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        import re as _re
        text = _re.sub(r'<script[^>]*>.*?</script>', '', html, flags=_re.DOTALL)
        text = _re.sub(r'<style[^>]*>.*?</style>', '', text, flags=_re.DOTALL)
        text = _re.sub(r'<[^>]+>', ' ', text)
        text = _re.sub(r'\s+', ' ', text).strip()
    except Exception as e:
        logger.warning(f"URL direct fetch failed for {url}: {e}")

    # If direct fetch got very little content, try Tavily
    if len(text) < 150 and TAVILY_API_KEY:
        try:
            tavily_result = _tavily_search_sync(url, max_results=3)
            if tavily_result and len(tavily_result) > len(text):
                text = tavily_result
        except Exception as e:
            logger.warning(f"URL Tavily fallback failed for {url}: {e}")

    # Last resort: Playwright for JS-heavy pages (Threads, Instagram, Twitter, etc.)
    if len(text) < 150:
        try:
            text = _playwright_fetch_sync(url)
        except Exception as e:
            logger.warning(f"URL Playwright fallback failed for {url}: {e}")

    return text[:max_chars] if text else ""


def _playwright_fetch_sync(url: str, timeout_ms: int = 15000) -> str:
    """Fetch page content using Playwright (handles JS-rendered pages)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        try:
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            text = page.inner_text("body")
            return text[:3000].strip() if text else ""
        finally:
            browser.close()


async def async_fetch_url(url: str) -> str:
    """Async wrapper for fetch_url_content."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fetch_url_content, url)


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
