"""用 Chrome DevTools Protocol 做本机、用户主动触发的 BOSS 页面读取。

这里不保存账号、密码或 Cookie。Chrome 使用项目自己的用户目录，用户在窗口中完成登录，
应用只读取当前页面的公开 DOM 文本和岗位链接。先同步预览，导入仍由用户逐条确认。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import socket
import struct
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from app.config import PROJECT_ROOT
from app.services.boss_job_parser import parse_boss_job_text


class ChromeAutomationError(RuntimeError):
    """Chrome 未启动、未连接或页面无法读取。"""


_BOSS_FAVORITE_PATH = re.compile(r"^/web/geek/(?:favorite|collection)(?:/|$)", re.IGNORECASE)
_BOSS_JOB_PATH = re.compile(r"^/job_detail/([\w~-]+?)(?:\.html)?/?$", re.IGNORECASE)
_BOSS_CHAT_PATH = re.compile(r"^/web/geek/chat(?:/|$)", re.IGNORECASE)


def _is_boss_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"zhipin.com", "www.zhipin.com"}


def _is_favorite_detail(url: str) -> bool:
    parsed = urlsplit(url)
    job = _BOSS_JOB_PATH.fullmatch(parsed.path)
    return bool(
        _is_boss_url(url)
        and job
        and parse_qs(parsed.query).get("ka") == [f"personal_interest_job_{job[1]}"]
    )


def _public_boss_url(url: str) -> str:
    parsed = urlsplit(url)
    # 临时校验参数不进入预览、数据库或用户看到的状态文字。
    query = parse_qs(parsed.query)
    public_query = {} if _BOSS_JOB_PATH.fullmatch(parsed.path) else {
        key: query[key] for key in ("tab", "sub", "page", "tag") if key in query
    }
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(public_query, doseq=True), ""))


def _normalize_job_title(value: str) -> str:
    value = re.sub(r"[（(]\s*猎头职位\s*[）)]", "", value or "", flags=re.IGNORECASE)
    return re.sub(r"[\s·•\-_／/]+", "", value).strip().lower()


def _is_boss_favorite_page(url: str, body: str) -> bool:
    if not _is_boss_url(url):
        return False
    if _is_favorite_detail(url):
        return True
    parsed = urlsplit(url)
    if _BOSS_FAVORITE_PATH.search(parsed.path):
        return True
    # BOSS 当前页面把“职位收藏”放在 recommend?tab=4&sub=1。
    query = parse_qs(parsed.query)
    return (
        parsed.path.lower().rstrip("/") == "/web/geek/recommend"
        and query.get("tab") == ["4"]
        and query.get("sub") == ["1"]
        and "职位收藏" in body
    )


def _looks_logged_out(body: str) -> bool:
    markers = ("扫码登录", "登录/注册", "请登录")
    return any(marker in body for marker in markers) or (
        "发送验证码" in body and "登录" in body
    )


def _chrome_path() -> Path:
    configured = os.getenv("CHROME_EXECUTABLE", "").strip()
    candidates = [
        Path(configured) if configured else None,
        Path(os.getenv("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.getenv("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.getenv("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    raise ChromeAutomationError("没有找到 Chrome，请设置 CHROME_EXECUTABLE 或安装 Chrome。")


class _CdpSocket:
    def __init__(self, websocket_url: str, timeout: float = 10.0):
        parsed = urlsplit(websocket_url)
        if parsed.scheme != "ws" or not parsed.hostname or not parsed.port:
            raise ChromeAutomationError("Chrome 调试连接地址无效。")
        self.socket = socket.create_connection((parsed.hostname, parsed.port), timeout=timeout)
        self.socket.settimeout(timeout)
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            f"GET {parsed.path or '/'} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        self.socket.sendall(request)
        response = self._read_until(b"\r\n\r\n")
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            self.close()
            raise ChromeAutomationError("无法建立 Chrome 调试连接。")

    def _read_until(self, marker: bytes) -> bytes:
        chunks = bytearray()
        while marker not in chunks:
            chunk = self.socket.recv(4096)
            if not chunk:
                raise ChromeAutomationError("Chrome 调试连接已关闭。")
            chunks.extend(chunk)
        return bytes(chunks)

    def _read_exact(self, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            chunk = self.socket.recv(size - len(result))
            if not chunk:
                raise ChromeAutomationError("Chrome 调试连接已关闭。")
            result.extend(chunk)
        return bytes(result)

    def send(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        mask = secrets.token_bytes(4)
        length = len(body)
        if length < 126:
            header = bytes((0x81, 0x80 | length))
        elif length < 65536:
            header = bytes((0x81, 0x80 | 126)) + struct.pack(">H", length)
        else:
            header = bytes((0x81, 0x80 | 127)) + struct.pack(">Q", length)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(body))
        self.socket.sendall(header + mask + masked)

    def receive(self) -> tuple[int, bytes]:
        first, second = self._read_exact(2)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._read_exact(8))[0]
        masked = second & 0x80
        mask = self._read_exact(4) if masked else b""
        body = self._read_exact(length)
        if masked:
            body = bytes(value ^ mask[index % 4] for index, value in enumerate(body))
        return opcode, body

    def command(self, command_id: int, method: str, params: dict | None = None) -> dict:
        self.send({"id": command_id, "method": method, "params": params or {}})
        while True:
            opcode, body = self.receive()
            if opcode == 9:  # ping
                self.socket.sendall(b"\x8a" + bytes((len(body),)) + body)
                continue
            if opcode == 8:
                raise ChromeAutomationError("Chrome 调试连接已关闭。")
            if opcode != 1:
                continue
            message = json.loads(body.decode("utf-8"))
            if message.get("id") == command_id:
                if "error" in message:
                    raise ChromeAutomationError(message["error"].get("message", "Chrome 操作失败。"))
                return message.get("result", {})

    def close(self) -> None:
        try:
            self.socket.close()
        except OSError:
            pass


class ChromeController:
    def __init__(self, port: int = 9222):
        self.port = port
        self.profile_dir = PROJECT_ROOT / "data" / "chrome_profile"
        self.process: subprocess.Popen | None = None

    def _targets(self) -> list[dict]:
        try:
            with urlopen(f"http://127.0.0.1:{self.port}/json/list", timeout=1.5) as response:
                return json.load(response)
        except (OSError, URLError, ValueError) as error:
            raise ChromeAutomationError("Chrome 调试端口未连接。") from error

    def _page_target(self, predicate=None) -> dict:
        pages = [target for target in self._targets() if target.get("type") == "page"]
        if predicate is not None:
            pages = [target for target in pages if predicate(target)]
        if not pages:
            raise ChromeAutomationError("Chrome 中没有可读取的页面。")
        return pages[0]

    def connect(self) -> dict:
        try:
            target = self._page_target()
        except ChromeAutomationError:
            chrome = _chrome_path()
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            args = [
                str(chrome),
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "https://www.zhipin.com/",
            ]
            # Keep the browser independent from Uvicorn. Otherwise a reload or
            # closing the terminal can also close the debugging browser, so a
            # page refresh immediately reports it as disconnected.
            creationflags = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            )
            self.process = subprocess.Popen(
                args,
                creationflags=creationflags,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    target = self._page_target()
                    break
                except ChromeAutomationError:
                    time.sleep(0.25)
            else:
                returncode = self.process.poll()
                if returncode is None:
                    raise ChromeAutomationError("Chrome 已启动但调试端口未就绪；请稍后重试或使用岗位文字粘贴导入。")
                raise ChromeAutomationError(
                    f"Chrome 启动失败（进程退出代码 {returncode}）。请从正常桌面终端启动 FastAPI 后重试。"
                )
        return self._status_from_target(target)

    def _status_from_target(self, target: dict) -> dict:
        url = target.get("url", "")
        public_url = _public_boss_url(url)
        return {
            "connected": True,
            "url": public_url,
            "title": target.get("title", ""),
            "logged_in": None,
            "message": "Chrome 已连接。可同步收藏、打开岗位详情或继续对应岗位的沟通会话。",
        }

    def status(self) -> dict:
        try:
            return self._status_from_target(self._page_target())
        except ChromeAutomationError:
            if self.process is not None and self.process.poll() is not None:
                message = "自动同步 Chrome 进程已退出；可以继续使用岗位文字粘贴导入，或重新连接自动同步 Chrome。"
            else:
                message = "自动同步 Chrome 尚未连接；普通 Chrome 登录页不会自动连接岗位同步。"
            return {
                "connected": False,
                "url": "",
                "title": "",
                "logged_in": None,
                "message": message,
            }

    def _evaluate(self, expression: str):
        return self._evaluate_on_target(self._page_target(), expression)

    def _evaluate_on_target(self, target: dict, expression: str):
        connection = _CdpSocket(target["webSocketDebuggerUrl"])
        try:
            result = connection.command(
                1,
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True, "awaitPromise": True},
            )
            if result.get("exceptionDetails"):
                raise ChromeAutomationError("读取 BOSS 页面时发生错误，请等待页面加载完成后重试。")
            return result.get("result", {}).get("value")
        finally:
            connection.close()

    def _run_on_current_page(self, expression: str) -> dict:
        """在当前页面执行一次脚本，并保留统一的连接错误处理。"""
        result = self._evaluate(expression)
        if not isinstance(result, dict):
            raise ChromeAutomationError("读取 BOSS 页面时返回了无效结果。")
        return result

    def open_boss(self) -> dict:
        target = self._page_target()
        connection = _CdpSocket(target["webSocketDebuggerUrl"])
        try:
            connection.command(1, "Page.navigate", {"url": "https://www.zhipin.com/"})
        finally:
            connection.close()
        return self._status_from_target({**target, "url": "https://www.zhipin.com/"})

    def open_job(self, url: str) -> dict:
        parsed = urlsplit(url)
        if not (
            parsed.scheme == "https"
            and parsed.hostname in {"www.zhipin.com", "zhipin.com"}
            and _BOSS_JOB_PATH.fullmatch(parsed.path)
        ):
            raise ChromeAutomationError("该岗位没有有效的 BOSS 直聘详情链接。")
        target = self._page_target()
        public_url = _public_boss_url(url)
        connection = _CdpSocket(target["webSocketDebuggerUrl"])
        try:
            connection.command(1, "Page.navigate", {"url": public_url})
        finally:
            connection.close()
        return self._status_from_target({**target, "url": public_url})

    def _ensure_job_chat(self, expected_url: str, expected_title: str = "", expected_city: str = "") -> dict:
        """确认用户已经打开目标岗位或对应的 BOSS 沟通会话。

        这里故意不点击“立即沟通”，避免触发 BOSS 的默认招呼语。
        """
        expected = urlsplit(expected_url)
        if not (
            expected.scheme == "https"
            and expected.hostname in {"www.zhipin.com", "zhipin.com"}
            and _BOSS_JOB_PATH.fullmatch(expected.path)
        ):
            raise ChromeAutomationError("该岗位没有有效的 BOSS 直聘详情链接。")
        state = self._run_on_current_page(
            r"""(() => {
                const visible = (node) => {
                    if (!node) return false;
                    const style = getComputedStyle(node);
                    const rect = node.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden'
                        && rect.width > 0 && rect.height > 0;
                };
                const inputs = [...document.querySelectorAll('textarea, [contenteditable="true"]')]
                    .filter(visible);
                const input = inputs.find((node) => {
                    const text = `${node.getAttribute('placeholder') || ''} ${node.getAttribute('aria-label') || ''} ${node.className || ''}`;
                    return /消息|沟通|输入|chat-input/i.test(text);
                }) || (inputs.length === 1 ? inputs[0] : null);
                const body = document.body?.innerText || '';
                const buttons = [...document.querySelectorAll('button, [role="button"]')]
                    .filter(visible)
                    .filter((node) => {
                        const text = (node.innerText || node.getAttribute('aria-label') || '').trim();
                        return text === '发送' || text === '发送消息' || /发送消息/.test(text);
                    });
                const position = document.querySelector('[ka="geek_chat_job_detail"], .chat-position-content .position-content');
                return {
                    url: location.href,
                    title: document.title,
                    body,
                    has_input: Boolean(input),
                    has_send_button: buttons.length === 1,
                    input_selector: input ? (input.matches('textarea') ? 'textarea' : '[contenteditable="true"]') : '',
                    position_title: position?.querySelector('.position-name')?.innerText?.trim() || '',
                    position_city: position?.querySelector('.city')?.innerText?.trim() || '',
                };
            })()"""
        )
        current = urlsplit(str(state.get("url", "")))
        is_detail = bool(_BOSS_JOB_PATH.fullmatch(current.path))
        is_chat = bool(_BOSS_CHAT_PATH.fullmatch(current.path))
        if current.hostname not in {"www.zhipin.com", "zhipin.com"} or not (is_detail or is_chat):
            raise ChromeAutomationError("请先在专用 Chrome 中打开对应岗位详情或该岗位的沟通会话。")
        if is_detail and current.path.rstrip("/") != expected.path.rstrip("/"):
            raise ChromeAutomationError("当前 Chrome 岗位与待发送材料不匹配，请先打开对应岗位。")
        if is_chat:
            actual_title = _normalize_job_title(str(state.get("position_title", "")))
            wanted_title = _normalize_job_title(expected_title)
            if not actual_title or not wanted_title or actual_title != wanted_title:
                raise ChromeAutomationError("当前 BOSS 沟通会话与待发送岗位不匹配，请重新打开该岗位的沟通页。")
            actual_city = str(state.get("position_city", "")).strip()
            wanted_city = str(expected_city or "").strip()
            if wanted_city and actual_city != wanted_city:
                raise ChromeAutomationError("当前 BOSS 沟通会话的城市与待发送岗位不匹配，请重新打开该岗位的沟通页。")
        if not state.get("has_input"):
            raise ChromeAutomationError("尚未打开 BOSS 沟通窗口，请先点击“打开沟通并填入招呼语”并等待聊天框出现。")
        if not state.get("has_send_button"):
            raise ChromeAutomationError("已找到沟通输入框，但无法唯一确认发送按钮；请等待聊天窗口加载完成后重试。")
        if _looks_logged_out(str(state.get("body", ""))):
            raise ChromeAutomationError("当前 Chrome 可能尚未登录 BOSS，请先登录后重试。")
        return state

    def send_greeting(self, expected_url: str, greeting: str, expected_title: str = "", expected_city: str = "") -> dict:
        greeting = greeting.strip()
        if not greeting:
            raise ChromeAutomationError("打招呼语不能为空。")
        self._ensure_job_chat(expected_url, expected_title, expected_city)
        escaped = json.dumps(greeting, ensure_ascii=False)
        result = self._run_on_current_page(
            f"""(() => {{
                const text = {escaped};
                const visible = (node) => {{
                    if (!node) return false;
                    const style = getComputedStyle(node);
                    const rect = node.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                }};
                const inputs = [...document.querySelectorAll('textarea, [contenteditable="true"]')].filter(visible);
                const input = inputs.find((node) => /消息|沟通|输入|chat-input/i.test(`${{node.getAttribute('placeholder') || ''}} ${{node.getAttribute('aria-label') || ''}} ${{node.className || ''}}`)) || (inputs.length === 1 ? inputs[0] : null);
                if (!input) return {{ ok: false, message: '未找到沟通输入框。' }};
                input.focus();
                if (input.isContentEditable) input.textContent = text;
                else {{ const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set; if (setter) setter.call(input, text); else input.value = text; }}
                input.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: text }}));
                const buttons = [...document.querySelectorAll('button, [role="button"]')].filter((node) => {{
                    if (!visible(node)) return false;
                    const label = (node.innerText || node.getAttribute('aria-label') || '').trim();
                    return label === '发送' || label === '发送消息' || /发送消息/.test(label);
                }});
                if (buttons.length !== 1 || buttons[0].disabled) return {{ ok: false, message: '无法唯一确认可用的发送按钮。' }};
                buttons[0].click();
                return {{ ok: true }};
            }})()"""
        )
        if not result.get("ok"):
            raise ChromeAutomationError(str(result.get("message") or "发送打招呼语失败。"))
        return {"sent": True, "type": "greeting", "url": _public_boss_url(expected_url)}

    def prepare_greeting(self, expected_url: str, greeting: str, expected_title: str = "", expected_city: str = "") -> dict:
        """打开目标岗位沟通页并预填招呼语，但不点击发送。"""
        greeting = greeting.strip()
        if not greeting:
            raise ChromeAutomationError("打招呼语不能为空。")
        try:
            self._ensure_job_chat(expected_url, expected_title, expected_city)
        except ChromeAutomationError:
            self._open_job_chat(expected_url, expected_title, expected_city)
        return self._fill_current_chat_greeting(expected_url, greeting)

    def _open_job_chat(self, expected_url: str, expected_title: str = "", expected_city: str = "") -> None:
        """从已核对的岗位详情页点击沟通入口；明确不点击发送按钮。"""
        expected = urlsplit(expected_url)
        if not (
            expected.scheme == "https"
            and expected.hostname in {"www.zhipin.com", "zhipin.com"}
            and _BOSS_JOB_PATH.fullmatch(expected.path)
        ):
            raise ChromeAutomationError("该岗位没有有效的 BOSS 直聘详情链接。")

        self.open_job(expected_url)
        deadline = time.monotonic() + 20
        last_error = "岗位详情还在加载。"
        while time.monotonic() < deadline:
            try:
                page = self._run_on_current_page(
                    r"""(() => {
                        const visible = (node) => {
                            if (!node) return false;
                            const style = getComputedStyle(node);
                            const rect = node.getBoundingClientRect();
                            return style.display !== 'none' && style.visibility !== 'hidden'
                                && rect.width > 0 && rect.height > 0;
                        };
                        const jobTitle = document.querySelector('.job-banner .info-primary h1, .job-banner .job-title, .job-title')?.innerText?.trim() || '';
                        const city = document.querySelector('.job-banner .text-city, .info-primary .text-city')?.innerText?.trim() || '';
                        const contacts = [...document.querySelectorAll('button, [role="button"], a')]
                            .filter(visible)
                            .filter((node) => /^(立即沟通|立即联系|继续沟通|聊一聊)$/.test((node.innerText || node.getAttribute('aria-label') || '').trim()));
                        return {
                            url: location.href,
                            title: document.title,
                            body: document.body?.innerText || '',
                            job_title: jobTitle,
                            city,
                            contact_count: contacts.length,
                            logged_out: /扫码登录|登录\/注册|请登录/.test(document.body?.innerText || ''),
                        };
                    })()"""
                )
            except ChromeAutomationError as error:
                last_error = str(error)
                time.sleep(0.5)
                continue

            current = urlsplit(str(page.get("url", "")))
            if current.hostname in {"www.zhipin.com", "zhipin.com"} and current.path.rstrip("/") == expected.path.rstrip("/"):
                if page.get("logged_out") or _looks_logged_out(str(page.get("body", ""))):
                    raise ChromeAutomationError("当前 Chrome 可能尚未登录 BOSS，请先登录后重试。")
                actual_title = _normalize_job_title(str(page.get("job_title", "")))
                wanted_title = _normalize_job_title(expected_title)
                if wanted_title and actual_title and wanted_title != actual_title:
                    raise ChromeAutomationError("当前岗位详情与待投递岗位不匹配，已停止打开沟通窗口。")
                actual_city = str(page.get("city", "")).strip()
                wanted_city = str(expected_city or "").strip()
                if wanted_city and actual_city and wanted_city != actual_city:
                    raise ChromeAutomationError("当前岗位详情城市与待投递岗位不匹配，已停止打开沟通窗口。")
                contact_count = int(page.get("contact_count", 0))
                if contact_count > 1:
                    raise ChromeAutomationError("岗位详情存在多个沟通入口，无法安全确认目标按钮。")
                if contact_count == 1:
                    clicked = self._run_on_current_page(
                        r"""(() => {
                            const visible = (node) => {
                                if (!node) return false;
                                const style = getComputedStyle(node);
                                const rect = node.getBoundingClientRect();
                                return style.display !== 'none' && style.visibility !== 'hidden'
                                    && rect.width > 0 && rect.height > 0;
                            };
                            const contacts = [...document.querySelectorAll('button, [role="button"], a')]
                                .filter(visible)
                                .filter((node) => /^(立即沟通|立即联系|继续沟通|聊一聊)$/.test((node.innerText || node.getAttribute('aria-label') || '').trim()));
                            if (contacts.length !== 1 || contacts[0].disabled) return {ok: false};
                            contacts[0].click();
                            return {ok: true};
                        })()"""
                    )
                    if not clicked.get("ok"):
                        raise ChromeAutomationError("没有找到唯一且可用的岗位沟通入口；请检查 BOSS 岗位页面后重试。")
                    break
                last_error = "岗位详情已打开，但没有找到可用的沟通入口。"
            time.sleep(0.5)
        else:
            raise ChromeAutomationError(f"未能打开岗位沟通窗口：{last_error} 请确认 BOSS 已登录且岗位详情可正常访问。")

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                self._ensure_job_chat(expected_url, expected_title, expected_city)
                return
            except ChromeAutomationError as error:
                last_error = str(error)
                if "不匹配" in last_error or "尚未登录" in last_error:
                    raise
                time.sleep(0.5)
        raise ChromeAutomationError(f"已点击岗位沟通入口，但沟通窗口未就绪：{last_error}")

    def _fill_current_chat_greeting(self, expected_url: str, greeting: str) -> dict:
        escaped = json.dumps(greeting, ensure_ascii=False)
        result = self._run_on_current_page(
            f"""(() => {{
                const text = {escaped};
                const visible = (node) => {{
                    if (!node) return false;
                    const style = getComputedStyle(node);
                    const rect = node.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden'
                        && rect.width > 0 && rect.height > 0;
                }};
                const inputs = [...document.querySelectorAll('textarea, [contenteditable=\"true\"]')].filter(visible);
                const input = inputs.find((node) => /消息|沟通|输入|chat-input/i.test(`${{node.getAttribute('placeholder') || ''}} ${{node.getAttribute('aria-label') || ''}} ${{node.className || ''}}`)) || (inputs.length === 1 ? inputs[0] : null);
                if (!input) return {{ ok: false, message: '未找到沟通输入框。' }};
                input.focus();
                if (input.isContentEditable) input.textContent = text;
                else {{ const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set; if (setter) setter.call(input, text); else input.value = text; }}
                input.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: text }}));
                return {{ ok: true }};
            }})()"""
        )
        if not result.get("ok"):
            raise ChromeAutomationError(str(result.get("message") or "填入打招呼语失败。"))
        return {"prepared": True, "type": "greeting", "url": _public_boss_url(expected_url)}

    def send_resume(self, expected_url: str, filename: str, content: bytes, expected_title: str = "", expected_city: str = "") -> dict:
        if not content:
            raise ChromeAutomationError("简历附件内容为空。")
        self._ensure_job_chat(expected_url, expected_title, expected_city)
        resume_action = self._run_on_current_page(
            r"""(() => {
                const node = document.querySelector('[aria-label*="求简历"], .toolbar-btn[aria-label*="简历"]');
                if (!node) return {blocked: false};
                const label = `${node.getAttribute('aria-label') || ''} ${node.innerText || ''}`;
                return {blocked: node.classList.contains('unable') || /双方回复后可用/.test(label)};
            })()"""
        )
        if resume_action.get("blocked"):
            raise ChromeAutomationError("BOSS 当前未开放发简历，页面提示“双方回复后可用”；请等待对方回复后再发送简历。")
        import tempfile

        suffix = Path(filename).suffix or ".docx"
        with tempfile.NamedTemporaryFile(prefix="boss-resume-", suffix=suffix, delete=False) as temporary:
            temporary.write(content)
            temporary_path = temporary.name
        try:
            target = self._page_target()
            connection = _CdpSocket(target["webSocketDebuggerUrl"])
            try:
                nodes = connection.command(1, "DOM.getDocument", {"depth": 0})
                root_id = nodes.get("root", {}).get("nodeId")
                if not root_id:
                    raise ChromeAutomationError("无法读取 BOSS 页面文档。")
                found = connection.command(2, "DOM.querySelectorAll", {"nodeId": root_id, "selector": "input[type=file]"})
                file_nodes = found.get("nodeIds", [])
                candidates = []
                for index, node_id in enumerate(file_nodes, start=3):
                    attributes = connection.command(index, "DOM.getAttributes", {"nodeId": node_id}).get("attributes", [])
                    pairs = dict(zip(attributes[::2], attributes[1::2]))
                    hints = " ".join((pairs.get("accept", ""), pairs.get("id", ""), pairs.get("class", ""), pairs.get("name", ""))).lower()
                    if any(marker in hints for marker in (".doc", ".pdf", "resume", "cv")):
                        candidates.append(node_id)
                if len(candidates) == 1:
                    node_id = candidates[0]
                elif not candidates and len(file_nodes) == 1:
                    node_id = file_nodes[0]
                else:
                    raise ChromeAutomationError("无法唯一识别当前聊天窗口的简历附件入口，请在 BOSS 页面手动上传。")
                if not node_id:
                    raise ChromeAutomationError("当前沟通窗口没有找到简历附件入口。")
                connection.command(100, "DOM.setFileInputFiles", {"nodeId": node_id, "files": [temporary_path]})
            finally:
                connection.close()
            # 文件选择后 BOSS 通常显示“发送”确认按钮；再次走页面检查，避免误点其它按钮。
            result = self._run_on_current_page(
                r"""(() => {
                    const visible = (node) => { if (!node) return false; const s = getComputedStyle(node); const r = node.getBoundingClientRect(); return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
                    const button = [...document.querySelectorAll('button, [role="button"]')].find((node) => {
                        if (!visible(node)) return false;
                        const label = (node.innerText || node.getAttribute('aria-label') || '').trim();
                        return label === '发送' || label === '发送附件' || /发送附件/.test(label);
                    });
                    if (!button) return { ok: false, message: '附件已选择，但没有找到发送附件按钮，请在聊天窗口确认后重试。' };
                    button.click();
                    return { ok: true };
                })()"""
            )
            if not result.get("ok"):
                raise ChromeAutomationError(str(result.get("message") or "发送简历附件失败。"))
            return {"sent": True, "type": "resume", "filename": Path(filename).name}
        finally:
            try:
                Path(temporary_path).unlink(missing_ok=True)
            except OSError:
                pass

    def _navigate_page(self, url: str) -> None:
        target = self._page_target()
        connection = _CdpSocket(target["webSocketDebuggerUrl"])
        try:
            connection.command(1, "Page.navigate", {"url": url})
        finally:
            connection.close()

    def sync_current_page(self) -> dict:
        page = self._evaluate(
            r"""(async () => {
                const text = (doc, selectors) => {
                    for (const selector of selectors) {
                        const node = doc.querySelector(selector);
                        if (!node) continue;
                        let value;
                        if (doc === document) {
                            value = node.innerText?.trim();
                        } else {
                            const copy = node.cloneNode(true);
                            copy.querySelectorAll('br').forEach(br => br.replaceWith('\n'));
                            copy.querySelectorAll('p, div, li').forEach(block => block.append('\n'));
                            value = copy.textContent?.trim();
                        }
                        if (value) return value;
                    }
                    return '';
                };
                const readDetail = (doc) => {
                    // 未渲染的样式可能隐藏额外文字；此时只接受用户打开后实际可见的正文。
                    if (doc !== document && doc.querySelector('.job-detail .job-sec-text [class], .job-detail .job-sec-text [style]')) return '';
                    const jobTitle = text(doc, ['.job-banner .info-primary h1', '.job-banner .job-title', '.job-title']);
                    const company = (text(doc, [
                        '.job-banner .brand-name', '.job-banner .company-name',
                        '.sider-company .company-info a', '.sider-company .company-name'
                    ]) || doc.title.match(/^「.*招聘」_(.+)招聘-BOSS直聘$/)?.[1] || '')
                        .replace(/^客户公司\s*[:：]\s*/, '');
                    const city = text(doc, ['.job-banner .text-city', '.info-primary .text-city']);
                    const description = text(doc, ['.job-detail .job-sec-text']);
                    if (!jobTitle || !description) return '';
                    return `岗位名称：${jobTitle}\n公司：${company}\n城市：${city}\n职位描述：\n${description}`;
                };
                const url = new URL(location.href);
                const bodyText = document.body?.innerText || '';
                const result = { url: url.href, title: document.title, bodyText, links: [] };
                if (!['www.zhipin.com', 'zhipin.com'].includes(url.hostname)) return result;
                if (/^\/job_detail\//i.test(url.pathname)) {
                    // 详情只读取当前岗位，不扫描页面里的推荐岗位。
                    result.currentDetail = { href: url.href, detailText: readDetail(document) };
                    return result;
                }
                const isList = /^\/web\/geek\/(favorite|collection)(\/|$)/i.test(url.pathname)
                    || (url.pathname.replace(/\/$/, '') === '/web/geek/recommend'
                        && url.searchParams.get('tab') === '4' && url.searchParams.get('sub') === '1'
                        && bodyText.includes('职位收藏'));
                if (!isList) return result;
                const seen = new Set();
                const anchors = Array.from(document.querySelectorAll('a[href]')).filter(anchor => {
                    const link = new URL(anchor.href);
                    const job = link.pathname.match(/^\/job_detail\/([\w~-]+?)(?:\.html)?\/?$/i);
                    if (link.origin !== url.origin || !job || seen.has(link.pathname)) return false;
                    // 新版收藏列表也含推荐侧栏，只有收藏来源的链接才属于本次同步。
                    if (url.pathname.replace(/\/$/, '') === '/web/geek/recommend'
                        && link.searchParams.get('ka') !== `personal_interest_job_${job[1]}`) return false;
                    seen.add(link.pathname);
                    return true;
                }).slice(0, 30);
                result.links = await Promise.all(anchors.map(async (anchor) => {
                    let detailText = '';
                    try {
                        const response = await fetch(anchor.href, {
                            credentials: 'include', signal: AbortSignal.timeout(6000)
                        });
                        if (response.ok && new URL(response.url).pathname === new URL(anchor.href).pathname) {
                            const detail = new DOMParser().parseFromString(await response.text(), 'text/html');
                            detailText = readDetail(detail);
                        }
                    } catch (_) { /* 无法读取的详情交由用户打开后再次同步。 */ }
                    return { href: anchor.href, detailText };
                }));
                return result;
            })()"""
        ) or {}
        page_url = str(page.get("url", ""))
        favorite_detail = _is_favorite_detail(page_url)
        favorite_page = _is_boss_favorite_page(page_url, str(page.get("bodyText", "")))
        if not favorite_page:
            body = str(page.get("bodyText", ""))
            return {
                "connected": True,
                "url": _public_boss_url(page_url),
                "title": page.get("title", ""),
                "logged_in": not _looks_logged_out(body),
                "jobs": [],
                "warnings": ["当前页面不是 BOSS 收藏岗位页或从收藏打开的岗位详情。请打开收藏列表，或从列表进入岗位详情后再次同步。"],
            }
        links = []
        seen: set[str] = set()
        candidate_urls: set[str] = set()
        entries = [page.get("currentDetail") or {}] if favorite_detail else page.get("links", [])
        current_list = urlsplit(page_url).path.lower().rstrip("/") == "/web/geek/recommend"
        for entry in entries:
            raw_href = page_url if favorite_detail else str(entry.get("href", ""))
            if not _is_boss_url(raw_href) or not _BOSS_JOB_PATH.fullmatch(urlsplit(raw_href).path):
                continue
            if current_list and not _is_favorite_detail(raw_href):
                continue
            href = _public_boss_url(raw_href)
            candidate_urls.add(href)
            if href in seen:
                continue
            source_text = str(entry.get("detailText", ""))
            if not source_text:
                continue
            parsed = parse_boss_job_text(source_text)
            if (
                not parsed["title"]
                or len(parsed["description"].strip()) < 40
                or not any(
                    marker in parsed["description"]
                    for marker in ("岗位职责", "工作职责", "任职要求", "岗位要求", "职位描述", "职位要求")
                )
            ):
                continue
            links.append({
                **parsed,
                "warnings": ["信息取自岗位详情，请与 BOSS 原始页面核对后再导入。"],
                "raw_text": source_text,
                "original_url": href,
                "source": "BOSS 直聘（Chrome 同步）",
                "status": "收藏",
            })
            seen.add(href)
        body = str(page.get("bodyText", ""))
        looks_logged_out = _looks_logged_out(body)
        warnings = []
        if looks_logged_out:
            links = []
            warnings.append("当前 Chrome 页面可能尚未登录 BOSS，请先登录后再同步收藏岗位。")
        if links:
            warnings.append("仅显示读取到完整详情的岗位。请核对原始页面和 JD 后再导入。")
        elif not warnings:
            if favorite_detail:
                warnings.append("已识别为收藏岗位详情页，但尚未读取到完整 JD。请等待正文加载或完成页面验证后再次同步；也可手动粘贴 JD。")
            else:
                warnings.append("已识别收藏列表，但没有读取到完整 JD。请在这个 Chrome 窗口打开一条收藏岗位详情，等待正文显示后再次同步，即可读取当前岗位。")
        if links and not favorite_detail and len(links) < len(candidate_urls):
            warnings.append(f"另有 {len(candidate_urls) - len(links)} 条岗位未读取到完整 JD，可打开相应收藏详情后再次同步。")
        return {
            "connected": True,
            "url": _public_boss_url(page_url),
            "title": page.get("title", ""),
            "logged_in": not looks_logged_out,
            "jobs": links[:100],
            "warnings": warnings,
        }


_controller = ChromeController()


def connect_chrome() -> dict:
    return _controller.connect()


def chrome_status() -> dict:
    return _controller.status()


def open_boss_in_chrome() -> dict:
    return _controller.open_boss()


def open_boss_job_in_chrome(url: str) -> dict:
    return _controller.open_job(url)


def sync_boss_page() -> dict:
    return _controller.sync_current_page()


def send_boss_greeting(url: str, greeting: str, expected_title: str = "", expected_city: str = "") -> dict:
    return _controller.send_greeting(url, greeting, expected_title, expected_city)


def prepare_boss_greeting(url: str, greeting: str, expected_title: str = "", expected_city: str = "") -> dict:
    return _controller.prepare_greeting(url, greeting, expected_title, expected_city)


def send_boss_resume(url: str, filename: str, content: bytes, expected_title: str = "", expected_city: str = "") -> dict:
    return _controller.send_resume(url, filename, content, expected_title, expected_city)


def check_boss_chat(url: str, expected_title: str = "", expected_city: str = "") -> dict:
    try:
        state = _controller._ensure_job_chat(url, expected_title, expected_city)
    except ChromeAutomationError as error:
        return {"ready": False, "message": str(error)}
    return {
        "ready": True,
        "url": _public_boss_url(str(state.get("url", ""))),
        "title": state.get("title", ""),
        "message": "已识别目标岗位的沟通窗口，可以分别确认发送招呼语或简历。",
    }


