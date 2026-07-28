"""生成 AP01 系统设置菜单首尾循环的待批准修改清单。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.firmware_image import AP01_1_0_2_0031, load_read_only_baseline


MODULE_DIR = Path(__file__).resolve().parent
ASSEMBLY_SOURCE = MODULE_DIR / "settings_menu_wrap_patch.S"
LINKER_SCRIPT = MODULE_DIR / "settings_menu_wrap_patch.ld"
APPROVAL_RECORD_PATH = MODULE_DIR / "approval_record.json"
EVIDENCE_PATH = (
    "knowledge/AP01-官方固件分析/cases/"
    "2026-07-27-系统设置菜单首尾循环静态定位.md"
)

DRAFT_PLAN_STATUS = "draft-awaiting-user-approval"
APPROVED_PLAN_STATUS = "approved-for-offline-build"
APPROVAL_RECORD_SCHEMA_VERSION = 1
APPROVAL_LIMIT = (
    "仅批准证据文档中的 3 个精确修改区间用于离线构建，不允许下载或安装"
)
EXPECTED_BINUTILS_VERSION = "2.46.1"
XIP_DELTA = 0x9FFFF000
CODE_GAP_START = 0x01C008
CODE_GAP_END = 0x01C100
CODE_GAP_PREVIOUS_INSTRUCTION = (0x01C006, bytes.fromhex("8280"))
CODE_GAP_NEXT_INSTRUCTION = (0x01C100, bytes.fromhex("23221500"))
PRESERVED_LOG_RANGES = (
    (0x0F912C, 0x0F914E, "右旋通用日志"),
    (0x0F9172, 0x0F918C, "右旋系统设置日志"),
    (0x0F96F8, 0x0F971A, "左旋通用日志"),
    (0x0F973E, 0x0F9758, "左旋系统设置日志"),
)


class SettingsMenuWrapError(RuntimeError):
    """设置菜单修改清单无法安全生成。"""


@dataclass(frozen=True)
class PatchDefinition:
    name: str
    objective: str
    section_name: str
    offset: int
    runtime_address: int
    expected_before: bytes
    expected_replacement: bytes
    evidence_note: str

    @property
    def end(self) -> int:
        return self.offset + len(self.expected_before)

    @property
    def runtime_end(self) -> int:
        return self.runtime_address + len(self.expected_before)

    def to_plan_entry(self, replacement: bytes) -> dict[str, Any]:
        return {
            "name": self.name,
            "objective": self.objective,
            "offset": self.offset,
            "offset_hex": f"0x{self.offset:x}",
            "runtime_address_hex": f"0x{self.runtime_address:x}",
            "length": len(self.expected_before),
            "expected_before_hex": self.expected_before.hex(),
            "replacement_hex": replacement.hex(),
            "evidence_path": EVIDENCE_PATH,
            "evidence_note": self.evidence_note,
            "region_kind": "application-code",
        }


PATCHES = (
    PatchDefinition(
        name="首尾循环处理程序",
        objective="在已验证零填充代码间隙中处理动态项目数和首尾循环",
        section_name=".payload",
        offset=0x01C008,
        runtime_address=0xA001B008,
        expected_before=b"\x00" * 138,
        expected_replacement=bytes.fromhex(
            "03a58900efa09a7daa8a83c71400094763f4ea006fd0cd0b9386"
            "17fd63f4da006fd00d0b638456016fd02d1793070003a380f400"
            "03a589009385faff0146ef805d516fd0ed0803a58900efa03a79"
            "aa8a83c71400094763f4ea006fd06d07938607fd63e456016fd0"
            "ad0699c26fd0ad6f9387fa02a380f40003a5890081451386faff"
            "ef801d4d6fd0ad04"
        ),
        evidence_note="证据文档第 15 节：138 字节处理程序从实际列表控件动态读取项目数",
    ),
    PatchDefinition(
        name="右旋状态挂接",
        objective="把系统设置右旋状态检查交给版本限定处理",
        section_name=".right_hook",
        offset=0x0F919E,
        runtime_address=0xA00F819E,
        expected_before=bytes.fromhex("83c71400"),
        expected_replacement=bytes.fromhex("6f20b2e6"),
        evidence_note="证据文档第 15 节：跳转目标为 0xa001b008",
    ),
    PatchDefinition(
        name="左旋状态挂接",
        objective="把系统设置左旋状态检查交给版本限定处理",
        section_name=".left_hook",
        offset=0x0F976A,
        runtime_address=0xA00F876A,
        expected_before=bytes.fromhex("83c71400"),
        expected_replacement=bytes.fromhex("6f20528e"),
        evidence_note="证据文档第 15 节：跳转目标为 0xa001b04e",
    ),
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _find_tool(name: str) -> Path:
    discovered = shutil.which(name)
    candidates = [
        Path(discovered) if discovered else None,
        Path("/opt/homebrew/bin") / name,
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise SettingsMenuWrapError(f"缺少构建工具：{name}")


def _first_version_line(tool: Path) -> str:
    try:
        result = subprocess.run(
            [str(tool), "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SettingsMenuWrapError(f"无法读取构建工具版本：{tool}") from error
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    if EXPECTED_BINUTILS_VERSION not in first_line:
        raise SettingsMenuWrapError(
            f"构建工具版本不匹配：预期 {EXPECTED_BINUTILS_VERSION}，实际 {first_line}"
        )
    return first_line


def _validate_definitions() -> None:
    previous_end = AP01_1_0_2_0031.immutable_header_end
    for patch in PATCHES:
        if patch.offset < previous_end:
            raise SettingsMenuWrapError("设置菜单修改区间重叠或顺序错误")
        if patch.runtime_address != XIP_DELTA + patch.offset:
            raise SettingsMenuWrapError(f"运行地址换算不匹配：{patch.name}")
        if len(patch.expected_before) != len(patch.expected_replacement):
            raise SettingsMenuWrapError(f"修改前后字节数不一致：{patch.name}")
        if patch.end > AP01_1_0_2_0031.recovery_trailer_offset:
            raise SettingsMenuWrapError(f"修改区间越过主程序安全边界：{patch.name}")
        for log_start, log_end, log_name in PRESERVED_LOG_RANGES:
            if patch.offset < log_end and log_start < patch.end:
                raise SettingsMenuWrapError(
                    f"修改区间触碰必须保留的原厂日志：{log_name}"
                )
        previous_end = patch.end


def _validate_code_gap(firmware: bytes) -> None:
    if firmware[CODE_GAP_START:CODE_GAP_END] != b"\x00" * (
        CODE_GAP_END - CODE_GAP_START
    ):
        raise SettingsMenuWrapError("新增处理程序所在完整函数间隙不是全零")
    previous_offset, previous_bytes = CODE_GAP_PREVIOUS_INSTRUCTION
    if firmware[
        previous_offset : previous_offset + len(previous_bytes)
    ] != previous_bytes:
        raise SettingsMenuWrapError("新增处理程序前一函数边界不匹配")
    next_offset, next_bytes = CODE_GAP_NEXT_INSTRUCTION
    if firmware[next_offset : next_offset + len(next_bytes)] != next_bytes:
        raise SettingsMenuWrapError("新增处理程序后一函数边界不匹配")
    payload = PATCHES[0]
    if payload.offset != CODE_GAP_START or payload.end > CODE_GAP_END:
        raise SettingsMenuWrapError("新增处理程序没有完整落在已验证函数间隙")


def assemble_and_verify() -> dict[str, Any]:
    """汇编版本限定修改，并与已审查字节逐区间比较。"""

    _validate_definitions()
    assembler = _find_tool("riscv64-elf-as")
    linker = _find_tool("riscv64-elf-ld")
    copier = _find_tool("riscv64-elf-objcopy")
    disassembler = _find_tool("riscv64-elf-objdump")
    versions = {
        "assembler": _first_version_line(assembler),
        "linker": _first_version_line(linker),
        "copier": _first_version_line(copier),
        "disassembler": _first_version_line(disassembler),
    }

    with tempfile.TemporaryDirectory(prefix="ap01-settings-menu-wrap-") as selected:
        build_dir = Path(selected)
        object_path = build_dir / "settings-menu-wrap.o"
        elf_path = build_dir / "settings-menu-wrap.elf"
        section_paths = {
            patch.offset: build_dir / f"patch-{patch.offset:06x}.bin"
            for patch in PATCHES
        }
        dump_sections: list[object] = [copier]
        for patch in PATCHES:
            dump_sections.extend(
                (
                    "--dump-section",
                    f"{patch.section_name}={section_paths[patch.offset]}",
                )
            )
        dump_sections.append(elf_path)
        commands = (
            (
                assembler,
                "-march=rv32imac",
                "-mabi=ilp32",
                "-o",
                object_path,
                ASSEMBLY_SOURCE,
            ),
            (
                linker,
                "-m",
                "elf32lriscv",
                "--no-relax",
                "-T",
                LINKER_SCRIPT,
                "-o",
                elf_path,
                object_path,
            ),
            tuple(dump_sections),
        )
        try:
            for command in commands:
                subprocess.run(
                    [str(item) for item in command],
                    check=True,
                    capture_output=True,
                    text=True,
                )
        except (OSError, subprocess.SubprocessError) as error:
            raise SettingsMenuWrapError("设置菜单修改字节汇编或链接失败") from error

        generated: dict[int, bytes] = {}
        for patch in PATCHES:
            replacement = section_paths[patch.offset].read_bytes()
            if replacement != patch.expected_replacement:
                raise SettingsMenuWrapError(
                    f"汇编结果与已审查字节不一致：{patch.name}"
                )
            generated[patch.offset] = replacement

        try:
            disassembly = subprocess.run(
                [
                    str(disassembler),
                    "-d",
                    "-M",
                    "no-aliases,numeric",
                    str(elf_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.lower()
        except (OSError, subprocess.SubprocessError) as error:
            raise SettingsMenuWrapError("无法反查设置菜单修改指令") from error
        reviewed_external_edges = (
            (0xA001B00C, 0xA00C5FE4),
            (0xA001B01C, 0xA00F80D8),
            (0xA001B028, 0xA00F80D8),
            (0xA001B030, 0xA00F81A2),
            (0xA001B046, 0xA00F3D5A),
            (0xA001B04A, 0xA00F80D8),
            (0xA001B052, 0xA00C5FE4),
            (0xA001B062, 0xA00F80D8),
            (0xA001B06E, 0xA00F80D8),
            (0xA001B074, 0xA00F876E),
            (0xA001B08A, 0xA00F3D5A),
            (0xA001B08E, 0xA00F80D8),
            (0xA00F819E, 0xA001B008),
            (0xA00F876A, 0xA001B04E),
        )
        disassembly_lines = {
            line.lstrip().split(":", 1)[0]: line.lower()
            for line in disassembly.splitlines()
            if ":" in line
        }
        for source, target in reviewed_external_edges:
            instruction = disassembly_lines.get(f"{source:08x}", "")
            if f"{target:08x}" not in instruction:
                raise SettingsMenuWrapError(
                    "反汇编控制流与已审查结果不一致："
                    f"0x{source:08x} -> 0x{target:08x}"
                )
        reviewed_list_count_loads = (
            (0xA001B008, "x10,8(x19)"),
            (0xA001B010, "x21,x10"),
            (0xA001B04E, "x10,8(x19)"),
            (0xA001B056, "x21,x10"),
        )
        for address, operands in reviewed_list_count_loads:
            instruction = disassembly_lines.get(f"{address:08x}", "")
            if operands not in instruction:
                raise SettingsMenuWrapError(
                    "实际设置列表计数的数据流与已审查结果不一致："
                    f"0x{address:08x}"
                )

    return {
        "version": EXPECTED_BINUTILS_VERSION,
        "tools": versions,
        "assembly_sha256": _sha256_file(ASSEMBLY_SOURCE),
        "linker_script_sha256": _sha256_file(LINKER_SCRIPT),
        "verified_control_flow": [
            {
                "source_hex": f"0x{source:08x}",
                "target_hex": f"0x{target:08x}",
            }
            for source, target in reviewed_external_edges
        ],
        "verified_list_count_loads": [
            {
                "address_hex": f"0x{address:08x}",
                "operands": operands,
            }
            for address, operands in reviewed_list_count_loads
        ],
        "replacements": generated,
    }


def build_draft_plan(
    source: Path,
    *,
    tool_revision: dict[str, Any],
) -> dict[str, Any]:
    """校验真实基线并返回无法用于构建的待批准清单。"""

    firmware, baseline = load_read_only_baseline(source, AP01_1_0_2_0031)
    _validate_code_gap(firmware)
    toolchain = assemble_and_verify()
    replacements = toolchain.pop("replacements")

    entries: list[dict[str, Any]] = []
    for patch in PATCHES:
        actual = firmware[patch.offset : patch.end]
        if actual != patch.expected_before:
            raise SettingsMenuWrapError(f"原厂旧字节断言失败：{patch.name}")
        entries.append(patch.to_plan_entry(replacements[patch.offset]))

    return {
        "schema_version": 1,
        "status": DRAFT_PLAN_STATUS,
        "target": {
            "model": AP01_1_0_2_0031.model,
            "version": AP01_1_0_2_0031.version,
            "baseline_sha256": AP01_1_0_2_0031.sha256,
        },
        "source_validation": baseline.to_dict(),
        "tool_revision": tool_revision,
        "toolchain": toolchain,
        "evidence_path": EVIDENCE_PATH,
        "review": {
            "patch_count": len(entries),
            "firmware_output_allowed": False,
            "approval_required": (
                "用户必须明确批准证据文档中的 3 个精确区间，"
                "才能另行形成允许离线构建的清单"
            ),
            "logging_changed": False,
            "preserved_log_ranges": [
                {
                    "name": name,
                    "start_hex": f"0x{start:x}",
                    "end_exclusive_hex": f"0x{end:x}",
                }
                for start, end, name in PRESERVED_LOG_RANGES
            ],
            "code_gap": {
                "start_hex": f"0x{CODE_GAP_START:x}",
                "end_exclusive_hex": f"0x{CODE_GAP_END:x}",
                "total_zero_bytes": CODE_GAP_END - CODE_GAP_START,
                "used_bytes": len(PATCHES[0].expected_replacement),
            },
        },
        "patches": entries,
    }


def _approval_scope(document: dict[str, Any]) -> dict[str, Any]:
    review = document["review"]
    return {
        "schema_version": document["schema_version"],
        "target": document["target"],
        "evidence_path": document["evidence_path"],
        "review": {
            "patch_count": review["patch_count"],
            "logging_changed": review["logging_changed"],
            "preserved_log_ranges": review["preserved_log_ranges"],
            "code_gap": review["code_gap"],
        },
        "patches": document["patches"],
    }


def _approval_scope_sha256(document: dict[str, Any]) -> str:
    payload = json.dumps(
        _approval_scope(document),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_approval_record(document: dict[str, Any]) -> dict[str, Any]:
    try:
        approval = json.loads(APPROVAL_RECORD_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SettingsMenuWrapError("无法读取系统设置菜单批准记录") from error
    if not isinstance(approval, dict):
        raise SettingsMenuWrapError("系统设置菜单批准记录根节点必须是对象")
    if approval.get("schema_version") != APPROVAL_RECORD_SCHEMA_VERSION:
        raise SettingsMenuWrapError("系统设置菜单批准记录版本不匹配")
    if approval.get("status") != APPROVED_PLAN_STATUS:
        raise SettingsMenuWrapError("系统设置菜单批准记录状态不允许离线构建")
    if approval.get("approval_statement") != "批准":
        raise SettingsMenuWrapError("系统设置菜单批准记录缺少明确批准原文")
    if approval.get("target") != document["target"]:
        raise SettingsMenuWrapError("系统设置菜单批准记录的目标基线不匹配")
    if approval.get("evidence_path") != document["evidence_path"]:
        raise SettingsMenuWrapError("系统设置菜单批准记录的证据路径不匹配")
    if approval.get("patch_count") != document["review"]["patch_count"]:
        raise SettingsMenuWrapError("系统设置菜单批准记录的修改区间数量不匹配")
    scope_sha256 = _approval_scope_sha256(document)
    if approval.get("scope_sha256") != scope_sha256:
        raise SettingsMenuWrapError("系统设置菜单批准范围指纹不一致，必须重新审批")
    approved_at = approval.get("approved_at_beijing")
    if not isinstance(approved_at, str) or not approved_at.strip():
        raise SettingsMenuWrapError("系统设置菜单批准记录缺少批准时间")
    if approval.get("approval_limit") != APPROVAL_LIMIT:
        raise SettingsMenuWrapError("系统设置菜单批准记录的使用限制不匹配")
    return approval


def build_approved_plan(
    source: Path,
    *,
    tool_revision: dict[str, Any],
) -> dict[str, Any]:
    """重新校验真实基线，并返回与用户批准范围完全一致的清单。"""

    document = build_draft_plan(source, tool_revision=tool_revision)
    approval = _load_approval_record(document)
    scope_sha256 = _approval_scope_sha256(document)
    document["status"] = APPROVED_PLAN_STATUS
    document["approval"] = {
        "record_path": str(APPROVAL_RECORD_PATH.relative_to(MODULE_DIR.parents[1])),
        "approved_at_beijing": approval["approved_at_beijing"],
        "approval_statement": approval["approval_statement"],
        "approval_limit": approval["approval_limit"],
        "scope_sha256": scope_sha256,
    }
    document["review"]["firmware_output_allowed"] = True
    document["review"]["approval_required"] = False
    document["review"]["experimental_download_allowed"] = False
    document["review"]["installation_allowed"] = False
    return document


def _write_plan(document: dict[str, Any], output: Path) -> None:
    destination = output.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    if temporary.exists():
        raise SettingsMenuWrapError(f"发现未处理的临时清单：{temporary}")
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
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_draft_plan(
    source: Path,
    output: Path,
    *,
    tool_revision: dict[str, Any],
) -> dict[str, Any]:
    """原子写入待批准清单，不提供修改批准状态的参数。"""

    document = build_draft_plan(source, tool_revision=tool_revision)
    _write_plan(document, output)
    return document


def write_approved_plan(
    source: Path,
    output: Path,
    *,
    tool_revision: dict[str, Any],
) -> dict[str, Any]:
    """原子写入与版本控制内批准记录完全一致的离线构建清单。"""

    document = build_approved_plan(source, tool_revision=tool_revision)
    _write_plan(document, output)
    return document
