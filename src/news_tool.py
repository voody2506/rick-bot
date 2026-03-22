#!/usr/bin/env python3
"""News scheduling CLI tool — called by Claude CLI via bash."""
import sys
import json
from pathlib import Path

MEMORY_DIR = Path("/app/memory")
NEWS_CONFIG_FILE = MEMORY_DIR / "news_config.json"


def load_config():
    if NEWS_CONFIG_FILE.exists():
        try: return json.loads(NEWS_CONFIG_FILE.read_text())
        except: pass
    return {}


def save_config(config):
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.news_tool <action> [args]")
        print("  schedule <chat_id> <HH:MM> <topic>")
        print("  cancel <chat_id>")
        print("  list")
        sys.exit(1)

    action = sys.argv[1]
    config = load_config()

    if action == "schedule" and len(sys.argv) >= 5:
        chat_id = sys.argv[2]
        time_str = sys.argv[3]
        topic = " ".join(sys.argv[4:])
        config[chat_id] = {"time": time_str, "topic": topic}
        save_config(config)
        print(f"Scheduled daily news for chat {chat_id} at {time_str}: {topic}")

    elif action == "cancel" and len(sys.argv) >= 3:
        chat_id = sys.argv[2]
        config.pop(chat_id, None)
        save_config(config)
        print(f"Cancelled news for chat {chat_id}")

    elif action == "list":
        if config:
            for cid, cfg in config.items():
                print(f"Chat {cid}: {cfg['time']} — {cfg.get('topic', '?')}")
        else:
            print("No news scheduled")

    else:
        print(f"Unknown action: {action}")
