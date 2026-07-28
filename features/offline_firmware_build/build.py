"""按已批准修改清单制作 AP01 离线固件。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from core.firmware_image import (
    AP01_1_0_2_0031,
    BaselineDefinition,
    ByteRange,
    FirmwareValidationError,
    load_read_only_baseline,
    refresh_recovery_crc,
    validate_candidate,
)


TOOL_VERSION = "0.1.0"
PLAN_SCHEMA_VERSION = 1
APPROVED_PLAN_STATUS = "approved-for-offline-build"
OUTPUT_FILENAME = "opt-setting.bin"
ALLOWED_REGION_KINDS = {
    "application-code",
    "application-read-only-data",
    "application-resource",
}


class BuildGateError(RuntimeError):
    """制作阶段门禁未满足。"""


@dataclass(frozen=True)
class PatchInstruction:
    name: str
    objective: str
    offset: int
    expected_before: bytes
    replacement: bytes
    evidence_path: str
    evidence_note: str
    region_kind: str

    @property
    def byte_range(self) -> ByteRange:
        return ByteRange(self.offset, self.offset + len(self.replacement))

    def to_manifest(self) -> dict[str, object]:
        return {
            "name": self.name,
            "objective": self.objective,
            "offset": self.offset,
            "offset_hex": f"0x{self.offset:x}",
            "length": len(self.replacement),
            "expected_before_hex": self.expected_before.hex(),
            "replacement_hex": self.replacement.hex(),
            "evidence_path": self.evidence_path,
            "evidence_note": self.evidence_note,
            "region_kind": self.region_kind,
        }


@dataclass(frozen=True)
class PatchPlan:
    path: Path
    status: str
    target_model: str
    target_version: str
    baseline_sha256: str
    patches: tuple[PatchInstruction, ...]


@dataclass(frozen=True)
class BuildResult:
    output: Path
    manifest: Path
    output_sha256: str
    output_md5: str


def _beijing_now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def _validated_cloud_check(
    version: str,
    md5: str,
    checked_at: str,
    definition: BaselineDefinition,
) -> dict[str, object]:
    if version != definition.version:
        raise BuildGateError("云端最新版本与固定原厂基线不一致")
    if md5.lower() != definition.md5:
        raise BuildGateError("云端最新固件 MD5 与固定原厂基线不一致")
    try:
        checked_time = datetime.fromisoformat(checked_at)
    except ValueError as error:
        raise BuildGateError("云端检查时间必须是带时区的标准时间") from error
    if checked_time.tzinfo is None:
        raise BuildGateError("云端检查时间必须包含时区")
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    age_seconds = (now - checked_time.astimezone(ZoneInfo("Asia/Shanghai"))).total_seconds()
    if age_seconds < -300 or age_seconds > 3600:
        raise BuildGateError("云端固件信息必须在本次制作前一小时内重新查询")
    return {
        "checked": True,
        "checked_at": checked_at,
        "version": version,
        "md5": md5.lower(),
        "matches_baseline": True,
    }


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BuildGateError(f"修改清单字段缺失或为空：{field}")
    return value.strip()


def _decode_hex(value: Any, field: str) -> bytes:
    text = _required_text(value, field)
    try:
        result = bytes.fromhex(text)
    except ValueError as error:
        raise BuildGateError(f"修改清单字段不是合法十六进制字节：{field}") from error
    if not result:
        raise BuildGateError(f"修改清单字节不能为空：{field}")
    return result


def _resolve_evidence(repo_root: Path, relative: str) -> Path:
    if Path(relative).is_absolute():
        raise BuildGateError("证据路径必须是仓库内的相对路径")
    root = (repo_root / "knowledge").resolve()
    selected = (repo_root / relative).resolve()
    try:
        selected.relative_to(root)
    except ValueError as error:
        raise BuildGateError("修改证据必须位于 knowledge 目录") from error
    if not selected.is_file():
        raise BuildGateError(f"修改证据文件不存在：{relative}")
    return selected


def load_patch_plan(
    path: Path,
    repo_root: Path,
    definition: BaselineDefinition = AP01_1_0_2_0031,
) -> PatchPlan:
    selected = path.expanduser().resolve(strict=True)
    try:
        document = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BuildGateError(f"无法读取修改清单：{selected}") from error
    if not isinstance(document, dict):
        raise BuildGateError("修改清单根节点必须是对象")
    if document.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise BuildGateError(
            f"修改清单版本必须为 {PLAN_SCHEMA_VERSION}"
        )

    status = _required_text(document.get("status"), "status")
    if status != APPROVED_PLAN_STATUS:
        raise BuildGateError(
            "修改清单尚未明确批准进入离线构建，禁止生成优化固件"
        )

    target = document.get("target")
    if not isinstance(target, dict):
        raise BuildGateError("修改清单缺少 target 对象")
    target_model = _required_text(target.get("model"), "target.model")
    target_version = _required_text(target.get("version"), "target.version")
    baseline_sha256 = _required_text(
        target.get("baseline_sha256"), "target.baseline_sha256"
    ).lower()
    if target_model != definition.model or target_version != definition.version:
        raise BuildGateError("修改清单的目标型号或版本与固定基线不一致")
    if baseline_sha256 != definition.sha256:
        raise BuildGateError("修改清单的原厂 SHA-256 与固定基线不一致")

    raw_patches = document.get("patches")
    if not isinstance(raw_patches, list) or not raw_patches:
        raise BuildGateError(
            "修改清单没有已批准修改区间，禁止把原厂副本伪装成优化固件"
        )

    patches: list[PatchInstruction] = []
    for index, raw in enumerate(raw_patches):
        field = f"patches[{index}]"
        if not isinstance(raw, dict):
            raise BuildGateError(f"{field} 必须是对象")
        offset = raw.get("offset")
        if not isinstance(offset, int):
            raise BuildGateError(f"{field}.offset 必须是整数")
        expected = _decode_hex(raw.get("expected_before_hex"), f"{field}.expected_before_hex")
        replacement = _decode_hex(raw.get("replacement_hex"), f"{field}.replacement_hex")
        if len(expected) != len(replacement):
            raise BuildGateError(f"{field} 修改前后字节数必须相同")
        if expected == replacement:
            raise BuildGateError(f"{field} 修改前后字节完全相同")
        region_kind = _required_text(raw.get("region_kind"), f"{field}.region_kind")
        if region_kind not in ALLOWED_REGION_KINDS:
            raise BuildGateError(f"{field} 区域类型不在允许范围内")
        evidence_path = _required_text(raw.get("evidence_path"), f"{field}.evidence_path")
        _resolve_evidence(repo_root, evidence_path)
        patch = PatchInstruction(
            name=_required_text(raw.get("name"), f"{field}.name"),
            objective=_required_text(raw.get("objective"), f"{field}.objective"),
            offset=offset,
            expected_before=expected,
            replacement=replacement,
            evidence_path=evidence_path,
            evidence_note=_required_text(raw.get("evidence_note"), f"{field}.evidence_note"),
            region_kind=region_kind,
        )
        byte_range = patch.byte_range
        if byte_range.start < definition.immutable_header_end:
            raise BuildGateError(f"{field} 进入禁止修改的文件头区域")
        if byte_range.end > definition.recovery_trailer_offset:
            raise BuildGateError(f"{field} 进入文件尾恢复记录或越过固件边界")
        if any(byte_range.overlaps(existing.byte_range) for existing in patches):
            raise BuildGateError(f"{field} 与其他修改区间重叠")
        patches.append(patch)

    patches.sort(key=lambda item: item.offset)
    return PatchPlan(
        path=selected,
        status=status,
        target_model=target_model,
        target_version=target_version,
        baseline_sha256=baseline_sha256,
        patches=tuple(patches),
    )


def _write_json(path: Path, document: dict[str, object], *, immutable: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        document,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    if immutable and path.exists():
        raise BuildGateError(f"不可覆盖已经存在的冻结记录：{path}")
    temporary = path.with_name(path.name + ".part")
    if temporary.exists():
        raise BuildGateError(f"发现未处理的临时记录，停止覆盖：{temporary}")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if immutable:
            path.chmod(0o444)
    finally:
        if temporary.exists():
            temporary.unlink()


def inspect_baseline(
    source: Path,
    report_path: Path,
    *,
    tool_revision: dict[str, object],
    cloud_version: str | None = None,
    cloud_md5: str | None = None,
    cloud_checked_at: str | None = None,
    definition: BaselineDefinition = AP01_1_0_2_0031,
) -> dict[str, object]:
    firmware, baseline = load_read_only_baseline(source, definition)
    del firmware

    cloud_supplied = any((cloud_version, cloud_md5, cloud_checked_at))
    if cloud_supplied and not all((cloud_version, cloud_md5, cloud_checked_at)):
        raise BuildGateError("云端复核信息必须同时提供版本、MD5 和检查时间")
    cloud_report: dict[str, object]
    if cloud_supplied:
        assert cloud_version is not None
        assert cloud_md5 is not None
        assert cloud_checked_at is not None
        cloud_report = _validated_cloud_check(
            cloud_version,
            cloud_md5,
            cloud_checked_at,
            definition,
        )
    else:
        cloud_report = {
            "checked": False,
            "checked_at": None,
            "version": None,
            "md5": None,
            "matches_baseline": False,
        }

    report: dict[str, object] = {
        "schema_version": 1,
        "report_type": "baseline-inspection",
        "checked_at_beijing": _beijing_now(),
        "tool": {"version": TOOL_VERSION, **tool_revision},
        "source": {
            "path": str(source.expanduser().resolve()),
            "read_only": True,
        },
        "baseline": baseline.to_dict(),
        "cloud_latest": cloud_report,
        "gates": {
            "static_analysis_allowed": True,
            "offline_build_allowed": False,
            "reason": "没有已批准且具备直接证据的修改清单",
            "experimental_download_allowed": False,
            "installation_allowed": False,
        },
    }
    _write_json(report_path, report, immutable=False)
    return report


def _write_frozen_binary(path: Path, payload: bytes) -> None:
    if path.exists():
        raise BuildGateError(f"不可覆盖已经存在的冻结成品：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    if temporary.exists():
        raise BuildGateError(f"发现未处理的临时成品，停止覆盖：{temporary}")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.read_bytes() != payload:
            raise BuildGateError("临时成品写后回读不一致")
        os.replace(temporary, path)
        path.chmod(0o444)
    finally:
        if temporary.exists():
            temporary.unlink()


def make_firmware(
    source: Path,
    plan_path: Path,
    output: Path,
    manifest_path: Path,
    *,
    repo_root: Path,
    tool_revision: dict[str, object],
    cloud_version: str,
    cloud_md5: str,
    cloud_checked_at: str,
    definition: BaselineDefinition = AP01_1_0_2_0031,
) -> BuildResult:
    if tool_revision.get("scoped_code_dirty") is not False:
        raise BuildGateError("制作代码尚未提交，无法固定工具代码版本")
    cloud_report = _validated_cloud_check(
        cloud_version,
        cloud_md5,
        cloud_checked_at,
        definition,
    )
    source_resolved = source.expanduser().resolve(strict=True)
    output_resolved = output.expanduser().resolve()
    if source_resolved == output_resolved:
        raise BuildGateError("原厂输入与优化成品路径不得相同")
    if output_resolved.name != OUTPUT_FILENAME:
        raise BuildGateError(f"优化成品文件名必须是 {OUTPUT_FILENAME}")
    try:
        source_resolved.relative_to(repo_root.resolve())
    except ValueError:
        pass
    else:
        raise BuildGateError("原厂输入必须位于代码仓库之外的只读路径")

    baseline, baseline_report = load_read_only_baseline(source_resolved, definition)
    plan = load_patch_plan(plan_path, repo_root, definition)
    candidate = bytearray(baseline)
    for patch in plan.patches:
        byte_range = patch.byte_range
        actual = bytes(candidate[byte_range.start : byte_range.end])
        if actual != patch.expected_before:
            raise BuildGateError(
                f"修改前旧字节断言失败：{patch.name}，位置 0x{patch.offset:x}"
            )
        candidate[byte_range.start : byte_range.end] = patch.replacement

    recovery_crc_value = refresh_recovery_crc(candidate, definition)
    recovery_crc_range = ByteRange(
        definition.recovery_trailer_offset + 36,
        definition.recovery_trailer_offset + 40,
    )
    allowed_ranges = [patch.byte_range for patch in plan.patches]
    allowed_ranges.append(recovery_crc_range)
    candidate_report = validate_candidate(
        baseline,
        bytes(candidate),
        allowed_ranges,
        definition,
    )

    manifest: dict[str, object] = {
        "schema_version": 1,
        "manifest_type": "offline-firmware-build",
        "built_at_beijing": _beijing_now(),
        "tool": {"version": TOOL_VERSION, **tool_revision},
        "cloud_latest": cloud_report,
        "plan": {
            "path": str(plan.path),
            "status": plan.status,
            "target_model": plan.target_model,
            "target_version": plan.target_version,
            "baseline_sha256": plan.baseline_sha256,
        },
        "input": {
            "path": str(source_resolved),
            "read_only": True,
            **baseline_report.to_dict(),
        },
        "output": {
            "path": str(output_resolved),
            "read_only": True,
            **candidate_report.to_dict(),
        },
        "declared_patches": [patch.to_manifest() for patch in plan.patches],
        "recovery_crc_after_build": f"0x{recovery_crc_value:08x}",
        "validation": {
            "old_bytes_asserted": True,
            "output_name_fixed": True,
            "input_output_paths_distinct": True,
            "input_outside_repository": True,
            "total_length_preserved": True,
            "immutable_header_preserved": True,
            "recovery_structure_preserved": True,
            "changed_ranges_outside_plan": False,
            "frozen_readback_sha256_matches": True,
            "experimental_download_allowed": False,
            "installation_allowed": False,
        },
    }
    output_written = False
    try:
        _write_frozen_binary(output_resolved, bytes(candidate))
        output_written = True
        frozen_readback = output_resolved.read_bytes()
        readback_report = validate_candidate(
            baseline,
            frozen_readback,
            allowed_ranges,
            definition,
        )
        if readback_report.sha256 != candidate_report.sha256:
            raise BuildGateError("冻结成品重新读取后的完整文件指纹不一致")
        _write_json(manifest_path.resolve(), manifest, immutable=True)
    except Exception:
        if output_written and output_resolved.exists():
            output_resolved.chmod(0o644)
            output_resolved.unlink()
        raise
    return BuildResult(
        output=output_resolved,
        manifest=manifest_path.resolve(),
        output_sha256=candidate_report.sha256,
        output_md5=candidate_report.md5,
    )
