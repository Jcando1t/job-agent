import unittest
from pathlib import Path

from app.database import (
    create_target,
    delete_target,
    get_targets,
    initialize_database,
    set_target_active,
    update_target,
)


class JobTargetDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_path = Path(__file__).resolve().parent / "job_targets_test.db"
        self.database_path.unlink(missing_ok=True)
        initialize_database(self.database_path)

    def tearDown(self) -> None:
        self.database_path.unlink(missing_ok=True)

    def test_target_is_saved_and_available_after_reopening_database(self) -> None:
        created = create_target(
            title="Agent 应用开发",
            keywords="Python, LLM",
            cities=["北京", "天津"],
            database_path=self.database_path,
        )

        initialize_database(self.database_path)
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


if __name__ == "__main__":
    unittest.main()
