import base64
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import main
from app.schemas import ResumeImageInput, ResumeImageOcrInput


class ResumeImageApiTests(unittest.TestCase):
    def test_image_upload_checks_signature_and_removes_client_path(self) -> None:
        png = b"\x89PNG\r\n\x1a\nlocal-test-image"
        payload = ResumeImageInput(
            filename="C:\\fakepath\\resume.png",
            content_type="image/png",
            content_base64=base64.b64encode(png).decode("ascii"),
        )
        with (
            patch("main.save_private_file", return_value="test-image.png") as save_file,
            patch("main.create_resume_image_source") as create_image,
        ):
            create_image.return_value = {"id": 7, "filename": "resume.png"}
            result = main.add_resume_image(payload)

        self.assertEqual(result["id"], 7)
        self.assertEqual(create_image.call_args.kwargs["filename"], "resume.png")
        self.assertEqual(create_image.call_args.kwargs["content"], b"")
        self.assertEqual(create_image.call_args.kwargs["storage_path"], "test-image.png")
        save_file.assert_called_once_with(png, ".png")

    def test_image_upload_rejects_mismatched_content_type(self) -> None:
        payload = ResumeImageInput(
            filename="resume.png",
            content_type="image/png",
            content_base64=base64.b64encode(b"not a png").decode("ascii"),
        )
        with self.assertRaises(HTTPException) as error:
            main.add_resume_image(payload)
        self.assertEqual(error.exception.status_code, 415)

    def test_recognize_images_returns_text_without_saving_it(self) -> None:
        payload = ResumeImageOcrInput(image_ids=[3, 2, 3])
        with (
            patch("main.get_resume_image_source", side_effect=[
                {"id": 3, "filename": "page-1.png", "content": b"page one"},
                {"id": 2, "filename": "page-2.png", "content": b"page two"},
            ]),
            patch("main.recognize_resume_image", side_effect=["姓名：张三", "项目经历"]),
        ):
            result = main.recognize_resume_images(payload)

        self.assertEqual(
            result["results"],
            [
                {"id": 3, "filename": "page-1.png", "text": "姓名：张三"},
                {"id": 2, "filename": "page-2.png", "text": "项目经历"},
            ],
        )

    def test_recognize_images_reports_missing_image(self) -> None:
        with patch("main.get_resume_image_source", return_value=None):
            with self.assertRaises(HTTPException) as error:
                main.recognize_resume_images(ResumeImageOcrInput(image_ids=[99]))
        self.assertEqual(error.exception.status_code, 404)

    def test_recognize_images_reports_missing_local_ocr_dependency(self) -> None:
        with (
            patch("main.get_resume_image_source", return_value={
                "id": 1, "filename": "page.png", "content": b"image"
            }),
            patch("main.recognize_resume_image", side_effect=ImportError("not installed")),
        ):
            with self.assertRaises(HTTPException) as error:
                main.recognize_resume_images(ResumeImageOcrInput(image_ids=[1]))
        self.assertEqual(error.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
