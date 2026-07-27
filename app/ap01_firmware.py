"""AP01 原厂基线检查与离线固件制作入口。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.firmware_image import FirmwareValidationError
from features.offline_firmware_build import (
    BuildGateError,
    inspect_baseline,
    make_firmware,
)
from features.settings_menu_wrap import (
    SettingsMenuWrapError,
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

    build_command = commands.add_parser("build", help="按已批准清单离线制作固件")
    build_command.add_argument("--input", type=Path, required=True)
    build_command.add_argument("--plan", type=Path, required=True)
    build_command.add_argument("--output", type=Path, required=True)
    build_command.add_argument("--manifest", type=Path, required=True)
    build_command.add_argument("--cloud-version", required=True)
    build_command.add_argument("--cloud-md5", required=True)
    build_command.add_argument("--cloud-checked-at", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    revision = _tool_revision()
    try:
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
        BuildGateError,
        FirmwareValidationError,
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
