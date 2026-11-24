"""读入与切块：把一篇文档变成能被检索的小段，并给出中文分词。

整个项目零第三方依赖，所以这里的分词不是 jieba，而是"中文单字 + 二元组"。
效果肯定不如分词器，但对检索够用：问"报销流程"时，包含"报销/流程"的段落会被排到前面。
"""

from __future__ import annotations

import html
import os
import re

# 支持的纯文本类扩展名（PDF/Word 建议先另存为 txt 或 md）
TEXT_EXTS = {".txt", ".md", ".markdown", ".html", ".htm", ".csv", ".log"}

_CJK = r"\u4e00-\u9fff"
_TOKEN_RE = re.compile(rf"[{_CJK}]+|[a-zA-Z][a-zA-Z0-9_+#.-]*|\d+[.,]?\d*")


class DocError(Exception):
    """文档读不进来。"""


def read_document(path: str) -> tuple[str, str]:
    """读一个文件，返回 (标题, 正文)。"""
    if not os.path.isfile(path):
        raise DocError(f"文件不存在：{path}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in TEXT_EXTS:
        raise DocError(f"暂不支持 {ext or '无扩展名'} 文件，先转成 .txt 或 .md：{path}")

    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()

    if ext in {".html", ".htm"}:
        raw = strip_html(raw)

    title = os.path.basename(path)
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            title = s.lstrip("#").strip() or title
        break

    return title, clean_text(raw)


def strip_html(raw: str) -> str:
    """去掉脚本、样式和标签，只留正文文字。"""
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return html.unescape(raw)


def clean_text(raw: str) -> str:
    """统一空白：去掉行尾空格、压缩连续空行（保留段落分隔）。"""
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in raw.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, size: int = 700, overlap: int = 80) -> list[dict]:
    """按段落拼块，块长不超过 size，块间保留 overlap 个字符的重叠。

    返回 [{"text": ..., "start": ..., "end": ...}]，start/end 是原文偏移，
    Web 端靠它把引用跳回原文。
    """
    if size <= 0:
        raise ValueError("size 必须为正")
    if overlap >= size:
        raise ValueError("overlap 必须小于 size")

    text = clean_text(text)
    if not text:
        return []

    # 先按空行切段，再按段落长度累积
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[dict] = []
    buf = ""
    buf_start = 0
    cursor = 0

    for para in paras:
        pos = text.find(para, cursor)
        if pos == -1:
            pos = cursor
        cursor = pos + len(para)

        if len(para) > size:
            # 超长段落先冲掉缓冲，再硬切
            if buf:
                chunks.append(_mk(buf, buf_start, text))
                buf = ""
            step = size - overlap
            for i in range(0, len(para), step):
                piece = para[i : i + size]
                if piece.strip():
                    chunks.append(_mk(piece, pos + i, text))
                if i + size >= len(para):
                    break
            continue

        if not buf:
            buf, buf_start = para, pos
        elif len(buf) + 2 + len(para) <= size:
            buf = buf + "\n\n" + para
        else:
            chunks.append(_mk(buf, buf_start, text))
            # 重叠：从上一块末尾取 overlap 个字符接在新块前面
            tail = buf[-overlap:] if overlap else ""
            buf = (tail + "\n\n" + para) if tail else para
            buf_start = max(pos - len(tail), 0) if tail else pos

    if buf.strip():
        chunks.append(_mk(buf, buf_start, text))
    return chunks


def _mk(piece: str, start: int, full: str) -> dict:
    piece = piece.strip()
    s = full.find(piece[:40], max(start - 10, 0)) if piece else -1
    if s == -1:
        s = max(start, 0)
    return {"text": piece, "start": s, "end": s + len(piece)}


def tokenize(s: str) -> list[str]:
    """中文：单字 + 相邻二元组；英文/数字：整词小写。"""
    tokens: list[str] = []
    for m in _TOKEN_RE.finditer(s or ""):
        piece = m.group(0)
        if re.fullmatch(rf"[{_CJK}]+", piece):
            if len(piece) == 1:
                tokens.append(piece)
            else:
                tokens.extend(piece)
                tokens.extend(piece[i : i + 2] for i in range(len(piece) - 1))
        else:
            tokens.append(piece.lower())
    return tokens


def token_set(s: str) -> set[str]:
    return set(tokenize(s))
