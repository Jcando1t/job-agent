import unittest

from app.services.boss_job_parser import parse_boss_job_text


class BossJobParserTests(unittest.TestCase):
    def test_uses_explicit_labels_and_keeps_jd_text(self) -> None:
        result = parse_boss_job_text(
            "AI 应用开发工程师\n公司：示例科技\n城市：北京\n岗位职责：\n负责开发 Python 和 RAG 应用。"
        )

        self.assertEqual(result["title"], "AI 应用开发工程师")
        self.assertEqual(result["company"], "示例科技")
        self.assertEqual(result["city"], "北京")
        self.assertIn("负责开发 Python 和 RAG 应用", result["description"])
        self.assertNotIn("公司：示例科技", result["description"])
        self.assertNotIn("城市：北京", result["description"])

    def test_does_not_guess_company_or_city_without_labels(self) -> None:
        result = parse_boss_job_text("后端开发工程师\n15-25K·14薪\n北京\n职位描述：负责接口开发")

        self.assertEqual(result["title"], "后端开发工程师")
        self.assertEqual(result["company"], "")
        self.assertEqual(result["city"], "")

    def test_skips_common_page_buttons_and_salary_before_title(self) -> None:
        result = parse_boss_job_text("职位已收藏\n15-25K·14薪\nAI 产品工程师\n公司：示例公司")

        self.assertEqual(result["title"], "AI 产品工程师")
        self.assertEqual(result["company"], "示例公司")

    def test_removes_salary_and_page_buttons_from_description(self) -> None:
        result = parse_boss_job_text(
            "职位已收藏\n15-25K·14薪\nAI 产品工程师\n公司：示例公司\n岗位职责：\n负责产品设计。"
        )

        self.assertEqual(result["description"], "岗位职责：\n负责产品设计。")
        self.assertNotIn("15-25K", result["description"])

    def test_empty_text_is_explained(self) -> None:
        result = parse_boss_job_text("\n\n")

        self.assertEqual(result["title"], "")
        self.assertTrue(result["warnings"])

    def test_extracts_city_and_company_from_boss_card_summary(self) -> None:
        result = parse_boss_job_text(
            "AI 应用开发工程师\n"
            "12-18K·14薪\n"
            "1-3年 本科 Python FastAPI\n"
            "示例科技\n"
            "天津·西青区·张家窝"
        )

        self.assertEqual(result["title"], "AI 应用开发工程师")
        self.assertEqual(result["company"], "示例科技")
        self.assertEqual(result["city"], "天津")
        self.assertNotIn("天津·西青区·张家窝", result["description"])
        self.assertNotIn("1-3年 本科", result["description"])

    def test_ignores_contact_name_when_card_has_no_company(self) -> None:
        result = parse_boss_job_text(
            "周女士\nAI大模型应用（RAG与智能体方向）\n"
            "15-25K·13薪\n天津·西青区·张家窝"
        )

        self.assertEqual(result["title"], "AI大模型应用（RAG与智能体方向）")
        self.assertEqual(result["city"], "天津")
        self.assertNotEqual(result["title"], "周女士")


if __name__ == "__main__":
    unittest.main()
