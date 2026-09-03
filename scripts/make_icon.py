# -*- coding: utf-8 -*-
"""生成应用图标 assets/icon.ico（indigo→cyan 渐变圆角方块 + 白色"毕"字 + 学士帽折角）。"""
import os

from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "icon.ico")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

# 渐变背景（对角 indigo -> cyan）
grad = Image.new("RGBA", (S, S))
px = grad.load()
for y in range(S):
    for x in range(S):
        t = (x + y) / (2 * S)
        r = int(79 + (14 - 79) * t)      # 0x4F46E5 -> 0x0EA5E9
        g = int(70 + (165 - 70) * t)
        b = int(229 + (233 - 229) * t)
        px[x, y] = (r, g, b, 255)

# 圆角掩码
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=110, fill=255)
img.paste(grad, (0, 0), mask)

# 高光
hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(hl).ellipse((-120, -140, 260, 220), fill=(255, 255, 255, 46))
hl = hl.filter(ImageFilter.GaussianBlur(60))
img.alpha_composite(hl)

draw = ImageDraw.Draw(img)
# 学士帽（白色简笔）
draw.polygon([(256 - 150, 190), (256, 128), (256 + 150, 190)], fill=(255, 255, 255, 235))
draw.rectangle((256 - 150, 186, 256 + 150, 212), fill=(255, 255, 255, 245))
draw.line((256, 212, 256, 250), fill=(255, 255, 255, 245), width=12)
# 帽穗
draw.line((256 + 130, 190, 256 + 190, 236), fill=(255, 255, 255, 235), width=10)
draw.ellipse((256 + 182, 228, 256 + 202, 248), fill=(255, 255, 255, 255))

# 白色"毕"字
try:
    from PIL import ImageFont

    for fp in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc"):
        if os.path.exists(fp):
            font = ImageFont.truetype(fp, 150)
            break
    else:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "毕", font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text(((S - w) / 2 - bbox[0], 300 - h / 2 - bbox[1] + 12), "毕", font=font, fill=(255, 255, 255, 255))
except Exception:
    pass

img = img.resize((256, 256), Image.LANCZOS)
img.save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon saved:", OUT, os.path.getsize(OUT), "bytes")
