"""AP01 最终版固件检查、制作与交互模拟入口。"""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.firmware_image import FirmwareValidationError, prepare_read_only_copy
from features.agents_dashboard_firmware import (
    AgentsDashboardFirmwareError,
    EndpointConfigError,
    InteractionSimulationError,
    PERSONALIZED_FIRMWARE_OUTPUT_FILENAME,
    PUBLIC_FIRMWARE_OUTPUT_FILENAME,
    build_live_data_weather_hidden_dashboard_v2_firmware,
    load_endpoint_config,
    simulate_current_manifest,
    write_simulation_report,
)
from features.firmware_installation import (
    FirmwareInstallError,
    install_firmware,
    query_ap01_update_status,
    upload_and_verify_firmware,
    verify_existing_ota_url,
)
from features.offline_firmware_build import BuildGateError, inspect_baseline, make_firmware
from features.official_firmware_source import (
    OfficialFirmwareError,
    XiaomiCloudClient,
    download_official_firmware,
)
from features.settings_menu_wrap import (
    SettingsMenuWrapError,
    write_approved_plan,
    write_draft_plan,
)


def _tool_revision() -> dict[str, object]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    scoped_status = subprocess.run(
        ["git", "status", "--porcelain", "--", "app", "core", "features"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {"commit": commit, "scoped_code_dirty": bool(scoped_status)}


def _path_arguments(command: argparse.ArgumentParser, *names: str) -> None:
    for name in names:
        command.add_argument(f"--{name}", type=Path, required=True)


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

    prepare = commands.add_parser("firmware-input-prepare", help="生成只读固件工作副本")
    prepare.add_argument("--source", type=Path, required=True)
    prepare.add_argument("--target-dir", type=Path, required=True)
    prepare.add_argument("--expected-size", type=int, required=True)
    prepare.add_argument("--expected-sha256", required=True)
    prepare.add_argument("--expected-md5")

    inspect = commands.add_parser("inspect", help="检查官方固件基线")
    _path_arguments(inspect, "input", "report")
    inspect.add_argument("--cloud-version")
    inspect.add_argument("--cloud-md5")
    inspect.add_argument("--cloud-checked-at")

    draft = commands.add_parser("settings-wrap-plan", help="生成设置菜单循环修改清单")
    _path_arguments(draft, "input", "output")

    approved = commands.add_parser(
        "settings-wrap-approved-plan",
        help="生成已批准的设置菜单循环修改清单",
    )
    _path_arguments(approved, "input", "output")

    settings_build = commands.add_parser("settings-build", help="制作设置菜单循环固件")
    _path_arguments(settings_build, "input", "plan", "output", "manifest")
    settings_build.add_argument("--cloud-version", required=True)
    settings_build.add_argument("--cloud-md5", required=True)
    settings_build.add_argument("--cloud-checked-at", required=True)

    release_build = commands.add_parser(
        "agents-release-build",
        help="制作不含服务地址的公开固件",
    )
    _path_arguments(release_build, "input", "output", "manifest", "build-dir")
    release_build.add_argument("--refresh-seconds", type=int, default=300)

    personalized_build = commands.add_parser(
        "agents-personalized-build",
        help="从本机配置制作包含服务地址的个人固件",
    )
    _path_arguments(
        personalized_build,
        "input",
        "env-file",
        "output",
        "manifest",
        "build-dir",
    )
    personalized_build.add_argument("--refresh-seconds", type=int, default=300)

    simulation = commands.add_parser(
        "agents-interaction-simulate",
        help="连续模拟最终版页面交互",
    )
    _path_arguments(simulation, "manifest", "report")
    simulation.add_argument("--depth", type=int, default=8)

    official_info = commands.add_parser(
        "official-firmware-info",
        help="从本项目查询小米云当前 AP01 官方固件信息",
    )
    official_info.add_argument("--env-file", type=Path)
    official_info.add_argument("--timeout", type=int, default=30)

    official_download = commands.add_parser(
        "official-firmware-download",
        help="下载并固定 AP01 官方原版固件",
    )
    official_download.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts")
        / "firmware"
        / "original"
        / "ap01-1.0.2_0031.bin",
    )
    official_download.add_argument("--env-file", type=Path)
    official_download.add_argument("--timeout", type=int, default=30)
    official_download.add_argument("--download-timeout", type=int, default=120)

    firmware_status = commands.add_parser(
        "firmware-install-status",
        help="查询唯一 AP01 的在线更新状态",
    )
    firmware_status.add_argument("--env-file", type=Path)
    firmware_status.add_argument("--timeout", type=int, default=30)

    upload_verify = commands.add_parser(
        "firmware-upload-verify",
        help="上传固件到小米云并完整回读核对",
    )
    upload_verify.add_argument("--firmware", type=Path, required=True)
    upload_verify.add_argument("--env-file", type=Path)
    upload_verify.add_argument("--fds-did")
    upload_verify.add_argument("--fds-model")
    upload_verify.add_argument("--url-output", type=Path)
    upload_verify.add_argument("--timeout", type=int, default=30)
    upload_verify.add_argument("--transfer-timeout", type=int, default=180)

    firmware_install = commands.add_parser(
        "firmware-install",
        help="上传回读核对后向唯一 AP01 下发一次安装",
    )
    firmware_install.add_argument("--firmware", type=Path, required=True)
    firmware_install.add_argument("--env-file", type=Path)
    firmware_install.add_argument("--fds-did")
    firmware_install.add_argument("--fds-model")
    firmware_install.add_argument("--ota-url")
    firmware_install.add_argument("--ota-url-file", type=Path)
    firmware_install.add_argument(
        "--self-signed-ota",
        action="store_true",
        help="OTA URL 指向本机自签 HTTPS 服务器：回读跳过证书校验，并携带 cert_verify=optional",
    )
    firmware_install.add_argument("--timeout", type=int, default=360)
    firmware_install.add_argument("--cloud-timeout", type=int, default=30)
    firmware_install.add_argument("--transfer-timeout", type=int, default=180)
    return parser


def _print(document: dict[str, object]) -> None:
    print(json.dumps(document, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    revision = _tool_revision()
    try:
        if args.command == "firmware-input-prepare":
            prepared = prepare_read_only_copy(
                args.source,
                args.target_dir,
                expected_size=args.expected_size,
                expected_sha256=args.expected_sha256,
                expected_md5=args.expected_md5,
            )
            _print({"result": "只读固件工作副本已准备", "material": prepared.to_dict()})
            return 0

        if args.command == "inspect":
            report = inspect_baseline(
                args.input,
                args.report,
                tool_revision=revision,
                cloud_version=args.cloud_version,
                cloud_md5=args.cloud_md5,
                cloud_checked_at=args.cloud_checked_at,
            )
            _print(
                {
                    "result": "官方基线检查通过",
                    "report": str(args.report.resolve()),
                    "baseline": report["baseline"],
                    "gates": report["gates"],
                }
            )
            return 0

        if args.command == "settings-wrap-plan":
            document = write_draft_plan(args.input, args.output, tool_revision=revision)
            _print(
                {
                    "result": "设置菜单循环修改清单已生成",
                    "plan": str(args.output.resolve()),
                    "status": document["status"],
                }
            )
            return 0

        if args.command == "settings-wrap-approved-plan":
            document = write_approved_plan(args.input, args.output, tool_revision=revision)
            _print(
                {
                    "result": "设置菜单循环批准清单已生成",
                    "plan": str(args.output.resolve()),
                    "status": document["status"],
                }
            )
            return 0

        if args.command == "settings-build":
            result = make_firmware(
                args.input,
                args.plan,
                args.output,
                args.manifest,
                repo_root=REPO_ROOT,
                tool_revision=revision,
                cloud_version=args.cloud_version,
                cloud_md5=args.cloud_md5,
                cloud_checked_at=args.cloud_checked_at,
            )
            _print(
                {
                    "result": "设置菜单循环固件制作完成",
                    "output": str(result.output),
                    "manifest": str(result.manifest),
                    "output_sha256": result.output_sha256,
                    "output_md5": result.output_md5,
                }
            )
            return 0

        if args.command in {"agents-release-build", "agents-personalized-build"}:
            personalized = args.command == "agents-personalized-build"
            endpoints = (
                load_endpoint_config(args.env_file).endpoints if personalized else ()
            )
            result = build_live_data_weather_hidden_dashboard_v2_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                endpoints=endpoints,
                endpoint_timeout_seconds=3 if personalized else 0,
                refresh_seconds=args.refresh_seconds,
                tool_revision=revision,
                standalone_timer=True,
            )
            _print(
                {
                    "result": (
                        "个人固件制作完成"
                        if personalized
                        else "无地址公开固件制作完成"
                    ),
                    "output": str(result.output),
                    "expected_name": (
                        PERSONALIZED_FIRMWARE_OUTPUT_FILENAME
                        if personalized
                        else PUBLIC_FIRMWARE_OUTPUT_FILENAME
                    ),
                    "manifest": str(result.manifest),
                    "output_sha256": result.sha256,
                    "output_md5": result.md5,
                    "payload_size": result.payload_size,
                    "payload_remaining": result.payload_remaining,
                }
            )
            return 0

        if args.command == "official-firmware-info":
            env_file = _project_internal_path(
                args.env_file or Path("env/mi-cloud.env")
            )
            client = XiaomiCloudClient(
                env_file=env_file,
                timeout=args.timeout,
            )
            info = client.firmware_info()
            _print(
                {
                    "result": "小米云官方固件信息查询完成",
                    "firmware": info.public_dict(),
                }
            )
            return 0

        if args.command == "official-firmware-download":
            env_file = _project_internal_path(
                args.env_file or Path("env/mi-cloud.env")
            )
            output = _project_internal_path(args.output)
            client = XiaomiCloudClient(
                env_file=env_file,
                timeout=args.timeout,
            )
            result = download_official_firmware(
                client,
                output,
                timeout=args.download_timeout,
            )
            _print(
                {
                    "result": "官方原版固件已固定",
                    "firmware": result.to_dict(),
                }
            )
            return 0

        if args.command == "firmware-install-status":
            env_file = _project_internal_path(
                args.env_file or Path("env/mi-cloud.env")
            )
            client = XiaomiCloudClient(env_file=env_file, timeout=args.timeout)
            status = query_ap01_update_status(client)
            _print({"result": "AP01 在线更新状态已查询", "status": status})
            return 0

        if args.command == "firmware-upload-verify":
            if bool(args.fds_did) != bool(args.fds_model):
                raise FirmwareInstallError("--fds-did 和 --fds-model 必须同时提供")
            env_file = _project_internal_path(
                args.env_file or Path("env/mi-cloud.env")
            )
            client = XiaomiCloudClient(env_file=env_file, timeout=args.timeout)
            upload_result = upload_and_verify_firmware(
                client,
                args.firmware,
                fds_did=args.fds_did,
                fds_model=args.fds_model,
                timeout=args.transfer_timeout,
            )
            if args.url_output:
                output = args.url_output.expanduser()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(upload_result.url + "\n", encoding="utf-8")
                os.chmod(output, stat.S_IRUSR | stat.S_IWUSR)
            _print({"result": "固件已上传且完整回读一致", "ota": upload_result.to_dict()})
            return 0

        if args.command == "firmware-install":
            if args.ota_url and args.ota_url_file:
                raise FirmwareInstallError("不能同时传入 --ota-url 和 --ota-url-file")
            if bool(args.fds_did) != bool(args.fds_model):
                raise FirmwareInstallError("--fds-did 和 --fds-model 必须同时提供")
            env_file = _project_internal_path(
                args.env_file or Path("env/mi-cloud.env")
            )
            client = XiaomiCloudClient(env_file=env_file, timeout=args.cloud_timeout)
            supplied_url = args.ota_url
            if args.ota_url_file:
                supplied_url = args.ota_url_file.expanduser().read_text(
                    encoding="utf-8"
                ).strip()
                if not supplied_url:
                    raise FirmwareInstallError("--ota-url-file 为空")
            if supplied_url:
                upload_result = verify_existing_ota_url(
                    args.firmware,
                    supplied_url,
                    timeout=args.transfer_timeout,
                    insecure=args.self_signed_ota,
                )
            else:
                upload_result = upload_and_verify_firmware(
                    client,
                    args.firmware,
                    fds_did=args.fds_did,
                    fds_model=args.fds_model,
                    timeout=args.transfer_timeout,
                )
            install_result = install_firmware(
                client,
                args.firmware,
                upload_result.url,
                timeout=args.timeout,
                cert_verify="optional" if args.self_signed_ota else None,
            )
            _print(
                {
                    "result": "AP01 安装命令已下发并完成轮询",
                    "ota": upload_result.to_dict(),
                    "installation": install_result.to_dict(),
                }
            )
            return 0

        report = simulate_current_manifest(args.manifest, exhaustive_depth=args.depth)
        selected_report = write_simulation_report(args.report, report)
        _print(
            {
                "result": "连续页面交互模拟通过" if report["summary"]["passed"] else "连续页面交互模拟失败",
                "report": str(selected_report),
                "summary": report["summary"],
                "failures": report["failures"][:5],
                "physical_acceptance_replaced": False,
            }
        )
        return 0 if report["summary"]["passed"] else 2
    except (
        AgentsDashboardFirmwareError,
        InteractionSimulationError,
        BuildGateError,
        EndpointConfigError,
        FirmwareValidationError,
        FirmwareInstallError,
        OfficialFirmwareError,
        SettingsMenuWrapError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        _print({"result": "已停止", "reason": str(error)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
