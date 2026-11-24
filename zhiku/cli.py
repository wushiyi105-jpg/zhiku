"""命令行入口：python -m zhiku <子命令>。"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, answer, store
from .llm import LLMError
from .text import DocError, read_document

DEFAULT_DB = os.path.join("data", "zhiku.db")


def _conn(args):
    return store.connect(args.db)


def cmd_add(args) -> int:
    conn = _conn(args)
    ok = 0
    for path in args.paths:
        try:
            title, text = read_document(path)
            if args.title and len(args.paths) == 1:
                title = args.title
            doc_id, n = store.add_document(
                conn,
                title=title,
                source=os.path.abspath(path),
                text=text,
                size=args.size,
                overlap=args.overlap,
                replace=not args.no_replace,
            )
            print(f"✓ [{doc_id}] {title} —— {len(text)} 字，切成 {n} 段")
            ok += 1
        except (DocError, ValueError, OSError) as e:
            print(f"✗ {path}：{e}", file=sys.stderr)
    if ok:
        s = store.stats(conn)
        print(f"\n库里现在有 {s['docs']} 篇文档、{s['chunks']} 段、{s['chars']} 字。")
    return 0 if ok else 1


def cmd_ask(args) -> int:
    conn = _conn(args)
    try:
        result = answer.ask(
            conn, args.question, top_k=args.top, min_score=args.min_score
        )
    except LLMError as e:
        print(f"模型调用失败：{e}", file=sys.stderr)
        print("检查一下 .env 里的 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL。", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({k: v for k, v in result.items() if k != "hits"}, ensure_ascii=False, indent=2))
    else:
        print(answer.format_terminal(result))

    if not result["insufficient"]:
        store.log_question(conn, args.question, result["answer"], [c["n"] for c in result["cites"]])
    return 0


def cmd_list(args) -> int:
    conn = _conn(args)
    docs = store.list_documents(conn)
    if not docs:
        print("库是空的，先 `python -m zhiku add 你的文件.md`。")
        return 0
    for d in docs:
        print(f"[{d['id']}] {d['title']}  {d['chars']} 字 / {d['n_chunks']} 段  {d['added_at']}")
        print(f"     {d['source']}")
    return 0


def cmd_rm(args) -> int:
    conn = _conn(args)
    n = store.remove_document(conn, args.key)
    print(f"删除了 {n} 篇文档。" if n else "没找到对应文档。")
    return 0 if n else 1


def cmd_stats(args) -> int:
    conn = _conn(args)
    s = store.stats(conn)
    print(f"文档 {s['docs']} 篇 · 片段 {s['chunks']} 段 · 正文 {s['chars']} 字 · 累计问答 {s['questions']} 次")
    return 0


def cmd_history(args) -> int:
    conn = _conn(args)
    for q in store.recent_questions(conn, args.limit):
        print(f"[{q['asked_at']}] {q['question']}")
        print(f"    引用 {q['cites'] or '无'} · {q['answer'][:80].replace(chr(10), ' ')}…")
    return 0


def cmd_serve(args) -> int:
    from .web import serve

    conn = _conn(args)
    print(f"知库 Web：http://127.0.0.1:{args.port}  （Ctrl+C 停）")
    serve(conn, host=args.host, port=args.port, config=None)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="zhiku",
        description="把一堆文档丢进本地库，问它问题，答案带出处。",
    )
    p.add_argument("--db", default=DEFAULT_DB, help=f"SQLite 路径（默认 {DEFAULT_DB}）")
    p.add_argument("--version", action="version", version=f"zhiku {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add", help="导入文档（txt/md/html/csv）")
    add.add_argument("paths", nargs="+")
    add.add_argument("--title", help="标题（只在导单篇时生效）")
    add.add_argument("--size", type=int, default=700, help="每段字符数")
    add.add_argument("--overlap", type=int, default=80, help="段间重叠字符数")
    add.add_argument("--no-replace", action="store_true", help="同路径已导入时报错而不是覆盖")
    add.set_defaults(func=cmd_add)

    ask = sub.add_parser("ask", help="提问")
    ask.add_argument("question")
    ask.add_argument("--top", type=int, default=6, help="检索几段材料")
    ask.add_argument("--min-score", type=float, default=0.0, help="低于这个分数不用（默认不过滤）")
    ask.add_argument("--json", action="store_true", help="输出 JSON")
    ask.set_defaults(func=cmd_ask)

    ls = sub.add_parser("list", help="看库里有啥")
    ls.set_defaults(func=cmd_list)

    rm = sub.add_parser("rm", help="删一篇（按 id 或路径）")
    rm.add_argument("key")
    rm.set_defaults(func=cmd_rm)

    st = sub.add_parser("stats", help="统计")
    st.set_defaults(func=cmd_stats)

    h = sub.add_parser("history", help="最近的问答")
    h.add_argument("--limit", type=int, default=10)
    h.set_defaults(func=cmd_history)

    sv = sub.add_parser("serve", help="起 Web 界面")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8765)
    sv.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
