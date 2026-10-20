import unittest
from unittest.mock import patch

from fastapi import HTTPException

import main
from app.schemas import JobInput


class JobApiTests(unittest.TestCase):
    def test_duplicate_job_is_rejected_by_api(self) -> None:
        with patch("main.create_job", return_value={"id": 1, "duplicate": True}):
            with self.assertRaises(HTTPException) as error:
                main.add_job(JobInput(title="后端工程师", original_url="https://example.com/job/1"))
        self.assertEqual(error.exception.status_code, 409)

    def test_status_and_original_url_are_passed_to_database(self) -> None:
        created = {"id": 2, "status": "收藏", "original_url": "https://example.com/job/2"}
        with patch("main.create_job", return_value=created) as create:
            result = main.add_job(
                JobInput(title="AI 工程师", status="收藏", original_url="https://example.com/job/2")
            )
        self.assertEqual(result, created)
        self.assertEqual(create.call_args.kwargs["status"], "收藏")
        self.assertEqual(create.call_args.kwargs["original_url"], "https://example.com/job/2")

    def test_follow_up_fields_are_passed_to_database(self) -> None:
        created = {"id": 3, "status": "收藏", "notes": "待核实", "next_action": "明天查看"}
        with patch("main.create_job", return_value=created) as create:
            main.add_job(
                JobInput(title="AI 工程师", notes="待核实", next_action="明天查看")
            )
        self.assertEqual(create.call_args.kwargs["notes"], "待核实")
        self.assertEqual(create.call_args.kwargs["next_action"], "明天查看")

    def test_duplicate_job_update_is_reported_as_conflict(self) -> None:
        with patch("main.update_job", return_value={"id": 1, "duplicate": True}):
            with self.assertRaises(HTTPException) as error:
                main.edit_job(1, JobInput(title="后端工程师", original_url="https://example.com/job/1"))
        self.assertEqual(error.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
