"""AP01 official firmware login, lookup, and download entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from features.official_firmware_source import (
    OfficialFirmwareError,
    XiaomiCloudClient,
    download_latest_official_firmware,
    ensure_login,
)


def _project_internal_path(path: Path) -> Path:
    if path.is_absolute():
        raise OfficialFirmwareError("官方固件工作流只接受项目内相对路径")
    selected = (REPO_ROOT / path).resolve()
    if selected != REPO_ROOT and REPO_ROOT not in selected.parents:
        raise OfficialFirmwareError("官方固件工作流路径不能离开项目目录")
    return selected


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    login = commands.add_parser("login", help="扫码登录米家并保存项目内登录态")
    login.add_argument("--env-file", type=Path, default=Path("env/mi-cloud.env"))
    login.add_argument(
        "--qr-output",
        type=Path,
        default=Path("artifacts/official-firmware/xiaomi-login-qr.png"),
    )
    login.add_argument("--timeout", type=float, default=300)

    info = commands.add_parser("info", help="查询小米云当前 AP01 官方固件")
    info.add_argument("--env-file", type=Path, default=Path("env/mi-cloud.env"))
    info.add_argument("--timeout", type=int, default=30)

    download = commands.add_parser("download", help="下载并固定 AP01 官方固件")
    download.add_argument("--env-file", type=Path, default=Path("env/mi-cloud.env"))
    download.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/firmware/original"),
    )
    download.add_argument("--timeout", type=int, default=30)
    download.add_argument("--download-timeout", type=int, default=120)
    return parser


def _print(document: dict[str, object]) -> None:
    print(json.dumps(document, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        env_file = _project_internal_path(args.env_file)
        if args.command == "login":
            qr_output = _project_internal_path(args.qr_output)

            def announce_qr(path: Path) -> None:
                print(f"二维码已生成：{args.qr_output}", flush=True)
                print("请用拥有目标 AP01 的米家账号扫码并在手机上确认。", flush=True)

            result = ensure_login(
                env_file,
                qr_output,
                timeout=args.timeout,
                announce_qr=announce_qr,
            )
            _print(
                {
                    "result": (
                        "已有米家登录态可用"
                        if result.reused_existing
                        else "扫码登录完成"
                    ),
                    "model": result.model,
                    "env_file": str(args.env_file),
                }
            )
            return 0

        client = XiaomiCloudClient(env_file=env_file, timeout=args.timeout)
        if args.command == "info":
            info = client.firmware_info()
            _print(
                {
                    "result": "小米云官方固件信息查询完成",
                    "firmware": info.public_dict(),
                }
            )
            return 0

        output_dir = _project_internal_path(args.output_dir)
        result = download_latest_official_firmware(
            client,
            output_dir,
            timeout=args.download_timeout,
        )
        document = result.to_dict()
        document["path"] = str(args.output_dir / result.path.name)
        _print({"result": "官方原版固件已固定", "firmware": document})
        return 0
    except (OfficialFirmwareError, OSError, ValueError) as exc:
        _print({"result": "已停止", "reason": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
