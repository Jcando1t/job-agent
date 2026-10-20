import unittest

from app.services.jd_analyzer import analyze_jd, match_jd_requirements


class JDAnalyzerTests(unittest.TestCase):
    def test_splits_sections_and_extracts_keywords(self) -> None:
        result = analyze_jd(
            "岗位职责：\n负责开发 Python 和 RAG 应用。\n任职要求：\n熟悉 FastAPI，至少三年经验。\n优先条件：\n有大模型项目经验优先。"
        )

        self.assertEqual(result["responsibilities"], ["负责开发 Python 和 RAG 应用"])
        self.assertEqual(result["hard_requirements"], ["熟悉 FastAPI，至少三年经验"])
        self.assertEqual(result["preferred_qualifications"], ["有大模型项目经验优先"])
        self.assertIn("Python", result["keywords"])
        self.assertIn("RAG", result["keywords"])

    def test_matches_requirements_to_source_resume_without_knowledge_base(self) -> None:
        analysis = analyze_jd("任职要求：\n熟悉 Python 和 FastAPI。")

        matches = match_jd_requirements(
            analysis, [], source_content="项目经历：使用 Python 和 FastAPI 开发内部工具"
        )

        self.assertEqual(matches[0]["status"], "有相关资料，需核对")
        self.assertEqual(matches[0]["evidence"][0]["title"], "原始简历")
        self.assertIsNone(matches[0]["evidence"][0]["knowledge_item_id"])

    def test_matches_requirements_to_knowledge_and_keeps_gaps_visible(self) -> None:
        analysis = analyze_jd("任职要求：\n熟悉 Python 和 FastAPI。\n具备医疗临床试验经验。")
        knowledge = [
            {"id": 3, "category": "项目经验", "title": "知识库项目", "content": "使用 Python、FastAPI 开发 RAG 服务"}
        ]

        matches = match_jd_requirements(analysis, knowledge)

        self.assertEqual(matches[0]["status"], "有相关资料，需核对")
        self.assertEqual(matches[0]["evidence"][0]["knowledge_item_id"], 3)
        self.assertEqual(matches[1]["status"], "未找到依据")
        self.assertEqual(matches[1]["evidence"], [])


if __name__ == "__main__":
    unittest.main()
