# -*- coding: utf-8 -*-
"""生成网易开发者平台提交模组所需的 7 张图片（程序化像素绘制）。

绘制风格与模组视觉一致：像素风棕色皮革小口袋 + 金绳扣，
深色渐变背景 + 星点 + 漂浮方块 + 随机物品点缀 + 中文标语。

输出目录：promo/submit/
用法: python gen_promo.py
"""

import os
import random

from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "promo", "submit")

# ---- 口袋像素画（与 build.py 保持一致）----
POCKET_ART = [
    "................",
    "......oooo......",
    ".....o....o.....",
    ".....o.ss.o.....",
    "....osbbbso.....",
    "...obbbbbbbbo...",
    "..olbbbbbbbbdo..",
    "..olbbbbbbbbdo..",
    "..olbbggggbdo...",
    "..olbbbbbbbbdo..",
    "..olbbbbbbbbdo..",
    "..obbbbbbbbbdo..",
    "...obbbbbbbbo...",
    "...oddddddddo...",
    "....oddddddo....",
    ".....oooooo.....",
]
POCKET_PAL = {
    "o": (62, 39, 35), "b": (121, 85, 72), "l": (141, 110, 99),
    "d": (93, 64, 55), "s": (237, 224, 200), "g": (253, 216, 53),
}

# ---- 点缀物品像素画 ----
DIAMOND = ["...b....", "..bwb...", ".bwlwb..", "bwlwwwb.",
           ".bwwwb..", "..bwb...", "...b....", "........"]
DIAMOND_PAL = {"b": (0, 131, 143), "w": (38, 198, 218), "l": (224, 247, 250)}

GOLD = ["........", "..oooo..", ".oyyyyo.", "oyylllyo",
        "oyyyyyyo", "oooooooo", "........", "........"]
GOLD_PAL = {"o": (141, 110, 0), "y": (255, 213, 79), "l": (255, 245, 157)}

APPLE = ["....g...", "...g....", ".rrlrr..", "rrrrrrr.",
         "rrrrrrr.", "rrrrrrr.", ".rrrrr..", "........"]
APPLE_PAL = {"r": (229, 57, 53), "g": (67, 160, 71), "l": (255, 205, 210)}

EMERALD = ["...b....", "..bwb...", ".bwlwb..", "bwlwwwb.",
           ".bwwwb..", "..bwb...", "...b....", "........"]
EMERALD_PAL = {"b": (27, 94, 32), "w": (102, 187, 106), "l": (200, 230, 201)}

ITEMS = [(DIAMOND, DIAMOND_PAL), (GOLD, GOLD_PAL),
         (APPLE, APPLE_PAL), (EMERALD, EMERALD_PAL)]

# ---- 7 张图的任务 ----
TASKS = [
    # (文件名, 宽, 高, 背景顶色, 背景底色, 标题, 副标题)
    ("1_迭代ICON_992x558.png", 992, 558, (26, 35, 126), (57, 73, 171),
     "随机口袋", "版本迭代 · 体验优化"),
    ("2_组件ICON_1000x1000.png", 1000, 1000, (38, 50, 56), (69, 90, 100),
     "随机口袋", "RandomPocket"),
    ("3_pos机_900x580.png", 900, 580, (78, 52, 46), (109, 76, 65),
     "随机口袋", "每天开出惊喜好物"),
    ("4_轮播图1_992x558.png", 992, 558, (13, 71, 161), (25, 118, 210),
     "每日随机刷新", "每个游戏日自动获得 1 个随机物品"),
    ("5_轮播图2_992x558.png", 992, 558, (27, 94, 32), (56, 142, 60),
     "10 格随身空间", "口袋容量 10 格，随身携带"),
    ("6_轮播图3_992x558.png", 992, 558, (49, 27, 146), (69, 39, 160),
     "宝箱式存取", "右键打开口袋，自由存放与取出"),
    ("7_资源中心首页轮播推广图_940x450.png", 940, 450, (63, 81, 181), (123, 31, 162),
     "随机口袋", "每天一个惊喜物品"),
]


def _font(size, bold=True):
    for name in (("msyhbd.ttc", "msyh.ttc", "simhei.ttf") if bold
                 else ("msyh.ttc", "simhei.ttf")):
        try:
            return ImageFont.truetype("C:/Windows/Fonts/" + name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def vgrad(w, h, top, bottom):
    """垂直渐变背景"""
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / float(h - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


def draw_stars(img, n, seed):
    rnd = random.Random(seed)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    w, h = img.size
    for _ in range(n):
        x, y = rnd.randint(0, w - 1), rnd.randint(0, h - 1)
        r = rnd.choice((1, 1, 2, 2, 3))
        a = rnd.randint(60, 160)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, a))
    img.alpha_composite(overlay)


def draw_blocks(img, n, seed):
    """漂浮的半透明方块，模拟 MC 粒子"""
    rnd = random.Random(seed)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    w, h = img.size
    for _ in range(n):
        s = rnd.randint(8, 26)
        x, y = rnd.randint(0, w - s), rnd.randint(0, h - s)
        a = rnd.randint(28, 70)
        if rnd.random() < 0.5:
            c = (255, 255, 255, a)
        else:
            c = (255, 213, 79, a)
        d.rectangle((x, y, x + s, y + s), fill=c)
    img.alpha_composite(overlay)


def draw_glow(img, cx, cy, radius, color=(255, 213, 79)):
    """柔和圆形光晕"""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    steps = 24
    for i in range(steps, 0, -1):
        r = int(radius * i / steps)
        a = int(70 * (steps - i) / steps)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color + (a,))
    img.alpha_composite(overlay)


def paste_art(img, art, pal, cx, cy, scale, shadow=True):
    """把像素画按 scale 放大后贴到 (cx, cy) 中心位置（阴影沿轮廓偏移）"""
    w, h = len(art[0]), len(art)
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    for y, row in enumerate(art):
        for x, ch in enumerate(row):
            if ch != ".":
                d.point((x, y), fill=pal[ch] + (255,))
    big = tile.resize((w * scale, h * scale), Image.NEAREST)
    if shadow:
        alpha = big.getchannel("A").point(lambda v: 90 if v > 10 else 0)
        sil = Image.new("RGBA", big.size, (0, 0, 0, 0))
        sil.putalpha(alpha)
        img.alpha_composite(sil, (cx - big.width // 2 + scale // 2,
                                  cy - big.height // 2 + scale // 2))
    img.alpha_composite(big, (cx - big.width // 2, cy - big.height // 2))


def draw_text(img, title, sub, cy, title_size=64, sub_size=34):
    """垂直排列的标题+副标题（用于方版），水平居中"""
    w = img.width
    d = ImageDraw.Draw(img)
    f1 = _font(title_size)
    f2 = _font(sub_size, bold=False)
    box = d.textbbox((0, 0), title, font=f1)
    tw, tbottom = box[2] - box[0], box[3]
    x = (w - tw) // 2
    d.text((x + 3, cy + 3), title, font=f1, fill=(0, 0, 0, 160))
    d.text((x, cy), title, font=f1, fill=(255, 255, 255))
    d.rectangle((w // 2 - 90, cy + tbottom + 8, w // 2 + 90,
                 cy + tbottom + 11), fill=(255, 213, 79))
    box2 = d.textbbox((0, 0), sub, font=f2)
    x2 = (w - (box2[2] - box2[0])) // 2
    d.text((x2 + 2, cy + tbottom + 22), sub, font=f2, fill=(0, 0, 0, 140))
    d.text((x2, cy + tbottom + 20), sub, font=f2, fill=(255, 224, 130))


def build(name, w, h, top, bottom, title, sub, seed):
    img = vgrad(w, h, top, bottom).convert("RGBA")
    draw_stars(img, 70, seed)
    draw_blocks(img, 14, seed + 1)

    if h >= w:  # 方版：口袋居中偏上，文字在下方
        cx, cy = w // 2, int(h * 0.40)
        scale = h // 30
        draw_glow(img, cx, cy, scale * 14)
        paste_art(img, POCKET_ART, POCKET_PAL, cx, cy, scale)
        for i, (art, pal) in enumerate(ITEMS):
            ang = [(-1, -0.62), (1, -0.58), (-1.15, 0.52), (1.15, 0.58)][i]
            paste_art(img, art, pal, int(cx + ang[0] * w * 0.36),
                      int(cy + ang[1] * h * 0.24), scale // 3)
        draw_text(img, title, sub, int(h * 0.74), title_size=h // 13,
                  sub_size=h // 26)
    else:       # 横版：口袋偏左，文字在右侧
        cx, cy = int(w * 0.27), int(h * 0.46)
        scale = h // 26
        draw_glow(img, cx, cy, scale * 15)
        paste_art(img, POCKET_ART, POCKET_PAL, cx, cy, scale)
        for i, (art, pal) in enumerate(ITEMS):
            pos = [(-0.30, -0.42), (0.34, -0.36), (-0.34, 0.40), (0.36, 0.34)][i]
            paste_art(img, art, pal, int(cx + pos[0] * scale * 16),
                      int(cy + pos[1] * scale * 16), max(scale // 3, 4))
        f1 = _font(h // 9)
        f2 = _font(h // 17, bold=False)
        d = ImageDraw.Draw(img)
        # 右栏中心：保证长副标题不出画布
        left, right = int(w * 0.52), w - 24
        rcx = (left + right) // 2
        tb = d.textbbox((0, 0), title, font=f1)
        sb = d.textbbox((0, 0), sub, font=f2)
        tx = rcx - (tb[2] - tb[0]) // 2
        sx = rcx - (sb[2] - sb[0]) // 2
        ty = int(h * 0.30)
        d.text((tx + 3, ty + 3), title, font=f1, fill=(0, 0, 0, 160))
        d.text((tx, ty), title, font=f1, fill=(255, 255, 255))
        d.rectangle((rcx - 100, ty + tb[3] + 10, rcx + 100, ty + tb[3] + 13),
                    fill=(255, 213, 79))
        sy = ty + tb[3] + 26
        d.text((sx + 2, sy + 2), sub, font=f2, fill=(0, 0, 0, 140))
        d.text((sx, sy), sub, font=f2, fill=(255, 224, 130))

    path = os.path.join(OUT, name)
    img.convert("RGB").save(path, "PNG")
    print("输出:", path, "(%dx%d)" % (w, h))


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    for i, task in enumerate(TASKS):
        build(*task, seed=100 + i * 17)
    print("全部完成，输出目录:", OUT)


if __name__ == "__main__":
    main()
