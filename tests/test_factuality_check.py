import unittest

from app.services.factuality_check import check_resume_facts


class FactualityCheckTests(unittest.TestCase):
    def test_flags_new_number_and_technology_term(self) -> None:
        result = check_resume_facts(
            "使用 Python 开发原型，编写 12 个测试。",
            "- 使用 Python 和 Django 开发原型，编写 20 个测试。",
            [],
        )

        self.assertEqual(result["status"], "需人工核对")
        self.assertEqual(result["items"][0]["claims"], ["20", "django"])

    def test_accepts_claims_present_in_original_or_knowledge(self) -> None:
        result = check_resume_facts(
            "使用 Python 开发原型。",
            "- 使用 Python 和 FastAPI 开发原型，完成 40 份文档处理。",
            [{"content": "使用 FastAPI 处理 40 份文档。"}],
        )

        self.assertEqual(result["status"], "未发现可识别的新增数字或技术名词")
        self.assertEqual(result["items"], [])

    def test_different_decimal_is_flagged(self) -> None:
        result = check_resume_facts("提升 15%", "提升 1.5%", [])

        self.assertEqual(result["items"][0]["claims"], ["1.5"])


if __name__ == "__main__":
    unittest.main()
