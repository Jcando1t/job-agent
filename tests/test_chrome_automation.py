import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import main
from app.services.chrome_automation import ChromeAutomationError, ChromeController


class ChromeAutomationApiTests(unittest.TestCase):
    def test_browser_status_is_exposed_without_starting_chrome(self) -> None:
        status = {"connected": False, "url": "", "title": "", "logged_in": None, "message": "Chrome 尚未连接。"}
        with patch("main.chrome_status", return_value=status):
            self.assertEqual(main.boss_browser_status(), status)

    def test_connect_error_is_a_readable_service_error(self) -> None:
        with patch("main.connect_chrome", side_effect=main.ChromeAutomationError("没有找到 Chrome")):
            with self.assertRaises(HTTPException) as error:
                main.connect_boss_browser()
        self.assertEqual(error.exception.status_code, 503)
        self.assertIn("没有找到 Chrome", error.exception.detail)

    def test_sync_returns_preview_without_importing_jobs(self) -> None:
        preview = {
            "connected": True,
            "url": "https://www.zhipin.com/web/geek/favorite",
            "title": "收藏",
            "logged_in": True,
            "jobs": [{"title": "AI 工程师", "original_url": "https://www.zhipin.com/job_detail/1"}],
            "warnings": [],
        }
        with patch("main.sync_boss_page", return_value=preview):
            result = main.sync_boss_browser()
        self.assertEqual(result["jobs"][0]["title"], "AI 工程师")

    def test_open_job_api_uses_the_dedicated_chrome_controller(self) -> None:
        result = {"connected": True, "url": "https://www.zhipin.com/job_detail/abc.html", "title": "AI 工程师"}
        payload = main.BossJobUrlInput(url=" https://www.zhipin.com/job_detail/abc.html ")
        with patch("main.open_boss_job_in_chrome", return_value=result) as opener:
            self.assertEqual(main.open_boss_job_browser(payload), result)
        opener.assert_called_once_with("https://www.zhipin.com/job_detail/abc.html")

    def test_open_job_api_rejects_invalid_links_as_client_errors(self) -> None:
        with patch(
            "main.open_boss_job_in_chrome",
            side_effect=ChromeAutomationError("该岗位没有有效的 BOSS 直聘详情链接。"),
        ):
            with self.assertRaises(HTTPException) as error:
                main.open_boss_job_browser(main.BossJobUrlInput(url="https://example.com/"))
        self.assertEqual(error.exception.status_code, 422)

    def test_greeting_requires_explicit_confirmation(self) -> None:
        from app.schemas import BossGreetingSendInput

        with self.assertRaises(HTTPException) as error:
            main.send_boss_greeting_api(BossGreetingSendInput(
                job_id=1, resume_id=2, greeting="你好", confirmed=False,
            ))
        self.assertEqual(error.exception.status_code, 400)

    def test_greeting_requires_resume_for_the_same_job(self) -> None:
        from app.schemas import BossGreetingSendInput

        job = {"id": 1, "original_url": "https://www.zhipin.com/job_detail/abc.html"}
        resume = {"id": 2, "title": "定制版", "content": "# 简历", "job_snapshot": {"job_id": 9}}
        with patch("main.get_job", return_value=job), patch("main.get_resume", return_value=resume):
            with self.assertRaises(HTTPException) as error:
                main.send_boss_greeting_api(BossGreetingSendInput(
                    job_id=1, resume_id=2, greeting="你好", confirmed=True,
                ))
        self.assertEqual(error.exception.status_code, 409)

    def test_greeting_sends_only_after_materials_match(self) -> None:
        from app.schemas import BossGreetingSendInput

        job = {"id": 1, "original_url": "https://www.zhipin.com/job_detail/abc.html"}
        resume = {"id": 2, "title": "定制版", "content": "# 简历", "job_snapshot": {"job_id": 1}}
        with patch("main.get_job", return_value=job), patch("main.get_resume", return_value=resume), patch(
            "main.send_boss_greeting", return_value={"sent": True, "type": "greeting"}
        ) as sender:
            result = main.send_boss_greeting_api(BossGreetingSendInput(
                job_id=1, resume_id=2, greeting="你好", confirmed=True,
            ))
        self.assertTrue(result["sent"])
        sender.assert_called_once_with(job["original_url"], "你好")

    def test_delivery_accepts_the_current_resume_for_the_jobs_target(self) -> None:
        job = {"id": 1, "target_id": 3, "original_url": "https://www.zhipin.com/job_detail/abc.html"}
        resume = {
            "id": 2,
            "title": "AI 方向简历",
            "content": "# 简历",
            "target_id": 3,
            "is_current": True,
            "job_snapshot": {},
        }
        with patch("main.get_job", return_value=job), patch("main.get_resume", return_value=resume):
            self.assertEqual(main._delivery_materials(1, 2), (job, resume))

    def test_delivery_rejects_a_current_resume_from_another_target(self) -> None:
        job = {"id": 1, "target_id": 3, "original_url": "https://www.zhipin.com/job_detail/abc.html"}
        resume = {
            "id": 2,
            "title": "其他方向简历",
            "content": "# 简历",
            "target_id": 4,
            "is_current": True,
            "job_snapshot": {},
        }
        with patch("main.get_job", return_value=job), patch("main.get_resume", return_value=resume):
            with self.assertRaises(HTTPException) as error:
                main._delivery_materials(1, 2)
        self.assertEqual(error.exception.status_code, 409)

    def test_prepare_greeting_requires_matching_materials_and_does_not_send(self) -> None:
        from app.schemas import BossGreetingPrepareInput

        job = {"id": 1, "original_url": "https://www.zhipin.com/job_detail/abc.html"}
        resume = {"id": 2, "title": "定制版", "content": "# 简历", "job_snapshot": {"job_id": 1}}
        with patch("main.get_job", return_value=job), patch("main.get_resume", return_value=resume), patch(
            "main.prepare_boss_greeting", return_value={"prepared": True, "type": "greeting"}
        ) as preparer:
            result = main.prepare_boss_greeting_api(BossGreetingPrepareInput(
                job_id=1, resume_id=2, greeting="  您好  ",
            ))
        self.assertTrue(result["prepared"])
        self.assertEqual(result["message"], "已打开对应岗位沟通页并填入打招呼语，尚未发送。")
        preparer.assert_called_once_with(job["original_url"], "您好")

    def test_resume_send_passes_only_matching_approved_version_to_chrome(self) -> None:
        from app.schemas import BossResumeSendInput

        job = {"id": 1, "original_url": "https://www.zhipin.com/job_detail/abc.html"}
        resume = {"id": 2, "title": "定制版", "content": "# 简历", "job_snapshot": {"job_id": 1}}
        with patch("main.get_job", return_value=job), patch("main.get_resume", return_value=resume), patch(
            "main.send_boss_resume", return_value={"sent": True, "type": "resume"}
        ) as sender:
            result = main.send_boss_resume_api(BossResumeSendInput(
                job_id=1, resume_id=2, confirmed=True,
            ))
        self.assertTrue(result["sent"])
        self.assertEqual(sender.call_args.args[0], job["original_url"])
        self.assertEqual(sender.call_args.args[1], "定制版.docx")
        self.assertTrue(sender.call_args.args[2])

    def test_chat_route_accepts_matching_job_card(self) -> None:
        controller = ChromeController()
        state = {
            "url": "https://www.zhipin.com/web/geek/chat",
            "title": "BOSS直聘",
            "body": "AI大模型应用（RAG与智能体方向）（猎头职位）\n天津",
            "has_input": True,
            "has_send_button": True,
            "position_title": "AI大模型应用（RAG与智能体方向）（猎头职位）",
            "position_city": "天津",
        }
        with patch.object(controller, "_evaluate", return_value=state):
            result = controller._ensure_job_chat(
                "https://www.zhipin.com/job_detail/target.html",
                "AI大模型应用（RAG与智能体方向）",
                "天津",
            )
        self.assertEqual(result["position_city"], "天津")

    def test_chat_route_rejects_different_job_card(self) -> None:
        controller = ChromeController()
        with patch.object(controller, "_evaluate", return_value={
            "url": "https://www.zhipin.com/web/geek/chat",
            "title": "BOSS直聘",
            "body": "其他岗位",
            "has_input": True,
            "has_send_button": True,
            "position_title": "其他岗位",
        }):
            with self.assertRaisesRegex(ChromeAutomationError, "沟通会话与待发送岗位不匹配"):
                controller._ensure_job_chat(
                    "https://www.zhipin.com/job_detail/target.html", "目标岗位", "北京"
                )

    def test_prepare_greeting_fills_chat_input_without_clicking_send(self) -> None:
        controller = ChromeController()
        with patch.object(controller, "_ensure_job_chat"), patch.object(
            controller, "_run_on_current_page", return_value={"ok": True}
        ) as evaluate:
            result = controller.prepare_greeting(
                "https://www.zhipin.com/job_detail/target.html", "您好，想进一步沟通。"
            )

        self.assertTrue(result["prepared"])
        script = evaluate.call_args.args[0]
        self.assertIn("dispatchEvent(new InputEvent('input'", script)
        self.assertNotIn("buttons[0].click", script)

    def test_prepare_greeting_opens_matching_job_chat_and_only_prefills(self) -> None:
        controller = ChromeController()
        detail = {
            "url": "https://www.zhipin.com/job_detail/target.html",
            "title": "目标岗位",
            "body": "",
            "job_title": "目标岗位",
            "city": "天津",
            "contact_count": 1,
            "logged_out": False,
        }
        with (
            patch.object(controller, "_ensure_job_chat", side_effect=[ChromeAutomationError("尚未打开沟通窗口"), None]) as ensure,
            patch.object(controller, "open_job") as open_job,
            patch.object(controller, "_run_on_current_page", side_effect=[detail, {"ok": True}]) as evaluate,
            patch.object(controller, "_fill_current_chat_greeting", return_value={"prepared": True, "type": "greeting"}) as fill,
        ):
            result = controller.prepare_greeting(
                "https://www.zhipin.com/job_detail/target.html",
                "您好，想进一步沟通。",
                "目标岗位",
                "天津",
            )

        self.assertTrue(result["prepared"])
        open_job.assert_called_once_with("https://www.zhipin.com/job_detail/target.html")
        ensure.assert_called()
        click_script = evaluate.call_args.args[0]
        self.assertIn("contacts[0].click()", click_script)
        self.assertNotIn("发送", click_script)
        fill.assert_called_once_with("https://www.zhipin.com/job_detail/target.html", "您好，想进一步沟通。")

    def test_prepare_greeting_does_not_open_chat_for_mismatched_job(self) -> None:
        controller = ChromeController()
        detail = {
            "url": "https://www.zhipin.com/job_detail/target.html",
            "title": "其他岗位",
            "body": "",
            "job_title": "其他岗位",
            "city": "天津",
            "contact_count": 1,
            "logged_out": False,
        }
        with (
            patch.object(controller, "_ensure_job_chat", side_effect=ChromeAutomationError("尚未打开沟通窗口")),
            patch.object(controller, "open_job"),
            patch.object(controller, "_run_on_current_page", return_value=detail) as evaluate,
        ):
            with self.assertRaisesRegex(ChromeAutomationError, "详情与待投递岗位不匹配"):
                controller.prepare_greeting(
                    "https://www.zhipin.com/job_detail/target.html", "你好", "目标岗位", "天津"
                )
        self.assertEqual(evaluate.call_count, 1)

    def test_prepare_greeting_stops_when_contact_entry_is_ambiguous(self) -> None:
        controller = ChromeController()
        detail = {
            "url": "https://www.zhipin.com/job_detail/target.html",
            "title": "目标岗位",
            "body": "",
            "job_title": "目标岗位",
            "city": "天津",
            "contact_count": 2,
            "logged_out": False,
        }
        with (
            patch.object(controller, "_ensure_job_chat", side_effect=ChromeAutomationError("尚未打开沟通窗口")),
            patch.object(controller, "open_job"),
            patch.object(controller, "_run_on_current_page", return_value=detail) as evaluate,
        ):
            with self.assertRaisesRegex(ChromeAutomationError, "多个沟通入口"):
                controller.prepare_greeting(
                    "https://www.zhipin.com/job_detail/target.html", "你好", "目标岗位", "天津"
                )
        self.assertEqual(evaluate.call_count, 1)

    def test_resume_send_explains_boss_reply_requirement(self) -> None:
        controller = ChromeController()
        with patch.object(controller, "_ensure_job_chat"), patch.object(
            controller, "_run_on_current_page", return_value={"blocked": True}
        ):
            with self.assertRaisesRegex(ChromeAutomationError, "双方回复后可用"):
                controller.send_resume(
                    "https://www.zhipin.com/job_detail/target.html",
                    "resume.docx",
                    b"docx",
                    "目标岗位",
                    "天津",
                )

    def test_send_greeting_rejects_wrong_current_job_or_closed_chat(self) -> None:
        controller = ChromeController()
        with patch.object(controller, "_evaluate", return_value={
            "url": "https://www.zhipin.com/job_detail/other.html",
            "title": "其他岗位",
            "body": "",
            "has_input": True,
            "has_send_button": True,
        }):
            with self.assertRaisesRegex(ChromeAutomationError, "不匹配"):
                controller.send_greeting(
                    "https://www.zhipin.com/job_detail/target.html", "你好"
                )

    def test_send_greeting_requires_user_opened_chat(self) -> None:
        controller = ChromeController()
        with patch.object(controller, "_evaluate", return_value={
            "url": "https://www.zhipin.com/job_detail/target.html",
            "title": "目标岗位",
            "body": "",
            "has_input": False,
            "has_send_button": False,
        }):
            with self.assertRaisesRegex(ChromeAutomationError, "打开沟通并填入招呼语"):
                controller.send_greeting(
                    "https://www.zhipin.com/job_detail/target.html", "你好"
                )

    def test_send_greeting_does_not_click_when_send_button_is_ambiguous(self) -> None:
        controller = ChromeController()
        with patch.object(controller, "_evaluate", side_effect=[
            {"url": "https://www.zhipin.com/job_detail/target.html", "title": "目标岗位", "body": "", "has_input": True, "has_send_button": True},
            {"ok": False, "message": "无法唯一确认可用的发送按钮。"},
        ]):
            with self.assertRaisesRegex(ChromeAutomationError, "唯一确认"):
                controller.send_greeting(
                    "https://www.zhipin.com/job_detail/target.html", "你好"
                )

    def test_login_page_is_not_reported_as_logged_in_on_non_favorite_page(self) -> None:
        page = {
            "url": "https://www.zhipin.com/job_detail/abc123.html",
            "title": "岗位详情",
            "bodyText": "手机号\n发送验证码\n登录",
        }
        with patch.object(ChromeController, "_evaluate", return_value=page):
            result = ChromeController().sync_current_page()

        self.assertFalse(result["logged_in"])

    def test_open_job_navigates_dedicated_chrome_and_drops_temporary_parameters(self) -> None:
        target = {"webSocketDebuggerUrl": "ws://localhost/test"}
        with patch.object(ChromeController, "_page_target", return_value=target), patch(
            "app.services.chrome_automation._CdpSocket"
        ) as connection:
            result = ChromeController().open_job(
                "https://www.zhipin.com/job_detail/abc123.html?securityId=secret&_security_check=1"
            )

        connection.return_value.command.assert_called_once_with(
            1,
            "Page.navigate",
            {"url": "https://www.zhipin.com/job_detail/abc123.html"},
        )
        connection.return_value.close.assert_called_once()
        self.assertTrue(result["connected"])

    def test_open_job_rejects_non_boss_and_non_detail_urls(self) -> None:
        with patch.object(ChromeController, "_page_target") as page_target:
            for url in (
                "https://example.com/job_detail/abc.html",
                "https://www.zhipin.com/web/geek/favorite",
                "http://www.zhipin.com/job_detail/abc.html",
            ):
                with self.subTest(url=url), self.assertRaisesRegex(ChromeAutomationError, "有效的 BOSS"):
                    ChromeController().open_job(url)
        page_target.assert_not_called()

    def test_page_script_error_is_not_misreported_as_wrong_page(self) -> None:
        with patch.object(ChromeController, "_page_target", return_value={"webSocketDebuggerUrl": "ws://localhost/test"}), patch(
            "app.services.chrome_automation._CdpSocket"
        ) as connection:
            connection.return_value.command.return_value = {"exceptionDetails": {"text": "script failed"}}
            with self.assertRaisesRegex(ChromeAutomationError, "读取 BOSS 页面"):
                ChromeController().sync_current_page()
            connection.return_value.close.assert_called_once()

    def test_recommendation_page_is_rejected_even_if_it_contains_favorite_text(self) -> None:
        page = {
            "url": "https://www.zhipin.com/web/geek/recommend",
            "title": "职位推荐",
            "bodyText": "你收藏的职位推荐如下",
            "links": [{"href": "https://www.zhipin.com/job_detail/1", "text": "周女士\n职位推荐"}],
        }
        with patch.object(ChromeController, "_evaluate", return_value=page):
            result = ChromeController().sync_current_page()

        self.assertEqual(result["jobs"], [])
        self.assertIn("不是 BOSS 收藏岗位页", result["warnings"][0])

    def test_current_boss_favorites_route_is_recognized(self) -> None:
        from app.services.chrome_automation import _is_boss_favorite_page

        self.assertTrue(_is_boss_favorite_page(
            "https://www.zhipin.com/web/geek/recommend?tab=4&sub=1&page=1&tag=4",
            "职位收藏\n公司收藏",
        ))
        self.assertFalse(_is_boss_favorite_page(
            "https://www.zhipin.com/web/geek/recommend?tab=4&sub=1&page=1&tag=4",
            "职位推荐\n你收藏的职位推荐",
        ))

    def test_only_matching_boss_favorite_origin_details_are_recognized(self) -> None:
        from app.services.chrome_automation import _is_boss_favorite_page

        for suffix in ("", ".html"):
            with self.subTest(suffix=suffix):
                self.assertTrue(_is_boss_favorite_page(
                    f"https://www.zhipin.com/job_detail/abc123{suffix}?ka=personal_interest_job_abc123",
                    "AI 应用工程师\n职位描述",
                ))
        rejected_urls = (
            "https://www.zhipin.com/job_detail/abc123.html",
            "https://www.zhipin.com/job_detail/abc123.html?ka=search_list_1",
            "https://www.zhipin.com/job_detail/abc123.html?ka=personal_interest_job_other",
            "https://example.com/job_detail/abc123.html?ka=personal_interest_job_abc123",
            "https://www.zhipin.com.example.com/job_detail/abc123.html?ka=personal_interest_job_abc123",
            "https://example.com/web/geek/favorite",
            "https://example.com/web/geek/recommend?tab=4&sub=1",
        )
        for url in rejected_urls:
            with self.subTest(url=url):
                self.assertFalse(_is_boss_favorite_page(url, "职位收藏\n职位描述"))

    def test_favorite_page_does_not_import_card_summary_as_job_details(self) -> None:
        page = {
            "url": "https://www.zhipin.com/web/geek/favorite",
            "title": "收藏的职位",
            "bodyText": "AI 应用工程师",
            "links": [{
                "href": "https://www.zhipin.com/job_detail/1",
                "text": "周女士\nAI 应用工程师\n15-25K\n北京",
            }],
        }
        with patch.object(ChromeController, "_evaluate", return_value=page):
            result = ChromeController().sync_current_page()

        self.assertEqual(result["jobs"], [])
        self.assertIn("完整 JD", result["warnings"][0])
        self.assertIn("打开", result["warnings"][0])
        self.assertIn("再次同步", result["warnings"][0])

    def test_favorite_page_uses_detail_text_for_import_preview(self) -> None:
        page = {
            "url": "https://www.zhipin.com/web/geek/favorite?ka=header-favorite",
            "title": "收藏的职位",
            "bodyText": "收藏的职位",
            "links": [{
                "href": "https://www.zhipin.com/job_detail/1",
                "text": "周女士\nAI 应用工程师\n15-25K\n北京",
                "detailText": (
                    "岗位名称：AI 应用工程师\n公司：示例科技\n城市：北京\n岗位职责：\n"
                    "负责建设 Python 服务和 RAG 应用，推动系统上线并持续优化稳定性。"
                ),
            }],
        }
        with patch.object(ChromeController, "_evaluate", return_value=page):
            result = ChromeController().sync_current_page()

        self.assertEqual(result["jobs"][0]["title"], "AI 应用工程师")
        self.assertEqual(result["jobs"][0]["company"], "示例科技")
        self.assertEqual(result["jobs"][0]["city"], "北京")
        self.assertIn("RAG", result["jobs"][0]["description"])

    def test_favorite_origin_detail_reads_current_job_not_recommendations(self) -> None:
        page_url = (
            "https://www.zhipin.com/job_detail/abc123.html?ka=personal_interest_job_abc123"
            "&securityId=temporary-value&_security_check=123&other=tracking#position"
        )
        detail_text = (
            "岗位名称：收藏的 AI 应用工程师\n公司：示例科技\n城市：天津\n岗位职责：\n"
            "负责建设 Python 服务和 RAG 应用，推动系统上线并持续优化稳定性，"
            "参与需求分析、接口设计和生产问题排查。"
        )
        page = {
            "url": page_url,
            "title": "收藏的 AI 应用工程师",
            "bodyText": "职位描述\nAI 应用工程师",
            "currentDetail": {"href": page_url, "detailText": detail_text},
            "links": [{
                "href": "https://www.zhipin.com/job_detail/recommended.html",
                "detailText": detail_text.replace("收藏的 AI 应用工程师", "推荐栏中的其他职位"),
            }],
        }
        with patch.object(ChromeController, "_evaluate", return_value=page):
            result = ChromeController().sync_current_page()

        self.assertEqual(len(result["jobs"]), 1)
        job = result["jobs"][0]
        self.assertEqual(job["title"], "收藏的 AI 应用工程师")
        self.assertEqual(job["company"], "示例科技")
        self.assertEqual(job["city"], "天津")
        self.assertEqual(job["original_url"], "https://www.zhipin.com/job_detail/abc123.html")
        self.assertEqual(result["url"], "https://www.zhipin.com/job_detail/abc123.html")
        self.assertEqual(job["raw_text"], detail_text)
        self.assertIn("参与需求分析", job["description"])

    def test_incomplete_favorite_detail_keeps_favorite_context(self) -> None:
        page_url = "https://www.zhipin.com/job_detail/abc123.html?ka=personal_interest_job_abc123"
        for detail_text in ("", "岗位名称：AI 应用工程师\n岗位职责：\n天津", "安全验证"):
            with self.subTest(detail_text=detail_text):
                page = {
                    "url": page_url,
                    "title": "AI 应用工程师",
                    "bodyText": detail_text,
                    "currentDetail": {"href": page_url, "detailText": detail_text},
                    "links": [],
                }
                with patch.object(ChromeController, "_evaluate", return_value=page):
                    result = ChromeController().sync_current_page()

                self.assertEqual(result["jobs"], [])
                warning = "\n".join(result["warnings"])
                self.assertIn("收藏岗位详情页", warning)
                self.assertIn("完整 JD", warning)
                self.assertNotIn("不是 BOSS 收藏岗位页", warning)

    def test_favorite_list_deduplicates_same_job_with_different_queries(self) -> None:
        detail_text = (
            "岗位名称：AI 应用工程师\n公司：示例科技\n城市：北京\n岗位职责：\n"
            "负责建设 Python 服务和 RAG 应用，推动系统上线并持续优化稳定性，"
            "参与需求分析、接口设计和生产问题排查。"
        )
        page = {
            "url": "https://www.zhipin.com/web/geek/recommend?tab=4&sub=1&page=1&tag=4",
            "title": "职位收藏",
            "bodyText": "职位收藏\n公司收藏",
            "links": [
                {
                    "href": "https://www.zhipin.com/job_detail/abc123.html?ka=personal_interest_job_abc123&securityId=one",
                    "detailText": detail_text,
                },
                {
                    "href": "https://www.zhipin.com/job_detail/abc123.html?ka=personal_interest_job_abc123&securityId=two#job",
                    "detailText": detail_text,
                },
            ],
        }
        with patch.object(ChromeController, "_evaluate", return_value=page):
            result = ChromeController().sync_current_page()

        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0]["original_url"], "https://www.zhipin.com/job_detail/abc123.html")

    def test_current_favorite_list_excludes_recommendation_sidebar_jobs(self) -> None:
        detail_text = (
            "岗位名称：收藏的 AI 工程师\n公司：示例科技\n城市：天津\n岗位职责：\n"
            "负责建设 Python 服务和 RAG 应用，推动系统上线并持续优化稳定性，"
            "参与需求分析、接口设计和生产问题排查。"
        )
        page = {
            "url": "https://www.zhipin.com/web/geek/recommend?tab=4&sub=1&page=1&tag=4",
            "title": "职位收藏",
            "bodyText": "职位收藏\n公司收藏\n相关推荐",
            "links": [
                {
                    "href": "https://www.zhipin.com/job_detail/recommended.html",
                    "detailText": detail_text.replace("收藏的 AI 工程师", "推荐栏岗位"),
                },
                {
                    "href": "https://www.zhipin.com/job_detail/favorite.html?ka=personal_interest_job_favorite",
                    "detailText": detail_text,
                },
            ],
        }
        with patch.object(ChromeController, "_evaluate", return_value=page):
            result = ChromeController().sync_current_page()

        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0]["title"], "收藏的 AI 工程师")
        self.assertEqual(result["jobs"][0]["original_url"], "https://www.zhipin.com/job_detail/favorite.html")
        self.assertNotIn("另有", "\n".join(result["warnings"]))

    def test_current_favorite_list_with_only_recommendations_imports_nothing(self) -> None:
        page = {
            "url": "https://www.zhipin.com/web/geek/recommend?tab=4&sub=1",
            "title": "职位收藏",
            "bodyText": "职位收藏\n公司收藏\n相关推荐",
            "links": [{
                "href": "https://www.zhipin.com/job_detail/recommended.html",
                "detailText": (
                    "岗位名称：推荐栏岗位\n公司：示例科技\n城市：天津\n岗位职责：\n"
                    "负责建设 Python 服务和 RAG 应用，推动系统上线并持续优化稳定性，"
                    "参与需求分析、接口设计和生产问题排查。"
                ),
            }],
        }
        with patch.object(ChromeController, "_evaluate", return_value=page):
            result = ChromeController().sync_current_page()

        self.assertEqual(result["jobs"], [])
        warning = "\n".join(result["warnings"])
        self.assertIn("收藏列表", warning)
        self.assertIn("再次同步", warning)

    def test_partial_list_warning_counts_unique_favorites_not_recommendations(self) -> None:
        detail_text = (
            "岗位名称：AI 工程师\n公司：示例科技\n城市：天津\n岗位职责：\n"
            "负责建设 Python 服务和 RAG 应用，推动系统上线并持续优化稳定性，"
            "参与需求分析、接口设计和生产问题排查。"
        )
        page = {
            "url": (
                "https://www.zhipin.com/web/geek/recommend?tab=4&sub=1&page=1&tag=4"
                "&securityId=temporary&_security_check=123#jobs"
            ),
            "title": "职位收藏",
            "bodyText": "职位收藏\n公司收藏",
            "links": [
                {
                    "href": f"https://www.zhipin.com/job_detail/{job_id}.html?ka=personal_interest_job_{job_id}&securityId={query}",
                    "detailText": detail_text if job_id == "complete" else "",
                }
                for job_id in ("complete", "incomplete") for query in ("first", "second")
            ] + [{
                "href": "https://www.zhipin.com/job_detail/recommended.html",
                "detailText": detail_text,
            }],
        }
        with patch.object(ChromeController, "_evaluate", return_value=page):
            result = ChromeController().sync_current_page()

        self.assertEqual(len(result["jobs"]), 1)
        self.assertIn("另有 1 条岗位未读取到完整 JD", "\n".join(result["warnings"]))
        self.assertEqual(
            result["url"],
            "https://www.zhipin.com/web/geek/recommend?tab=4&sub=1&page=1&tag=4",
        )


if __name__ == "__main__":
    unittest.main()
