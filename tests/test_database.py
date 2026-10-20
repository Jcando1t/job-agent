import unittest
from pathlib import Path

from app.database import (
    create_job,
    create_knowledge_item,
    create_target,
    delete_job,
    delete_knowledge_item,
    delete_target,
    get_jobs,
    get_knowledge_items,
    get_resumes,
    get_resume_sources,
    get_resume_image_sources,
    get_resume_image_source,
    get_targets,
    set_target_active,
    update_job,
    update_knowledge_item,
    update_target,
    create_resume,
    create_resume_source,
    delete_resume_source,
    create_resume_image_source,
    delete_resume_image_source,
)
from tests.db_support import initialize_test_database


class JobTargetDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_path = Path(__file__).resolve().parent / "job_targets_test.db"
        self.database_path.unlink(missing_ok=True)
        initialize_test_database(self.database_path)

    def tearDown(self) -> None:
        self.database_path.unlink(missing_ok=True)

    def test_target_is_saved_and_available_after_reopening_database(self) -> None:
        created = create_target(
            title="Agent 应用开发",
            keywords="Python, LLM",
            cities=["北京", "天津"],
            database_path=self.database_path,
        )

        initialize_test_database(self.database_path)
        saved_targets = get_targets(self.database_path)

        self.assertEqual(len(saved_targets), 1)
        self.assertEqual(saved_targets[0]["id"], created["id"])
        self.assertEqual(saved_targets[0]["cities"], ["北京", "天津"])

    def test_target_can_be_updated_paused_and_deleted(self) -> None:
        created = create_target(
            title="Agent 应用开发",
            keywords="Python",
            cities=["北京"],
            database_path=self.database_path,
        )

        updated = update_target(
            target_id=created["id"],
            title="AI 应用工程师",
            keywords="Python, FastAPI",
            cities=["天津", "上海"],
            database_path=self.database_path,
        )
        paused = set_target_active(
            target_id=created["id"],
            is_active=False,
            database_path=self.database_path,
        )

        self.assertEqual(updated["title"], "AI 应用工程师")
        self.assertEqual(updated["cities"], ["天津", "上海"])
        self.assertFalse(paused["is_active"])
        self.assertTrue(delete_target(created["id"], self.database_path))
        self.assertEqual(get_targets(self.database_path), [])

    def test_job_can_be_created_updated_and_deleted(self) -> None:
        target = create_target(
            title="Python 后端开发",
            keywords="Python, FastAPI",
            cities=["北京"],
            database_path=self.database_path,
        )
        created = create_job(
            title="后端工程师",
            company="示例科技",
            city="北京",
            source="手动录入",
            original_url="https://example.com/jobs/1",
            notes="需要确认是否接受远程",
            next_action="周五前准备定制简历",
            description="负责 Python 服务开发。",
            target_id=target["id"],
            database_path=self.database_path,
        )

        self.assertEqual(len(get_jobs(self.database_path)), 1)
        self.assertEqual(created["target_title"], "Python 后端开发")
        self.assertEqual(created["status"], "未处理")
        self.assertEqual(created["notes"], "需要确认是否接受远程")
        self.assertEqual(created["next_action"], "周五前准备定制简历")

        duplicate = create_job(
            title="后端工程师",
            company="示例科技",
            city="北京",
            original_url="https://example.com/jobs/1",
            database_path=self.database_path,
        )
        self.assertTrue(duplicate["duplicate"])

        another = create_job(
            title="算法工程师",
            company="示例实验室",
            city="北京",
            original_url="https://example.com/jobs/3",
            database_path=self.database_path,
        )
        collision = update_job(
            job_id=another["id"],
            title="后端工程师",
            company="示例科技",
            city="北京",
            original_url="https://example.com/jobs/1",
            database_path=self.database_path,
        )
        self.assertTrue(collision["duplicate"])
        self.assertTrue(delete_job(another["id"], self.database_path))

        updated = update_job(
            job_id=created["id"],
            title="高级后端工程师",
            company="另一家科技公司",
            city="天津",
            source="招聘网站",
            original_url="https://example.com/jobs/2",
            description="维护 Web API。",
            status="已投递",
            notes="已通过官网提交",
            next_action="等待一周后跟进",
            target_id=None,
            database_path=self.database_path,
        )

        self.assertEqual(updated["title"], "高级后端工程师")
        self.assertEqual(updated["target_id"], None)
        self.assertEqual(updated["original_url"], "https://example.com/jobs/2")
        self.assertEqual(updated["status"], "已投递")
        self.assertEqual(updated["notes"], "已通过官网提交")
        self.assertEqual(updated["next_action"], "等待一周后跟进")
        self.assertTrue(delete_job(created["id"], self.database_path))
        self.assertEqual(get_jobs(self.database_path), [])
        self.assertFalse(delete_job(created["id"], self.database_path))

    def test_deleting_target_unlinks_jobs_without_deleting_them(self) -> None:
        target = create_target(
            title="数据分析",
            keywords="SQL",
            cities=["天津"],
            database_path=self.database_path,
        )
        job = create_job(
            title="数据分析师",
            target_id=target["id"],
            database_path=self.database_path,
        )

        self.assertTrue(delete_target(target["id"], self.database_path))

        saved_jobs = get_jobs(self.database_path)
        self.assertEqual(len(saved_jobs), 1)
        self.assertEqual(saved_jobs[0]["id"], job["id"])
        self.assertIsNone(saved_jobs[0]["target_id"])

    def test_knowledge_item_can_be_created_updated_and_deleted(self) -> None:
        created = create_knowledge_item(
            category="项目经验",
            title="智能问答项目",
            organization="个人项目",
            period="2025.01–2025.03",
            content="使用 Python 构建检索问答原型。",
            source_note="本人手动补充",
            database_path=self.database_path,
        )

        initialize_test_database(self.database_path)
        saved_items = get_knowledge_items(self.database_path)
        self.assertEqual(len(saved_items), 1)
        self.assertEqual(saved_items[0]["id"], created["id"])
        self.assertEqual(saved_items[0]["source_note"], "本人手动补充")

        updated = update_knowledge_item(
            item_id=created["id"],
            category="成果",
            title="问答检索效果改进",
            organization="个人项目",
            period="2025.01–2025.03",
            content="基于测试问题检查检索结果并调整切分方式。",
            source_note="本人补充，待提供量化数据",
            database_path=self.database_path,
        )
        self.assertEqual(updated["category"], "成果")
        self.assertEqual(updated["title"], "问答检索效果改进")
        self.assertTrue(delete_knowledge_item(created["id"], self.database_path))
        self.assertEqual(get_knowledge_items(self.database_path), [])

    def test_resume_versions_are_saved_with_source_item_ids(self) -> None:
        item = create_knowledge_item(
            category="技能",
            title="Python",
            content="使用 Python 编写过后端服务。",
            database_path=self.database_path,
        )

        first = create_resume(
            title="基础简历",
            content="# 基础简历\n技能：Python",
            source_item_ids=[item["id"]],
            database_path=self.database_path,
        )
        second = create_resume(
            title="基础简历（补充）",
            content="# 基础简历\n技能：Python、SQLite",
            source_item_ids=[item["id"], item["id"]],
            database_path=self.database_path,
        )

        self.assertEqual(first["version"], 1)
        self.assertEqual(second["version"], 2)
        self.assertEqual(second["source_item_ids"], [item["id"]])
        self.assertEqual([resume["version"] for resume in get_resumes(self.database_path)], [2, 1])

    def test_resume_source_is_saved_and_can_be_deleted_without_deleting_versions(self) -> None:
        source = create_resume_source(
            filename="resume.txt",
            content="# 我的原始简历\n项目经验：本地原型",
            database_path=self.database_path,
        )
        saved_source = get_resume_sources(self.database_path)
        self.assertEqual(saved_source[0]["id"], source["id"])
        self.assertEqual(saved_source[0]["filename"], "resume.txt")
        self.assertEqual(saved_source[0]["content"], "# 我的原始简历\n项目经验：本地原型")

        resume = create_resume(
            title="升级草稿",
            content="# 升级草稿",
            source_item_ids=[],
            source_resume_id=source["id"],
            database_path=self.database_path,
        )
        self.assertEqual(resume["source_resume_id"], source["id"])
        self.assertTrue(delete_resume_source(source["id"], self.database_path))
        self.assertEqual(get_resume_sources(self.database_path), [])
        self.assertEqual(get_resumes(self.database_path)[0]["id"], resume["id"])

    def test_resume_image_is_saved_locally_and_can_be_read_or_deleted(self) -> None:
        image_bytes = b"\\x89PNG\\r\\n\\x1a\\nexample-image-data"
        image = create_resume_image_source(
            filename="resume-page.png",
            content_type="image/png",
            content=image_bytes,
            database_path=self.database_path,
        )

        self.assertEqual(get_resume_image_sources(self.database_path)[0], image)
        saved_image = get_resume_image_source(image["id"], self.database_path)
        self.assertEqual(saved_image["content"], image_bytes)
        self.assertTrue(delete_resume_image_source(image["id"], self.database_path))
        self.assertIsNone(get_resume_image_source(image["id"], self.database_path))
        self.assertEqual(get_resume_image_sources(self.database_path), [])

    def test_resume_text_keeps_reference_to_confirmed_image_sources(self) -> None:
        image = create_resume_image_source(
            filename="resume-page.png",
            content_type="image/png",
            content=b"image",
            database_path=self.database_path,
        )
        source = create_resume_source(
            filename="resume-page.png（人工校对文字）",
            content="已核对的简历文字",
            source_image_ids=[image["id"], image["id"]],
            database_path=self.database_path,
        )
        self.assertEqual(source["source_image_ids"], [image["id"]])


if __name__ == "__main__":
    unittest.main()
