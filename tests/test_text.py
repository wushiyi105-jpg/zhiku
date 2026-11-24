import unittest

from zhiku.text import chunk_text, clean_text, read_document, strip_html, tokenize
import os


class TestClean(unittest.TestCase):
    def test_collapse_blank_lines(self):
        self.assertEqual(clean_text("a\n\n\n\nb\n  \n"), "a\n\nb")

    def test_strip_html(self):
        raw = "<html><style>.a{}</style><body><h1>报销</h1><p>15 天内提交</p></body></html>"
        out = strip_html(raw)
        self.assertIn("报销", out)
        self.assertIn("15 天内提交", out)
        self.assertNotIn("<h1>", out)
        self.assertNotIn(".a{}", out)


class TestTokenize(unittest.TestCase):
    def test_cjk_bigram(self):
        toks = tokenize("报销流程")
        self.assertIn("报", toks)
        self.assertIn("报销", toks)
        self.assertIn("流程", toks)

    def test_english_word(self):
        self.assertIn("api", tokenize("API Key"))

    def test_number(self):
        self.assertIn("30", tokenize("最多 30 天"))


class TestChunk(unittest.TestCase):
    def test_short_text_one_chunk(self):
        chunks = chunk_text("很短的一段话。")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["text"], "很短的一段话。")

    def test_long_text_splits(self):
        text = "\n\n".join(f"第{i}段。" + "内容" * 200 for i in range(5))
        chunks = chunk_text(text, size=300, overlap=40)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c["text"]), 300)

    def test_offsets_point_back(self):
        text = "开头。\n\n" + "甲" * 500 + "\n\n结尾。"
        chunks = chunk_text(text, size=260, overlap=30)
        for c in chunks:
            self.assertTrue(0 <= c["start"] < c["end"] <= len(text))
            head = c["text"][:12]
            self.assertEqual(text[c["start"] : c["start"] + len(head)], head)

    def test_overlap_validation(self):
        with self.assertRaises(ValueError):
            chunk_text("正文", size=100, overlap=100)

    def test_empty(self):
        self.assertEqual(chunk_text("   \n\n "), [])


class TestReadDocument(unittest.TestCase):
    def test_unsupported_ext(self):
        from zhiku.text import DocError
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake")
            path = f.name
        try:
            with self.assertRaises(DocError):
                read_document(path)
        finally:
            os.unlink(path)

    def test_missing_file(self):
        from zhiku.text import DocError

        with self.assertRaises(DocError):
            read_document("不存在.txt")

    def test_read_markdown_title(self):
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# 差旅制度\n\n住宿标准按城市分级。")
            path = f.name
        try:
            title, text = read_document(path)
            self.assertEqual(title, "差旅制度")
            self.assertIn("住宿标准", text)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
