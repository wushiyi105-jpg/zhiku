import unittest

from zhiku.bm25 import BM25Index, highlight

DOCS = [
    {"chunk_id": 1, "title": "员工手册", "text": "报销需要在 15 天内提交，超过 30 天不再受理。"},
    {"chunk_id": 2, "title": "员工手册", "text": "年假按照工龄计算，满一年 5 天。"},
    {"chunk_id": 3, "title": "产品 FAQ", "text": "退款会在 7 个工作日内原路退回。"},
]


class TestBM25(unittest.TestCase):
    def test_best_match_first(self):
        idx = BM25Index(DOCS)
        hits = idx.search("报销最晚几天提交", top_k=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["chunk_id"], 1)

    def test_no_intersection(self):
        idx = BM25Index(DOCS)
        self.assertEqual(idx.search("量子纠缠"), [])

    def test_bigram_beats_unigram_noise(self):
        idx = BM25Index(DOCS)
        hits = idx.search("年假")
        self.assertEqual(hits[0]["chunk_id"], 2)

    def test_top_k_limit(self):
        idx2 = BM25Index(DOCS * 5)
        hits = idx2.search("报销", top_k=2)
        self.assertLessEqual(len(hits), 2)

    def test_scores_positive(self):
        idx = BM25Index(DOCS)
        for h in idx.search("退款", top_k=3):
            self.assertGreater(h["score"], 0)

    def test_empty_index(self):
        self.assertEqual(BM25Index([]).search("任何"), [])

    def test_highlight_returns_snippet(self):
        s = highlight(DOCS[0]["text"], "报销")
        self.assertIn("报销", s)


if __name__ == "__main__":
    unittest.main()
