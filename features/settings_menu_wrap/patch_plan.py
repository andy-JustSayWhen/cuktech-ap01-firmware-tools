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
EVIDENCE_PATH = (
    "knowledge/AP01-官方固件分析/cases/"
    "2026-07-27-系统设置菜单首尾循环静态定位.md"
)

DRAFT_PLAN_STATUS = "draft-awaiting-user-approval"
EXPECTED_BINUTILS_VERSION = "2.46.1"
MAP_BASE_RUNTIME_ADDRESS = 0xA00F3D5A
XIP_DELTA = 0x9FFFF000


class SettingsMenuWrapError(RuntimeError):
    """设置菜单修改清单无法安全生成。"""


@dataclass(frozen=True)
class PatchDefinition:
    name: str
    objective: str
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
        name="右旋通用日志尾部",
        objective="保留原厂寄存器初始化，并容纳右旋末项回到首项的等长处理",
        offset=0x0F9134,
        runtime_address=0xA00F8134,
        expected_before=bytes.fromhex(
            "37a74ca01307073c93064b8f1306606493854a770d45ef4098e5"
        ),
        expected_replacement=bytes.fromhex(
            "29a893070003a380f40003a589009385faff0146efb03fc171b7"
        ),
        evidence_note="证据文档第 4、5 节：保留前置初始化，只替换日志尾部",
    ),
    PatchDefinition(
        name="右旋设置日志",
        objective="容纳项目数、状态边界检查并把内部项交回原厂处理",
        offset=0x0F9172,
        runtime_address=0xA00F8172,
        expected_before=bytes.fromhex(
            "37a74ca093064b8f93854a771307c73e1306e0640d45ef40b8e1"
        ),
        expected_replacement=bytes.fromhex(
            "29a883c714000947e3efeaf4938617fde3ebdaf4e38856fb21a8"
        ),
        evidence_note="证据文档第 4、5 节：当次项目数小于 2 或状态越界即返回",
    ),
    PatchDefinition(
        name="右旋状态读取",
        objective="把系统设置右旋状态检查交给版本限定处理",
        offset=0x0F919E,
        runtime_address=0xA00F819E,
        expected_before=bytes.fromhex("83c71400"),
        expected_replacement=bytes.fromhex("6ff07ffd"),
        evidence_note="证据文档第 4、5 节：跳转目标为右旋边界检查",
    ),
    PatchDefinition(
        name="左旋通用日志尾部",
        objective="保留原厂寄存器初始化，并容纳左旋首项回到末项的等长处理",
        offset=0x0F9700,
        runtime_address=0xA00F8700,
        expected_before=bytes.fromhex(
            "37a74ca01307875193864b8f1306a07793854a770d45ef40d888"
        ),
        expected_replacement=bytes.fromhex(
            "29a89387fa02a380f40003a5890081451386faffefb06fe4c1b2"
        ),
        evidence_note="证据文档第 4、5 节：保留前置初始化，只替换日志尾部",
    ),
    PatchDefinition(
        name="左旋设置日志",
        objective="容纳项目数、状态边界检查并把内部项交回原厂处理",
        offset=0x0F973E,
        runtime_address=0xA00F873E,
        expected_before=bytes.fromhex(
            "37a74ca093854a771307c73e93864b8f130620780d45ef40f884"
        ),
        expected_replacement=bytes.fromhex(
            "29a883c714000947e3e9ea98938607fde3f55699c5da29a80100"
        ),
        evidence_note="证据文档第 4、5 节：当次项目数小于 2 或状态越界即返回",
    ),
    PatchDefinition(
        name="左旋状态读取",
        objective="把系统设置左旋状态检查交给版本限定处理",
        offset=0x0F976A,
        runtime_address=0xA00F876A,
        expected_before=bytes.fromhex("83c71400"),
        expected_replacement=bytes.fromhex("6ff07ffd"),
        evidence_note="证据文档第 4、5 节：跳转目标为左旋边界检查",
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
        previous_end = patch.end


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
        map_path = build_dir / "settings-menu-wrap-map.bin"
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
            (
                copier,
                "--dump-section",
                f".patch_map={map_path}",
                elf_path,
            ),
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

        patch_map = map_path.read_bytes()
        generated: dict[int, bytes] = {}
        for patch in PATCHES:
            start = patch.runtime_address - MAP_BASE_RUNTIME_ADDRESS
            end = start + len(patch.expected_replacement)
            replacement = patch_map[start:end]
            if replacement != patch.expected_replacement:
                raise SettingsMenuWrapError(
                    f"汇编结果与已审查字节不一致：{patch.name}"
                )
            generated[patch.offset] = replacement

    return {
        "version": EXPECTED_BINUTILS_VERSION,
        "tools": versions,
        "assembly_sha256": _sha256_file(ASSEMBLY_SOURCE),
        "linker_script_sha256": _sha256_file(LINKER_SCRIPT),
        "replacements": generated,
    }


def build_draft_plan(
    source: Path,
    *,
    tool_revision: dict[str, Any],
) -> dict[str, Any]:
    """校验真实基线并返回无法用于构建的待批准清单。"""

    firmware, baseline = load_read_only_baseline(source, AP01_1_0_2_0031)
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
                "用户必须明确批准证据文档中的 6 个精确区间，"
                "才能另行形成允许离线构建的清单"
            ),
            "known_logging_change": (
                "左右各减少一条通用调试日志和一条系统设置专用调试日志"
            ),
        },
        "patches": entries,
    }


def write_draft_plan(
    source: Path,
    output: Path,
    *,
    tool_revision: dict[str, Any],
) -> dict[str, Any]:
    """原子写入待批准清单，不提供修改批准状态的参数。"""

    document = build_draft_plan(source, tool_revision=tool_revision)
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
    return document
