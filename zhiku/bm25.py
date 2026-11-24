"""BM25 检索：纯 Python，几十行，不依赖任何向量库。

有意做了两点取舍：
1. 中文用「单字 + 二元组」当词项，"报销流程" 会同时命中 "报销/销流/流程"，
   比按空格切词稳一些；
2. 单字权重压到二元组的 0.3，否则 "的/是/在" 这类字会把分数撑起来。
"""

from __future__ import annotations

import math
from collections import Counter

from .text import tokenize

K1 = 1.5
B = 0.75
UNIGRAM_WEIGHT = 0.3


def _weighted_counts(s: str) -> Counter:
    counts: Counter = Counter()
    for tok in tokenize(s):
        counts[tok] += UNIGRAM_WEIGHT if len(tok) == 1 else 1.0
    return counts


class BM25Index:
    """对一组 chunk 建立内存索引。"""

    def __init__(self, docs: list[dict]):
        self.docs = docs
        self.tfs: list[Counter] = []
        self.lens: list[float] = []
        self.df: Counter = Counter()

        for d in docs:
            counts = _weighted_counts(d.get("text", ""))
            self.tfs.append(counts)
            self.lens.append(sum(counts.values()) or 1.0)
            for term in counts:
                self.df[term] += 1

        self.n = len(docs)
        self.avgdl = (sum(self.lens) / self.n) if self.n else 0.0

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1.0 + (self.n - df + 0.5) / (df + 0.5))

    def score(self, idx: int, q_terms: set[str]) -> float:
        tf = self.tfs[idx]
        dl = self.lens[idx]
        s = 0.0
        for term in q_terms:
            f = tf.get(term, 0.0)
            if not f:
                continue
            s += self.idf(term) * (f * (K1 + 1)) / (f + K1 * (1 - B + B * dl / self.avgdl))
        return s

    def search(self, query: str, top_k: int = 6, min_score: float = 0.0) -> list[dict]:
        """返回 [{"score","text","start","end","doc_id","title"}]，按分数降序。

        过滤规则：查询里的二元组一个都没命中，就不算相关——单字命中的一律扔掉，
        否则「的」「不」这类字会把整库都捞出来。
        """
        q_terms = {t for t in tokenize(query)}
        if not q_terms or not self.n:
            return []

        bigrams = [t for t in q_terms if len(t) > 1]
        hits = []
        for i, doc in enumerate(self.docs):
            s = self.score(i, q_terms)
            if s <= 0:
                continue
            covered = sum(1 for t in bigrams if self.tfs[i].get(t))
            if bigrams and covered == 0:
                continue
            cover = covered / len(bigrams) if bigrams else 0.0
            hits.append((s * (0.6 + 0.4 * cover), doc))

        hits.sort(key=lambda x: x[0], reverse=True)
        out = []
        for s, doc in hits[:top_k]:
            if s < min_score:
                continue
            out.append({**doc, "score": round(s, 4)})
        return out


def highlight(text: str, query: str, width: int = 40) -> str:
    """把命中的词附近截一段出来，给终端预览用。"""
    terms = [t for t in tokenize(query) if len(t) > 1 and t in text]
    if not terms:
        return text[: width * 2].replace("\n", " ")
    pos = min(text.find(t) for t in terms if text.find(t) >= 0) if any(text.find(t) >= 0 for t in terms) else 0
    start = max(0, pos - width)
    return ("…" if start else "") + text[start : start + width * 2].replace("\n", " ")
