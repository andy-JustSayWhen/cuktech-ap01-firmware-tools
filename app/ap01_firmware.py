"""AP01 原厂基线检查与离线固件制作入口。"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.firmware_image import FirmwareValidationError, prepare_read_only_copy
from features.agents_dashboard_firmware import (
    AgentsDashboardFirmwareError,
    CONFIRM_COMPAT_OUTPUT_FILENAME,
    DETAIL_COMPAT_OUTPUT_FILENAME,
    LOCAL_UI_BASE_SAFE_OUTPUT_FILENAME,
    LIVE_DATA_REFERENCE_COMPLETE_OUTPUT_FILENAME,
    LIVE_DATA_LOW_STACK_OUTPUT_FILENAME,
    LIVE_DATA_LOCATION_INDEPENDENT_OUTPUT_FILENAME,
    LOCAL_UI_STOCK_RESUME_OUTPUT_FILENAME,
    LOCAL_UI_STOCK_SAFE_OUTPUT_FILENAME,
    PET_OVERLAY_OUTPUT_FILENAME,
    STOCK_CALLCHAIN_OUTPUT_FILENAME,
    STOCK_DISPATCH_OUTPUT_FILENAME,
    STOCK_ENTER_GATE_OUTPUT_FILENAME,
    STOCK_PET_REUSE_OUTPUT_FILENAME,
    InteractionSimulationError,
    build_observation_firmware,
    build_page_registration_payload,
    build_stock_callchain_firmware,
    build_stock_enter_gate_firmware,
    build_local_ui_stock_resume_firmware,
    build_local_ui_base_safe_firmware,
    build_live_data_reference_complete_firmware,
    build_live_data_low_stack_firmware,
    build_live_data_location_independent_firmware,
    build_local_ui_stock_safe_firmware,
    build_sync_firmware,
    simulate_current_manifest,
    write_simulation_report,
)
from features.offline_firmware_build import (
    BuildGateError,
    inspect_baseline,
    make_firmware,
)
from core.firmware_payload_space import (
    FirmwarePayloadSpaceError,
    inspect_payload_space,
)
from features.optimized_firmware_build import (
    OptimizedFirmwareBuildError,
    inspect_optimized_baseline,
)
from features.primary_page_navigation import (
    PrimaryPageNavigationError,
    inspect_primary_page_navigation,
)
from features.primary_page_settings import (
    HOOK_OBSERVATION_OUTPUT_NAME,
    READ_ONLY_ENTRY_OUTPUT_NAME,
    ROW_CREATION_OUTPUT_NAME,
    STARTUP_PASSTHROUGH_OUTPUT_NAME,
    PageSettingsReadOnlyEntryError,
    PageSettingsRowCreationError,
    PageSettingsStartupPassthroughError,
    PrimaryPageSettingsBuildError,
    SettingsHookObservationError,
    build_page_settings_read_only_entry,
    build_page_settings_row_creation,
    build_page_settings_startup_passthrough,
    build_settings_hook_observation,
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare_input_command = commands.add_parser(
        "firmware-input-prepare",
        help="核对版本化固件并生成本机只读工作副本",
    )
    prepare_input_command.add_argument("--source", type=Path, required=True)
    prepare_input_command.add_argument("--target-dir", type=Path, required=True)
    prepare_input_command.add_argument("--expected-size", type=int, required=True)
    prepare_input_command.add_argument("--expected-sha256", required=True)
    prepare_input_command.add_argument("--expected-md5")

    inspect_command = commands.add_parser("inspect", help="检查原厂固件基线")
    inspect_command.add_argument("--input", type=Path, required=True)
    inspect_command.add_argument("--report", type=Path, required=True)
    inspect_command.add_argument("--cloud-version")
    inspect_command.add_argument("--cloud-md5")
    inspect_command.add_argument("--cloud-checked-at")

    settings_plan_command = commands.add_parser(
        "settings-wrap-plan",
        help="生成系统设置菜单首尾循环的待批准修改清单",
    )
    settings_plan_command.add_argument("--input", type=Path, required=True)
    settings_plan_command.add_argument("--output", type=Path, required=True)

    approved_settings_plan_command = commands.add_parser(
        "settings-wrap-approved-plan",
        help="生成与批准记录完全一致的系统设置菜单离线构建清单",
    )
    approved_settings_plan_command.add_argument(
        "--input",
        type=Path,
        required=True,
    )
    approved_settings_plan_command.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    build_command = commands.add_parser("build", help="按已批准清单离线制作固件")
    build_command.add_argument("--input", type=Path, required=True)
    build_command.add_argument("--plan", type=Path, required=True)
    build_command.add_argument("--output", type=Path, required=True)
    build_command.add_argument("--manifest", type=Path, required=True)
    build_command.add_argument("--cloud-version", required=True)
    build_command.add_argument("--cloud-md5", required=True)
    build_command.add_argument("--cloud-checked-at", required=True)

    optimized_inspect_command = commands.add_parser(
        "opt-bin-inspect",
        help="检查完整优化固件使用的原厂锚点和已验收阶段输入",
    )
    optimized_inspect_command.add_argument("--original", type=Path, required=True)
    optimized_inspect_command.add_argument("--input", type=Path, required=True)
    optimized_inspect_command.add_argument("--report", type=Path, required=True)

    navigation_inspect_command = commands.add_parser(
        "primary-page-inspect",
        help="检查一级页面注册、动态导航和新增页挂接候选",
    )
    navigation_inspect_command.add_argument("--original", type=Path, required=True)
    navigation_inspect_command.add_argument("--input", type=Path, required=True)
    navigation_inspect_command.add_argument("--report", type=Path, required=True)

    payload_space_command = commands.add_parser(
        "payload-space-inspect",
        help="无损优化固定原厂动图并检查载荷候选空间",
    )
    payload_space_command.add_argument("--input", type=Path, required=True)
    payload_space_command.add_argument("--optimized-gif", type=Path, required=True)
    payload_space_command.add_argument("--report", type=Path, required=True)

    agents_page_payload_command = commands.add_parser(
        "agents-page-payload",
        help="构建并检查 AGENTS 独立页面注册载荷",
    )
    agents_page_payload_command.add_argument("--input", type=Path, required=True)
    agents_page_payload_command.add_argument("--build-dir", type=Path, required=True)
    agents_page_payload_command.add_argument("--report", type=Path, required=True)

    observation_command = commands.add_parser(
        "agents-observation-build",
        help="生成专用测试设备的 AGENTS 首次真机观察固件",
    )
    observation_command.add_argument("--input", type=Path, required=True)
    observation_command.add_argument("--output", type=Path, required=True)
    observation_command.add_argument("--manifest", type=Path, required=True)
    observation_command.add_argument("--build-dir", type=Path, required=True)

    sync_command = commands.add_parser(
        "agents-sync-build",
        help="生成设备专属的 AGENTS 四页后台同步实验固件",
    )
    sync_command.add_argument("--input", type=Path, required=True)
    sync_command.add_argument("--output", type=Path, required=True)
    sync_command.add_argument("--manifest", type=Path, required=True)
    sync_command.add_argument("--build-dir", type=Path, required=True)
    sync_command.add_argument("--url-base", required=True)
    sync_command.add_argument("--refresh-seconds", type=int, default=300)

    detail_compat_command = commands.add_parser(
        "agents-detail-compat-build",
        help="生成保留原厂详情对象序号的 AGENTS 四页观察固件",
    )
    detail_compat_command.add_argument("--input", type=Path, required=True)
    detail_compat_command.add_argument("--output", type=Path, required=True)
    detail_compat_command.add_argument("--manifest", type=Path, required=True)
    detail_compat_command.add_argument("--build-dir", type=Path, required=True)
    detail_compat_command.add_argument("--url-base", required=True)
    detail_compat_command.add_argument(
        "--refresh-seconds",
        type=int,
        default=300,
    )

    confirm_compat_command = commands.add_parser(
        "agents-confirm-compat-build",
        help="生成兼容原厂确认键固定边界的 AGENTS 四页观察固件",
    )
    confirm_compat_command.add_argument("--input", type=Path, required=True)
    confirm_compat_command.add_argument("--output", type=Path, required=True)
    confirm_compat_command.add_argument("--manifest", type=Path, required=True)
    confirm_compat_command.add_argument("--build-dir", type=Path, required=True)
    confirm_compat_command.add_argument("--url-base", required=True)
    confirm_compat_command.add_argument(
        "--refresh-seconds",
        type=int,
        default=300,
    )

    pet_overlay_command = commands.add_parser(
        "agents-pet-overlay-build",
        help="生成保持原厂九个一级对象的 AGENTS 覆盖层观察固件",
    )
    pet_overlay_command.add_argument("--input", type=Path, required=True)
    pet_overlay_command.add_argument("--output", type=Path, required=True)
    pet_overlay_command.add_argument("--manifest", type=Path, required=True)
    pet_overlay_command.add_argument("--build-dir", type=Path, required=True)
    pet_overlay_command.add_argument("--url-base", required=True)
    pet_overlay_command.add_argument(
        "--refresh-seconds",
        type=int,
        default=300,
    )

    stock_pet_reuse_command = commands.add_parser(
        "agents-stock-pet-reuse-build",
        help="生成只复用原厂萌宠动图控件的 AGENTS 观察固件",
    )
    stock_pet_reuse_command.add_argument("--input", type=Path, required=True)
    stock_pet_reuse_command.add_argument("--output", type=Path, required=True)
    stock_pet_reuse_command.add_argument("--manifest", type=Path, required=True)
    stock_pet_reuse_command.add_argument("--build-dir", type=Path, required=True)
    stock_pet_reuse_command.add_argument("--url-base", required=True)
    stock_pet_reuse_command.add_argument(
        "--refresh-seconds",
        type=int,
        default=300,
    )

    stock_dispatch_command = commands.add_parser(
        "agents-stock-dispatch-build",
        help="生成按原厂交互分派路由的 AGENTS 观察固件",
    )
    stock_dispatch_command.add_argument("--input", type=Path, required=True)
    stock_dispatch_command.add_argument("--output", type=Path, required=True)
    stock_dispatch_command.add_argument("--manifest", type=Path, required=True)
    stock_dispatch_command.add_argument("--build-dir", type=Path, required=True)
    stock_dispatch_command.add_argument("--url-base", required=True)
    stock_dispatch_command.add_argument(
        "--refresh-seconds",
        type=int,
        default=300,
    )

    stock_callchain_command = commands.add_parser(
        "agents-stock-callchain-build",
        help="生成沿原厂实际调用链工作的 AGENTS 离线观察固件",
    )
    stock_callchain_command.add_argument("--input", type=Path, required=True)
    stock_callchain_command.add_argument("--output", type=Path, required=True)
    stock_callchain_command.add_argument("--manifest", type=Path, required=True)
    stock_callchain_command.add_argument("--build-dir", type=Path, required=True)
    stock_callchain_command.add_argument("--url-base", required=True)
    stock_callchain_command.add_argument(
        "--refresh-seconds",
        type=int,
        default=300,
    )

    stock_enter_gate_command = commands.add_parser(
        "agents-stock-enter-gate-build",
        help="生成确认键无栈透传的 AGENTS 离线观察固件",
    )
    stock_enter_gate_command.add_argument("--input", type=Path, required=True)
    stock_enter_gate_command.add_argument("--output", type=Path, required=True)
    stock_enter_gate_command.add_argument("--manifest", type=Path, required=True)
    stock_enter_gate_command.add_argument("--build-dir", type=Path, required=True)
    stock_enter_gate_command.add_argument("--url-base", required=True)
    stock_enter_gate_command.add_argument(
        "--refresh-seconds",
        type=int,
        default=300,
    )

    stock_local_branches_command = commands.add_parser(
        "agents-local-ui-stock-resume-build",
        help="生成恢复后交还原厂右旋分支的 AGENTS 局部界面固件",
    )
    stock_local_branches_command.add_argument(
        "--input", type=Path, required=True
    )
    stock_local_branches_command.add_argument(
        "--output", type=Path, required=True
    )
    stock_local_branches_command.add_argument(
        "--manifest", type=Path, required=True
    )
    stock_local_branches_command.add_argument(
        "--build-dir", type=Path, required=True
    )

    stock_safe_command = commands.add_parser(
        "agents-local-ui-stock-safe-build",
        help="生成保留原厂页面收尾顺序的 AGENTS 双向局部界面固件",
    )
    stock_safe_command.add_argument("--input", type=Path, required=True)
    stock_safe_command.add_argument("--output", type=Path, required=True)
    stock_safe_command.add_argument("--manifest", type=Path, required=True)
    stock_safe_command.add_argument("--build-dir", type=Path, required=True)

    base_safe_command = commands.add_parser(
        "agents-local-ui-base-safe-build",
        help="生成带基座生命周期保护的 AGENTS 局部界面固件",
    )
    base_safe_command.add_argument("--input", type=Path, required=True)
    base_safe_command.add_argument("--output", type=Path, required=True)
    base_safe_command.add_argument("--manifest", type=Path, required=True)
    base_safe_command.add_argument("--build-dir", type=Path, required=True)

    live_data_command = commands.add_parser(
        "agents-live-data-reference-complete-build",
        help="生成完整复用成功参考路径的 AGENTS 真实数据固件",
    )
    live_data_command.add_argument("--input", type=Path, required=True)
    live_data_command.add_argument("--output", type=Path, required=True)
    live_data_command.add_argument("--manifest", type=Path, required=True)
    live_data_command.add_argument("--build-dir", type=Path, required=True)
    live_data_command.add_argument("--url-base", required=True)
    live_data_command.add_argument("--refresh-seconds", type=int, default=300)

    low_stack_live_data_command = commands.add_parser(
        "agents-live-data-low-stack-build",
        help="生成下载状态不占后台任务栈的 AGENTS 真实数据固件",
    )
    low_stack_live_data_command.add_argument("--input", type=Path, required=True)
    low_stack_live_data_command.add_argument("--output", type=Path, required=True)
    low_stack_live_data_command.add_argument("--manifest", type=Path, required=True)
    low_stack_live_data_command.add_argument("--build-dir", type=Path, required=True)
    low_stack_live_data_command.add_argument("--url-base", required=True)
    low_stack_live_data_command.add_argument(
        "--refresh-seconds", type=int, default=300
    )

    location_independent_live_data_command = commands.add_parser(
        "agents-live-data-location-independent-build",
        help="生成不依赖天气位置的 AGENTS 真实数据固件",
    )
    location_independent_live_data_command.add_argument(
        "--input", type=Path, required=True
    )
    location_independent_live_data_command.add_argument(
        "--output", type=Path, required=True
    )
    location_independent_live_data_command.add_argument(
        "--manifest", type=Path, required=True
    )
    location_independent_live_data_command.add_argument(
        "--build-dir", type=Path, required=True
    )
    location_independent_live_data_command.add_argument(
        "--url-base", required=True
    )
    location_independent_live_data_command.add_argument(
        "--refresh-seconds", type=int, default=300
    )

    interaction_simulation_command = commands.add_parser(
        "agents-interaction-simulate",
        help="对刷前构建清单执行连续页面事件模拟",
    )
    interaction_simulation_command.add_argument(
        "--manifest", type=Path, required=True
    )
    interaction_simulation_command.add_argument(
        "--report", type=Path, required=True
    )
    interaction_simulation_command.add_argument(
        "--depth", type=int, default=5
    )

    optimized_build_command = commands.add_parser(
        "opt-build",
        help="组合页面开关与 AGENTS 看板，生成完整优化固件",
    )
    optimized_build_command.add_argument("--input", type=Path, required=True)
    optimized_build_command.add_argument("--output", type=Path, required=True)
    optimized_build_command.add_argument("--manifest", type=Path, required=True)
    optimized_build_command.add_argument("--build-dir", type=Path, required=True)
    optimized_build_command.add_argument("--url-base", required=True)
    optimized_build_command.add_argument(
        "--refresh-seconds",
        type=int,
        default=300,
    )

    hook_observation_command = commands.add_parser(
        "settings-hook-observation-build",
        help="从已验收同步固件生成设置列表空挂接观察成品",
    )
    hook_observation_command.add_argument("--input", type=Path, required=True)
    hook_observation_command.add_argument("--output", type=Path, required=True)
    hook_observation_command.add_argument("--manifest", type=Path, required=True)
    hook_observation_command.add_argument("--build-dir", type=Path, required=True)
    read_only_entry_command = commands.add_parser(
        "page-settings-read-only-entry-build",
        help="从已验收设置固件生成第八项只读入口候选",
    )
    read_only_entry_command.add_argument("--input", type=Path, required=True)
    read_only_entry_command.add_argument("--output", type=Path, required=True)
    read_only_entry_command.add_argument("--manifest", type=Path, required=True)
    read_only_entry_command.add_argument("--build-dir", type=Path, required=True)
    startup_passthrough_command = commands.add_parser(
        "page-settings-startup-passthrough-build",
        help="从已验收设置固件生成启动基础透传候选",
    )
    startup_passthrough_command.add_argument("--input", type=Path, required=True)
    startup_passthrough_command.add_argument("--output", type=Path, required=True)
    startup_passthrough_command.add_argument("--manifest", type=Path, required=True)
    startup_passthrough_command.add_argument("--build-dir", type=Path, required=True)
    row_creation_command = commands.add_parser(
        "page-settings-row-creation-build",
        help="从启动基础透传固件生成第八项普通行候选",
    )
    row_creation_command.add_argument("--input", type=Path, required=True)
    row_creation_command.add_argument("--output", type=Path, required=True)
    row_creation_command.add_argument("--manifest", type=Path, required=True)
    row_creation_command.add_argument("--build-dir", type=Path, required=True)
    return parser


def _required_tool(name: str) -> Path:
    selected = shutil.which(name)
    if selected is None:
        fallback = Path("/opt/homebrew/bin") / name
        if fallback.is_file():
            return fallback
        raise PrimaryPageSettingsBuildError(f"缺少构建工具：{name}")
    return Path(selected)


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
            print(
                json.dumps(
                    {
                        "result": "只读固件工作副本已准备",
                        "material": prepared.to_dict(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
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
            print(
                json.dumps(
                    {
                        "result": "原厂基线检查通过",
                        "report": str(args.report.resolve()),
                        "baseline": report["baseline"],
                        "gates": report["gates"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "settings-wrap-plan":
            document = write_draft_plan(
                args.input,
                args.output,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "系统设置菜单修改清单已生成，等待用户批准",
                        "plan": str(args.output.resolve()),
                        "status": document["status"],
                        "patch_count": document["review"]["patch_count"],
                        "firmware_output_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "settings-wrap-approved-plan":
            document = write_approved_plan(
                args.input,
                args.output,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "系统设置菜单批准范围绑定清单已生成",
                        "plan": str(args.output.resolve()),
                        "status": document["status"],
                        "patch_count": document["review"]["patch_count"],
                        "firmware_output_allowed": True,
                        "experimental_download_allowed": False,
                        "installation_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "opt-bin-inspect":
            report = inspect_optimized_baseline(
                args.original,
                args.input,
                args.report,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "完整优化固件制作输入检查通过",
                        "report": str(args.report.resolve()),
                        "stage_input": report["stage_input"],
                        "gates": report["gates"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "primary-page-inspect":
            report = inspect_primary_page_navigation(
                args.original,
                args.input,
                args.report,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "一级页面注册与导航检查通过",
                        "report": str(args.report.resolve()),
                        "page_hook_candidate": report["page_hook_candidate"],
                        "gates": report["gates"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "payload-space-inspect":
            report = inspect_payload_space(
                args.input,
                args.optimized_gif,
                args.report,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "原厂动图无损优化与载荷空间检查通过",
                        "optimized_gif": str(args.optimized_gif.resolve()),
                        "report": str(args.report.resolve()),
                        "payload_space": report["payload_space"],
                        "gates": report["gates"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-page-payload":
            report = build_page_registration_payload(
                args.input,
                args.build_dir,
                args.report,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "AGENTS 独立页面注册载荷构建通过",
                        "report": str(args.report.resolve()),
                        "payload": report["payload"],
                        "gates": report["gates"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-observation-build":
            result = build_observation_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "AGENTS 首次真机观察固件制作完成",
                        "output": str(result.output),
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "recovery_crc": f"0x{result.recovery_crc:08x}",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-sync-build":
            result = build_sync_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                url_base=args.url_base,
                refresh_seconds=args.refresh_seconds,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "AGENTS 四页后台同步实验固件制作完成",
                        "output": str(result.output),
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-detail-compat-build":
            result = build_sync_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                url_base=args.url_base,
                refresh_seconds=args.refresh_seconds,
                tool_revision=revision,
                expected_output_name=DETAIL_COMPAT_OUTPUT_FILENAME,
                implemented_scope_extra=("保留原厂详情对象序号",),
            )
            print(
                json.dumps(
                    {
                        "result": "原厂详情序号兼容观察固件制作完成",
                        "output": str(result.output),
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-confirm-compat-build":
            result = build_sync_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                url_base=args.url_base,
                refresh_seconds=args.refresh_seconds,
                tool_revision=revision,
                expected_output_name=CONFIRM_COMPAT_OUTPUT_FILENAME,
                implemented_scope_extra=(
                    "保留原厂详情对象序号",
                    "兼容原厂确认键固定边界",
                ),
            )
            print(
                json.dumps(
                    {
                        "result": "原厂确认键边界兼容观察固件制作完成",
                        "output": str(result.output),
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-pet-overlay-build":
            result = build_sync_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                url_base=args.url_base,
                refresh_seconds=args.refresh_seconds,
                tool_revision=revision,
                expected_output_name=PET_OVERLAY_OUTPUT_FILENAME,
                implemented_scope_extra=(
                    "保持原厂九个一级对象",
                    "萌宠根对象内的 AGENTS 独立覆盖层",
                    "AGENTS 虚拟一级导航状态",
                ),
            )
            print(
                json.dumps(
                    {
                        "result": "AGENTS 九对象覆盖层观察固件制作完成",
                        "output": str(result.output),
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-stock-pet-reuse-build":
            result = build_sync_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                url_base=args.url_base,
                refresh_seconds=args.refresh_seconds,
                tool_revision=revision,
                expected_output_name=STOCK_PET_REUSE_OUTPUT_FILENAME,
                implemented_scope_extra=(
                    "复用原厂萌宠动图控件",
                    "只使用萌宠状态高三位保存 AGENTS 导航",
                    "离开 AGENTS 时恢复原厂萌宠数据源",
                ),
                reuse_stock_pet=True,
            )
            print(
                json.dumps(
                    {
                        "result": "AGENTS 原厂萌宠控件复用观察固件制作完成",
                        "output": str(result.output),
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-stock-dispatch-build":
            result = build_sync_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                url_base=args.url_base,
                refresh_seconds=args.refresh_seconds,
                tool_revision=revision,
                expected_output_name=STOCK_DISPATCH_OUTPUT_FILENAME,
                implemented_scope_extra=(
                    "复用原厂萌宠动图控件",
                    "按原厂交互分派序号路由键值",
                    "原厂内部详情直接进入原厂回调",
                ),
                reuse_stock_pet=True,
            )
            print(
                json.dumps(
                    {
                        "result": "AGENTS 原厂交互分派兼容观察固件制作完成",
                        "output": str(result.output),
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-stock-callchain-build":
            result = build_stock_callchain_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                url_base=args.url_base,
                refresh_seconds=args.refresh_seconds,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "AGENTS 原厂精确调用链观察固件制作完成",
                        "output": str(result.output),
                        "expected_name": STOCK_CALLCHAIN_OUTPUT_FILENAME,
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-stock-enter-gate-build":
            result = build_stock_enter_gate_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                url_base=args.url_base,
                refresh_seconds=args.refresh_seconds,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "AGENTS 原厂确认键无栈透传观察固件制作完成",
                        "output": str(result.output),
                        "expected_name": STOCK_ENTER_GATE_OUTPUT_FILENAME,
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-local-ui-stock-resume-build":
            result = build_local_ui_stock_resume_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "AGENTS 交还原厂右旋分支的局部界面固件制作完成",
                        "output": str(result.output),
                        "expected_name": LOCAL_UI_STOCK_RESUME_OUTPUT_FILENAME,
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-local-ui-stock-safe-build":
            result = build_local_ui_stock_safe_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "AGENTS 原厂收尾顺序双向局部界面固件制作完成",
                        "output": str(result.output),
                        "expected_name": LOCAL_UI_STOCK_SAFE_OUTPUT_FILENAME,
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-local-ui-base-safe-build":
            result = build_local_ui_base_safe_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "AGENTS 基座生命周期保护固件制作完成",
                        "output": str(result.output),
                        "expected_name": LOCAL_UI_BASE_SAFE_OUTPUT_FILENAME,
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-live-data-reference-complete-build":
            result = build_live_data_reference_complete_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                url_base=args.url_base,
                refresh_seconds=args.refresh_seconds,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "AGENTS 完整参考复用真实数据固件制作完成",
                        "output": str(result.output),
                        "expected_name": (
                            LIVE_DATA_REFERENCE_COMPLETE_OUTPUT_FILENAME
                        ),
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-live-data-low-stack-build":
            result = build_live_data_low_stack_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                url_base=args.url_base,
                refresh_seconds=args.refresh_seconds,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "AGENTS 低栈真实数据固件制作完成",
                        "output": str(result.output),
                        "expected_name": LIVE_DATA_LOW_STACK_OUTPUT_FILENAME,
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-live-data-location-independent-build":
            result = build_live_data_location_independent_firmware(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                url_base=args.url_base,
                refresh_seconds=args.refresh_seconds,
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "AGENTS 位置无关真实数据固件制作完成",
                        "output": str(result.output),
                        "expected_name": (
                            LIVE_DATA_LOCATION_INDEPENDENT_OUTPUT_FILENAME
                        ),
                        "manifest": str(result.manifest),
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "agents-interaction-simulate":
            report = simulate_current_manifest(
                args.manifest,
                exhaustive_depth=args.depth,
            )
            selected_report = write_simulation_report(args.report, report)
            print(
                json.dumps(
                    {
                        "result": (
                            "刷前连续页面事件模拟通过"
                            if report["summary"]["passed"]
                            else "刷前连续页面事件模拟失败"
                        ),
                        "report": str(selected_report),
                        "summary": report["summary"],
                        "failures": report["failures"][:5],
                        "failures_truncated": len(report["failures"]) > 5,
                        "instruction_level_execution": False,
                        "physical_acceptance_replaced": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0 if report["summary"]["passed"] else 2

        if args.command == "opt-build":
            raise AgentsDashboardFirmwareError(
                "完整重写候选已因卡开机动画停用；"
                "请使用 agents-local-ui-stock-resume-build"
            )

        if args.command == "settings-hook-observation-build":
            result = build_settings_hook_observation(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                assembler=_required_tool("riscv64-elf-as"),
                linker=_required_tool("riscv64-elf-ld"),
                copier=_required_tool("riscv64-elf-objcopy"),
                readelf=_required_tool("riscv64-elf-readelf"),
                nm=_required_tool("riscv64-elf-nm"),
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "设置列表空挂接观察固件制作完成",
                        "output": str(result.output),
                        "manifest": str(result.manifest),
                        "output_name": HOOK_OBSERVATION_OUTPUT_NAME,
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "installation_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "page-settings-read-only-entry-build":
            result = build_page_settings_read_only_entry(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                assembler=_required_tool("riscv64-elf-as"),
                linker=_required_tool("riscv64-elf-ld"),
                copier=_required_tool("riscv64-elf-objcopy"),
                readelf=_required_tool("riscv64-elf-readelf"),
                nm=_required_tool("riscv64-elf-nm"),
                dumper=_required_tool("riscv64-elf-objdump"),
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "页面开关第八项只读入口候选制作完成",
                        "output": str(result.output),
                        "manifest": str(result.manifest),
                        "output_name": READ_ONLY_ENTRY_OUTPUT_NAME,
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "simulation_sequences": result.simulation_sequences,
                        "installation_allowed": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "page-settings-startup-passthrough-build":
            result = build_page_settings_startup_passthrough(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                assembler=_required_tool("riscv64-elf-as"),
                linker=_required_tool("riscv64-elf-ld"),
                copier=_required_tool("riscv64-elf-objcopy"),
                readelf=_required_tool("riscv64-elf-readelf"),
                nm=_required_tool("riscv64-elf-nm"),
                dumper=_required_tool("riscv64-elf-objdump"),
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "页面开关启动基础透传候选制作完成",
                        "output": str(result.output),
                        "manifest": str(result.manifest),
                        "output_name": STARTUP_PASSTHROUGH_OUTPUT_NAME,
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "simulation_indices": result.simulation_indices,
                        "installation_allowed": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "page-settings-row-creation-build":
            result = build_page_settings_row_creation(
                args.input,
                args.output,
                args.manifest,
                args.build_dir,
                assembler=_required_tool("riscv64-elf-as"),
                linker=_required_tool("riscv64-elf-ld"),
                copier=_required_tool("riscv64-elf-objcopy"),
                readelf=_required_tool("riscv64-elf-readelf"),
                nm=_required_tool("riscv64-elf-nm"),
                dumper=_required_tool("riscv64-elf-objdump"),
                tool_revision=revision,
            )
            print(
                json.dumps(
                    {
                        "result": "页面开关第八项普通行候选制作完成",
                        "output": str(result.output),
                        "manifest": str(result.manifest),
                        "output_name": ROW_CREATION_OUTPUT_NAME,
                        "output_sha256": result.sha256,
                        "output_md5": result.md5,
                        "payload_size": result.payload_size,
                        "payload_remaining": result.payload_remaining,
                        "simulation_indices": result.simulation_indices,
                        "installation_allowed": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

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
        print(
            json.dumps(
                {
                    "result": "离线固件制作完成",
                    "output": str(result.output),
                    "manifest": str(result.manifest),
                    "output_sha256": result.output_sha256,
                    "output_md5": result.output_md5,
                    "experimental_download_allowed": False,
                    "installation_allowed": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (
        AgentsDashboardFirmwareError,
        InteractionSimulationError,
        BuildGateError,
        FirmwarePayloadSpaceError,
        FirmwareValidationError,
        OptimizedFirmwareBuildError,
        PrimaryPageNavigationError,
        PrimaryPageSettingsBuildError,
        PageSettingsReadOnlyEntryError,
        PageSettingsRowCreationError,
        PageSettingsStartupPassthroughError,
        SettingsHookObservationError,
        SettingsMenuWrapError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        print(
            json.dumps(
                {
                    "result": "已停止",
                    "reason": str(error),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
