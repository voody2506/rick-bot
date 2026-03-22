# Rick Bot

<img width="580" height="383" alt="Снимок экрана 2026-03-22 в 05 08 52" src="https://github.com/user-attachments/assets/b3b023fb-edd5-4a72-a12a-cd6b3e83e664" />


> Rick Sanchez AI Telegram Bot — powered by Claude

[![CI/CD](https://github.com/voody2506/rick-bot/actions/workflows/deploy.yml/badge.svg)](https://github.com/voody2506/rick-bot/actions/workflows/deploy.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Telegram bot that roleplays as Rick Sanchez from Rick and Morty, powered by Claude AI. Supports text, voice messages (input & output), photo analysis, web search, scheduled tasks, and group chats with persistent memory.

## Features

- **Rick Sanchez personality** — sarcastic, genius-level responses in character
- **Voice input** — transcribes voice messages via Whisper
- **Voice responses** — Rick occasionally sends voice messages via Fish Audio TTS (7% chance)
- **Photo analysis** — analyzes images using Claude's vision
- **Web search** — real-time search via Tavily (DuckDuckGo fallback)
- **Group chats** — context-aware responses, @mentions participants
- **Three-tier memory** — conversation history + episodic summaries + user profiles
- **Time awareness** — Rick knows the current date and references past conversations
- **Emoji reactions** — Rick reacts to messages with mood-based emojis (20% chance)
- **Stickers** — sends Rick & Morty stickers by mood (10% chance)
- **GIFs** — searches and sends relevant Rick & Morty GIFs (5% chance)
- **Markdown formatting** — code blocks, bold, italic in responses
- **Parallel tasks** — splits complex requests into subtasks
- **Scheduled tasks** — reminders and recurring tasks via APScheduler
- **Skills system** — extensible via ClawHub skills marketplace
- **Auto language** — responds in the user's language
- **Dual Claude mode** — Anthropic API or Claude CLI fallback
- **Rate limiting** — protects against spam (10 msg/min per user)
- **Reply context** — Rick sees what message you're replying to
- **CI/CD** — auto-deploy via GitHub Actions + GHCR + Docker

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
| `TTS_ENABLED` | No | `false` | Enable voice responses |
| `FISH_AUDIO_API_KEY` | No | — | Fish Audio API key for TTS |
| `FISH_AUDIO_VOICE_ID` | No | `d2e75a3e...` | Fish Audio voice model ID |
| `TAVILY_API_KEY` | No | — | Tavily API key for web search (recommended) |

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
├── media.py        # Voice (Whisper), web search (Tavily), files
├── memes.py        # GIF reactions via Tavily image search
├── memory.py       # Three-tier memory: history, summaries, profiles
├── parallel.py     # Parallel task decomposition
├── prompts.py      # All system and task prompts
├── reactions.py    # Emoji reactions on user messages
├── scheduler.py    # APScheduler for reminders
├── skills.py       # ClawHub skills marketplace integration
├── stickers.py     # Rick & Morty sticker responses by mood
└── tts.py          # Text-to-Speech via Fish Audio
```

### Memory System

Rick has a three-tier memory system:

1. **Working memory** — last 20 messages in the current conversation
2. **Episodic memory** — conversation summaries with timestamps, stored when history fills up
3. **User profile** — structured knowledge (name, language, interests, communication style), updated automatically

This lets Rick reference past conversations and remember user preferences across sessions.

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
