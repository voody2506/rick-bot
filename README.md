# Rick Bot

> Rick Sanchez AI Telegram Bot — powered by Claude

[![CI/CD](https://github.com/voody2506/rick-bot/actions/workflows/deploy.yml/badge.svg)](https://github.com/voody2506/rick-bot/actions/workflows/deploy.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Telegram bot that roleplays as Rick Sanchez from Rick and Morty, powered by Claude AI. Supports text, voice messages, photo analysis, scheduled tasks, and group chats.

## Features

- **Rick Sanchez personality** — sarcastic, genius-level responses in character
- **Voice messages** — transcribes via Whisper and responds
- **Photo analysis** — analyzes images using Claude's vision
- **Group chats** — context-aware responses, @mentions participants
- **Memory** — remembers conversation history and facts about users
- **Parallel tasks** — splits complex requests into subtasks
- **Scheduled tasks** — reminders and recurring tasks via APScheduler
- **Skills system** — extensible via ClawHub skills marketplace
- **Auto language** — responds in the user's language
- **Dual Claude mode** — Anthropic API or Claude CLI fallback

## Quick Start

1. Clone and configure:
   ```bash
   git clone https://github.com/voody2506/rick-bot.git
   cd rick-bot
   cp .env.example .env
   # Edit .env — set BOT_TOKEN and OWNER_ID at minimum
   ```

2. Run with Docker:
   ```bash
   docker compose up -d
   ```

   Or run directly:
   ```bash
   pip install -r requirements.txt
   python -m src.bot
   ```

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BOT_TOKEN` | Yes | — | Telegram bot token from @BotFather |
| `OWNER_ID` | Yes | — | Your Telegram user ID |
| `ANTHROPIC_API_KEY` | No | — | Anthropic API key (recommended) |
| `CLAUDE_MODEL` | No | `sonnet` | Claude model name |
| `CLAUDE_TIMEOUT` | No | `90` | Claude request timeout (seconds) |
| `MAX_HISTORY` | No | `20` | Messages kept in conversation history |
| `MAX_FACTS` | No | `50` | Max facts remembered per chat |
| `GROUP_RANDOM_CHANCE` | No | `0.07` | Chance Rick interjects in groups (0-1) |
| `WHISPER_MODEL` | No | `tiny` | Whisper model: tiny/base/small/medium/large |

### Claude Authentication

**Option A (recommended):** Set `ANTHROPIC_API_KEY` in `.env`. Get your key at [console.anthropic.com](https://console.anthropic.com).

**Option B:** Install [Claude CLI](https://docs.anthropic.com/en/docs/claude-cli), run `claude login` on the host. The Docker container mounts `~/.claude` as a read-only volume.

## Architecture

```
src/
├── bot.py          # Telegram handlers, main entry point
├── claude.py       # Dual-mode Claude client (SDK + CLI)
├── config.py       # Environment-based configuration
├── groups.py       # Group chat logic and response decisions
├── media.py        # Voice (Whisper), vision, web search, files
├── memory.py       # Chat history and facts persistence
├── parallel.py     # Parallel task decomposition
├── prompts.py      # All system and task prompts
├── scheduler.py    # APScheduler for reminders
└── skills.py       # ClawHub skills marketplace integration
```

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Start conversation with Rick |
| `/reset` | Clear conversation history |
| `/forget` | Clear history and all remembered facts |
| `/skill search <query>` | Search ClawHub for skills |
| `/skill install <slug>` | Install a skill |
| `/skill list` | List installed skills |
| `/schedule list` | View scheduled tasks |
| `/schedule cancel <id>` | Cancel a scheduled task |

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make changes and ensure lint passes: `ruff check src/ tests/`
4. Run tests: `pytest tests/ -v`
5. Submit a pull request

## License

[MIT](LICENSE)
