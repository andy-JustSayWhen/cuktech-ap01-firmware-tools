#!/usr/bin/env python3
"""启动 AP01 本机网页刷机入口。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import webbrowser
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from features.web_firmware_flash import OperationStore, XiaomiCloudClient, XiaomiCredentials, XiaomiQrLogin
from features.web_firmware_flash.firmware_inspection import InspectedFirmware
from features.web_firmware_flash.server import WebFlashServer
from features.web_firmware_flash.workflow import FlashWorkflow


def strict_simulation(firmware: InspectedFirmware) -> list[str]:
    report = firmware.manifest_path.parent / "interaction-simulation.json"
    if not report.is_file():
        raise RuntimeError("发布包缺少严格刷前交互模拟结果")
    payload = json.loads(report.read_text(encoding="utf-8"))
    summary = payload.get("summary") or {}
    bound_sha = (payload.get("firmware") or {}).get("sha256") or payload.get("firmware_sha256")
    if (
        summary.get("passed") is not True
        or summary.get("build_allowed") is not True
        or summary.get("failure_count") != 0
        or bound_sha != firmware.sha256
    ):
        raise RuntimeError("严格刷前交互模拟结果与冻结成品不匹配")
    return [
        f"场景 {int(summary.get('scenario_count') or 0)}",
        f"步骤 {int(summary.get('trace_step_count') or 0)}",
        f"序列 {int(summary.get('exhaustive_sequence_count') or 0)}",
        "失败 0",
    ]


def open_chrome(url: str) -> bool:
    commands = [
        ["open", "-a", "Google Chrome", url],
        ["cmd", "/c", "start", "chrome", url],
    ]
    for command in commands:
        try:
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            continue
    return webbrowser.open(url)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".cuktech-ap01-web")
    parser.add_argument("--private-env", type=Path, default=REPO_ROOT / "env" / ".env")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    credentials_path = args.data_dir / "xiaomi.env"
    store = OperationStore(args.data_dir / "operations")
    workflow = FlashWorkflow(
        release_directory=args.release_dir,
        store=store,
        cloud_factory=lambda: XiaomiCloudClient(
            XiaomiCredentials.load(credentials_path if credentials_path.is_file() else args.private_env)
        ),
        simulation=strict_simulation,
        qr_login=XiaomiQrLogin(),
        credentials_path=credentials_path,
    )
    server = WebFlashServer(("127.0.0.1", 0), workflow)
    url = f"http://127.0.0.1:{server.server_port}/?access={server.access_token}"
    if not args.no_browser and not open_chrome(url):
        raise RuntimeError("无法打开 Chrome，请确认已经安装后重新启动")
    print(f"AP01 本机刷机服务已启动：127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
