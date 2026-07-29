"""定时生成并向同一局域网内的 AP01 提供四页 AGENTS 看板结果包。"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .result_package import (
    DeviceCredentials,
    ResultPackageError,
    decode_package,
    load_credentials,
    load_or_create_credentials,
    publish_current_result,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "env" / "agents-dashboard-device.json"
DEFAULT_CACHE = PROJECT_ROOT / "env" / "agents-dashboard-cache"
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "agents-dashboard"
DEFAULT_FONTS = PROJECT_ROOT / "env" / "fonts"


def lan_ip() -> str:
    override = os.environ.get("AP01_LAN_IP", "").strip()
    try:
        if override and ipaddress.ip_address(override).is_private:
            return override
    except ValueError:
        pass
    if sys.platform == "darwin":
        for interface in ("en0", "en1"):
            try:
                result = subprocess.run(
                    ["ipconfig", "getifaddr", interface],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                candidate = result.stdout.strip()
                if candidate and ipaddress.ip_address(candidate).is_private:
                    return candidate
            except (OSError, subprocess.SubprocessError, ValueError):
                continue
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 80))
        candidate = str(probe.getsockname()[0])
        if ipaddress.ip_address(candidate).is_private:
            return candidate
    except (OSError, ValueError):
        pass
    finally:
        probe.close()
    return "127.0.0.1"


class BridgeState:
    def __init__(
        self,
        credentials: DeviceCredentials,
        output: Path,
        fonts: Path,
        *,
        codex_home: Path | None = None,
        cache_directory: Path | None = None,
    ) -> None:
        self.credentials = credentials
        self.output = output
        self.fonts = fonts
        self.codex_home = codex_home
        self.cache_directory = cache_directory
        self.lock = threading.Lock()
        self.last_refresh: float | None = None
        self.last_request: float | None = None
        self.requests = 0
        self.error: str | None = None
        self.data_sources: dict[str, bool] = {}
        self.refreshing = False
        self._nonces: deque[str] = deque(maxlen=128)
        self._nonce_set: set[str] = set()

    @staticmethod
    def _safe_error(error: Exception) -> str:
        message = str(error)
        for private_path in (
            str(PROJECT_ROOT.resolve()),
            str(Path.home().resolve()),
        ):
            message = message.replace(private_path, "<本机路径>")
        return message[:300]

    def has_valid_result(self) -> bool:
        package_path = self.output / "agents-dashboard.apag"
        try:
            decode_package(package_path.read_bytes(), self.credentials)
        except (OSError, ResultPackageError):
            return False
        return True

    def refresh(self) -> None:
        with self.lock:
            if self.refreshing:
                return
            self.refreshing = True
        try:
            manifest = publish_current_result(
                self.output,
                self.fonts,
                self.credentials,
                codex_home=self.codex_home,
                cache_directory=self.cache_directory,
            )
            with self.lock:
                self.last_refresh = time.time()
                self.error = None
                source_status = manifest.get("data_sources", {})
                self.data_sources = (
                    {
                        str(name): available
                        for name, available in source_status.items()
                        if isinstance(name, str) and isinstance(available, bool)
                    }
                    if isinstance(source_status, dict)
                    else {}
                )
        except Exception as error:
            with self.lock:
                self.error = self._safe_error(error)
            raise
        finally:
            with self.lock:
                self.refreshing = False

    def authorize(self, query: dict[str, list[str]]) -> bool:
        device = query.get("d", [""])[0].lower()
        token = query.get("t", [""])[0].lower()
        nonce = query.get("n", [""])[0]
        if (
            device != self.credentials.device_id[-4:]
            or token != self.credentials.access_token[-12:]
            or not nonce.isdigit()
            or len(nonce) > 20
        ):
            return False
        key = f"{device}:{nonce}"
        with self.lock:
            if key in self._nonce_set:
                return False
            if len(self._nonces) == self._nonces.maxlen:
                self._nonce_set.discard(self._nonces[0])
            self._nonces.append(key)
            self._nonce_set.add(key)
        return True

    def health(self) -> bytes:
        result_available = self.has_valid_result()
        with self.lock:
            document = {
                "ok": result_available,
                "degraded": self.error is not None,
                "last_refresh": self.last_refresh,
                "last_request": self.last_request,
                "requests": self.requests,
                "refreshing": self.refreshing,
                "error": self.error,
                "data_sources": dict(self.data_sources),
            }
        return json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")


def make_handler(state: BridgeState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AP01AgentsBridge/1.0"

        def do_GET(self) -> None:  # noqa: N802
            split = urlsplit(self.path)
            if split.path == "/health":
                self._send(state.health(), "application/json; charset=utf-8")
                return
            if split.path != "/a":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if not state.authorize(parse_qs(split.query, keep_blank_values=True)):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            package_path = state.output / "agents-dashboard.apag"
            try:
                body = package_path.read_bytes()
            except OSError:
                self.send_error(HTTPStatus.SERVICE_UNAVAILABLE)
                return
            with state.lock:
                state.requests += 1
                state.last_request = time.time()
            self._send(body, "application/octet-stream")

        def _send(self, body: bytes, content_type: str) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            message = fmt % args
            if '"GET /health ' in message:
                return
            safe_path = urlsplit(self.path).path
            print(
                f"[{self.log_date_time_string()}] "
                f"{self.address_string()} {self.command} {safe_path} {message.rsplit(' ', 1)[-1]}"
            )

    return Handler


def _refresh_loop(state: BridgeState, interval: int) -> None:
    while True:
        time.sleep(interval)
        try:
            state.refresh()
        except Exception as error:
            print(f"AGENTS 看板刷新失败，继续提供上次成功结果：{error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--font-directory", type=Path, default=DEFAULT_FONTS)
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--cache-directory", type=Path, default=DEFAULT_CACHE)
    parser.add_argument(
        "--initialize-config",
        action="store_true",
        help="只初始化或复用设备专属配置，随后退出",
    )
    arguments = parser.parse_args(argv)
    if not 10 <= arguments.interval <= 7200:
        parser.error("刷新周期必须在 10～7200 秒之间")
    try:
        if arguments.initialize_config:
            credentials = load_or_create_credentials(arguments.config)
            print(f"设备专属配置已就绪：{arguments.config.expanduser().resolve()}")
            return 0
        credentials = load_credentials(arguments.config)
    except ResultPackageError as error:
        parser.error(str(error))
    state = BridgeState(
        credentials,
        arguments.output,
        arguments.font_directory,
        codex_home=arguments.codex_home,
        cache_directory=arguments.cache_directory,
    )
    try:
        state.refresh()
    except Exception as error:
        if not state.has_valid_result():
            parser.error(f"无法生成新结果且没有可用旧结果：{state._safe_error(error)}")
        print(
            "AGENTS 看板首次刷新失败，继续提供已验证的旧结果："
            f"{state._safe_error(error)}"
        )
    worker = threading.Thread(
        target=_refresh_loop,
        args=(state, arguments.interval),
        daemon=True,
    )
    worker.start()
    server = ThreadingHTTPServer(
        (arguments.bind, arguments.port),
        make_handler(state),
    )
    print(f"AGENTS 看板服务：http://{lan_ip()}:{arguments.port}/a")
    print(f"本机检查：http://127.0.0.1:{arguments.port}/health")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
