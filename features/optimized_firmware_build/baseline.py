"""校验完整优化固件使用的已验收阶段输入。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.firmware_image import (
    AP01_1_0_2_0031,
    BaselineDefinition,
    ByteRange,
    load_read_only_baseline,
    validate_candidate,
)


FINAL_OUTPUT_FILENAME = "ap01-1.0.2_0031-opt.bin"


class OptimizedFirmwareBuildError(RuntimeError):
    """完整优化固件输入没有通过制作门禁。"""


@dataclass(frozen=True)
class StageBaselineDefinition:
    """一个已经验收并允许继续组合的精确阶段成品。"""

    filename: str
    size: int
    md5: str
    sha256: str
    recovery_crc: int
    approved_ranges: tuple[ByteRange, ...]


ACCEPTED_OPT_SETTING = StageBaselineDefinition(
    filename="opt-setting.bin",
    size=6_804_520,
    md5="13a7286f4824b1ad87d9bc32f1d3d39c",
    sha256="348d0843ac3f3f380eb155170c4104fd8467a018ddfd13670d67be998f269dc1",
    recovery_crc=0xE57875A7,
    approved_ranges=(
        ByteRange(0x01C008, 0x01C0AC),
        ByteRange(0x0F919E, 0x0F91A2),
        ByteRange(0x0F976A, 0x0F976E),
        ByteRange(0x108E20, 0x108E22),
        ByteRange(0x67D424, 0x67D428),
    ),
)


def _fingerprints(payload: bytes) -> tuple[str, str]:
    return (
        hashlib.md5(payload).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )


def _load_read_only_stage(
    path: Path,
    definition: StageBaselineDefinition,
) -> tuple[Path, bytes]:
    selected = path.expanduser().resolve(strict=True)
    if not selected.is_file():
        raise OptimizedFirmwareBuildError(f"阶段成品路径不是普通文件：{selected}")
    if selected.name != definition.filename:
        raise OptimizedFirmwareBuildError(
            f"阶段成品文件名必须是 {definition.filename}"
        )
    writable_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    if selected.stat().st_mode & writable_bits:
        raise OptimizedFirmwareBuildError(
            f"阶段成品必须先设为只读，当前仍可写：{selected}"
        )
    payload = selected.read_bytes()
    actual_md5, actual_sha256 = _fingerprints(payload)
    if len(payload) != definition.size:
        raise OptimizedFirmwareBuildError("阶段成品总字节数不匹配")
    if actual_md5 != definition.md5:
        raise OptimizedFirmwareBuildError("阶段成品 MD5 不匹配")
    if actual_sha256 != definition.sha256:
        raise OptimizedFirmwareBuildError("阶段成品 SHA-256 不匹配")
    return selected, payload


def _write_report(path: Path, document: dict[str, object]) -> None:
    selected = path.expanduser().resolve()
    selected.parent.mkdir(parents=True, exist_ok=True)
    temporary = selected.with_name(selected.name + ".part")
    if temporary.exists():
        raise OptimizedFirmwareBuildError(f"发现未处理的临时报告：{temporary}")
    payload = json.dumps(
        document,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, selected)
    finally:
        if temporary.exists():
            temporary.unlink()


def inspect_optimized_baseline(
    original_path: Path,
    stage_path: Path,
    report_path: Path,
    *,
    tool_revision: dict[str, object],
    original_definition: BaselineDefinition = AP01_1_0_2_0031,
    stage_definition: StageBaselineDefinition = ACCEPTED_OPT_SETTING,
) -> dict[str, object]:
    """验证原厂锚点和阶段成品，尚不生成最终固件。"""

    original, original_report = load_read_only_baseline(
        original_path,
        original_definition,
    )
    stage_selected, stage = _load_read_only_stage(stage_path, stage_definition)
    candidate_report = validate_candidate(
        original,
        stage,
        stage_definition.approved_ranges,
        original_definition,
    )
    if candidate_report.recovery.stored_crc != stage_definition.recovery_crc:
        raise OptimizedFirmwareBuildError("阶段成品文件尾恢复校验值不匹配")

    document: dict[str, object] = {
        "schema_version": 1,
        "report_type": "optimized-firmware-baseline-inspection",
        "checked_at_beijing": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
            timespec="seconds"
        ),
        "tool": tool_revision,
        "original": {
            "path": str(original_path.expanduser().resolve()),
            **original_report.to_dict(),
        },
        "stage_input": {
            "path": str(stage_selected),
            "filename": stage_definition.filename,
            **candidate_report.to_dict(),
        },
        "final_output": {
            "required_filename": FINAL_OUTPUT_FILENAME,
            "created": False,
        },
        "gates": {
            "original_identity_matches": True,
            "stage_identity_matches": True,
            "stage_diff_within_approved_ranges": True,
            "optimized_baseline_ready": True,
            "full_build_allowed": False,
            "reason": "完整看板新增修改区间尚未完成直接证据、设计记录和批准",
            "experimental_download_allowed": False,
            "installation_allowed": False,
        },
    }
    _write_report(report_path, document)
    return document
