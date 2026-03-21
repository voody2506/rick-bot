"""Memory management — chat history, facts, group state."""
import json
from pathlib import Path
from collections import defaultdict, deque
from src.config import MAX_HISTORY, MEMORY_DIR


def get_memory_dir(chat_id):
    d = MEMORY_DIR / str(chat_id)
    d.mkdir(parents=True, exist_ok=True)
    return d

def load_history(chat_id):
    path = get_memory_dir(chat_id) / "history.json"
    if path.exists():
        try: return deque(json.loads(path.read_text()), maxlen=MAX_HISTORY * 2)
        except: pass
    return deque(maxlen=MAX_HISTORY * 2)

def save_history(chat_id, history):
    (get_memory_dir(chat_id) / "history.json").write_text(
        json.dumps(list(history), ensure_ascii=False, indent=2))

def load_facts(chat_id):
    path = get_memory_dir(chat_id) / "facts.json"
    if path.exists():
        try: return json.loads(path.read_text())
        except: pass
    return []

def save_facts(chat_id, facts):
    (get_memory_dir(chat_id) / "facts.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=2))

chat_histories = defaultdict(lambda: deque(maxlen=MAX_HISTORY * 2))
# Буфер последних сообщений группы для контекста
group_context = defaultdict(lambda: deque(maxlen=8))
# Участники групповых чатов {chat_id: {user_id: {"name": str, "username": str}}}
group_members = defaultdict(dict)
# Последнее фото в группе для follow-up вопросов {chat_id: {"path": str, "ts": float}}
group_recent_photos = {}
PHOTO_QUESTION_KEYWORDS = [
    "реши", "решить", "объясни", "объяснить", "что здесь", "что на",
    "разбери", "помоги", "задачу", "задачи", "ответ", "посмотри",
    "можешь", "что написано", "прочитай", "переведи", "вычисли", "найди ответ"
]

def init_chat(chat_id):
    if chat_id not in chat_histories or len(chat_histories[chat_id]) == 0:
        chat_histories[chat_id] = load_history(chat_id)
