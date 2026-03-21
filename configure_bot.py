#!/usr/bin/env python3
import requests, os, sys

BOT_TOKEN = "8535704067:AAHPbfzNYQafEOhJWeRGDTgqcGoQsOxMzyE"
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

def set_name():
    r = requests.post(f"{BASE_URL}/setMyName", json={"name": "Rick Sanchez C-137"})
    print("✅ Имя:" if r.json().get("ok") else f"⚠️ Имя: {r.json()}")

def set_description():
    desc = "*ырп* Это я, Рик Санчез, умнейший человек во вселенной. Просто напиши что-нибудь... если хватит мозгов, Морти."
    r = requests.post(f"{BASE_URL}/setMyDescription", json={"description": desc})
    print("✅ Описание" if r.json().get("ok") else f"⚠️ Описание: {r.json()}")

def set_short_description():
    r = requests.post(f"{BASE_URL}/setMyShortDescription", json={"short_description": "Рик Санчез C-137 • Умнейший человек во вселенной 🧪"})
    print("✅ Краткое описание" if r.json().get("ok") else f"⚠️ {r.json()}")

def set_avatar():
    avatar_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rick_avatar.jpg")
    if not os.path.exists(avatar_path):
        print(f"⚠️ Файл rick_avatar.jpg не найден по пути: {avatar_path}")
        return
    with open(avatar_path, "rb") as f:
        r = requests.post(f"{BASE_URL}/setMyPhoto", files={"photo": f})
    print("✅ Аватарка!" if r.json().get("ok") else f"⚠️ Аватарка: {r.json()}")

if __name__ == "__main__":
    print("🧪 Настраиваем профиль бота...\n")
    set_name()
    set_description()
    set_short_description()
    set_avatar()
    print("\n✅ Готово!")
