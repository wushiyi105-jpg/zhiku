import os
import tempfile
import unittest

from zhiku import store

TEXT = "报销流程\n\n" + "员工需在费用发生后 15 天内提交单据。" * 40 + "\n\n主管审批后财务打款。"


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.conn = store.connect(self.db)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_add_and_list(self):
        doc_id, n = store.add_document(self.conn, "制度", "a.md", TEXT)
        self.assertGreater(n, 0)
        docs = store.list_documents(self.conn)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["id"], doc_id)
        self.assertEqual(docs[0]["n_chunks"], n)

    def test_chunks_keep_offset(self):
        store.add_document(self.conn, "制度", "a.md", TEXT)
        chunks = store.all_chunks(self.conn)
        for c in chunks:
            self.assertTrue(0 <= c["start"] < c["end"] <= len(TEXT))
            head = c["text"][:10]
            self.assertEqual(TEXT[c["start"] : c["start"] + len(head)], head)

    def test_same_source_replaces(self):
        store.add_document(self.conn, "旧版", "a.md", TEXT)
        store.add_document(self.conn, "新版", "a.md", "只有一句话。")
        docs = store.list_documents(self.conn)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["title"], "新版")
        self.assertEqual(len(store.all_chunks(self.conn)), 1)

    def test_no_replace_raises(self):
        store.add_document(self.conn, "制度", "a.md", TEXT)
        with self.assertRaises(ValueError):
            store.add_document(self.conn, "制度", "a.md", TEXT, replace=False)

    def test_remove_by_source_and_id(self):
        doc_id, _ = store.add_document(self.conn, "制度", "a.md", TEXT)
        self.assertEqual(store.remove_document(self.conn, "a.md"), 1)
        self.assertEqual(store.list_documents(self.conn), [])
        self.assertEqual(store.all_chunks(self.conn), [])
        doc_id2, _ = store.add_document(self.conn, "制度2", "b.md", TEXT)
        self.assertEqual(store.remove_document(self.conn, str(doc_id2)), 1)
        self.assertEqual(store.remove_document(self.conn, "nope"), 0)

    def test_empty_text_raises(self):
        with self.assertRaises(ValueError):
            store.add_document(self.conn, "空", "e.md", "   ")

    def test_stats_and_question_log(self):
        store.add_document(self.conn, "制度", "a.md", TEXT)
        s = store.stats(self.conn)
        self.assertEqual(s["docs"], 1)
        store.log_question(self.conn, "报销几天内提交", "15 天内 [1]", [1])
        self.assertEqual(store.stats(self.conn)["questions"], 1)
        recent = store.recent_questions(self.conn)
        self.assertEqual(recent[0]["question"], "报销几天内提交")

    def test_reopen_keeps_data(self):
        store.add_document(self.conn, "制度", "a.md", TEXT)
        self.conn.close()
        conn2 = store.connect(self.db)
        self.assertEqual(len(store.list_documents(conn2)), 1)
        conn2.close()
        self.conn = store.connect(self.db)


if __name__ == "__main__":
    unittest.main()
