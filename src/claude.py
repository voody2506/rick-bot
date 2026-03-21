"""Claude client — dual-mode: Anthropic SDK or CLI fallback."""
import subprocess
import asyncio
import logging
import os
import base64
from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_TIMEOUT, WORK_DIR

logger = logging.getLogger(__name__)


def run_claude_sync(prompt: str, timeout: int = CLAUDE_TIMEOUT, image_path: str = None) -> str:
    if ANTHROPIC_API_KEY:
        return _run_sdk_sync(prompt, timeout, image_path)
    return _run_cli_sync(prompt, timeout, image_path)


def _run_sdk_sync(prompt: str, timeout: int, image_path: str = None) -> str:
    """Anthropic SDK mode."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    content = []
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": data}
        })
    content.append({"type": "text", "text": prompt})
    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": content}],
            timeout=timeout
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"SDK error: {e}")
        return ""


def _run_cli_sync(prompt: str, timeout: int, image_path: str = None) -> str:
    """Claude CLI fallback."""
    if image_path:
        prompt = _build_vision_cli_prompt(prompt, image_path)
    cmd = ["claude", "-p", prompt, "--dangerously-skip-permissions"]
    try:
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(WORK_DIR)
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except subprocess.TimeoutExpired:
        return ""
    except FileNotFoundError:
        return "claude CLI not found"
    except Exception as e:
        return f"error: {e}"


def _build_vision_cli_prompt(user_question: str, image_path: str) -> str:
    """Build prompt for CLI vision — uses Read tool approach from v9."""
    from src.prompts import RICK_SYSTEM
    abs_path = os.path.abspath(image_path)
    return (
        RICK_SYSTEM
        + f"\n\nИспользуй Read tool чтобы прочитать файл изображения '{abs_path}'. "
        + f"Затем ответь на вопрос: {user_question}"
    )


async def run_claude(prompt: str, timeout: int = CLAUDE_TIMEOUT, image_path: str = None) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, run_claude_sync, prompt, timeout, image_path)
