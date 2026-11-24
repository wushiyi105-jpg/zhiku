"""Web 入口：标准库 http.server，一个页面搞定导入和提问。

没有前端框架，也没有打包工具——页面就是一个字符串，
改样式直接改 CSS。少一层构建，就少一处能坏的地方。
"""

from __future__ import annotations

import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import answer, store
from .llm import LLMError

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>知库 · 本地知识库问答</title>
<style>
  :root { --ink:#1c1f23; --muted:#6b7280; --line:#e6e8eb; --bg:#f7f8fa; --accent:#2f6f4f; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         color:var(--ink); background:var(--bg); }
  header { padding:18px 28px; border-bottom:1px solid var(--line); background:#fff;
           display:flex; align-items:baseline; gap:14px; }
  header h1 { margin:0; font-size:20px; letter-spacing:1px; }
  header span { color:var(--muted); font-size:13px; }
  main { display:grid; grid-template-columns: 300px 1fr; gap:0; min-height: calc(100vh - 61px); }
  aside { border-right:1px solid var(--line); background:#fff; padding:18px; overflow:auto; }
  aside h2 { font-size:13px; color:var(--muted); font-weight:500; margin:0 0 10px; }
  .doc { padding:8px 10px; border-radius:8px; margin-bottom:6px; font-size:13px; cursor:pointer;
         border:1px solid transparent; }
  .doc:hover { background:#f2f6f4; border-color:#d8e6de; }
  .doc b { display:block; font-weight:600; }
  .doc small { color:var(--muted); }
  .addbox { margin-top:18px; border-top:1px solid var(--line); padding-top:14px; }
  textarea, input { width:100%; font:inherit; font-size:13px; padding:8px; border:1px solid var(--line);
                    border-radius:8px; background:#fff; color:var(--ink); }
  textarea { resize:vertical; }
  button { font:inherit; font-size:13px; padding:7px 14px; border:0; border-radius:8px;
           background:var(--accent); color:#fff; cursor:pointer; }
  button.ghost { background:#eef2ef; color:var(--accent); }
  button:disabled { opacity:.5; cursor:default; }
  section { padding:24px 32px; display:flex; flex-direction:column; gap:16px; }
  .ask { display:flex; gap:10px; }
  .bubble { background:#fff; border:1px solid var(--line); border-radius:12px; padding:16px 18px;
            font-size:15px; line-height:1.85; white-space:pre-wrap; }
  .bubble.user { background:#eef4f0; border-color:#dbe8e0; }
  sup.cite { color:var(--accent); cursor:pointer; font-size:12px; padding:0 1px; font-weight:600; }
  sup.cite:hover { text-decoration:underline; }
  .cites { display:flex; flex-direction:column; gap:8px; }
  .citecard { background:#fff; border:1px solid var(--line); border-left:3px solid var(--accent);
              border-radius:8px; padding:10px 12px; font-size:13px; }
  .citecard .meta { color:var(--muted); margin-bottom:4px; }
  .citecard .warn { color:#a15c00; }
  .citecard pre { margin:6px 0 0; white-space:pre-wrap; font:inherit; color:#374151; }
  .empty { color:var(--muted); font-size:14px; padding:30px 0; }
  .hint { color:var(--muted); font-size:12px; margin-top:6px; }
  #status { color:var(--muted); font-size:12px; min-height:16px; }
</style>
</head>
<body>
<header>
  <h1>知库</h1>
  <span>本地知识库 · 答案带出处 · 模型 deepseek-flash</span>
</header>
<main>
<aside>
  <h2>库里的文档 <span id="stats"></span></h2>
  <div id="docs"></div>
  <div class="addbox">
    <h2>导入</h2>
    <input id="title" placeholder="标题（可留空）">
    <textarea id="text" rows="4" placeholder="粘贴正文……" style="margin-top:6px"></textarea>
    <div style="display:flex; gap:8px; margin-top:8px">
      <button onclick="addText()">存进库</button>
      <button class="ghost" onclick="document.getElementById('file').click()">选文件</button>
      <input id="file" type="file" accept=".txt,.md,.markdown,.html,.htm,.csv" multiple hidden onchange="addFiles(this)">
    </div>
    <div class="hint">支持 txt / md / html / csv；同一路径再导入会覆盖旧版本。</div>
  </div>
</aside>
<section>
  <div class="ask">
    <input id="q" placeholder="问点什么，比如：报销最晚几天内提交？" onkeydown="if(event.key==='Enter')ask()">
    <button id="askbtn" onclick="ask()">问</button>
  </div>
  <div id="status"></div>
  <div id="thread"></div>
</section>
</main>
<script>
const $ = id => document.getElementById(id);
const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

async function api(path, body) {
  const r = await fetch(path, body ? {method:'POST', headers:{'Content-Type':'application/json'},
                                       body: JSON.stringify(body)} : {});
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

async function loadDocs() {
  const j = await api('/api/docs');
  $('stats').textContent = `(${j.stats.docs} 篇 / ${j.stats.chunks} 段)`;
  $('docs').innerHTML = j.docs.length ? j.docs.map(d =>
    `<div class="doc" onclick="rm(${d.id}, this)"><b>${esc(d.title)}</b>
     <small>${d.chars} 字 · ${d.n_chunks} 段 · ${esc(d.added_at)}</small></div>`).join('')
    : '<div class="empty">还空着。左边贴一段正文，或者选个文件。</div>';
}

async function rm(id) {
  if (!confirm('从库里删掉这篇？')) return;
  await api('/api/rm', {id});
  loadDocs();
}

async function addText() {
  const text = $('text').value.trim();
  if (!text) return;
  $('status').textContent = '切块入库…';
  try {
    const j = await api('/api/add', {title: $('title').value.trim() || '未命名', text});
    $('status').textContent = `已入库：${j.title}，${j.chunks} 段`;
    $('text').value = ''; $('title').value = '';
    loadDocs();
  } catch (e) { $('status').textContent = '失败：' + e.message; }
}

async function addFiles(input) {
  for (const f of input.files) {
    const text = await f.text();
    $('status').textContent = `导入 ${f.name}…`;
    try {
      await api('/api/add', {title: f.name, text});
    } catch (e) { $('status').textContent = '失败：' + e.message; }
  }
  input.value = '';
  $('status').textContent = '文件导入完成。';
  loadDocs();
}

function renderAnswer(j) {
  const body = esc(j.answer).replace(/\\[(\\d+)\\]/g, (m, n) =>
    `<sup class="cite" onclick="showCite(${n})">[${n}]</sup>`);
  const cards = j.cites.map(c => `
    <div class="citecard" id="cite-${c.n}">
      <div class="meta">[${c.n}] ${esc(c.title)} · 原文第 ${c.start}–${c.end} 字
        ${c.weak ? '<span class="warn">· 词面对不上，建议核对</span>' : ''}</div>
      <pre>${esc(c.snippet.slice(0, 220))}${c.snippet.length > 220 ? '…' : ''}</pre>
    </div>`).join('');
  return `<div class="bubble user">${esc(j.question)}</div>
          <div class="bubble">${body}</div>
          ${j.note ? `<div class="status" style="color:#a15c00">${esc(j.note)}</div>` : ''}
          <div class="cites">${cards}</div>`;
}

function showCite(n) {
  const el = $('cite-' + n);
  if (el) el.scrollIntoView({behavior:'smooth', block:'center'});
}

async function ask() {
  const q = $('q').value.trim();
  if (!q) return;
  $('askbtn').disabled = true;
  $('status').textContent = '检索 + 作答…';
  try {
    const j = await api('/api/ask', {question: q});
    $('thread').innerHTML = renderAnswer(j) + $('thread').innerHTML;
    $('q').value = '';
    $('status').textContent = '';
  } catch (e) { $('status').textContent = '失败：' + e.message; }
  $('askbtn').disabled = false;
}

loadDocs();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    conn = None  # 由 serve() 注入
    lock = threading.Lock()  # sqlite 连接跨线程使用，读写都得排队
    server_version = "zhiku/0.1"

    def log_message(self, fmt, *args):  # 安静一点，别把每个请求都喷到终端
        pass

    # ---------- 路由 ----------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if parsed.path == "/api/docs":
            with self.lock:
                docs = store.list_documents(self.conn)
                stats = store.stats(self.conn)
            return self._json({"docs": docs, "stats": stats})
        if parsed.path == "/api/history":
            with self.lock:
                items = store.recent_questions(self.conn, 20)
            return self._json({"items": items})
        return self._json({"error": "not found"}, status=404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            body = self._read_json()
        except ValueError as e:
            return self._json({"error": str(e)}, status=400)

        if parsed.path == "/api/add":
            title = (body.get("title") or "").strip() or "未命名"
            text = body.get("text") or ""
            if not text.strip():
                return self._json({"error": "正文是空的"}, status=400)
            try:
                with self.lock:
                    doc_id, n = store.add_document(
                        self.conn, title=title, source="web:" + title, text=text
                    )
            except ValueError as e:
                return self._json({"error": str(e)}, status=400)
            return self._json({"id": doc_id, "title": title, "chunks": n})

        if parsed.path == "/api/rm":
            with self.lock:
                n = store.remove_document(self.conn, str(body.get("id") or ""))
            return self._json({"removed": n})

        if parsed.path == "/api/ask":
            q = (body.get("question") or "").strip()
            if not q:
                return self._json({"error": "问题是空的"}, status=400)
            try:
                with self.lock:
                    result = answer.ask(self.conn, q, top_k=int(body.get("top") or 6))
            except LLMError as e:
                return self._json({"error": f"模型调用失败：{e}"}, status=502)
            if not result["insufficient"]:
                with self.lock:
                    store.log_question(self.conn, q, result["answer"], [c["n"] for c in result["cites"]])
            return self._json({k: v for k, v in result.items() if k != "hits"})

        return self._json({"error": "not found"}, status=404)

    # ---------- 工具 ----------
    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 8 * 1024 * 1024:
            raise ValueError("请求太大（>8MB），先切成小文件")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败：{e}") from e

    def _json(self, obj, status: int = 200):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send(self, status: int, payload: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def make_server(conn, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    handler = type(
        "BoundHandler",
        (Handler,),
        {"conn": conn, "lock": threading.Lock()},
    )
    return ThreadingHTTPServer((host, port), handler)


def serve(conn, host: str = "127.0.0.1", port: int = 8765, config: dict | None = None):
    httpd = make_server(conn, host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停了。")
    finally:
        httpd.server_close()
