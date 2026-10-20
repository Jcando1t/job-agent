import unittest

from app.services.knowledge_retriever import retrieve_knowledge, retrieve_resume_chunks


class KnowledgeRetrieverTests(unittest.TestCase):
    def test_selects_related_experiences_and_respects_limit(self) -> None:
        items = [
            {"id": 1, "category": "项目经验", "title": "RAG 智能问答", "content": "使用 Python 和 FastAPI 开发知识库检索"},
            {"id": 2, "category": "工作经历", "title": "财务专员", "content": "负责财务报表和预算管理"},
            {"id": 3, "category": "技能", "title": "Python", "content": "Python、FastAPI、LLM"},
        ]
        result = retrieve_knowledge(items, "AI 应用开发，要求 RAG 和 Python", limit=1)
        self.assertEqual([item["id"] for item in result], [1])

    def test_returns_no_false_match_when_query_has_no_overlap(self) -> None:
        items = [{"id": 1, "title": "Java 后端", "content": "Spring 服务维护"}]
        self.assertEqual(retrieve_knowledge(items, "生物医药临床试验"), [])

    def test_empty_query_uses_a_small_fallback_set(self) -> None:
        items = [{"id": index, "title": str(index)} for index in range(12)]
        self.assertEqual(len(retrieve_knowledge(items, "")), 8)

    def test_resume_retrieval_returns_relevant_numbered_chunks(self) -> None:
        resume = "教育经历\n北京大学\n\n项目经历\n使用 Python 和 RAG 构建知识问答系统。\n\n工作经历\n负责线下活动运营。"
        result = retrieve_resume_chunks(resume, "AI 应用开发 RAG Python")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["chunk_id"], 2)
        self.assertEqual(result[0]["match_type"], "keyword")
        self.assertIn("RAG", result[0]["content"])

    def test_resume_retrieval_keeps_a_labeled_fallback_when_no_terms_match(self) -> None:
        result = retrieve_resume_chunks("第一段经历\n\n第二段经历", "量子化学", limit=2)
        self.assertEqual([item["match_type"] for item in result], ["fallback", "fallback"])

    def test_resume_retrieval_splits_long_text_within_chunk_size(self) -> None:
        result = retrieve_resume_chunks("Python。" * 600, "Python", chunk_size=100)
        self.assertTrue(result)
        self.assertLessEqual(max(len(item["content"]) for item in result), 100)


if __name__ == "__main__":
    unittest.main()
