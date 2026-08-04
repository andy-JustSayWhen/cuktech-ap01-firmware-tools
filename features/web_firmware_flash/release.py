"""构建双平台同源网页刷机发布包并执行敏感内容门禁。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path


SENSITIVE_TEXT = (
    "/Users/mac/",
    "/Users/mac/Desktop/cuktech-screen-controller",
    "CUKTECH_MI_PASS_TOKEN=",
    "192.168.31.",
)


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseReport:
    root: Path
    file_count: int
    manifest_sha256: str


def _copy_tree(source: Path, target: Path) -> None:
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", "test_*.py", "SOURCE.md", "release.py"
        ),
    )


def _write_launchers(stage: Path) -> None:
    mac = stage / "启动 AP01 刷机.command"
    mac.write_text(
        "#!/bin/zsh\nset -euo pipefail\nHERE=\"${0:A:h}\"\n"
        "python3 \"$HERE/app/ap01_web.py\" --release-dir \"$HERE/firmware\" "
        "--data-dir \"$HOME/Library/Application Support/CUKTECH AP01 Web\"\n",
        encoding="utf-8",
    )
    mac.chmod(mac.stat().st_mode | stat.S_IXUSR)
    (stage / "启动 AP01 刷机.cmd").write_text(
        "@echo off\r\nset HERE=%~dp0\r\n"
        "py -3 \"%HERE%app\\ap01_web.py\" --release-dir \"%HERE%firmware\" "
        "--data-dir \"%LOCALAPPDATA%\\CUKTECH AP01 Web\"\r\n"
        "if errorlevel 1 pause\r\n",
        encoding="utf-8",
    )


def _scan(stage: Path) -> None:
    for path in stage.rglob("*"):
        if not path.is_file() or path.name == "FILE-MANIFEST.json":
            continue
        if path.suffix.lower() in {".bin", ".png", ".gif", ".zip"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in SENSITIVE_TEXT:
            if needle in text:
                raise ReleaseError(f"发布文件包含禁止内容：{path.name}")


def _manifest(stage: Path) -> tuple[list[dict[str, object]], str]:
    files: list[dict[str, object]] = []
    for path in sorted(stage.rglob("*")):
        if not path.is_file() or path.name == "FILE-MANIFEST.json":
            continue
        payload = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(stage).as_posix(),
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    encoded = json.dumps({"schema_version": 1, "files": files}, ensure_ascii=False, indent=2).encode("utf-8")
    (stage / "FILE-MANIFEST.json").write_bytes(encoded)
    return files, hashlib.sha256(encoded).hexdigest()


def build_release(
    project_root: Path,
    output: Path,
    *,
    firmware: Path | None = None,
    firmware_manifest: Path | None = None,
    simulation_report: Path | None = None,
) -> ReleaseReport:
    root = project_root.expanduser().resolve(strict=True)
    stage = output.expanduser().resolve()
    if stage.exists():
        raise ReleaseError("发布目录已存在，拒绝覆盖")
    stage.mkdir(parents=True)
    try:
        (stage / "app").mkdir()
        shutil.copy2(root / "app/ap01_web.py", stage / "app/ap01_web.py")
        _copy_tree(root / "features/web_firmware_flash", stage / "features/web_firmware_flash")
        _copy_tree(root / "core/firmware_image", stage / "core/firmware_image")
        for package in (stage / "features", stage / "core"):
            (package / "__init__.py").write_text("", encoding="utf-8")
        (stage / "firmware").mkdir()
        if any(value is not None for value in (firmware, firmware_manifest, simulation_report)):
            if not all(value is not None for value in (firmware, firmware_manifest, simulation_report)):
                raise ReleaseError("固件、构建清单和模拟报告必须同时提供")
            assert firmware is not None and firmware_manifest is not None and simulation_report is not None
            shutil.copy2(firmware, stage / "firmware" / firmware.name)
            shutil.copy2(firmware_manifest, stage / "firmware" / (firmware.name + ".manifest.json"))
            shutil.copy2(simulation_report, stage / "firmware/interaction-simulation.json")
        (stage / "requirements.txt").write_text("requests==2.34.2\n", encoding="ascii")
        (stage / "先读我.txt").write_text(
            "双击对应系统的启动文件，Chrome 会自动打开。页面将依次完成准备、设备、固件、风险、执行和结果六个阶段。\n",
            encoding="utf-8",
        )
        _write_launchers(stage)
        _scan(stage)
        files, manifest_sha = _manifest(stage)
        return ReleaseReport(stage, len(files), manifest_sha)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
