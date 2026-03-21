# Rick Bot Redesign — v9 to v10

## Summary
Refactor Rick Bot from a monolithic script into a modular, dockerized, open-source project with CI/CD.

## Goals
- **Portfolio** — clean code, good README, solid architecture
- **Open-source** — anyone can fork and run via `docker-compose up`
- **Auto-deploy** — `git push` to main → bot updates on server automatically

## Architecture

### Module structure
```
src/
  bot.py          — Application, handlers, main()
  claude.py       — dual-mode: Anthropic SDK (API key) or CLI fallback
  memory.py       — history, facts — load/save JSON
  groups.py       — should_respond_in_group, group context, members
  parallel.py     — try_parallel, merge subtasks
  scheduler.py    — APScheduler, reminders
  skills.py       — Clawhub skills system
  media.py        — photo (anthropic SDK), voice (whisper)
  prompts.py      — all system/task prompts
```

### Configuration (.env)
| Variable | Default | Description |
|----------|---------|-------------|
| BOT_TOKEN | required | Telegram bot token |
| OWNER_ID | required | Owner's Telegram ID |
| ANTHROPIC_API_KEY | optional | If set, uses SDK; otherwise falls back to CLI |
| MAX_HISTORY | 20 | Messages in conversation history |
| MAX_FACTS | 50 | Max facts per chat |
| CLAUDE_TIMEOUT | 90 | Claude call timeout (seconds) |
| CLAUDE_MODEL | sonnet | Model name (SDK mode) |
| GROUP_RANDOM_CHANCE | 0.07 | Chance Rick interjects in groups (0-1) |
| WHISPER_MODEL | tiny | Whisper model size |

### Claude dual-mode
- If `ANTHROPIC_API_KEY` is set → use `anthropic` Python SDK
- If not → fall back to `claude` CLI (requires `~/.claude` volume mount)

### Language
Auto-detect from user messages. System prompt says "respond in the user's language" instead of hardcoding Russian.

## Docker

### Dockerfile
- Base: `python:3.11-slim`
- Install: ffmpeg, Claude CLI, requirements.txt
- Whisper model cached in volume

### docker-compose.yml
- Volumes: `memory/`, `work/`, `skills/`, `~/.claude` (ro)
- `env_file: .env`
- `restart: unless-stopped`

## CI/CD

### GitHub Actions (deploy.yml)
1. Trigger: push to `main`
2. Lint: `ruff`
3. Test: `pytest`
4. Build Docker image
5. Push to `ghcr.io/voody2506/rick-bot:latest`
6. SSH to server → `docker pull` + `docker-compose up -d`

Other branches: lint + test only, no deploy.

### GitHub Secrets
- `SERVER_HOST`, `SERVER_SSH_KEY`
- `BOT_TOKEN`, `OWNER_ID`

## Tests
- `test_memory.py` — load/save history and facts, limits, corrupted files
- `test_groups.py` — should_respond_in_group logic
- `test_prompts.py` — build_prompt with/without facts/history

Linter: ruff

## Documentation
- `README.md` — English, badges, features, quick start, architecture, contributing
- `.env.example` — all variables with comments and defaults
- `LICENSE` — MIT
