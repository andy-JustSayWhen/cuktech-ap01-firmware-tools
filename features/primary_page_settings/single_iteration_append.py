"""构建保持原厂七次循环并在最后一次迭代追加两行的固件。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.firmware_image import (
    AP01_1_0_2_0031,
    ByteRange,
    refresh_recovery_crc,
    validate_candidate,
)
from core.firmware_payload_space import PAYLOAD_CAPACITY, PAYLOAD_START
from . import row_creation as row_support


MODULE_DIR = Path(__file__).resolve().parent
SOURCE = MODULE_DIR / "single_iteration_append.S"
LINKER = MODULE_DIR / "single_iteration_append.ld"
OUTPUT_NAME = "ap01-1.0.2_0031-page-settings-single-iteration-append.bin"
PAYLOAD_VA = row_support.PAYLOAD_VA
STAGE_SIZE = row_support.STAGE_SIZE
STAGE_SHA256 = row_support.STAGE_SHA256
STAGE_MD5 = row_support.STAGE_MD5
MENU_LIMIT_OFFSET = row_support.MENU_LIMIT_OFFSET
MENU_LIMIT_SEVEN = row_support.MENU_LIMIT_SEVEN
MENU_DISPATCH_OFFSET = row_support.MENU_DISPATCH_OFFSET
MENU_DISPATCH_A = row_support.MENU_DISPATCH_A
SETTINGS_CALLBACK_HIGH_OFFSET = row_support.SETTINGS_CALLBACK_HIGH_OFFSET
SETTINGS_CALLBACK_HIGH_ORIGINAL = row_support.SETTINGS_CALLBACK_HIGH_ORIGINAL
SETTINGS_CALLBACK_LOW_OFFSET = row_support.SETTINGS_CALLBACK_LOW_OFFSET
SETTINGS_CALLBACK_LOW_ORIGINAL = row_support.SETTINGS_CALLBACK_LOW_ORIGINAL
STOCK_ROW_CREATE = 0xA0192FB4
STOCK_RETURN_CREATE = 0xA0193058
STOCK_ROW_TARGET = 0xA01989E0
STOCK_LOOP_DONE = 0xA01989B2
ROW_LABEL = "开关一级页面"


class PageSettingsSingleIterationAppendError(RuntimeError):
    """单迭代追加固件不满足固定合同。"""


@dataclass(frozen=True)
class PageSettingsSingleIterationAppendResult:
    output: Path
    manifest: Path
    sha256: str
    md5: str
    payload_size: int
    payload_remaining: int
    simulation_iterations: int
    simulation_items: int


def _support(function: object, *args: object) -> object:
    try:
        return function(*args)  # type: ignore[operator]
    except row_support.PageSettingsRowCreationError as error:
        raise PageSettingsSingleIterationAppendError(str(error)) from error


def simulate_page_settings_single_iteration_append() -> dict[str, object]:
    """验证七次循环生成八个项目且不存在第八次迭代。"""

    iterations = [
        {"sequence": 0, "created": ["stock-first-row"]},
        *(
            {"sequence": sequence, "created": ["stock-row"]}
            for sequence in range(1, 6)
        ),
        {"sequence": 6, "created": ["new-stock-row", "stock-return"]},
    ]
    created = [item for iteration in iterations for item in iteration["created"]]
    expected = [
        "stock-first-row",
        "stock-row",
        "stock-row",
        "stock-row",
        "stock-row",
        "stock-row",
        "new-stock-row",
        "stock-return",
    ]
    if created != expected:
        raise PageSettingsSingleIterationAppendError("单迭代追加项目顺序不匹配")
    if [int(item["sequence"]) for item in iterations] != list(range(7)):
        raise PageSettingsSingleIterationAppendError("单迭代追加循环序号不匹配")
    return {
        "passed": True,
        "iterations_checked": len(iterations),
        "items_created": len(created),
        "iterations": iterations,
        "failures": 0,
        "sequence_7_exists": False,
        "settings_callback_changed": False,
        "temporary_state_54_press": "stock-return",
        "temporary_state_55_selectable": False,
        "physical_acceptance_replaced": False,
    }


def _run(command: list[Path | str]) -> str:
    result = _support(row_support._run, command)
    if not isinstance(result, str):
        raise PageSettingsSingleIterationAppendError("构建工具返回值类型不匹配")
    return result


def _build_payload(
    directory: Path,
    *,
    assembler: Path,
    linker: Path,
    copier: Path,
    readelf: Path,
    nm: Path,
    dumper: Path,
) -> tuple[bytes, str, str]:
    selected = directory.expanduser().resolve()
    selected.mkdir(parents=True, exist_ok=True)
    object_path = selected / "page-settings-single-iteration-append.o"
    elf_path = selected / "page-settings-single-iteration-append.elf"
    binary_path = selected / "page-settings-single-iteration-append.bin"
    _run(
        [
            assembler,
            "-march=rv32imac",
            "-mabi=ilp32",
            "-o",
            object_path,
            SOURCE,
        ]
    )
    _run(
        [
            linker,
            "-m",
            "elf32lriscv",
            "--no-relax",
            "-T",
            LINKER,
            "-o",
            elf_path,
            object_path,
        ]
    )
    readelf_text = _run([readelf, "-h", "-S", "-s", "-r", elf_path])
    if "There are no relocations in this file." not in readelf_text:
        raise PageSettingsSingleIterationAppendError(
            "单迭代追加载荷仍含未处理重定位"
        )
    symbol_map = _support(row_support._symbols, nm, elf_path)
    if not isinstance(symbol_map, dict):
        raise PageSettingsSingleIterationAppendError("载荷符号表类型不匹配")
    if symbol_map.get("ap01_page_settings_single_iteration_append") != PAYLOAD_VA:
        raise PageSettingsSingleIterationAppendError("单迭代追加载荷符号地址不匹配")
    _run([copier, "-O", "binary", elf_path, binary_path])
    payload = binary_path.read_bytes()
    if not payload or len(payload) > PAYLOAD_CAPACITY:
        raise PageSettingsSingleIterationAppendError("单迭代追加载荷超出固定空间")
    if ROW_LABEL.encode("utf-8") + b"\x00" not in payload:
        raise PageSettingsSingleIterationAppendError("单迭代追加载荷缺少固定标签")
    disassembly = _run([dumper, "-d", "-M", "no-aliases,numeric", elf_path])
    lowered = disassembly.lower()
    for target in (
        STOCK_ROW_CREATE,
        STOCK_RETURN_CREATE,
        STOCK_ROW_TARGET,
        STOCK_LOOP_DONE,
    ):
        if f"{target:08x}" not in lowered:
            raise PageSettingsSingleIterationAppendError(
                f"单迭代追加载荷缺少批准的原厂地址：0x{target:08x}"
            )
    call_lines = [
        line
        for line in lowered.splitlines()
        if re.search(r"\bjalr?\s+(?:ra|x1),", line)
    ]
    if len(call_lines) != 2:
        raise PageSettingsSingleIterationAppendError(
            "单迭代追加载荷必须恰好包含两个原厂调用"
        )
    if f"{STOCK_ROW_CREATE:08x}" not in call_lines[0]:
        raise PageSettingsSingleIterationAppendError("第一个调用不是原厂普通行入口")
    if f"{STOCK_RETURN_CREATE:08x}" not in call_lines[1]:
        raise PageSettingsSingleIterationAppendError("第二个调用不是原厂返回行入口")
    if re.search(r"\bc\.li\s+x5,7\b", lowered):
        raise PageSettingsSingleIterationAppendError("载荷出现禁止的序号 7 分支")
    for forbidden in (0xA00F8096, 0xA00C6DFE, 0xA00F3D5A, 0xA00BFA4E):
        if f"{forbidden:08x}" in lowered:
            raise PageSettingsSingleIterationAppendError(
                f"单迭代追加载荷包含本阶段禁止地址：0x{forbidden:08x}"
            )
    for marker in (b"/data/", b"http://", b"https://", b"APAG"):
        if marker in payload:
            raise PageSettingsSingleIterationAppendError(
                "单迭代追加载荷包含越界功能字符串"
            )
    return payload, disassembly, readelf_text


def build_page_settings_single_iteration_append(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    assembler: Path,
    linker: Path,
    copier: Path,
    readelf: Path,
    nm: Path,
    dumper: Path,
    tool_revision: dict[str, object],
) -> PageSettingsSingleIterationAppendResult:
    """从 A 阶段生成保持七次循环的新增入口固件。"""

    if tool_revision.get("scoped_code_dirty") is not False:
        raise PageSettingsSingleIterationAppendError(
            "制作代码尚未提交，不能冻结单迭代追加固件"
        )
    stage_result = _support(row_support._load_stage, stage_path)
    if not isinstance(stage_result, tuple) or len(stage_result) != 2:
        raise PageSettingsSingleIterationAppendError("A 阶段输入结果类型不匹配")
    stage_selected, stage = stage_result
    if not isinstance(stage_selected, Path) or not isinstance(stage, bytes):
        raise PageSettingsSingleIterationAppendError("A 阶段输入内容类型不匹配")
    output = output_path.expanduser().resolve()
    if output.name != OUTPUT_NAME:
        raise PageSettingsSingleIterationAppendError(
            f"输出文件名必须为 {OUTPUT_NAME}"
        )
    selected_build = build_directory.expanduser().resolve()
    selected_build.mkdir(parents=True, exist_ok=True)
    versions: dict[str, object] = {}
    for label, tool in {
        "assembler": assembler,
        "linker": linker,
        "copier": copier,
        "readelf": readelf,
        "nm": nm,
        "dumper": dumper,
    }.items():
        versions[label] = _support(row_support._version, tool)
    first = _build_payload(
        selected_build / "first",
        assembler=assembler,
        linker=linker,
        copier=copier,
        readelf=readelf,
        nm=nm,
        dumper=dumper,
    )
    second = _build_payload(
        selected_build / "second",
        assembler=assembler,
        linker=linker,
        copier=copier,
        readelf=readelf,
        nm=nm,
        dumper=dumper,
    )
    if first[0] != second[0]:
        raise PageSettingsSingleIterationAppendError(
            "两次单迭代追加载荷构建不一致"
        )
    payload, disassembly, readelf_text = first
    (selected_build / "disassembly.txt").write_text(
        disassembly, encoding="utf-8", newline="\n"
    )
    (selected_build / "readelf.txt").write_text(
        readelf_text, encoding="utf-8", newline="\n"
    )
    simulation = simulate_page_settings_single_iteration_append()

    candidate = bytearray(stage)
    allowed: list[ByteRange] = []
    payload_before = bytes(candidate[PAYLOAD_START : PAYLOAD_START + len(payload)])
    candidate[PAYLOAD_START : PAYLOAD_START + len(payload)] = payload
    if payload_before == payload:
        raise PageSettingsSingleIterationAppendError("单迭代载荷写入前后相同")
    allowed.append(ByteRange(PAYLOAD_START, PAYLOAD_START + len(payload)))
    if bytes(candidate[MENU_LIMIT_OFFSET : MENU_LIMIT_OFFSET + 2]) != MENU_LIMIT_SEVEN:
        raise PageSettingsSingleIterationAppendError("原厂七次循环上限发生越界修改")
    if (
        bytes(candidate[MENU_DISPATCH_OFFSET : MENU_DISPATCH_OFFSET + 4])
        != MENU_DISPATCH_A
    ):
        raise PageSettingsSingleIterationAppendError("A 阶段分发挂接发生越界修改")
    if (
        bytes(
            candidate[
                SETTINGS_CALLBACK_HIGH_OFFSET : SETTINGS_CALLBACK_HIGH_OFFSET + 4
            ]
        )
        != SETTINGS_CALLBACK_HIGH_ORIGINAL
    ):
        raise PageSettingsSingleIterationAppendError("设置回调地址高位发生越界修改")
    if (
        bytes(
            candidate[
                SETTINGS_CALLBACK_LOW_OFFSET : SETTINGS_CALLBACK_LOW_OFFSET + 4
            ]
        )
        != SETTINGS_CALLBACK_LOW_ORIGINAL
    ):
        raise PageSettingsSingleIterationAppendError("设置回调地址低位发生越界修改")
    recovery_crc = refresh_recovery_crc(candidate, AP01_1_0_2_0031)
    allowed.append(
        ByteRange(
            AP01_1_0_2_0031.recovery_trailer_offset + 36,
            AP01_1_0_2_0031.recovery_trailer_offset + 40,
        )
    )
    report = validate_candidate(stage, bytes(candidate), allowed, AP01_1_0_2_0031)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "manifest_type": "page-settings-single-iteration-append-firmware",
        "status": "built-approved-for-single-startup-test",
        "built_at_beijing": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
            timespec="seconds"
        ),
        "tool": {**tool_revision, "versions": versions},
        "input": {
            "path": str(stage_selected),
            "size": len(stage),
            "sha256": STAGE_SHA256,
            "md5": STAGE_MD5,
            "read_only": True,
        },
        "output": {"path": str(output), "read_only": True, **report.to_dict()},
        "source_evidence": [
            "knowledge/AP01-官方固件分析/原厂各页面物理旋钮交互实现.md",
            "knowledge/AP01-官方固件分析/cases/2026-08-03-FW-PAGE-004-B开机动画回归.md",
        ],
        "payload": {
            "file_offset": PAYLOAD_START,
            "runtime_address": f"0x{PAYLOAD_VA:08x}",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "capacity": PAYLOAD_CAPACITY,
            "remaining": PAYLOAD_CAPACITY - len(payload),
            "relocations": 0,
            "deterministic_links": 2,
            "max_static_stack": 16,
            "stock_row_create_calls": 1,
            "stock_return_create_calls": 1,
            "row_label": ROW_LABEL,
        },
        "implemented_scope": [
            "原厂七次循环保持不变",
            "序号六同一迭代创建新增普通行",
            "序号六同一迭代继续创建原厂返回行",
        ],
        "excluded_scope": [
            "第八次循环迭代",
            "设置事件回调替换",
            "新增行确认与页面开关界面",
            "一级导航、AGENTS、网络与持久化",
        ],
        "simulation": simulation,
        "allowed_ranges": [item.to_dict() for item in allowed],
        "recovery_crc_after_build": f"0x{recovery_crc:08x}",
        "validation": {
            "input_identity_fixed": True,
            "menu_limit_unchanged_at_seven": True,
            "menu_dispatch_hook_unchanged": True,
            "settings_callbacks_unchanged": True,
            "single_stock_row_create_call": True,
            "single_stock_return_create_call": True,
            "sequence_7_absent": True,
            "deterministic_payload_links": True,
            "seven_iteration_eight_item_simulation_passed": True,
            "outside_allowed_ranges_identical": True,
            "physical_acceptance_replaced": False,
            "installation_allowed": True,
        },
    }
    output_written = False
    try:
        _support(row_support._write_frozen, output, bytes(candidate))
        output_written = True
        readback = validate_candidate(
            stage, output.read_bytes(), allowed, AP01_1_0_2_0031
        )
        if readback.sha256 != report.sha256:
            raise PageSettingsSingleIterationAppendError(
                "单迭代追加成品回读指纹不一致"
            )
        manifest_bytes = (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        _support(row_support._write_frozen, manifest_path, manifest_bytes)
    except Exception:
        if output_written and output.exists():
            output.chmod(0o644)
            output.unlink()
        raise
    return PageSettingsSingleIterationAppendResult(
        output=output,
        manifest=manifest_path.expanduser().resolve(),
        sha256=report.sha256,
        md5=report.md5,
        payload_size=len(payload),
        payload_remaining=PAYLOAD_CAPACITY - len(payload),
        simulation_iterations=int(simulation["iterations_checked"]),
        simulation_items=int(simulation["items_created"]),
    )
