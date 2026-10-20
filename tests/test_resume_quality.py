import unittest

from app.services.resume_quality import analyze_resume_quality, estimate_resume_layout


class ResumeQualityTests(unittest.TestCase):
    def test_layout_estimate_flags_long_resume(self) -> None:
        result = estimate_resume_layout("\n".join("- " + "中文经历" * 30 for _ in range(60)))

        self.assertGreater(result["estimated_pages"], 1)
        self.assertEqual(result["status"], "预计超过一页")

    def test_star_check_groups_bullets_under_one_experience(self) -> None:
        result = analyze_resume_quality(
            "# 简历\n- 负责整理数据",
            "# 简历\n## 项目经历\n### 数据平台｜开发者\n"
            "- 使用 Python 整理和校验数据\n- 通过优化流程提升效率 20%",
        )

        self.assertEqual(result["diff"]["added_lines"], 4)
        self.assertEqual(result["diff"]["removed_lines"], 1)
        self.assertEqual(result["star"]["total_experiences"], 1)
        self.assertEqual(result["star"]["needs_follow_up"], 0)
        self.assertEqual(result["star"]["status"], "要点较清晰")

    def test_action_and_result_can_appear_in_different_bullets_of_same_experience(self) -> None:
        result = analyze_resume_quality(
            "原文",
            "## 工作经历\n### 示例公司｜后端工程师\n"
            "- 负责设计并开发数据接口\n- 接口上线后错误率降低 20%",
        )

        self.assertEqual(result["star"]["status"], "要点较清晰")
        self.assertEqual(result["star"]["needs_follow_up"], 0)

    def test_missing_result_is_reported_once_for_the_whole_experience(self) -> None:
        result = analyze_resume_quality(
            "原文",
            "## 工作经历\n"
            "### 示例公司｜后端工程师\n"
            "- 使用 Python 开发数据接口\n- 负责补充接口测试",
        )

        self.assertEqual(result["star"]["total_experiences"], 1)
        self.assertEqual(result["star"]["needs_follow_up"], 1)
        self.assertEqual(result["star"]["experiences"][0]["title"], "示例公司｜后端工程师")
        self.assertEqual(result["star"]["experiences"][0]["bullet_count"], 2)
        self.assertEqual(result["star"]["experiences"][0]["missing"], ["result"])

    def test_gaps_do_not_leak_between_different_experiences(self) -> None:
        result = analyze_resume_quality(
            "原文",
            "## 项目经历\n### 项目 A\n- 使用 Python 搭建服务\n"
            "### 项目 B\n- 上线后处理时间减少 30%",
        )

        self.assertEqual(result["star"]["total_experiences"], 2)
        self.assertEqual(result["star"]["needs_follow_up"], 2)
        self.assertEqual(result["star"]["experiences"][0]["missing"], ["result"])
        self.assertEqual(result["star"]["experiences"][1]["missing"], ["action"])

    def test_contact_and_skill_lines_are_not_counted_as_experiences(self) -> None:
        result = analyze_resume_quality(
            "原文",
            "张三\n邮箱：test@example.com\n技能：Python、FastAPI\n- 负责搭建数据平台并提升效率 20%",
        )

        self.assertEqual(result["star"]["total_experiences"], 1)
        self.assertEqual(result["star"]["needs_follow_up"], 0)
        self.assertEqual(result["star"]["status"], "要点较清晰")

    def test_only_work_and_project_bullets_are_checked_when_sections_exist(self) -> None:
        result = analyze_resume_quality(
            "原文",
            "# 张三\n\n## 个人简介\n具备 Python 后端经验。\n\n## 技能\n- Python、FastAPI\n\n## 工作经历\n- 在项目期间负责接口开发，通过优化流程提升效率 20%\n\n## 教育经历\n- 北京示例大学，计算机科学与技术",
        )

        self.assertEqual(result["star"]["total_experiences"], 1)
        self.assertEqual(result["star"]["needs_follow_up"], 0)


if __name__ == "__main__":
    unittest.main()
