"""检索 + 作答：先 BM25 捞片段，再让模型带着片段回答，最后回查引用。

模型的自由度被压得很低：它只能看给定的几段材料，每个结论必须挂 [n]，
材料里没有就直说没有。好处是答案可核对——点一下 [n] 就能跳回原文那一行。
"""

from __future__ import annotations

import re

from . import llm
from .bm25 import BM25Index
from .text import token_set

CITE_RE = re.compile(r"\[(\d{1,2})\]")
INSUFFICIENT = "INSUFFICIENT"

SYSTEM_PROMPT = """你是一个只依据给定材料回答问题的助理。规则：

1. 只能使用【材料】里的内容，不许用自己的常识补全，也不许猜测。
2. 每个结论后面必须紧跟引用编号，例如：报销需要在 15 天内提交 [2]。
3. 如果材料里没有能回答这个问题的内容，只输出 INSUFFICIENT 这一个词，不要解释。
4. 如果几段材料互相矛盾，直接指出矛盾在哪，并分别标注引用。
5. 用中文回答，先给结论再给依据，不要重复材料原文的长句。"""


def build_messages(question: str, hits: list[dict]) -> list[dict]:
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(f"[{i}] 来源：{h['title']}\n{h['text']}")
    user = "【材料】\n" + "\n\n".join(blocks) + f"\n\n【问题】{question}\n\n按要求作答。"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def retrieve(conn, question: str, top_k: int = 6, min_score: float = 0.0) -> list[dict]:
    from .store import all_chunks

    chunks = all_chunks(conn)
    if not chunks:
        return []
    index = BM25Index(chunks)
    return index.search(question, top_k=top_k, min_score=min_score)


def ask(
    conn,
    question: str,
    config: dict | None = None,
    top_k: int = 6,
    min_score: float = 0.0,
) -> dict:
    """完整问答链路，返回可直接序列化的结果。"""
    hits = retrieve(conn, question, top_k=top_k, min_score=min_score)
    if not hits:
        return {
            "question": question,
            "answer": "资料库里没有找到相关内容。可以先 `add` 几篇文档，或者换个说法再问。",
            "insufficient": True,
            "cites": [],
            "hits": [],
        }

    text = llm.chat(
        build_messages(question, hits),
        config=config,
        temperature=0.2,
        max_tokens=1200,
    ).strip()

    if text.strip().upper().startswith(INSUFFICIENT):
        return {
            "question": question,
            "answer": "材料里没有能回答这个问题的内容，我不编。",
            "insufficient": True,
            "cites": [],
            "hits": hits,
        }

    nums = sorted({int(n) for n in CITE_RE.findall(text)})
    valid = [n for n in nums if 1 <= n <= len(hits)]
    answer_text = text
    note = ""
    if not valid:
        note = "模型这段没标引用，已按最相关的一段挂上，请自行核对。"
        valid = [1]
    elif len(valid) != len(nums):
        note = "模型引用了不存在的编号，已剔除越界引用。"

    cites = []
    for n in valid:
        h = hits[n - 1]
        cites.append(
            {
                "n": n,
                "chunk_id": h["chunk_id"],
                "title": h["title"],
                "source": h["source"],
                "snippet": h["text"],
                "start": h["start"],
                "end": h["end"],
                "score": h.get("score", 0),
                "weak": _weak_cite(answer_text, h["text"], n),
            }
        )

    return {
        "question": question,
        "answer": answer_text,
        "insufficient": False,
        "cites": cites,
        "hits": hits,
        "note": note,
    }


def _weak_cite(answer: str, snippet: str, n: int) -> bool:
    """看看 [n] 前后的说法跟这段材料有没有词面上的交集。

    只用词面重合做粗筛，故意保守：重合太少才标 weak，不会因为同义改写就误伤。
    """
    around = answer
    idx = answer.find(f"[{n}]")
    if idx != -1:
        around = answer[max(0, idx - 60) : idx]
    a, b = token_set(around), token_set(snippet)
    a = {t for t in a if len(t) > 1}
    if not a:
        return False
    overlap = len(a & b) / len(a)
    return overlap < 0.15


def format_terminal(result: dict) -> str:
    """终端展示：答案 + 引用块。"""
    lines = [result["answer"].strip(), ""]
    if result.get("note"):
        lines.append(f"（{result['note']}）")
        lines.append("")
    for c in result.get("cites", []):
        flag = "  ⚠ 词面对不上，建议核对" if c.get("weak") else ""
        lines.append(f"[{c['n']}] {c['title']} · 第 {c['start']}-{c['end']} 字{flag}")
        preview = c["snippet"].replace("\n", " ")
        lines.append(f"    {preview[:120]}{'…' if len(preview) > 120 else ''}")
    return "\n".join(lines).strip()
