import os
import tempfile
import unittest
from unittest import mock

from zhiku import answer, store

DOC = """报销制度

员工需在费用发生后 15 天内提交报销单据，超过 30 天不再受理。提交路径：OA-费用-报销。

差旅住宿标准

一线城市每晚不超过 500 元，其他城市 350 元。超标部分需要部门负责人审批。
"""


class AnswerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = store.connect(os.path.join(self.tmp.name, "t.db"))
        store.add_document(self.conn, "制度汇编", "a.md", DOC, size=200, overlap=30)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_answer_with_valid_cite(self):
        with mock.patch("zhiku.llm.chat", return_value="报销要在 15 天内提交 [1]。"):
            r = answer.ask(self.conn, "报销几天内提交")
        self.assertFalse(r["insufficient"])
        self.assertEqual(r["answer"], "报销要在 15 天内提交 [1]。")
        self.assertEqual([c["n"] for c in r["cites"]], [1])
        self.assertIn("制度汇编", r["cites"][0]["title"])
        self.assertTrue(r["cites"][0]["snippet"])

    def test_insufficient_answer(self):
        # 问的是材料里根本没有的事：检索能命中「报销」，但模型必须承认没答案
        with mock.patch("zhiku.llm.chat", return_value="INSUFFICIENT"):
            r = answer.ask(self.conn, "住宿超标的钱谁出")
        self.assertTrue(r["insufficient"])
        self.assertEqual(r["cites"], [])
        self.assertIn("不编", r["answer"])

    def test_no_hits_answer(self):
        with mock.patch("zhiku.llm.chat", return_value="不该被调用") as m:
            r = answer.ask(self.conn, "量子纠缠退火")
        self.assertTrue(r["insufficient"])
        self.assertIn("没有找到", r["answer"])
        m.assert_not_called()

    def test_out_of_range_cite_is_dropped(self):
        with mock.patch("zhiku.llm.chat", return_value="报销 15 天内提交 [1]，另外 [9] 也提到。"):
            r = answer.ask(self.conn, "报销几天内提交")
        self.assertEqual([c["n"] for c in r["cites"]], [1])
        self.assertIn("不存在", r["note"])

    def test_no_cite_gets_note(self):
        with mock.patch("zhiku.llm.chat", return_value="十五天内提交就行。"):
            r = answer.ask(self.conn, "报销几天内提交")
        self.assertEqual([c["n"] for c in r["cites"]], [1])
        self.assertIn("没标引用", r["note"])

    def test_empty_kb(self):
        conn2 = store.connect(os.path.join(self.tmp.name, "empty.db"))
        r = answer.ask(conn2, "任何问题")
        self.assertTrue(r["insufficient"])
        self.assertEqual(r["hits"], [])
        conn2.close()

    def test_retrieve_ranks_relevant_chunk(self):
        hits = answer.retrieve(self.conn, "住宿标准 一线城市")
        self.assertTrue(hits)
        self.assertIn("住宿", hits[0]["text"])

    def test_weak_cite_flag(self):
        with mock.patch("zhiku.llm.chat", return_value="今天天气不错 [1]。"):
            r = answer.ask(self.conn, "报销几天内提交")
        self.assertTrue(r["cites"][0].get("weak"))

    def test_terminal_format_has_cite_block(self):
        with mock.patch("zhiku.llm.chat", return_value="15 天内 [1]。"):
            r = answer.ask(self.conn, "报销几天内提交")
        text = answer.format_terminal(r)
        self.assertIn("[1]", text)
        self.assertIn("第", text)


if __name__ == "__main__":
    unittest.main()
