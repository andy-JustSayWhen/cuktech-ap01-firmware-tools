"""从 A 阶段构建只复用原厂返回行文字指针的固件。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import struct
import subprocess
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
from core.firmware_payload_space import (
    GIF_SIZE_OFFSET,
    OPTIMIZED_SIZE,
    PAYLOAD_CAPACITY,
    PAYLOAD_START,
)


MODULE_DIR = Path(__file__).resolve().parent
SOURCE = MODULE_DIR / "return_row_label.S"
LINKER = MODULE_DIR / "return_row_label.ld"
OUTPUT_NAME = "ap01-1.0.2_0031-page-settings-return-label.bin"
STAGE_SIZE = 6_804_520
STAGE_SHA256 = "8986ceb31b7d26802bb06fc62a23f5c29eb00f089dc86a5a40d33d95b4dd345b"
STAGE_MD5 = "a066fab43085e8ab4c8b8aa33ff8af6f"
XIP_DELTA = 0x9FFFF000
PAYLOAD_VA = XIP_DELTA + PAYLOAD_START
A_PAYLOAD_SIZE = 28
A_PAYLOAD_SHA256 = "6c280eb1aa6fb2835a5df8ea12ac088f33e53be9e9524fa3818c21c0088e243c"
MENU_LIMIT_OFFSET = 0x1999B4
MENU_LIMIT_SEVEN = bytes.fromhex("9d47")
MENU_DISPATCH_OFFSET = 0x1999DC
MENU_DISPATCH_A = bytes.fromhex("6fd05a3f")
SETTINGS_CALLBACK_HIGH_OFFSET = 0x0BE8CC
SETTINGS_CALLBACK_HIGH_ORIGINAL = bytes.fromhex("b7850fa0")
SETTINGS_CALLBACK_LOW_OFFSET = 0x0BE8D4
SETTINGS_CALLBACK_LOW_ORIGINAL = bytes.fromhex("93856509")
RETURN_LABEL_HIGH_OFFSET = 0x19408C
RETURN_LABEL_HIGH_ORIGINAL = bytes.fromhex("b76529a0")
RETURN_LABEL_LOW_OFFSET = 0x1940A4
RETURN_LABEL_LOW_ORIGINAL = bytes.fromhex("9385c5bb")
STOCK_RETURN_LABEL_ADDRESS = 0xA0295BBC
STOCK_ROW_TARGET = 0xA01989E0
STOCK_RETURN_TARGET = 0xA0198AD0
STOCK_ROW_CREATE = 0xA0192FB4
STOCK_RETURN_CREATE = 0xA0193058
STOCK_LABEL_SET_TEXT = 0xA0086BCC
ROW_LABEL = "开关一级页面"
EXPECTED_BINUTILS_VERSION = "2.46.1"


class PageSettingsReturnRowLabelError(RuntimeError):
    """返回行文字复用固件不满足固定合同。"""


@dataclass(frozen=True)
class PageSettingsReturnRowLabelResult:
    output: Path
    manifest: Path
    sha256: str
    md5: str
    payload_size: int
    payload_remaining: int
    label_runtime_address: int
    simulation_items: int


def simulate_page_settings_return_row_label() -> dict[str, object]:
    """证明七项对象树、状态和原厂按下路径不变。"""

    items = [
        {
            "index": index,
            "state": 48 + index,
            "kind": "stock-return" if index == 6 else "stock-row",
            "label": ROW_LABEL if index == 6 else "stock",
        }
        for index in range(7)
    ]
    states = [int(item["state"]) for item in items]
    if len(items) != 7 or states != list(range(48, 55)):
        raise PageSettingsReturnRowLabelError("原厂七项对象或状态模拟不匹配")
    return {
        "passed": True,
        "items": items,
        "item_count": len(items),
        "states": states,
        "last_row_label": ROW_LABEL,
        "last_row_press": "stock-return",
        "list_objects_added": 0,
        "settings_callback_changed": False,
        "physical_acceptance_replaced": False,
    }


def _run(command: list[Path | str]) -> str:
    try:
        completed = subprocess.run(
            [str(item) for item in command],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise PageSettingsReturnRowLabelError(
            "无法启动返回行文字构建工具"
        ) from error
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PageSettingsReturnRowLabelError(
            f"返回行文字构建失败：{detail}"
        )
    return completed.stdout


def _version(tool: Path) -> str:
    first = _run([tool, "--version"]).splitlines()
    value = first[0] if first else ""
    if EXPECTED_BINUTILS_VERSION not in value:
        raise PageSettingsReturnRowLabelError(
            f"构建工具版本不匹配：预期 {EXPECTED_BINUTILS_VERSION}，实际 {value}"
        )
    return value


def _decode_address_pair(high: bytes, low: bytes) -> int:
    if len(high) != 4 or len(low) != 4:
        raise PageSettingsReturnRowLabelError("文字指针指令长度不匹配")
    high_word = struct.unpack("<I", high)[0]
    low_word = struct.unpack("<I", low)[0]
    if high_word & 0x7F != 0x37 or low_word & 0x707F != 0x13:
        raise PageSettingsReturnRowLabelError("文字指针指令格式不匹配")
    if (high_word >> 7) & 0x1F != 11:
        raise PageSettingsReturnRowLabelError("文字指针高位寄存器不匹配")
    if (low_word >> 7) & 0x1F != 11 or (low_word >> 15) & 0x1F != 11:
        raise PageSettingsReturnRowLabelError("文字指针低位寄存器不匹配")
    upper = high_word & 0xFFFFF000
    lower = (low_word >> 20) & 0xFFF
    if lower & 0x800:
        lower -= 0x1000
    return (upper + lower) & 0xFFFFFFFF


def _encode_address_pair(address: int) -> tuple[bytes, bytes]:
    upper = (address + 0x800) >> 12
    lower = address - (upper << 12)
    if not -2048 <= lower <= 2047:
        raise PageSettingsReturnRowLabelError("文字指针地址无法分解")
    high_word = ((upper & 0xFFFFF) << 12) | (11 << 7) | 0x37
    low_word = ((lower & 0xFFF) << 20) | (11 << 15) | (11 << 7) | 0x13
    encoded = struct.pack("<I", high_word), struct.pack("<I", low_word)
    if _decode_address_pair(*encoded) != address:
        raise PageSettingsReturnRowLabelError("文字指针指令回读地址不匹配")
    return encoded


def _load_stage(path: Path) -> tuple[Path, bytes]:
    selected = path.expanduser().resolve(strict=True)
    if not selected.is_file():
        raise PageSettingsReturnRowLabelError("返回行文字输入不是普通文件")
    writable = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    if selected.stat().st_mode & writable:
        raise PageSettingsReturnRowLabelError("返回行文字输入必须为只读文件")
    stage = selected.read_bytes()
    if len(stage) != STAGE_SIZE:
        raise PageSettingsReturnRowLabelError("返回行文字输入长度不匹配")
    if hashlib.sha256(stage).hexdigest() != STAGE_SHA256:
        raise PageSettingsReturnRowLabelError("返回行文字输入 SHA-256 不匹配")
    if hashlib.md5(stage).hexdigest() != STAGE_MD5:
        raise PageSettingsReturnRowLabelError("返回行文字输入 MD5 不匹配")
    expected = (
        (MENU_LIMIT_OFFSET, MENU_LIMIT_SEVEN, "设置循环上限"),
        (MENU_DISPATCH_OFFSET, MENU_DISPATCH_A, "A 阶段分发挂接"),
        (SETTINGS_CALLBACK_HIGH_OFFSET, SETTINGS_CALLBACK_HIGH_ORIGINAL, "设置回调高位"),
        (SETTINGS_CALLBACK_LOW_OFFSET, SETTINGS_CALLBACK_LOW_ORIGINAL, "设置回调低位"),
        (RETURN_LABEL_HIGH_OFFSET, RETURN_LABEL_HIGH_ORIGINAL, "返回行文字指针高位"),
        (RETURN_LABEL_LOW_OFFSET, RETURN_LABEL_LOW_ORIGINAL, "返回行文字指针低位"),
    )
    for offset, original, label in expected:
        if stage[offset : offset + len(original)] != original:
            raise PageSettingsReturnRowLabelError(f"{label}原字节不匹配")
    if _decode_address_pair(RETURN_LABEL_HIGH_ORIGINAL, RETURN_LABEL_LOW_ORIGINAL) != STOCK_RETURN_LABEL_ADDRESS:
        raise PageSettingsReturnRowLabelError("原厂返回行文字地址不匹配")
    if hashlib.sha256(stage[PAYLOAD_START : PAYLOAD_START + A_PAYLOAD_SIZE]).hexdigest() != A_PAYLOAD_SHA256:
        raise PageSettingsReturnRowLabelError("A 阶段透传载荷指纹不匹配")
    optimized_size = int.from_bytes(stage[GIF_SIZE_OFFSET : GIF_SIZE_OFFSET + 4], "little")
    if optimized_size != OPTIMIZED_SIZE:
        raise PageSettingsReturnRowLabelError("A 阶段动图长度字段不匹配")
    return selected, stage


def _replace(
    firmware: bytearray,
    offset: int,
    expected: bytes,
    replacement: bytes,
    label: str,
) -> ByteRange:
    if len(expected) != len(replacement):
        raise PageSettingsReturnRowLabelError(f"{label}修改前后长度不一致")
    end = offset + len(expected)
    if bytes(firmware[offset:end]) != expected:
        raise PageSettingsReturnRowLabelError(f"{label}原字节不匹配")
    firmware[offset:end] = replacement
    return ByteRange(offset, end)


def _write_frozen(path: Path, payload: bytes) -> Path:
    selected = path.expanduser().resolve()
    selected.parent.mkdir(parents=True, exist_ok=True)
    if selected.exists():
        raise PageSettingsReturnRowLabelError(f"不可覆盖冻结文件：{selected}")
    temporary = selected.with_name(selected.name + ".part")
    if temporary.exists():
        raise PageSettingsReturnRowLabelError(f"发现未处理临时文件：{temporary}")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, selected)
        selected.chmod(0o444)
        return selected
    finally:
        if temporary.exists():
            temporary.unlink()


def _symbols(nm: Path, elf: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in _run([nm, "-n", elf]).splitlines():
        parts = line.split()
        if len(parts) == 3:
            try:
                result[parts[2]] = int(parts[0], 16)
            except ValueError:
                continue
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
) -> tuple[bytes, int, str, str]:
    selected = directory.expanduser().resolve()
    selected.mkdir(parents=True, exist_ok=True)
    object_path = selected / "page-settings-return-row-label.o"
    elf_path = selected / "page-settings-return-row-label.elf"
    binary_path = selected / "page-settings-return-row-label.bin"
    _run([assembler, "-march=rv32imac", "-mabi=ilp32", "-o", object_path, SOURCE])
    _run([linker, "-m", "elf32lriscv", "--no-relax", "-T", LINKER, "-o", elf_path, object_path])
    readelf_text = _run([readelf, "-h", "-S", "-s", "-r", elf_path])
    if "There are no relocations in this file." not in readelf_text:
        raise PageSettingsReturnRowLabelError("返回行文字载荷仍含未处理重定位")
    symbol_map = _symbols(nm, elf_path)
    if symbol_map.get("ap01_page_settings_return_label") != PAYLOAD_VA:
        raise PageSettingsReturnRowLabelError("返回行文字载荷入口地址不匹配")
    label_address = symbol_map.get("page_settings_entry_label")
    if label_address is None or not PAYLOAD_VA + A_PAYLOAD_SIZE <= label_address < PAYLOAD_VA + PAYLOAD_CAPACITY:
        raise PageSettingsReturnRowLabelError("返回行文字载荷标签地址不匹配")
    _run([copier, "-O", "binary", elf_path, binary_path])
    payload = binary_path.read_bytes()
    label_bytes = ROW_LABEL.encode("utf-8") + b"\x00"
    if not payload or len(payload) > PAYLOAD_CAPACITY:
        raise PageSettingsReturnRowLabelError("返回行文字载荷超出固定空间")
    if hashlib.sha256(payload[:A_PAYLOAD_SIZE]).hexdigest() != A_PAYLOAD_SHA256:
        raise PageSettingsReturnRowLabelError("返回行文字载荷未保持 A 阶段透传代码")
    if payload.count(label_bytes) != 1:
        raise PageSettingsReturnRowLabelError("返回行文字载荷固定文字数量不匹配")
    label_offset = label_address - PAYLOAD_VA
    if payload[label_offset : label_offset + len(label_bytes)] != label_bytes:
        raise PageSettingsReturnRowLabelError("返回行文字载荷指针未指向完整文字")
    disassembly = _run([
        dumper,
        "-d",
        "-M",
        "no-aliases,numeric",
        f"--start-address=0x{PAYLOAD_VA:x}",
        f"--stop-address=0x{PAYLOAD_VA + A_PAYLOAD_SIZE:x}",
        elf_path,
    ])
    lowered = disassembly.lower()
    for target in (STOCK_ROW_TARGET, STOCK_RETURN_TARGET):
        if f"{target:08x}" not in lowered:
            raise PageSettingsReturnRowLabelError(f"返回行文字载荷缺少原厂继续地址：0x{target:08x}")
    if re.search(r"\bjalr?\s+(?:ra|x1),", lowered):
        raise PageSettingsReturnRowLabelError("返回行文字载荷包含函数调用")
    for forbidden in (STOCK_ROW_CREATE, STOCK_RETURN_CREATE, STOCK_LABEL_SET_TEXT):
        if f"{forbidden:08x}" in lowered:
            raise PageSettingsReturnRowLabelError(f"返回行文字载荷包含禁止地址：0x{forbidden:08x}")
    for marker in (b"/data/", b"http://", b"https://", b"APAG"):
        if marker in payload:
            raise PageSettingsReturnRowLabelError("返回行文字载荷包含越界功能字符串")
    return payload, label_address, disassembly, readelf_text


def build_page_settings_return_row_label(
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
) -> PageSettingsReturnRowLabelResult:
    """从 A 阶段冻结成品生成原厂返回行文字复用候选。"""

    if tool_revision.get("scoped_code_dirty") is not False:
        raise PageSettingsReturnRowLabelError("制作代码尚未提交，不能冻结返回行文字固件")
    stage_selected, stage = _load_stage(stage_path)
    output = output_path.expanduser().resolve()
    if output.name != OUTPUT_NAME:
        raise PageSettingsReturnRowLabelError(f"输出文件名必须为 {OUTPUT_NAME}")
    selected_build = build_directory.expanduser().resolve()
    selected_build.mkdir(parents=True, exist_ok=True)
    versions = {
        "assembler": _version(assembler),
        "linker": _version(linker),
        "copier": _version(copier),
        "readelf": _version(readelf),
        "nm": _version(nm),
        "dumper": _version(dumper),
    }
    first = _build_payload(selected_build / "first", assembler=assembler, linker=linker, copier=copier, readelf=readelf, nm=nm, dumper=dumper)
    second = _build_payload(selected_build / "second", assembler=assembler, linker=linker, copier=copier, readelf=readelf, nm=nm, dumper=dumper)
    if first[0] != second[0] or first[1] != second[1]:
        raise PageSettingsReturnRowLabelError("两次返回行文字载荷构建不一致")
    payload, label_address, disassembly, readelf_text = first
    (selected_build / "disassembly.txt").write_text(disassembly, encoding="utf-8", newline="\n")
    (selected_build / "readelf.txt").write_text(readelf_text, encoding="utf-8", newline="\n")
    simulation = simulate_page_settings_return_row_label()
    label_high, label_low = _encode_address_pair(label_address)

    candidate = bytearray(stage)
    allowed: list[ByteRange] = []
    payload_before = bytes(candidate[PAYLOAD_START : PAYLOAD_START + len(payload)])
    candidate[PAYLOAD_START : PAYLOAD_START + len(payload)] = payload
    if payload_before == payload:
        raise PageSettingsReturnRowLabelError("返回行文字载荷写入前后相同")
    allowed.append(ByteRange(PAYLOAD_START, PAYLOAD_START + len(payload)))
    allowed.append(_replace(candidate, RETURN_LABEL_HIGH_OFFSET, RETURN_LABEL_HIGH_ORIGINAL, label_high, "返回行文字指针高位"))
    allowed.append(_replace(candidate, RETURN_LABEL_LOW_OFFSET, RETURN_LABEL_LOW_ORIGINAL, label_low, "返回行文字指针低位"))
    if _decode_address_pair(
        bytes(candidate[RETURN_LABEL_HIGH_OFFSET : RETURN_LABEL_HIGH_OFFSET + 4]),
        bytes(candidate[RETURN_LABEL_LOW_OFFSET : RETURN_LABEL_LOW_OFFSET + 4]),
    ) != label_address:
        raise PageSettingsReturnRowLabelError("成品返回行文字指针未指向载荷文字")
    invariant_bytes = (
        (MENU_LIMIT_OFFSET, MENU_LIMIT_SEVEN, "设置循环上限"),
        (MENU_DISPATCH_OFFSET, MENU_DISPATCH_A, "A 阶段分发挂接"),
        (SETTINGS_CALLBACK_HIGH_OFFSET, SETTINGS_CALLBACK_HIGH_ORIGINAL, "设置回调高位"),
        (SETTINGS_CALLBACK_LOW_OFFSET, SETTINGS_CALLBACK_LOW_ORIGINAL, "设置回调低位"),
    )
    for offset, expected, label in invariant_bytes:
        if bytes(candidate[offset : offset + len(expected)]) != expected:
            raise PageSettingsReturnRowLabelError(f"{label}发生越界修改")
    recovery_crc = refresh_recovery_crc(candidate, AP01_1_0_2_0031)
    allowed.append(ByteRange(AP01_1_0_2_0031.recovery_trailer_offset + 36, AP01_1_0_2_0031.recovery_trailer_offset + 40))
    report = validate_candidate(stage, bytes(candidate), allowed, AP01_1_0_2_0031)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "manifest_type": "page-settings-return-row-label-firmware",
        "status": "built-approved-for-single-return-label-test",
        "built_at_beijing": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "tool": {**tool_revision, "versions": versions},
        "input": {"path": str(stage_selected), "size": len(stage), "sha256": STAGE_SHA256, "md5": STAGE_MD5, "read_only": True},
        "output": {"path": str(output), "read_only": True, **report.to_dict()},
        "source_evidence": [
            "knowledge/AP01-官方固件分析/原厂各页面物理旋钮交互实现.md",
            "knowledge/AP01-官方固件分析/cases/2026-08-04-原厂返回行标签与文字更新入口静态定位.md",
        ],
        "payload": {
            "file_offset": PAYLOAD_START,
            "runtime_address": f"0x{PAYLOAD_VA:08x}",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "capacity": PAYLOAD_CAPACITY,
            "remaining": PAYLOAD_CAPACITY - len(payload),
            "label": ROW_LABEL,
            "label_runtime_address": f"0x{label_address:08x}",
            "relocations": 0,
            "deterministic_links": 2,
            "max_static_stack": 0,
            "function_calls": 0,
        },
        "implemented_scope": ["保持 A 阶段设置分发", "复用原厂返回行文字指针"],
        "excluded_scope": ["新增设置列表对象", "设置事件回调", "按下进入开关页", "一级导航", "AGENTS 看板", "网络、持久化与后台刷新"],
        "simulation": simulation,
        "allowed_ranges": [item.to_dict() for item in allowed],
        "recovery_crc_after_build": f"0x{recovery_crc:08x}",
        "validation": {
            "input_identity_fixed": True,
            "old_bytes_asserted": True,
            "a_payload_code_preserved": True,
            "menu_limit_unchanged": True,
            "menu_dispatch_unchanged": True,
            "settings_callbacks_unchanged": True,
            "list_objects_unchanged": True,
            "return_label_pointer_resolved": True,
            "payload_calls_absent": True,
            "deterministic_payload_links": True,
            "outside_allowed_ranges_identical": True,
            "physical_acceptance_replaced": False,
            "installation_allowed": True,
        },
    }
    output_written = False
    try:
        _write_frozen(output, bytes(candidate))
        output_written = True
        readback = validate_candidate(stage, output.read_bytes(), allowed, AP01_1_0_2_0031)
        if readback.sha256 != report.sha256:
            raise PageSettingsReturnRowLabelError("返回行文字成品回读指纹不一致")
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        _write_frozen(manifest_path, manifest_bytes)
    except Exception:
        if output_written and output.exists():
            output.chmod(0o644)
            output.unlink()
        raise
    return PageSettingsReturnRowLabelResult(
        output=output,
        manifest=manifest_path.expanduser().resolve(),
        sha256=report.sha256,
        md5=report.md5,
        payload_size=len(payload),
        payload_remaining=PAYLOAD_CAPACITY - len(payload),
        label_runtime_address=label_address,
        simulation_items=int(simulation["item_count"]),
    )
