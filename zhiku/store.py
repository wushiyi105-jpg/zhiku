"""本地存储：SQLite 一张 documents 表 + 一张 chunks 表。

为什么不存倒排：这套东西的定位是"一个人自己的资料库"，
几百到几千个 chunk 全量读进内存算 BM25 是毫秒级的，
省掉一层索引维护，也就少了一堆能出错的地方。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime

from .text import chunk_text

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    title     TEXT NOT NULL,
    source    TEXT NOT NULL UNIQUE,
    chars     INTEGER NOT NULL DEFAULT 0,
    n_chunks  INTEGER NOT NULL DEFAULT 0,
    added_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id  INTEGER NOT NULL,
    ord     INTEGER NOT NULL,
    start   INTEGER NOT NULL,
    end     INTEGER NOT NULL,
    text    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS questions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    question  TEXT NOT NULL,
    answer    TEXT NOT NULL,
    cites     TEXT NOT NULL,
    asked_at  TEXT NOT NULL
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    parent = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add_document(
    conn: sqlite3.Connection,
    title: str,
    source: str,
    text: str,
    size: int = 700,
    overlap: int = 80,
    replace: bool = True,
) -> tuple[int, int]:
    """导入一篇文档，返回 (doc_id, chunk 数)。

    同一个 source 再导入一次时默认替换旧版本，免得改了文件却检索到旧内容。
    """
    old = conn.execute("SELECT id FROM documents WHERE source = ?", (source,)).fetchone()
    if old and not replace:
        raise ValueError(f"已存在同源文档：{source}（加 --replace 覆盖）")
    if old:
        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (old["id"],))
        conn.execute("DELETE FROM documents WHERE id = ?", (old["id"],))

    pieces = chunk_text(text, size=size, overlap=overlap)
    if not pieces:
        raise ValueError(f"文档没有可用正文：{source}")

    cur = conn.execute(
        "INSERT INTO documents(title, source, chars, n_chunks, added_at) VALUES (?,?,?,?,?)",
        (title, source, len(text), len(pieces), _now()),
    )
    doc_id = int(cur.lastrowid)
    conn.executemany(
        "INSERT INTO chunks(doc_id, ord, start, end, text) VALUES (?,?,?,?,?)",
        [(doc_id, i, p["start"], p["end"], p["text"]) for i, p in enumerate(pieces)],
    )
    conn.commit()
    return doc_id, len(pieces)


def all_chunks(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.id AS chunk_id, c.doc_id, c.ord, c.start, c.end, c.text, d.title, d.source
        FROM chunks c JOIN documents d ON d.id = c.doc_id
        ORDER BY c.doc_id, c.ord
        """
    ).fetchall()
    return [dict(r) for r in rows]


def list_documents(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, source, chars, n_chunks, added_at FROM documents ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def remove_document(conn: sqlite3.Connection, key: str) -> int:
    """按 id 或 source 删除，返回删掉的文档数。"""
    rows = conn.execute("SELECT id FROM documents WHERE source = ?", (key,)).fetchall()
    if not rows and key.isdigit():
        rows = conn.execute("SELECT id FROM documents WHERE id = ?", (int(key),)).fetchall()
    for r in rows:
        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (r["id"],))
        conn.execute("DELETE FROM documents WHERE id = ?", (r["id"],))
    conn.commit()
    return len(rows)


def stats(conn: sqlite3.Connection) -> dict:
    docs = conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(chars),0) AS c FROM documents").fetchone()
    chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
    asked = conn.execute("SELECT COUNT(*) AS n FROM questions").fetchone()
    return {"docs": docs["n"], "chars": docs["c"], "chunks": chunks["n"], "questions": asked["n"]}


def log_question(conn: sqlite3.Connection, question: str, answer: str, cites: list[int]) -> None:
    conn.execute(
        "INSERT INTO questions(question, answer, cites, asked_at) VALUES (?,?,?,?)",
        (question, answer, ",".join(str(c) for c in cites), _now()),
    )
    conn.commit()


def recent_questions(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT id, question, answer, cites, asked_at FROM questions ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
