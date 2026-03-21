#!/usr/bin/env python3
"""Generate Rick Sanchez avatar using Pillow"""
from PIL import Image, ImageDraw, ImageFont
import math, os

W, H = 512, 512
img = Image.new("RGB", (W, H), (10, 10, 20))
draw = ImageDraw.Draw(img)

# Portal green glow background
for r in range(220, 0, -1):
    alpha = int(180 * (1 - r / 220))
    green = min(255, 60 + int(195 * (1 - r / 220)))
    draw.ellipse([W//2 - r, H//2 - r, W//2 + r, H//2 + r],
                 fill=(0, green, 0))

# Re-draw darker center (not pure glow)
for r in range(150, 0, -1):
    g = int(20 + 80 * (r / 150))
    draw.ellipse([W//2 - r, H//2 - r + 30, W//2 + r, H//2 + r + 30],
                 fill=(0, g, 10))

# --- Lab coat (body) ---
# Torso white coat
draw.rectangle([155, 310, 355, 512], fill=(230, 230, 240))
# Coat lapels / collar
draw.polygon([(230, 310), (256, 370), (256, 512), (155, 512), (155, 310)], fill=(210, 210, 220))
draw.polygon([(282, 310), (256, 370), (256, 512), (355, 512), (355, 310)], fill=(215, 215, 225))
# Blue shirt underneath
draw.rectangle([232, 310, 280, 512], fill=(100, 140, 200))

# --- Neck ---
draw.rectangle([236, 265, 276, 318], fill=(255, 220, 175))

# --- Head ---
head_cx, head_cy = 256, 210
draw.ellipse([head_cx-90, head_cy-95, head_cx+90, head_cy+90], fill=(255, 220, 175))

# --- Ears ---
draw.ellipse([head_cx-105, head_cy-20, head_cx-80, head_cy+20], fill=(255, 210, 165))
draw.ellipse([head_cx+80, head_cy-20, head_cx+105, head_cy+20], fill=(255, 210, 165))

# --- White spiky hair ---
hair_color = (245, 245, 255)
spikes = [
    (head_cx - 80, head_cy - 85),
    (head_cx - 55, head_cy - 115),
    (head_cx - 20, head_cy - 130),
    (head_cx + 15, head_cy - 125),
    (head_cx + 50, head_cy - 110),
    (head_cx + 80, head_cy - 85),
]
# Hair base
draw.ellipse([head_cx-88, head_cy-105, head_cx+88, head_cy-30], fill=hair_color)
# Hair spikes
for i, (sx, sy) in enumerate(spikes):
    prev_x = head_cx - 88 + i * 35
    next_x = prev_x + 35
    draw.polygon([(prev_x, head_cy - 75), (sx, sy), (next_x, head_cy - 75)], fill=hair_color)

# --- Droopy eyes (drunk Rick) ---
# Left eye
draw.ellipse([head_cx-58, head_cy-35, head_cx-22, head_cy+5], fill=(255, 255, 255))
draw.ellipse([head_cx-52, head_cy-28, head_cx-30, head_cy+2], fill=(80, 180, 80))
draw.ellipse([head_cx-47, head_cy-24, head_cx-35, head_cy-2], fill=(20, 20, 20))
# Droopy eyelid left
draw.arc([head_cx-60, head_cy-38, head_cx-20, head_cy+8], start=200, end=340, fill=(255, 200, 160), width=7)

# Right eye
draw.ellipse([head_cx+22, head_cy-35, head_cx+58, head_cy+5], fill=(255, 255, 255))
draw.ellipse([head_cx+30, head_cy-28, head_cx+52, head_cy+2], fill=(80, 180, 80))
draw.ellipse([head_cx+35, head_cy-24, head_cx+47, head_cy-2], fill=(20, 20, 20))
# Droopy eyelid right
draw.arc([head_cx+20, head_cy-38, head_cx+60, head_cy+8], start=200, end=340, fill=(255, 200, 160), width=7)

# --- Eyebrows (big & expressive) ---
draw.line([(head_cx-62, head_cy-45), (head_cx-20, head_cy-38)], fill=(200, 200, 210), width=7)
draw.line([(head_cx+20, head_cy-38), (head_cx+62, head_cy-45)], fill=(200, 200, 210), width=7)

# --- Nose ---
draw.ellipse([head_cx-12, head_cy+5, head_cx+12, head_cy+30], fill=(240, 200, 155))
draw.ellipse([head_cx-14, head_cy+12, head_cx-2, head_cy+28], fill=(220, 175, 135))
draw.ellipse([head_cx+2, head_cy+12, head_cx+14, head_cy+28], fill=(220, 175, 135))

# --- Drunk open mouth ---
draw.arc([head_cx-35, head_cy+30, head_cx+35, head_cy+70], start=10, end=170, fill=(80, 20, 20), width=3)
draw.ellipse([head_cx-32, head_cy+35, head_cx+32, head_cy+68], fill=(120, 40, 40))
# Teeth
draw.rectangle([head_cx-28, head_cy+36, head_cx-10, head_cy+52], fill=(240, 240, 240))
draw.rectangle([head_cx-8, head_cy+36, head_cx+8, head_cy+52], fill=(240, 240, 240))
draw.rectangle([head_cx+10, head_cy+36, head_cx+28, head_cy+52], fill=(240, 240, 240))

# --- Green flask (portal gun style) ---
# Flask body
draw.ellipse([340, 340, 420, 430], fill=(20, 200, 60))
draw.rectangle([368, 290, 392, 350], fill=(150, 200, 150))
# Flask neck
draw.rectangle([372, 275, 388, 295], fill=(100, 160, 100))
draw.ellipse([366, 268, 394, 284], fill=(80, 150, 80))
# Glow bubbles inside
for bx, by, br in [(360, 380, 12), (390, 400, 8), (375, 360, 6)]:
    draw.ellipse([bx-br, by-br, bx+br, by+br], fill=(100, 255, 130, 180))

# --- Speech bubble "*ырп*" ---
bub_x, bub_y = 370, 150
bub_w, bub_h = 130, 60
# Bubble
draw.rounded_rectangle([bub_x, bub_y, bub_x+bub_w, bub_y+bub_h], radius=18, fill=(255, 255, 255), outline=(50, 200, 50), width=3)
# Tail
draw.polygon([(bub_x+10, bub_y+bub_h), (bub_x-15, bub_y+bub_h+30), (bub_x+35, bub_y+bub_h)], fill=(255, 255, 255))
draw.line([(bub_x+10, bub_y+bub_h), (bub_x-15, bub_y+bub_h+30)], fill=(50, 200, 50), width=3)
draw.line([(bub_x-15, bub_y+bub_h+30), (bub_x+35, bub_y+bub_h)], fill=(50, 200, 50), width=3)

# Text in bubble
try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
    font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
except:
    font = ImageFont.load_default()
    font_small = font

draw.text((bub_x + 18, bub_y + 10), "*ырп*", fill=(0, 150, 0), font=font)
draw.text((bub_x + 8, bub_y + 36), "Морти...", fill=(80, 80, 80), font=font_small)

# --- "C-137" label at bottom ---
draw.rectangle([160, 470, 350, 510], fill=(0, 0, 0, 180))
try:
    label_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
except:
    label_font = ImageFont.load_default()
draw.text((185, 478), "Rick Sanchez C-137", fill=(0, 255, 80), font=label_font)

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rick_avatar.jpg")
img.save(out_path, "JPEG", quality=95)
print(f"✅ Аватарка сохранена: {out_path}")
