#!/usr/bin/env python3
import requests, os
TOKEN = "8535704067:AAHPbfzNYQafEOhJWeRGDTgqcGoQsOxMzyE"
path = os.path.expanduser("~/Desktop/rick_bot/rick_avatar.jpg")
with open(path, "rb") as f:
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/setMyPhoto", files={"photo": f})
print(r.json())
