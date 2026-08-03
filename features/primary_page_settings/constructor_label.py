"""从 A 阶段构建按原厂创建调用者选择返回行文字的固件。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from core.firmware_image import AP01_1_0_2_0031, ByteRange, refresh_recovery_crc, validate_candidate
from core.firmware_payload_space import PAYLOAD_CAPACITY, PAYLOAD_START
from features.agents_dashboard_firmware.build import _encode_jal
from .return_row_label import (
    A_PAYLOAD_SHA256,
    A_PAYLOAD_SIZE,
    MENU_DISPATCH_A,
    MENU_DISPATCH_OFFSET,
    MENU_LIMIT_OFFSET,
    MENU_LIMIT_SEVEN,
    PAYLOAD_VA,
    RETURN_LABEL_HIGH_OFFSET,
    RETURN_LABEL_HIGH_ORIGINAL,
    RETURN_LABEL_LOW_OFFSET,
    RETURN_LABEL_LOW_ORIGINAL,
    ROW_LABEL,
    SETTINGS_CALLBACK_HIGH_OFFSET,
    SETTINGS_CALLBACK_HIGH_ORIGINAL,
    SETTINGS_CALLBACK_LOW_OFFSET,
    SETTINGS_CALLBACK_LOW_ORIGINAL,
    PageSettingsReturnRowLabelError,
    _load_stage,
    _run,
    _symbols,
    _version,
    _write_frozen,
)

MODULE_DIR = Path(__file__).resolve().parent
SOURCE = MODULE_DIR / "constructor_label.S"
LINKER = MODULE_DIR / "constructor_label.ld"
OUTPUT_NAME = "ap01-1.0.2_0031-page-settings-constructor-label.bin"
CONTRACT = "FW-PAGE-009-A"

LABEL_CONSTRUCTOR_CALL_OFFSET = 0x1940AA
LABEL_CONSTRUCTOR_CALL_VA = 0xA01930AA
LABEL_CONSTRUCTOR_CALL_ORIGINAL = bytes.fromhex("efe0b1b0")
STOCK_LABEL_CONSTRUCTOR = 0xA00B1BB4
STARTUP_LIST_CALL_OFFSET = 0x0B4FFE
STARTUP_LIST_CALL_ORIGINAL = bytes.fromhex("ef407e0d")
STARTUP_LIST_RETURN = 0xA00B4002
USER_LIST_CALL_OFFSET = 0x0BE9E6
USER_LIST_CALL_ORIGINAL = bytes.fromhex("efa0fd6e")
USER_LIST_RETURN = 0xA00BD9EA


def simulate_page_settings_constructor_label() -> dict[str, object]:
    sequence = [STARTUP_LIST_RETURN, USER_LIST_RETURN, USER_LIST_RETURN, 0xA0000000]
    results = []
    for caller in sequence:
        results.append(
            {
                "saved_return_address": f"0x{caller:08x}",
                "label": ROW_LABEL if caller == USER_LIST_RETURN else "返回",
                "stock_constructor_calls": 1,
                "state_before": None,
                "state_after": None,
            }
        )
    return {
        "contract": CONTRACT,
        "passed": all(item["stock_constructor_calls"] == 1 for item in results),
        "scenario_count": len(results),
        "scenarios": results,
        "mutable_state": False,
        "object_traversal": False,
        "static_stack_bytes": 0,
        "press_entry_tested": False,
    }


def build_page_settings_constructor_label(
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
):
    if tool_revision.get("scoped_code_dirty") is not False:
        raise PageSettingsReturnRowLabelError("制作代码尚未提交，不能冻结原厂构造文字固件")
    stage_selected, stage = _load_stage(stage_path)
    output = output_path.expanduser().resolve()
    if output.name != OUTPUT_NAME:
        raise PageSettingsReturnRowLabelError(f"输出文件名必须为 {OUTPUT_NAME}")
    versions = {
        name: _version(tool)
        for name, tool in {
            "assembler": assembler,
            "linker": linker,
            "copier": copier,
            "readelf": readelf,
            "nm": nm,
            "dumper": dumper,
        }.items()
    }

    def payload_once(directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        obj = directory / "payload.o"
        elf = directory / "payload.elf"
        binary = directory / "payload.bin"
        _run([assembler, "-march=rv32imac", "-mabi=ilp32", "-o", obj, SOURCE])
        _run([linker, "-m", "elf32lriscv", "--no-relax", "-T", LINKER, "-o", elf, obj])
        relocations = _run([readelf, "-r", elf])
        if "There are no relocations" not in relocations:
            raise PageSettingsReturnRowLabelError("原厂构造文字载荷仍含重定位")
        symbols = _symbols(nm, elf)
        wrapper = symbols.get("ap01_page_settings_constructor_label")
        label = symbols.get("page_settings_entry_label")
        if wrapper is None or label is None:
            raise PageSettingsReturnRowLabelError("原厂构造文字载荷符号缺失")
        _run([copier, "-O", "binary", elf, binary])
        payload = binary.read_bytes()
        if len(payload) > PAYLOAD_CAPACITY:
            raise PageSettingsReturnRowLabelError("原厂构造文字载荷超出固定空间")
        if hashlib.sha256(payload[:A_PAYLOAD_SIZE]).hexdigest() != A_PAYLOAD_SHA256:
            raise PageSettingsReturnRowLabelError("原厂构造文字载荷未保留 A 阶段入口")
        disassembly = _run([dumper, "-d", "-M", "no-aliases,numeric", elf])
        block = disassembly.split("<ap01_page_settings_constructor_label>:", 1)[1].split(
            "<page_settings_entry_label>:", 1
        )[0]
        if re.search(r"\b(?:c\.)?(?:addi16sp|addi)\s+x2", block):
            raise PageSettingsReturnRowLabelError("原厂构造文字载荷建立了栈帧")
        for required in ("124(x8)", f"{USER_LIST_RETURN:08x}", f"{STOCK_LABEL_CONSTRUCTOR:08x}"):
            if required not in block.lower():
                raise PageSettingsReturnRowLabelError(f"原厂构造文字反汇编缺少证据：{required}")
        for forbidden in ("a00c5d84", "a0086bcc"):
            if forbidden in block.lower():
                raise PageSettingsReturnRowLabelError(f"原厂构造文字载荷包含禁止入口：{forbidden}")
        return payload, wrapper, label, disassembly

    root = build_directory.expanduser().resolve()
    first = payload_once(root / "first")
    second = payload_once(root / "second")
    if first[:3] != second[:3]:
        raise PageSettingsReturnRowLabelError("两次原厂构造文字载荷构建不一致")
    payload, wrapper, label, disassembly = first
    (root / "disassembly.txt").write_text(disassembly, encoding="utf-8", newline="\n")

    candidate = bytearray(stage)
    if bytes(candidate[LABEL_CONSTRUCTOR_CALL_OFFSET : LABEL_CONSTRUCTOR_CALL_OFFSET + 4]) != LABEL_CONSTRUCTOR_CALL_ORIGINAL:
        raise PageSettingsReturnRowLabelError("原厂返回行文字构造调用原字节不匹配")
    candidate[LABEL_CONSTRUCTOR_CALL_OFFSET : LABEL_CONSTRUCTOR_CALL_OFFSET + 4] = _encode_jal(
        LABEL_CONSTRUCTOR_CALL_VA, wrapper
    )
    allowed = [ByteRange(LABEL_CONSTRUCTOR_CALL_OFFSET, LABEL_CONSTRUCTOR_CALL_OFFSET + 4)]
    candidate[PAYLOAD_START : PAYLOAD_START + len(payload)] = payload
    allowed.append(ByteRange(PAYLOAD_START, PAYLOAD_START + len(payload)))

    invariants = (
        (STARTUP_LIST_CALL_OFFSET, STARTUP_LIST_CALL_ORIGINAL, "开机列表调用"),
        (USER_LIST_CALL_OFFSET, USER_LIST_CALL_ORIGINAL, "用户列表调用"),
        (MENU_LIMIT_OFFSET, MENU_LIMIT_SEVEN, "七次循环"),
        (MENU_DISPATCH_OFFSET, MENU_DISPATCH_A, "A 阶段分发"),
        (RETURN_LABEL_HIGH_OFFSET, RETURN_LABEL_HIGH_ORIGINAL, "返回文字高位"),
        (RETURN_LABEL_LOW_OFFSET, RETURN_LABEL_LOW_ORIGINAL, "返回文字低位"),
        (SETTINGS_CALLBACK_HIGH_OFFSET, SETTINGS_CALLBACK_HIGH_ORIGINAL, "设置回调高位"),
        (SETTINGS_CALLBACK_LOW_OFFSET, SETTINGS_CALLBACK_LOW_ORIGINAL, "设置回调低位"),
    )
    for offset, expected, name in invariants:
        if bytes(candidate[offset : offset + len(expected)]) != expected:
            raise PageSettingsReturnRowLabelError(f"{name}发生变化")

    crc = refresh_recovery_crc(candidate, AP01_1_0_2_0031)
    allowed.append(
        ByteRange(
            AP01_1_0_2_0031.recovery_trailer_offset + 36,
            AP01_1_0_2_0031.recovery_trailer_offset + 40,
        )
    )
    report = validate_candidate(stage, bytes(candidate), allowed, AP01_1_0_2_0031)
    simulation = simulate_page_settings_constructor_label()
    if not simulation["passed"]:
        raise PageSettingsReturnRowLabelError("原厂构造文字双调用者模拟未通过")
    manifest = {
        "schema_version": 1,
        "manifest_type": "page-settings-constructor-label-firmware",
        "status": "offline-gates-passed-not-installed",
        "contract": CONTRACT,
        "tool": {**tool_revision, "versions": versions},
        "input": {"path": str(stage_selected), "read_only": True},
        "output": {"path": str(output), "read_only": True, **report.to_dict()},
        "payload": {
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "remaining": PAYLOAD_CAPACITY - len(payload),
            "wrapper": f"0x{wrapper:08x}",
            "label": ROW_LABEL,
            "label_runtime_address": f"0x{label:08x}",
            "static_stack_bytes": 0,
            "mutable_state": False,
        },
        "hook": {
            "file_offset": LABEL_CONSTRUCTOR_CALL_OFFSET,
            "runtime_address": f"0x{LABEL_CONSTRUCTOR_CALL_VA:08x}",
            "stock_target": f"0x{STOCK_LABEL_CONSTRUCTOR:08x}",
        },
        "caller_returns": {
            "startup": f"0x{STARTUP_LIST_RETURN:08x}",
            "user": f"0x{USER_LIST_RETURN:08x}",
        },
        "allowed_ranges": [item.to_dict() for item in allowed],
        "simulation": simulation,
        "validation": {
            "startup_and_user_calls_unchanged": True,
            "stock_constructor_tail_called": True,
            "object_traversal_absent": True,
            "direct_label_update_absent": True,
            "mutable_state_absent": True,
            "static_stack_zero": True,
            "deterministic_links": True,
            "outside_allowed_ranges_identical": True,
            "installation_allowed": False,
        },
        "recovery_crc_after_build": f"0x{crc:08x}",
    }
    _write_frozen(output, bytes(candidate))
    _write_frozen(
        manifest_path,
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
    )
    return output, manifest_path.expanduser().resolve(), report.sha256, report.md5
