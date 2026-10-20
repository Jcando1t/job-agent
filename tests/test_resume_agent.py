import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import main
from app.database import (
    create_agent_run,
    create_target,
    create_resume_source,
    get_agent_run,
    get_resumes,
    save_approved_agent_run,
    update_agent_run,
)
from tests.db_support import initialize_test_database
from app.schemas import ResumeRunApproval, ResumeRunInput, ResumeRunUpdate
from app.services.resume_agent import build_user_prompt, generate_resume_draft
from app.services.llm_client import LLMConfigurationError, LLMError


class FakeLLMClient:
    def complete_json(self, _system_prompt: str, _user_prompt: str) -> dict:
        return {
            "resume_markdown": "# AI 简历\n项目：如实描述",
            "greeting": "您好，我对贵公司的岗位很感兴趣。",
            "evidence": [
                {"knowledge_item_id": 7, "used_for": "支撑项目经验"},
                {"knowledge_item_id": 99, "used_for": "无效资料编号"},
            ],
            "missing_information": ["请补充可验证的项目成果数据"],
        }


class SourceOnlyFakeLLMClient:
    def complete_json(self, _system_prompt: str, _user_prompt: str) -> dict:
        return {
            "resume_markdown": "# AI 简历\n仅按原始简历整理",
            "greeting": "",
            "evidence": [],
            "missing_information": [],
        }


class ResumeAgentServiceTests(unittest.TestCase):
    def test_prompt_requests_experience_level_star_and_result_first_resume_bullets(self) -> None:
        from app.services.resume_agent import SYSTEM_PROMPT

        self.assertIn("同一段经历作为整体", SYSTEM_PROMPT)
        self.assertIn("最有分量且有事实依据的成果", SYSTEM_PROMPT)
        self.assertIn("不得补造数字", SYSTEM_PROMPT)

    def test_jd_is_part_of_the_model_input(self) -> None:
        prompt = build_user_prompt(
            "简历原文", [], "突出相关经验", "负责 RAG 应用开发", "AI 应用开发工程师"
        )
        self.assertIn('"job_description": "负责 RAG 应用开发"', prompt)
        self.assertIn('"job_title": "AI 应用开发工程师"', prompt)

    def test_structured_jd_analysis_and_requirement_evidence_are_sent_to_model(self) -> None:
        prompt = build_user_prompt(
            "简历原文",
            [],
            "",
            jd_text="要求 Python",
            jd_analysis={"hard_requirements": ["要求 Python"]},
            requirement_matches=[{"requirement": "要求 Python", "status": "未找到依据", "evidence": []}],
        )
        self.assertIn('"hard_requirements"', prompt)
        self.assertIn('"要求 Python"', prompt)
        self.assertIn('"status": "未找到依据"', prompt)

    def test_prompt_uses_retrieved_resume_chunks_instead_of_full_source(self) -> None:
        prompt = build_user_prompt(
            "完整简历不应直接传给模型",
            [],
            "突出 RAG 项目",
            resume_chunks=[{"chunk_id": 3, "content": "使用 RAG 完成知识问答", "match_type": "keyword"}],
        )
        self.assertIn('"original_resume_retrieval"', prompt)
        self.assertIn("使用 RAG 完成知识问答", prompt)
        self.assertNotIn("完整简历不应直接传给模型", prompt)

    def test_draft_keeps_only_evidence_from_current_knowledge_base(self) -> None:
        result = generate_resume_draft(
            source_content="原始简历文字",
            knowledge_items=[{"id": 7, "category": "项目经验", "title": "项目", "organization": "", "period": "", "content": "项目描述"}],
            instruction="突出项目",
            client=FakeLLMClient(),
        )
        self.assertEqual(result["result_content"], "# AI 简历\n项目：如实描述")
        self.assertEqual(result["greeting"], "您好，我对贵公司的岗位很感兴趣。")
        self.assertEqual(result["knowledge_item_ids"], [7])
        self.assertEqual(result["evidence"], [{"knowledge_item_id": 7, "used_for": "支撑项目经验"}])
        self.assertIn("请补充可验证的项目成果数据", result["missing_info"])

    def test_draft_keeps_only_citations_from_retrieved_resume_chunks(self) -> None:
        class ResumeCitationClient:
            def complete_json(self, _system_prompt: str, _user_prompt: str) -> dict:
                return {
                    "resume_markdown": "项目经历",
                    "evidence": [
                        {"resume_chunk_id": 3, "used_for": "支撑项目经历"},
                        {"resume_chunk_id": 99, "used_for": "无效片段"},
                    ],
                    "missing_information": [],
                }

        result = generate_resume_draft(
            source_content="完整原稿",
            knowledge_items=[],
            instruction="整理经历",
            resume_chunks=[{"chunk_id": 3, "content": "项目内容"}],
            client=ResumeCitationClient(),
        )
        self.assertEqual(result["evidence"], [{"resume_chunk_id": 3, "used_for": "支撑项目经历"}])
        self.assertEqual(result["knowledge_item_ids"], [])

    def test_source_only_draft_does_not_claim_knowledge_evidence_is_missing(self) -> None:
        result = generate_resume_draft(
            source_content="原始简历中的项目经历",
            knowledge_items=[],
            instruction="只依据原始简历改写",
            client=SourceOnlyFakeLLMClient(),
        )

        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["missing_info"], [])

    def test_api_requires_explicit_external_data_consent(self) -> None:
        with patch("main.generate_resume_draft") as generate:
            with self.assertRaises(HTTPException) as error:
                main.create_resume_run(
                    ResumeRunInput(source_resume_id=1, allow_external_model=False)
                )
        self.assertEqual(error.exception.status_code, 400)
        generate.assert_not_called()

    def test_api_returns_unapproved_reviewable_draft(self) -> None:
        run = {"id": 12, "status": "draft", "result_content": "改进后简历", "evidence": [], "missing_info": []}
        with (
            patch("main.get_resume_sources", return_value=[{"id": 2, "filename": "resume.txt", "content": "原稿"}]),
            patch("main.get_knowledge_items", return_value=[]),
            patch("main.create_agent_run", return_value={"id": 12}) as create_run,
            patch("main.generate_resume_draft", return_value={"result_content": "改进后简历", "greeting": "打招呼语", "evidence": [], "missing_info": [], "knowledge_item_ids": []}) as generate,
            patch("main.update_agent_run", return_value=run) as update,
        ):
            result = main.create_resume_run(
                ResumeRunInput(
                    source_resume_id=2,
                    allow_external_model=True,
                    job_title="AI 应用开发工程师",
                    company="示例公司",
                    jd_text="负责 Agent 应用开发",
                )
            )
        self.assertEqual(result["status"], "draft")
        self.assertEqual(create_run.call_args.args[1]["jd_text"], "负责 Agent 应用开发")
        self.assertEqual(create_run.call_args.args[1]["jd_analysis"]["responsibilities"], ["负责 Agent 应用开发"])
        self.assertTrue(create_run.call_args.args[1]["requirement_matches"])
        self.assertEqual(generate.call_args.kwargs["job_title"], "AI 应用开发工程师")
        self.assertEqual(generate.call_args.kwargs["jd_text"], "负责 Agent 应用开发")
        self.assertEqual(generate.call_args.kwargs["jd_analysis"]["responsibilities"], ["负责 Agent 应用开发"])
        self.assertTrue(generate.call_args.kwargs["resume_chunks"])
        self.assertTrue(create_run.call_args.args[1]["resume_chunks"])
        update.assert_called_once()

    def test_jd_evidence_uses_original_resume_when_knowledge_is_empty(self) -> None:
        source = {"id": 2, "filename": "resume.txt", "content": "项目经历：使用 Python 和 FastAPI 开发工具"}
        with (
            patch("main.get_resume_sources", return_value=[source]),
            patch("main.get_knowledge_items", return_value=[]),
            patch("main.create_agent_run", return_value={"id": 13}) as create_run,
            patch("main.generate_resume_draft", return_value={"result_content": "改进后简历", "greeting": "", "evidence": [], "missing_info": [], "knowledge_item_ids": []}),
            patch("main.update_agent_run", return_value={"id": 13, "status": "draft"}),
        ):
            main.create_resume_run(
                ResumeRunInput(
                    source_resume_id=2,
                    jd_text="任职要求：\n熟悉 Python 和 FastAPI。",
                    allow_external_model=True,
                )
            )

        match = create_run.call_args.args[1]["requirement_matches"][0]
        self.assertEqual(match["status"], "有相关资料，需核对")
        self.assertEqual(match["evidence"][0]["title"], "原始简历")

    def test_model_configuration_failure_is_saved_as_failed_run(self) -> None:
        self._assert_model_failure_is_saved(
            LLMConfigurationError("尚未配置 DEEPSEEK_API_KEY。"), 503
        )

    def test_model_request_failure_is_saved_as_failed_run(self) -> None:
        self._assert_model_failure_is_saved(LLMError("模型调用失败：Connection error。"), 502)

    def _assert_model_failure_is_saved(self, failure: Exception, expected_status: int) -> None:
        failed_run = {
            "id": 18,
            "status": "failed",
            "error_message": str(failure),
        }
        with (
            patch("main.get_resume_sources", return_value=[
                {"id": 2, "filename": "resume.txt", "content": "原稿"}
            ]),
            patch("main.get_knowledge_items", return_value=[]),
            patch("main.create_agent_run", return_value={"id": 18}),
            patch("main.generate_resume_draft", side_effect=failure),
            patch("main.update_agent_run", return_value=failed_run) as update,
        ):
            with self.assertRaises(HTTPException) as error:
                main.create_resume_run(
                    ResumeRunInput(source_resume_id=2, allow_external_model=True)
                )

        self.assertEqual(error.exception.status_code, expected_status)
        self.assertEqual(update.call_args.args[:2], (18, "failed"))
        self.assertEqual(update.call_args.kwargs["error_message"], str(failure))

    def test_editing_draft_recalculates_local_quality_check(self) -> None:
        run = {
            "id": 12,
            "status": "draft",
            "source_resume_id": 2,
            "result_content": "旧草稿",
            "greeting": "旧问候语",
            "evidence": [],
            "missing_info": [],
            "input_snapshot": {"job_title": "测试岗位"},
        }
        with (
            patch("main.get_agent_run", return_value=run),
            patch("main.get_resume_sources", return_value=[
                {"id": 2, "filename": "resume.txt", "content": "原稿"}
            ]),
            patch("main.update_agent_run", return_value={"id": 12, "status": "draft"}) as update,
        ):
            main.edit_resume_run(
                12,
                ResumeRunUpdate(
                    result_content="# 简历\n## 工作经历\n- 在项目期间负责接口开发，通过优化流程提升效率 20%",
                    greeting="新问候语",
                ),
            )

        snapshot = update.call_args.kwargs["input_snapshot"]
        self.assertEqual(snapshot["quality_check"]["star"]["status"], "要点较清晰")
        self.assertEqual(snapshot["quality_check"]["star"]["total_experiences"], 1)

    def test_approval_rejects_a_draft_estimated_over_one_page(self) -> None:
        long_content = "\n".join("- " + "中文经历" * 30 for _ in range(60))
        run = {
            "id": 12,
            "status": "draft",
            "result_content": long_content,
            "input_snapshot": {},
        }
        with (
            patch("main.get_agent_run", return_value=run),
            patch("main.save_approved_agent_run") as save,
        ):
            with self.assertRaises(HTTPException) as error:
                main.approve_resume_run(12, ResumeRunApproval(title="一页测试"))

        self.assertEqual(error.exception.status_code, 409)
        self.assertIn("超过一页", error.exception.detail)
        save.assert_not_called()

    def test_selected_saved_job_fills_prompt_and_remains_linked_to_saved_version(self) -> None:
        job = {
            "id": 21,
            "title": "AI 应用工程师",
            "company": "示例公司",
            "description": "负责构建 Agent 工作流并使用 Python。",
        }
        with (
            patch("main.get_resume_sources", return_value=[{"id": 2, "filename": "resume.txt", "content": "原稿"}]),
            patch("main.get_job", return_value=job),
            patch("main.get_knowledge_items", return_value=[]),
            patch("main.create_agent_run", return_value={"id": 13}) as create_run,
            patch("main.generate_resume_draft", return_value={"result_content": "改进后简历", "greeting": "打招呼语", "evidence": [], "missing_info": [], "knowledge_item_ids": []}) as generate,
            patch("main.update_agent_run", return_value={"id": 13, "status": "draft"}),
        ):
            main.create_resume_run(
                ResumeRunInput(source_resume_id=2, job_id=21, allow_external_model=True)
            )

        snapshot = create_run.call_args.args[1]
        self.assertEqual(snapshot["job_id"], 21)
        self.assertEqual(snapshot["job_title"], "AI 应用工程师")
        self.assertEqual(generate.call_args.kwargs["jd_text"], job["description"])


class ResumeAgentPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_path = Path(__file__).resolve().parent / "agent_run_test.db"
        self.database_path.unlink(missing_ok=True)
        initialize_test_database(self.database_path)
        self.source = create_resume_source("resume.txt", "原始简历", database_path=self.database_path)

    def tearDown(self) -> None:
        self.database_path.unlink(missing_ok=True)

    def test_approval_saves_new_version_once_and_links_original(self) -> None:
        run = create_agent_run(
            self.source["id"],
            {
                "knowledge_item_ids": [4],
                "job_id": 21,
                "job_title": "AI 应用开发工程师",
                "company": "示例公司",
                "jd_text": "负责 Agent 应用开发",
            },
            database_path=self.database_path,
        )
        update_agent_run(
            run["id"], "draft", result_content="已人工审核的简历", greeting="您好", database_path=self.database_path
        )

        saved = save_approved_agent_run(
            run["id"], "AI 改进版", database_path=self.database_path
        )

        self.assertEqual(saved["version"], 1)
        self.assertEqual(saved["source_resume_id"], self.source["id"])
        self.assertEqual(saved["greeting"], "您好")
        self.assertEqual(saved["job_snapshot"]["job_title"], "AI 应用开发工程师")
        self.assertEqual(saved["job_snapshot"]["job_id"], 21)
        self.assertEqual(saved["source_item_ids"], [4])
        self.assertEqual(get_agent_run(run["id"], self.database_path)["status"], "approved")
        self.assertIsNone(save_approved_agent_run(run["id"], "重复保存", self.database_path))
        self.assertEqual(len(get_resumes(self.database_path)), 1)

    def test_target_resume_replaces_only_the_current_default_after_approval(self) -> None:
        target = create_target("AI 应用开发", "Agent", ["北京"], self.database_path)

        def approve(snapshot: dict, title: str) -> dict:
            run = create_agent_run(self.source["id"], snapshot, database_path=self.database_path)
            update_agent_run(run["id"], "draft", result_content=title, database_path=self.database_path)
            return save_approved_agent_run(run["id"], title, self.database_path)

        first = approve({"target_id": target["id"]}, "方向版一")
        self.assertTrue(first["is_current"])
        job_version = approve({"target_id": target["id"], "job_id": 8}, "单岗定制版")
        self.assertFalse(job_version["is_current"])
        self.assertTrue(next(item for item in get_resumes(self.database_path) if item["id"] == first["id"])["is_current"])

        second = approve({"target_id": target["id"]}, "方向版二")
        saved = {item["id"]: item for item in get_resumes(self.database_path)}
        self.assertTrue(second["is_current"])
        self.assertFalse(saved[first["id"]]["is_current"])
        self.assertFalse(saved[job_version["id"]]["is_current"])


if __name__ == "__main__":
    unittest.main()
