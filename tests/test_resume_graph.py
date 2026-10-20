import unittest

from app.services.resume_graph import run_resume_graph


def _fake_draft(**kwargs):
    assert kwargs["job_title"] == "AI 应用开发工程师"
    assert kwargs["jd_analysis"]["keywords"] == ["Agent"]
    return {
        "result_content": "# 个人简介\n- 使用 Python 开发 Agent 应用，完成可验证的项目交付。",
        "greeting": "您好，我想应聘贵公司的 AI 应用开发岗位。",
        "evidence": [{"knowledge_item_id": 1, "used_for": "Agent 项目经历"}],
        "missing_info": [],
        "knowledge_item_ids": [1],
    }


def _one_page_quality(original, revised, knowledge):
    return {"layout": {"estimated_pages": 1}, "star": {"status": "要点较清晰"}}


def _over_page_quality(original, revised, knowledge):
    return {"layout": {"estimated_pages": 2}, "star": {"status": "建议补充"}}


class ResumeGraphTests(unittest.TestCase):
    def test_graph_routes_a_valid_draft_to_user_review(self):
        state = run_resume_graph(
            source_content="项目经历：Agent 应用",
            all_knowledge_items=[
                {
                    "id": 1,
                    "category": "项目经验",
                    "title": "Agent 项目",
                    "organization": "示例团队",
                    "period": "2025",
                    "content": "使用 Python 开发 Agent 应用",
                }
            ],
            knowledge_items=[{"id": 1}],
            jd_analysis={"keywords": ["Agent"]},
            requirement_matches=[],
            job_title="AI 应用开发工程师",
            draft_generator=_fake_draft,
            quality_checker=_one_page_quality,
        )

        self.assertEqual(state["status"], "awaiting_review")
        self.assertEqual(state["result_content"].splitlines()[0], "# 个人简介")
        self.assertEqual(state["knowledge_item_ids"], [1])

    def test_graph_routes_an_overlong_draft_to_revision(self):
        state = run_resume_graph(
            source_content="原稿",
            all_knowledge_items=[],
            knowledge_items=[],
            draft_generator=lambda **kwargs: {
                "result_content": "内容",
                "greeting": "",
                "evidence": [],
                "missing_info": [],
                "knowledge_item_ids": [],
            },
            quality_checker=_over_page_quality,
        )

        self.assertEqual(state["status"], "needs_revision")
        self.assertIn("超过一页", state["status_message"])


if __name__ == "__main__":
    unittest.main()
