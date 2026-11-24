"""生成 assets/demo.gif：960×600 的终端风演示动图。

只用 Pillow（开发期依赖，不进 requirements）。跑法：
    python scripts/make_demo_gif.py
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 960, 600
BG = "#0b0f14"
BAR = "#161b22"
LINE = "#21262d"
GREEN = "#7ee787"
TEXT = "#c9d1d9"
DIM = "#8b949e"
BLUE = "#79c0ff"
YELLOW = "#e3b341"

FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"


def font(size: int):
    return ImageFont.truetype(FONT_PATH, size)


LINE_H = 26


def render(rows, cursor_row=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 标题栏
    d.rectangle([0, 0, W, 36], fill=BAR)
    for i, color in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        d.ellipse([16 + i * 22, 12, 28 + i * 22, 24], fill=color)
    d.text((92, 9), "zhiku — 本地知识库问答", font=font(15), fill=DIM)
    d.line([0, 36, W, 36], fill=LINE)

    y = 56
    for idx, (style, text) in enumerate(rows):
        color = {
            "cmd": GREEN,
            "out": TEXT,
            "dim": DIM,
            "cite": BLUE,
            "warn": YELLOW,
        }[style]
        d.text((28, y), text, font=font(17), fill=color)
        if cursor_row == idx:
            w = d.textlength(text, font=font(17))
            d.rectangle([28 + w + 4, y + 2, 28 + w + 13, y + 20], fill=GREEN)
        y += LINE_H
        if y > H - 18:
            break
    return img


# 每行：(样式, 文本)。cmd 行会做"逐字打出来"的效果。
SCRIPT = [
    ("cmd", "> python -m zhiku add samples/员工手册.md samples/云盘产品答疑.md"),
    ("out", "✓ [1] 青梧科技员工手册（2026 版） —— 1643 字，切成 3 段"),
    ("out", "✓ [2] 云盘产品答疑（客服内部版） —— 1153 字，切成 2 段"),
    ("out", "库里现在有 2 篇文档、5 段、2796 字。"),
    ("dim", ""),
    ("cmd", '> python -m zhiku ask "报销最晚多少天内必须提交？超过会怎样？"'),
    ("out", "结论：报销应在费用实际发生后 15 天内提交 [1]。"),
    ("out", "超过 30 天的单据，财务不再受理 [1]。"),
    ("dim", ""),
    ("cite", "[1] 青梧科技员工手册（2026 版） · 原文第 0–676 字"),
    ("dim", "    # 青梧科技员工手册（2026 版） …（按住 ctrl 点引用可跳回原文）"),
    ("dim", ""),
    ("cmd", '> python -m zhiku ask "团队版买了还能退款吗？怎么算钱？"'),
    ("out", "可以退，团队版需管理员发起并确认成员数据已导出 [2]。"),
    ("out", "7 天内且用量 <1GB 全额退；超 7 天按剩余月份比例退 [1][2]。"),
    ("cite", "[1] 云盘产品答疑 · 第 0–641 字   [2] 云盘产品答疑 · 第 561–1153 字"),
]
TAIL = [
    ("dim", ""),
    ("warn", "退出码 0 · 以上答案全部来自库里的原文，模型没有自由发挥。"),
]


def build():
    frames = []

    # 阶段一：两条命令逐字打出来
    typed = ""
    for ch in SCRIPT[0][1][::3]:
        typed += ch
        frames.append(render([("cmd", typed)], cursor_row=0))

    # 阶段二：命令输出逐行出现
    rows = [SCRIPT[0]]
    for row in SCRIPT[1:6]:
        rows = rows + [row]
        frames.append(render(rows))

    # 阶段三：第二次提问逐字打
    typed2 = ""
    for ch in SCRIPT[5][1][::3]:
        typed2 += ch
        rows_wo_last = rows[:-1]
        frames.append(render(rows_wo_last + [("cmd", typed2)], cursor_row=len(rows_wo_last)))

    # 阶段四：剩下逐行出
    rows = [SCRIPT[0]] + SCRIPT[1:]
    for i in range(6, len(SCRIPT)):
        shown = rows[: i + 1]
        frames.append(render(shown))

    # 阶段五：收尾停留
    full = rows + TAIL
    for _ in range(6):
        frames.append(render(full))

    frames = [f.quantize(colors=32, method=Image.MEDIANCUT) for f in frames]
    out = os.path.join("assets", "demo.gif")
    os.makedirs("assets", exist_ok=True)
    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=140,
        loop=0,
        optimize=True,
    )
    size = os.path.getsize(out)
    print(f"ok -> {out}  {len(frames)} 帧  {size/1024:.1f} KB")


if __name__ == "__main__":
    build()


