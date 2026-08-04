"""只监听本机的网页刷机服务。"""

from __future__ import annotations

import json
import mimetypes
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .workflow import FlashWorkflow, WorkflowError


MAX_BODY = 64 * 1024
STATIC_DIR = Path(__file__).resolve().parent / "static"


class WebFlashServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], workflow: FlashWorkflow, access_token: str | None = None) -> None:
        if address[0] != "127.0.0.1":
            raise ValueError("网页刷机服务只能监听 127.0.0.1")
        self.workflow = workflow
        self.access_token = access_token or secrets.token_urlsafe(32)
        self.session_value: str | None = None
        super().__init__(address, WebFlashHandler)


class WebFlashHandler(BaseHTTPRequestHandler):
    server: WebFlashServer

    def log_message(self, format: str, *args: Any) -> None:
        return None

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _cookies(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in self.headers.get("Cookie", "").split(";"):
            if "=" in item:
                key, value = item.strip().split("=", 1)
                result[key] = value
        return result

    def _authorized(self) -> bool:
        return self.server.session_value is not None and secrets.compare_digest(
            self._cookies().get("ap01_session", ""), self.server.session_value
        )

    def _require_write(self) -> bool:
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "本次访问凭证无效"})
            return False
        expected = f"http://127.0.0.1:{self.server.server_port}"
        if self.headers.get("Origin") != expected:
            self._json(HTTPStatus.FORBIDDEN, {"error": "修改请求来源无效"})
            return False
        return True

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise WorkflowError("请求体长度无效") from exc
        if length < 0 or length > MAX_BODY:
            raise WorkflowError("请求体超过固定上限")
        if length == 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise WorkflowError("请求体无法解析") from exc
        if not isinstance(payload, dict):
            raise WorkflowError("请求体不是对象")
        return payload

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            token = parse_qs(parsed.query).get("access", [""])[0]
            if not secrets.compare_digest(token, self.server.access_token):
                self.send_error(HTTPStatus.UNAUTHORIZED)
                return
            if self.server.session_value is None:
                self.server.session_value = secrets.token_urlsafe(32)
            self._static("index.html", set_cookie=True)
            return
        if parsed.path.startswith("/static/"):
            self._static(parsed.path.removeprefix("/static/"))
            return
        if parsed.path == "/api/v1/session":
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "本次访问凭证无效"})
                return
            self._json(HTTPStatus.OK, self.server.workflow.snapshot())
            return
        if parsed.path == "/api/v1/device/login-qr":
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "本次访问凭证无效"})
                return
            selected = self.server.workflow.qr_path
            if not selected.is_file() or not self.server.workflow.snapshot().get("qr_available"):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = selected.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path.startswith("/api/v1/operations/"):
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "本次访问凭证无效"})
                return
            operation_id = parsed.path.rsplit("/", 1)[-1]
            snapshot = self.server.workflow.snapshot()
            if snapshot.get("operation_id") != operation_id:
                self._json(HTTPStatus.NOT_FOUND, {"error": "操作不存在"})
            else:
                self._json(HTTPStatus.OK, snapshot)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _static(self, name: str, *, set_cookie: bool = False) -> None:
        if not name or Path(name).name != name:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        selected = STATIC_DIR / name
        if not selected.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = selected.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(selected.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if set_cookie:
            self.send_header("Set-Cookie", f"ap01_session={self.server.session_value}; HttpOnly; SameSite=Strict; Path=/")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if not self._require_write():
            return
        try:
            payload = self._body()
            path = urlparse(self.path).path
            if path == "/api/v1/preflight":
                result = self.server.workflow.preflight()
            elif path == "/api/v1/device/login/start":
                result = self.server.workflow.start_login()
            elif path == "/api/v1/device/login/complete":
                result = self.server.workflow.complete_login()
            elif path == "/api/v1/device/identify":
                result = self.server.workflow.identify_device()
            elif path == "/api/v1/firmware/inspect":
                result = self.server.workflow.inspect_firmware(str(payload.get("filename") or ""))
            elif path == "/api/v1/operations":
                result = self.server.workflow.create_operation()
            elif path.startswith("/api/v1/operations/") and path.endswith("/start"):
                operation_id = path.split("/")[-2]
                result = self.server.workflow.start(operation_id)
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
                return
            self._json(HTTPStatus.OK, result)
        except (OSError, ValueError, RuntimeError) as exc:
            self._json(HTTPStatus.CONFLICT, {"error": str(exc)})
