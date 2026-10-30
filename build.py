# -*- coding: utf-8 -*-
"""构建脚本（本机运行，不进游戏包）：
1. 生成口袋贴图 textures/items/pocket.png 与两个包的 pack_icon.png
2. 把行为包+资源包打包为 RandomPocket.mcaddon
用法: python build.py
"""

import os
import struct
import zlib
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
BEHAVIOR_DIR = os.path.join(BASE, "randompocket_behavior")
RESOURCE_DIR = os.path.join(BASE, "randompocket_resource")

# 调色板：o描边 b主体 l高光 d暗部 s绳扣 g金扣
PALETTE = {
    "o": (62, 39, 35, 255),
    "b": (121, 85, 72, 255),
    "l": (141, 110, 99, 255),
    "d": (93, 64, 55, 255),
    "s": (237, 224, 200, 255),
    "g": (253, 216, 53, 255),
}

# 已满状态的配色：整体偏红，金扣更亮
PALETTE_FULL = {
    "o": (60, 12, 12, 255),
    "b": (183, 28, 28, 255),
    "l": (239, 83, 80, 255),
    "d": (139, 0, 0, 255),
    "s": (255, 235, 59, 255),
    "g": (255, 193, 7, 255),
}

PIXART = [
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


def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))


def write_png(path, rows, palette=None):
    palette = palette or PALETTE
    h = len(rows)
    w = len(rows[0])
    raw = b""
    for row in rows:
        line = b"\x00"
        for ch in row:
            rgba = (0, 0, 0, 0) if ch == "." else palette[ch]
            line += bytes(rgba)
        raw += line
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(raw, 9))
    png += _chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    print("生成:", path)


def scale_rows(rows, factor):
    out = []
    for row in rows:
        for _ in range(factor):
            out.append("".join(ch * factor for ch in row))
    return out


def build_textures():
    for i, row in enumerate(PIXART):
        assert len(row) == 16, "第%d行长度不是16: %r" % (i, row)
    item_dir = os.path.join(RESOURCE_DIR, "textures", "items")
    if not os.path.isdir(item_dir):
        os.makedirs(item_dir)
    write_png(os.path.join(item_dir, "pocket.png"), PIXART)
    write_png(os.path.join(item_dir, "pocket_full.png"), PIXART, PALETTE_FULL)
    icon = scale_rows(PIXART, 4)  # 64x64 包图标
    write_png(os.path.join(BEHAVIOR_DIR, "pack_icon.png"), icon)
    write_png(os.path.join(RESOURCE_DIR, "pack_icon.png"), icon)


def build_addon():
    out = os.path.join(BASE, "RandomPocket.mcaddon")
    if os.path.exists(out):
        os.remove(out)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for folder in (BEHAVIOR_DIR, RESOURCE_DIR):
            for root, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fn in sorted(files):
                    full = os.path.join(root, fn)
                    arc = os.path.relpath(full, BASE).replace("\\", "/")
                    z.write(full, arc)
                    count += 1
    print("打包完成: %s (共 %d 个文件)" % (out, count))


BEHAVIOR_UUID = "89ffbf9e-73d8-4a02-9aa1-8fd7962edf45"
RESOURCE_UUID = "06f2ca7d-d7ff-474d-967d-507e9ef32ae7"


def _pack_version():
    import json
    with open(os.path.join(BEHAVIOR_DIR, "manifest.json"), "r", encoding="utf-8") as f:
        return json.load(f)["header"]["version"]


PACK_VERSION = _pack_version()


def _copytree(src, dst):
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel = os.path.relpath(root, src)
        target = os.path.join(dst, rel) if rel != "." else dst
        if not os.path.isdir(target):
            os.makedirs(target)
        for fn in files:
            with open(os.path.join(root, fn), "rb") as f:
                data = f.read()
            with open(os.path.join(target, fn), "wb") as f:
                f.write(data)


def build_pctest():
    """生成网易电脑版手动导入用的目录（路径A测试）"""
    import json as _json
    import shutil
    out = os.path.join(BASE, "pctest")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    _copytree(BEHAVIOR_DIR, os.path.join(out, "behavior_pack"))
    _copytree(RESOURCE_DIR, os.path.join(out, "resource_pack"))
    refs = [
        ("netease_world_behavior_packs.json", BEHAVIOR_UUID),
        ("netease_world_resource_packs.json", RESOURCE_UUID),
    ]
    for fn, uid in refs:
        data = [{"pack_id": uid, "version": PACK_VERSION}]
        with open(os.path.join(out, fn), "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
    print("已生成 pctest 目录（网易电脑版手动导入用）:", out)


def build_import_zip():
    """生成 MC Studio「本地导入」用的 zip（根目录为 behavior_pack + resource_pack）"""
    out = os.path.join(BASE, "RandomPocket.zip")
    if os.path.exists(out):
        os.remove(out)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, arc_root in ((BEHAVIOR_DIR, "behavior_pack"),
                                 (RESOURCE_DIR, "resource_pack")):
            for root, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fn in sorted(files):
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, folder).replace("\\", "/")
                    z.write(full, arc_root + "/" + rel)
                    count += 1
    print("已生成 MC Studio 导入包: %s (共 %d 个文件)" % (out, count))


def _rgba_rows_to_png(path, w, h, pixel_rows):
    """pixel_rows: list[bytearray]，每项长度 = w*4"""
    raw = b""
    for line in pixel_rows:
        raw += b"\x00" + bytes(line)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(raw, 6))
    png += _chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    print("生成:", path)


def _pixel_rgba(ch):
    return (0, 0, 0, 0) if ch == "." else PALETTE[ch]


def build_promo():
    """生成平台「图片信息」占位素材"""
    out_dir = os.path.join(BASE, "promo")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    # 1) 组件图标 512x512（口袋等比放大）
    size = 512
    scale = size // len(PIXART[0])
    rows = []
    for row in PIXART:
        line = bytearray()
        for ch in row:
            px = _pixel_rgba(ch)
            line += bytes(px) * scale
        for _ in range(scale):
            rows.append(bytearray(line))
    _rgba_rows_to_png(os.path.join(out_dir, "icon_512.png"), size, size, rows)

    # 2) 封面 1280x720（深色背景 + 居中的口袋）
    w, h = 1280, 720
    pocket_scale = 24
    pw = len(PIXART[0]) * pocket_scale
    ph = len(PIXART) * pocket_scale
    ox, oy = (w - pw) // 2, (h - ph) // 2
    bg = (30, 30, 30, 255)
    rows = []
    for y in range(h):
        line = bytearray(bytes(bg) * w)
        if oy <= y < oy + ph:
            src_row = PIXART[(y - oy) // pocket_scale]
            for x in range(pw):
                ch = src_row[x // pocket_scale]
                if ch == ".":
                    continue
                px = _pixel_rgba(ch)
                start = (ox + x) * 4
                line[start:start + 4] = bytes(px)
        rows.append(line)
    _rgba_rows_to_png(os.path.join(out_dir, "cover_1280x720.png"), w, h, rows)


if __name__ == "__main__":
    build_textures()
    build_addon()
    build_pctest()
    build_import_zip()
    build_promo()
