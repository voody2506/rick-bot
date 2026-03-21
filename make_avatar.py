#!/usr/bin/env python3
"""Рисуем drunk Rick аватарку"""
from PIL import Image, ImageDraw, ImageFont
import math, os

SIZE = 512
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
draw = ImageDraw.Draw(img)

# --- Фон: портальное зелёное свечение ---
for r in range(SIZE // 2, 0, -1):
    ratio = r / (SIZE // 2)
    g = int(180 * (1 - ratio) + 20)
    b = int(60 * (1 - ratio))
    alpha = int(255 * (1 - ratio * 0.6))
    draw.ellipse(
        [SIZE // 2 - r, SIZE // 2 - r, SIZE // 2 + r, SIZE // 2 + r],
        fill=(0, g, b, alpha)
    )

# Тёмный фон поверх для контраста
draw.rectangle([0, 0, SIZE, SIZE], fill=(10, 20, 10, 180))

# --- Лицо Рика ---
cx, cy = SIZE // 2, SIZE // 2 + 30

# Шея
draw.rectangle([cx - 28, cy + 80, cx + 28, cy + 130], fill=(210, 200, 170))

# Лабораторный халат (белый)
draw.polygon([
    (cx - 120, SIZE), (cx - 90, cy + 120), (cx - 30, cy + 110),
    (cx + 30, cy + 110), (cx + 90, cy + 120), (cx + 120, SIZE)
], fill=(240, 240, 240))
# Воротник
draw.polygon([
    (cx - 30, cy + 110), (cx, cy + 140), (cx + 30, cy + 110),
    (cx + 20, cy + 160), (cx - 20, cy + 160)
], fill=(200, 200, 200))

# Голова
draw.ellipse([cx - 90, cy - 100, cx + 90, cy + 90], fill=(210, 200, 170))

# --- Белые торчащие волосы ---
hair_color = (245, 245, 250)
# Основная шапка волос
draw.ellipse([cx - 85, cy - 160, cx + 85, cy - 60], fill=hair_color)
# Торчащие пряди слева
for i, (ox, oy, angle) in enumerate([(-70, -140, -40), (-90, -120, -60), (-80, -100, -50)]):
    x1, y1 = cx + ox, cy + oy
    x2 = x1 + int(35 * math.cos(math.radians(angle)))
    y2 = y1 + int(35 * math.sin(math.radians(angle)))
    draw.line([x1, y1, x2, y2], fill=hair_color, width=8)
    draw.ellipse([x2-6, y2-6, x2+6, y2+6], fill=hair_color)
# Торчащие пряди справа
for i, (ox, oy, angle) in enumerate([(70, -140, -140), (90, -120, -120), (80, -100, -130)]):
    x1, y1 = cx + ox, cy + oy
    x2 = x1 + int(35 * math.cos(math.radians(angle)))
    y2 = y1 + int(35 * math.sin(math.radians(angle)))
    draw.line([x1, y1, x2, y2], fill=hair_color, width=8)
    draw.ellipse([x2-6, y2-6, x2+6, y2+6], fill=hair_color)

# --- Брови ---
# Левая бровь (нахмурена)
draw.line([cx - 70, cy - 40, cx - 30, cy - 32], fill=(100, 90, 80), width=6)
# Правая бровь — droopy (опущена, пьяная)
draw.line([cx + 30, cy - 28, cx + 70, cy - 22], fill=(100, 90, 80), width=6)

# --- Глаза ---
# Левый глаз — нормальный
draw.ellipse([cx - 65, cy - 25, cx - 30, cy + 10], fill=(255, 255, 255))
draw.ellipse([cx - 58, cy - 18, cx - 37, cy + 3], fill=(50, 180, 50))
draw.ellipse([cx - 54, cy - 14, cx - 41, cy - 1], fill=(20, 20, 20))
draw.ellipse([cx - 50, cy - 12, cx - 46, cy - 8], fill=(255, 255, 255))  # блик

# Правый глаз — droopy (пьяный, полузакрытый)
draw.ellipse([cx + 30, cy - 18, cx + 65, cy + 10], fill=(255, 255, 255))
draw.ellipse([cx + 36, cy - 12, cx + 58, cy + 4], fill=(50, 180, 50))
draw.ellipse([cx + 40, cy - 8, cx + 54, cy + 2], fill=(20, 20, 20))
# Веко опущено
draw.arc([cx + 30, cy - 18, cx + 65, cy + 10], start=200, end=340, fill=(210, 200, 170), width=10)
draw.line([cx + 30, cy - 5, cx + 65, cy - 2], fill=(210, 200, 170), width=9)

# --- Нос ---
draw.ellipse([cx - 12, cy + 5, cx + 12, cy + 30], fill=(190, 175, 145))
draw.ellipse([cx - 10, cy + 22, cx - 2, cy + 32], fill=(160, 140, 110))
draw.ellipse([cx + 2, cy + 22, cx + 10, cy + 32], fill=(160, 140, 110))

# --- Рот (пьяная ухмылка) ---
draw.arc([cx - 40, cy + 35, cx + 40, cy + 80], start=10, end=170, fill=(100, 60, 60), width=5)
# Зубы
draw.rectangle([cx - 18, cy + 42, cx + 18, cy + 58], fill=(230, 230, 220))
draw.line([cx - 5, cy + 42, cx - 5, cy + 58], fill=(150, 140, 130), width=2)
draw.line([cx + 5, cy + 42, cx + 5, cy + 58], fill=(150, 140, 130), width=2)

# --- Зелёная колба в руке ---
flask_x, flask_y = cx + 130, cy + 60
# Тело колбы
draw.ellipse([flask_x - 28, flask_y, flask_x + 28, flask_y + 55], fill=(0, 200, 80, 220))
# Горлышко
draw.rectangle([flask_x - 10, flask_y - 35, flask_x + 10, flask_y + 5], fill=(180, 200, 180))
# Пробка
draw.rectangle([flask_x - 12, flask_y - 42, flask_x + 12, flask_y - 33], fill=(80, 60, 40))
# Свечение внутри
draw.ellipse([flask_x - 18, flask_y + 8, flask_x + 18, flask_y + 42], fill=(80, 255, 130, 180))
# Рука
draw.rectangle([cx + 90, cy + 80, cx + 135, cy + 110], fill=(210, 200, 170))

# --- Речевой пузырь с "*ырп*" ---
bubble_x, bubble_y = 80, 60
# Пузырь
draw.ellipse([bubble_x - 60, bubble_y - 30, bubble_x + 60, bubble_y + 30], fill=(255, 255, 255, 230))
draw.ellipse([bubble_x - 60, bubble_y - 30, bubble_x + 60, bubble_y + 30], outline=(50, 50, 50), width=2)
# Хвостик
draw.polygon([
    (bubble_x + 10, bubble_y + 28),
    (cx - 60, cy - 85),
    (bubble_x + 30, bubble_y + 22)
], fill=(255, 255, 255, 230))
draw.polygon([
    (bubble_x + 10, bubble_y + 28),
    (cx - 60, cy - 85),
    (bubble_x + 30, bubble_y + 22)
], outline=(50, 50, 50), width=1)

# Текст в пузыре
try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
    font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
except:
    font = ImageFont.load_default()
    font_small = font

draw.text((bubble_x, bubble_y), "*ырп*", fill=(30, 30, 30), font=font, anchor="mm")

# --- Финальные мазки: пятна от алкоголя на халате ---
draw.ellipse([cx - 50, cy + 150, cx - 30, cy + 165], fill=(200, 180, 160, 120))
draw.ellipse([cx + 10, cy + 160, cx + 35, cy + 175], fill=(200, 180, 160, 100))

# Сохраняем
out_path = os.path.expanduser("~/Desktop/rick_bot/rick_avatar.jpg")
rgb = img.convert("RGB")
rgb.save(out_path, "JPEG", quality=95)
print(f"Аватарка сохранена: {out_path}")
