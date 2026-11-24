import json
import threading
import unittest
import urllib.request
from unittest import mock

from zhiku import store
from zhiku.web import make_server

import os
import tempfile


class WebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.conn = store.connect(os.path.join(cls.tmp.name, "w.db"))
        cls.httpd = make_server(cls.conn, port=0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.conn.close()
        cls.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def post(self, path, obj):
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(obj, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def test_index_page(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as r:
            html = r.read().decode("utf-8")
        self.assertIn("知库", html)
        self.assertIn("/api/ask", html)

    def test_add_and_ask_flow(self):
        j = self.post("/api/add", {"title": "差旅", "text": "差旅住宿一线城市 500 元以内。"})
        self.assertEqual(j["title"], "差旅")
        self.assertGreater(j["chunks"], 0)

        with mock.patch("zhiku.llm.chat", return_value="一线城市 500 元以内 [1]。"):
            r = self.post("/api/ask", {"question": "一线城市住宿标准"})
        self.assertFalse(r["insufficient"])
        self.assertEqual(len(r["cites"]), 1)

    def test_docs_endpoint(self):
        j = self.get("/api/docs")
        self.assertIn("docs", j)
        self.assertIn("stats", j)
        self.assertGreaterEqual(j["stats"]["docs"], 1)

    def test_rm_endpoint(self):
        j = self.post("/api/add", {"title": "临时", "text": "这条待会删掉。"})
        self.post("/api/rm", {"id": j["id"]})
        docs = self.get("/api/docs")["docs"]
        self.assertNotIn("临时", [d["title"] for d in docs])

    def test_bad_payload(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/add", {"title": "空", "text": " "})
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
