# Rick Bot v10 Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor monolithic rick_bot.py (1300 lines) into modular project with Docker, CI/CD, tests, and dual Claude mode.

**Architecture:** Split into 10 modules under `src/`, extract secrets to `.env`, add Docker + GHCR CI/CD, basic unit tests. Keep all existing functionality intact.

**Tech Stack:** Python 3.11, python-telegram-bot, anthropic SDK, whisper, APScheduler, Docker, GitHub Actions, ruff, pytest

---

### Task 1: Project scaffolding — config, .env, requirements.txt

**Files:**
- Create: `src/__init__.py`
- Create: `src/config.py`
- Create: `.env.example`
- Create: `requirements.txt`

- [ ] **Step 1: Create `src/config.py`** — centralized config from env vars

```python
import os
from pathlib import Path

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "sonnet")
CLAUDE_TIMEOUT = int(os.getenv("CLAUDE_TIMEOUT", "90"))

MAX_HISTORY = int(os.getenv("MAX_HISTORY", "20"))
MAX_FACTS = int(os.getenv("MAX_FACTS", "50"))
GROUP_RANDOM_CHANCE = float(os.getenv("GROUP_RANDOM_CHANCE", "0.07"))
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")

BASE_DIR = Path(os.getenv("BASE_DIR", Path(__file__).resolve().parent.parent))
MEMORY_DIR = BASE_DIR / "memory"
WORK_DIR = BASE_DIR / "work"
SKILLS_DIR = BASE_DIR / "skills"
TOKENS_DIR = BASE_DIR / "tokens"

RICK_NAMES = ["рик", "rick", "санчез", "sanchez", "рика", "рику", "риком"]

CLAWHUB_SEARCH_URL = "https://clawhub.ai/api/search"
CLAWHUB_DOWNLOAD_URL = "https://wry-manatee-359.convex.site/api/v1/download"
```

- [ ] **Step 2: Create `src/__init__.py`** — empty file

- [ ] **Step 3: Create `.env.example`**

```env
# Required
BOT_TOKEN=your-telegram-bot-token
OWNER_ID=your-telegram-id

# Claude — Option A (recommended): Anthropic API key
ANTHROPIC_API_KEY=your-api-key
# Option B: leave empty, use claude CLI (mount ~/.claude as volume)

# Model (SDK mode)
CLAUDE_MODEL=sonnet

# Timeouts
CLAUDE_TIMEOUT=90

# Memory
MAX_HISTORY=20
MAX_FACTS=50

# Groups
GROUP_RANDOM_CHANCE=0.07

# Whisper model: tiny/base/small/medium/large
WHISPER_MODEL=tiny
```

- [ ] **Step 4: Create `requirements.txt`**

```
python-telegram-bot>=21.0
anthropic>=0.40.0
openai-whisper>=20231117
apscheduler>=3.10.0
sqlalchemy>=2.0.0
Pillow>=10.0.0
python-dotenv>=1.0.0
ruff>=0.4.0
pytest>=8.0.0
```

- [ ] **Step 5: Commit**

```bash
git add src/__init__.py src/config.py .env.example requirements.txt
git commit -m "feat: add project scaffolding — config, .env, requirements"
```

---

### Task 2: Extract prompts module

**Files:**
- Create: `src/prompts.py`

- [ ] **Step 1: Create `src/prompts.py`** — move all prompt constants from rick_bot.py

Move these constants: `RICK_SYSTEM`, `GROUP_SYSTEM`, `PARALLEL_CHECK`, `MERGE_PROMPT`, `EXTRACT_FACTS_PROMPT`, `DECISION_PROMPT`, `GROUP_RESPONSE_PROMPT`.

Update `RICK_SYSTEM` language line: replace "Говоришь по-русски" with "Отвечай на языке собеседника. Технические термины на английском ок."

- [ ] **Step 2: Commit**

```bash
git add src/prompts.py
git commit -m "feat: extract prompts module"
```

---

### Task 3: Extract memory module

**Files:**
- Create: `src/memory.py`

- [ ] **Step 1: Create `src/memory.py`**

Move from rick_bot.py: `get_memory_dir`, `load_history`, `save_history`, `load_facts`, `save_facts`, `chat_histories`, `group_context`, `group_members`, `group_recent_photos`, `init_chat`.

Import `MAX_HISTORY`, `MAX_FACTS`, `MEMORY_DIR` from `src.config`.

Keep `PHOTO_QUESTION_KEYWORDS` here as it's used by group photo logic.

- [ ] **Step 2: Commit**

```bash
git add src/memory.py
git commit -m "feat: extract memory module"
```

---

### Task 4: Extract claude module (dual-mode)

**Files:**
- Create: `src/claude.py`

- [ ] **Step 1: Create `src/claude.py`** — dual-mode Claude client

```python
import subprocess
import asyncio
import logging
import os
from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_TIMEOUT, WORK_DIR

logger = logging.getLogger(__name__)

def run_claude_sync(prompt: str, timeout: int = CLAUDE_TIMEOUT, image_path: str = None) -> str:
    if ANTHROPIC_API_KEY:
        return _run_sdk_sync(prompt, timeout, image_path)
    return _run_cli_sync(prompt, timeout, image_path)

def _run_sdk_sync(prompt: str, timeout: int, image_path: str = None) -> str:
    """Anthropic SDK mode"""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    # Build message content
    content = []
    if image_path and os.path.exists(image_path):
        import base64
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
    """Claude CLI fallback"""
    # Vision via CLI uses Read tool approach (existing logic from v9)
    if image_path:
        from src.media import build_vision_cli_prompt
        prompt = build_vision_cli_prompt(prompt, image_path)
    cmd = ["claude", "-p", prompt, "--dangerously-skip-permissions"]
    try:
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(WORK_DIR))
        return result.stdout.strip() if result.returncode == 0 else ""
    except subprocess.TimeoutExpired:
        return ""
    except FileNotFoundError:
        return "claude CLI not found"
    except Exception as e:
        return f"error: {e}"

async def run_claude(prompt: str, timeout: int = CLAUDE_TIMEOUT, image_path: str = None) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, run_claude_sync, prompt, timeout, image_path)
```

- [ ] **Step 2: Commit**

```bash
git add src/claude.py
git commit -m "feat: extract claude module with dual SDK/CLI mode"
```

---

### Task 5: Extract media module

**Files:**
- Create: `src/media.py`

- [ ] **Step 1: Create `src/media.py`**

Move from rick_bot.py:
- `run_claude_vision_sync` (renamed to `build_vision_cli_prompt` helper + keep vision logic)
- `web_search`
- `find_created_files`, `find_new_workdir_files`, `cleanup_work_dir`
- Whisper model loading and transcription helper

Import config from `src.config`.

- [ ] **Step 2: Commit**

```bash
git add src/media.py
git commit -m "feat: extract media module — vision, voice, web search, files"
```

---

### Task 6: Extract groups module

**Files:**
- Create: `src/groups.py`

- [ ] **Step 1: Create `src/groups.py`**

Move from rick_bot.py:
- `should_respond_in_group`
- `format_members_for_prompt`
- `build_group_response`

Import `GROUP_RANDOM_CHANCE` from config instead of hardcoded `0.07`.

- [ ] **Step 2: Commit**

```bash
git add src/groups.py
git commit -m "feat: extract groups module"
```

---

### Task 7: Extract parallel, scheduler, skills modules

**Files:**
- Create: `src/parallel.py`
- Create: `src/scheduler.py`
- Create: `src/skills.py`

- [ ] **Step 1: Create `src/parallel.py`** — move `try_parallel`

- [ ] **Step 2: Create `src/scheduler.py`** — move scheduler init, `SCHEDULE_TRIGGERS`, `is_schedule_request`, `handle_schedule_request`, `send_scheduled_message`

- [ ] **Step 3: Create `src/skills.py`** — move `load_skills_for_chat`, `search_clawhub`, `install_clawhub_skill`, `SERVICE_MAP`, `detect_service`, `handle_service_request`

- [ ] **Step 4: Commit**

```bash
git add src/parallel.py src/scheduler.py src/skills.py
git commit -m "feat: extract parallel, scheduler, skills modules"
```

---

### Task 8: Rewrite bot.py — main entry point with handlers

**Files:**
- Create: `src/bot.py`
- Delete: `rick_bot.py` (monolith)

- [ ] **Step 1: Create `src/bot.py`**

This is the main entry point. Contains:
- All handler functions: `handle_message`, `handle_voice`, `handle_photo`, `handle_document`
- Command handlers: `start_command`, `reset_command`, `forget_command`, `skill_command`, `schedule_command`
- `send_response` helper
- `keep_typing` helper
- `post_init`, `main`
- Imports everything from other modules

All handlers import from the extracted modules. Logic stays the same, just references change.

Add `dotenv` loading at top:
```python
from dotenv import load_dotenv
load_dotenv()
```

- [ ] **Step 2: Delete `rick_bot.py`**

```bash
git rm rick_bot.py
```

- [ ] **Step 3: Verify bot runs locally**

```bash
python -m src.bot
```

- [ ] **Step 4: Commit**

```bash
git add src/bot.py
git commit -m "feat: rewrite bot.py as main entry point, delete monolith"
```

---

### Task 9: Add tests

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_memory.py`
- Create: `tests/test_groups.py`
- Create: `tests/test_prompts.py`

- [ ] **Step 1: Create `tests/test_memory.py`**

```python
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from src.memory import load_history, save_history, load_facts, save_facts

def test_save_and_load_history(tmp_path):
    with patch("src.memory.MEMORY_DIR", tmp_path):
        from collections import deque
        h = deque(["hello", "world"], maxlen=40)
        save_history(123, h)
        loaded = load_history(123)
        assert list(loaded) == ["hello", "world"]

def test_load_history_empty(tmp_path):
    with patch("src.memory.MEMORY_DIR", tmp_path):
        loaded = load_history(999)
        assert len(loaded) == 0

def test_load_history_corrupted(tmp_path):
    with patch("src.memory.MEMORY_DIR", tmp_path):
        d = tmp_path / "999"
        d.mkdir()
        (d / "history.json").write_text("NOT JSON")
        loaded = load_history(999)
        assert len(loaded) == 0

def test_save_and_load_facts(tmp_path):
    with patch("src.memory.MEMORY_DIR", tmp_path):
        save_facts(123, ["fact1", "fact2"])
        loaded = load_facts(123)
        assert loaded == ["fact1", "fact2"]

def test_load_facts_empty(tmp_path):
    with patch("src.memory.MEMORY_DIR", tmp_path):
        assert load_facts(999) == []
```

- [ ] **Step 2: Create `tests/test_groups.py`**

```python
from src.groups import should_respond_in_group

def test_responds_to_direct_mention():
    assert should_respond_in_group("Рик, помоги", reply_to_bot=False) is True

def test_responds_to_reply():
    assert should_respond_in_group("что думаешь?", reply_to_bot=True) is True

def test_ignores_short_messages():
    assert should_respond_in_group("ок", reply_to_bot=False) is False

def test_responds_to_rick_topic_question():
    assert should_respond_in_group("Как работает квантовая физика?", reply_to_bot=False) is True

def test_ignores_irrelevant():
    # With random=0 to ensure deterministic test
    import unittest.mock
    with unittest.mock.patch("src.groups.random") as mock_random:
        mock_random.random.return_value = 1.0  # never triggers random
        assert should_respond_in_group("пойдём поедим пиццу вечером", reply_to_bot=False) is False
```

- [ ] **Step 3: Create `tests/test_prompts.py`**

```python
from unittest.mock import patch
from collections import deque

def test_build_prompt_with_facts():
    from src.memory import chat_histories, init_chat
    from src.prompts import RICK_SYSTEM
    # Import after patching
    with patch("src.memory.load_facts", return_value=["user is a dev"]):
        with patch("src.memory.load_history", return_value=deque()):
            with patch("src.skills.load_skills_for_chat", return_value=""):
                from src.bot import build_prompt
                prompt = build_prompt(123, "hello")
                assert "user is a dev" in prompt
                assert "hello" in prompt

def test_build_prompt_empty():
    with patch("src.memory.load_facts", return_value=[]):
        with patch("src.memory.load_history", return_value=deque()):
            with patch("src.skills.load_skills_for_chat", return_value=""):
                from src.bot import build_prompt
                prompt = build_prompt(456, "test")
                assert "test" in prompt
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/ -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: add unit tests for memory, groups, prompts"
```

---

### Task 10: Docker setup

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

# Install Claude CLI (for fallback mode)
RUN curl -fsSL https://cli.anthropic.com/install.sh | sh || true

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

CMD ["python", "-m", "src.bot"]
```

- [ ] **Step 2: Create `docker-compose.yml`**

```yaml
services:
  rick-bot:
    image: ghcr.io/voody2506/rick-bot:latest
    build: .
    env_file: .env
    volumes:
      - ./memory:/app/memory
      - ./work:/app/work
      - ./skills:/app/skills
      - ./tokens:/app/tokens
      - ${HOME}/.claude:/root/.claude:ro
    restart: unless-stopped
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: add Docker setup"
```

---

### Task 11: GitHub Actions CI/CD

**Files:**
- Create: `.github/workflows/deploy.yml`

- [ ] **Step 1: Create `.github/workflows/deploy.yml`**

```yaml
name: CI/CD

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install ruff pytest python-dotenv
      - run: ruff check src/ tests/
      - run: |
          pip install -r requirements.txt
          pytest tests/ -v
        env:
          BOT_TOKEN: fake-token-for-tests
          OWNER_ID: "0"

  build-and-push:
    needs: lint-and-test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest

  deploy:
    needs: build-and-push
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: root
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            cd /home/rickbot/rick_bot
            docker compose pull
            docker compose up -d
```

- [ ] **Step 2: Commit**

```bash
git add .github/
git commit -m "feat: add GitHub Actions CI/CD pipeline"
```

---

### Task 12: README and LICENSE

**Files:**
- Create: `README.md`
- Create: `LICENSE`

- [ ] **Step 1: Create `LICENSE`** — MIT license, copyright voody2506

- [ ] **Step 2: Create `README.md`** — English, containing:
- Title + badges (CI status, license, Docker)
- Features list
- Quick Start (3 steps: clone, .env, docker-compose up)
- Configuration table (all .env vars)
- Claude auth options (API key vs CLI)
- Architecture diagram (module list)
- Bot commands (/start, /reset, /forget, /skill, /schedule)
- Contributing guide (fork, branch, ruff, pytest, PR)
- License

- [ ] **Step 3: Add `ruff.toml`**

```toml
line-length = 120
target-version = "py311"
```

- [ ] **Step 4: Commit and push**

```bash
git add README.md LICENSE ruff.toml
git commit -m "docs: add README, LICENSE (MIT), ruff config"
git push origin main
```

---

### Task 13: Server migration to Docker

**Files:**
- No new files — server setup commands

- [ ] **Step 1: Install Docker on server**

```bash
ssh root@204.168.162.250 'curl -fsSL https://get.docker.com | sh'
```

- [ ] **Step 2: Copy `.env` and `docker-compose.yml` to server**

```bash
scp .env docker-compose.yml root@204.168.162.250:/home/rickbot/rick_bot/
```

- [ ] **Step 3: Stop old systemd service**

```bash
ssh root@204.168.162.250 'systemctl stop rick_bot && systemctl disable rick_bot'
```

- [ ] **Step 4: Pull and start Docker container**

```bash
ssh root@204.168.162.250 'cd /home/rickbot/rick_bot && docker compose pull && docker compose up -d'
```

- [ ] **Step 5: Verify bot responds in Telegram**

- [ ] **Step 6: Add GitHub Secrets**

In repo settings → Secrets → Actions:
- `SERVER_HOST` = `204.168.162.250`
- `SERVER_SSH_KEY` = contents of `~/.ssh/id_ed25519`

- [ ] **Step 7: Test full pipeline** — make a small change, push, verify auto-deploy
