"""在临时 SQLite 数据库中验证简历改进 API 的完整审核流程。"""

from pathlib import Path
import unittest
from io import BytesIO
from unittest.mock import patch

from docx import Document
from fastapi.testclient import TestClient

import main
from app.database import (
    create_agent_run,
    create_job,
    create_knowledge_item,
    create_resume_source,
    create_target,
    get_knowledge_items,
    get_agent_run,
    get_resume,
    get_resume_sources,
    get_targets,
    save_approved_agent_run,
    update_agent_run,
)
from app.schemas import ResumeRunApproval, ResumeRunInput, ResumeRunUpdate
from tests.db_support import initialize_test_database


class ResumeWorkflowEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_path = Path(__file__).resolve().parent / "resume_workflow_e2e_test.db"
        self.database_path.unlink(missing_ok=True)
        initialize_test_database(self.database_path)
        self.source = create_resume_source(
            "原始简历.txt",
            "# 张三\n## 项目经历\n- 使用 Python 构建内部问答原型",
            database_path=self.database_path,
        )
        self.knowledge = create_knowledge_item(
            category="项目经验",
            title="内部知识问答原型",
            organization="个人项目",
            period="2025 年",
            content="使用 Python 和 RAG 构建问答原型，完成文档检索与答案展示。",
            source_note="用户录入",
            database_path=self.database_path,
        )
        self.target = create_target(
            "AI 应用开发",
            "Agent",
            ["北京"],
            database_path=self.database_path,
        )
        self.job = create_job(
            title="AI 应用工程师",
            company="示例公司",
            city="北京",
            original_url="https://example.invalid/jobs/ai-engineer",
            description="负责 Python 应用开发和 RAG 工作流建设。",
            target_id=self.target["id"],
            database_path=self.database_path,
        )

    def tearDown(self) -> None:
        self.database_path.unlink(missing_ok=True)

    def test_draft_edit_approval_and_exports_use_only_temporary_database(self) -> None:
        def fake_generate_resume_draft(**kwargs: object) -> dict:
            # 断言传给模型的上下文确实来自本测试数据。
            self.assertIn("张三", str(kwargs["source_content"]))
            self.assertEqual(kwargs["job_title"], "AI 应用工程师")
            self.assertIn("RAG", kwargs["jd_text"])
            return {
                "result_content": (
                    "# 张三\n## 项目经历\n"
                    "- 基于 Python 和 RAG 构建内部知识问答原型，支持文档检索与答案展示。"
                ),
                "greeting": "您好，我关注到贵公司正在招聘 AI 应用工程师。",
                "evidence": [
                    {"knowledge_item_id": self.knowledge["id"], "used_for": "支撑 RAG 项目经历"}
                ],
                "missing_info": ["请补充可验证的项目效果数据"],
                "knowledge_item_ids": [self.knowledge["id"]],
            }

        with (
            patch("main.get_resume_sources", lambda: get_resume_sources(self.database_path)),
            patch("main.get_knowledge_items", lambda: get_knowledge_items(self.database_path)),
            patch("main.get_job", lambda job_id: self.job if job_id == self.job["id"] else None),
            patch("main.get_targets", lambda: get_targets(self.database_path)),
            patch("main.create_agent_run", lambda source_id, snapshot: create_agent_run(source_id, snapshot, database_path=self.database_path)),
            patch("main.update_agent_run", lambda run_id, status, **kwargs: update_agent_run(run_id, status, database_path=self.database_path, **kwargs)),
            patch("main.get_agent_run", lambda run_id: get_agent_run(run_id, self.database_path)),
            patch("main.save_approved_agent_run", lambda run_id, title: save_approved_agent_run(run_id, title, self.database_path)),
            patch("main.generate_resume_draft", side_effect=fake_generate_resume_draft),
        ):
            client = TestClient(main.app)
            draft_response = client.post(
                "/api/resume-runs",
                json=ResumeRunInput(
                    source_resume_id=self.source["id"],
                    job_id=self.job["id"],
                    instruction="突出与岗位相关的项目经验",
                    allow_external_model=True,
                ).model_dump(),
            )
            self.assertEqual(draft_response.status_code, 201)
            draft = draft_response.json()
            self.assertEqual(draft["status"], "draft")
            self.assertEqual(draft["evidence"][0]["knowledge_item_id"], self.knowledge["id"])
            self.assertEqual(draft["missing_info"], ["请补充可验证的项目效果数据"])
            self.assertEqual(draft["input_snapshot"]["job_id"], self.job["id"])
            self.assertEqual(draft["input_snapshot"]["target_id"], self.target["id"])
            self.assertEqual(draft["input_snapshot"]["jd_text"], self.job["description"])

            edited_content = (
                "# 张三\n## 项目经历\n"
                "- 基于 Python 和 RAG 构建内部知识问答原型，提供 REST API 接口，支持文档检索与答案展示。"
            )
            edit_response = client.put(
                f"/api/resume-runs/{draft['id']}/draft",
                json=ResumeRunUpdate(
                    result_content=edited_content,
                    greeting="您好，我希望进一步介绍相关项目经验。",
                ).model_dump(),
            )
            self.assertEqual(edit_response.status_code, 200)
            edited = edit_response.json()
            self.assertEqual(edited["status"], "draft")
            self.assertEqual(edited["result_content"], edited_content)
            self.assertIn("quality_check", edited["input_snapshot"])
            self.assertEqual(
                edited["input_snapshot"]["quality_check"]["factuality"]["items"][0]["claims"],
                ["api", "rest"],
            )

            approval_response = client.post(
                f"/api/resume-runs/{draft['id']}/approve",
                json=ResumeRunApproval(title="AI 应用工程师定制简历").model_dump(),
            )
            self.assertEqual(approval_response.status_code, 201)
            saved = approval_response.json()
            self.assertEqual(saved["version"], 1)
            self.assertEqual(saved["content"], edited_content)
            self.assertEqual(saved["source_resume_id"], self.source["id"])
            self.assertEqual(saved["source_item_ids"], [self.knowledge["id"]])
            self.assertEqual(saved["job_snapshot"]["job_id"], self.job["id"])
            self.assertEqual(saved["target_id"], self.target["id"])
            self.assertFalse(saved["is_current"])
            self.assertEqual(saved["job_snapshot"]["jd_text"], self.job["description"])
            self.assertEqual(get_agent_run(draft["id"], self.database_path)["status"], "approved")

            with patch("main.get_resume", lambda resume_id: get_resume(resume_id, self.database_path)):
                markdown_response = client.get(
                    f"/api/resumes/{saved['id']}/download?format=md"
                )
                docx_response = client.get(
                    f"/api/resumes/{saved['id']}/download?format=docx"
                )

        self.assertEqual(markdown_response.status_code, 200)
        self.assertEqual(markdown_response.content.decode("utf-8"), edited_content)
        self.assertEqual(docx_response.status_code, 200)
        self.assertIn("wordprocessingml", docx_response.headers["content-type"])
        docx = Document(BytesIO(docx_response.content))
        self.assertIn("项目经历", [paragraph.text for paragraph in docx.paragraphs])


if __name__ == "__main__":
    unittest.main()
