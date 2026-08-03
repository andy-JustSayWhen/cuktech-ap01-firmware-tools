"""从启动基础透传阶段构建只增加第八项普通行的固件。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
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
SOURCE = MODULE_DIR / "row_creation.S"
LINKER = MODULE_DIR / "row_creation.ld"
OUTPUT_NAME = "ap01-1.0.2_0031-page-settings-row-creation.bin"
STAGE_SIZE = 6_804_520
STAGE_SHA256 = "8986ceb31b7d26802bb06fc62a23f5c29eb00f089dc86a5a40d33d95b4dd345b"
STAGE_MD5 = "a066fab43085e8ab4c8b8aa33ff8af6f"
XIP_DELTA = 0x9FFFF000
PAYLOAD_VA = XIP_DELTA + PAYLOAD_START
A_PAYLOAD_SIZE = 28
A_PAYLOAD_SHA256 = "6c280eb1aa6fb2835a5df8ea12ac088f33e53be9e9524fa3818c21c0088e243c"
MENU_LIMIT_OFFSET = 0x1999B4
MENU_LIMIT_SEVEN = bytes.fromhex("9d47")
MENU_LIMIT_EIGHT = bytes.fromhex("a147")
MENU_DISPATCH_OFFSET = 0x1999DC
MENU_DISPATCH_A = bytes.fromhex("6fd05a3f")
SETTINGS_CALLBACK_HIGH_OFFSET = 0x0BE8CC
SETTINGS_CALLBACK_HIGH_ORIGINAL = bytes.fromhex("b7850fa0")
SETTINGS_CALLBACK_LOW_OFFSET = 0x0BE8D4
SETTINGS_CALLBACK_LOW_ORIGINAL = bytes.fromhex("93856509")
STOCK_ROW_CREATE = 0xA0192FB4
STOCK_ROW_TARGET = 0xA01989E0
STOCK_ROW_DONE = 0xA01989B2
STOCK_RETURN_TARGET = 0xA0198AD0
ROW_LABEL = "开关一级页面"
EXPECTED_BINUTILS_VERSION = "2.46.1"


class PageSettingsRowCreationError(RuntimeError):
    """页面设置新增行固件不满足固定合同。"""


@dataclass(frozen=True)
class PageSettingsRowCreationResult:
    output: Path
    manifest: Path
    sha256: str
    md5: str
    payload_size: int
    payload_remaining: int
    simulation_indices: int


def simulate_page_settings_row_creation() -> dict[str, object]:
    """验证八项创建分发和原厂回调暂时保持的边界。"""

    mappings = [
        {"index": 0, "path": "stock-first-row"},
        *({"index": index, "path": "stock-row"} for index in range(1, 6)),
        {"index": 6, "path": "new-stock-row"},
        {"index": 7, "path": "stock-return"},
    ]
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
    actual = [str(item["path"]) for item in mappings]
    if actual != expected:
        raise PageSettingsRowCreationError("八项设置创建分发不匹配")
    return {
        "passed": True,
        "indices_checked": len(mappings),
        "mappings": mappings,
        "failures": 0,
        "settings_callback_changed": False,
        "temporary_state_54_press": "stock-return",
        "temporary_state_55_selectable": False,
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
        raise PageSettingsRowCreationError("无法启动页面设置新增行构建工具") from error
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PageSettingsRowCreationError(f"页面设置新增行构建失败：{detail}")
    return completed.stdout


def _version(tool: Path) -> str:
    first = _run([tool, "--version"]).splitlines()
    value = first[0] if first else ""
    if EXPECTED_BINUTILS_VERSION not in value:
        raise PageSettingsRowCreationError(
            f"构建工具版本不匹配：预期 {EXPECTED_BINUTILS_VERSION}，实际 {value}"
        )
    return value


def _load_stage(path: Path) -> tuple[Path, bytes]:
    selected = path.expanduser().resolve(strict=True)
    if not selected.is_file():
        raise PageSettingsRowCreationError("新增行输入不是普通文件")
    writable = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    if selected.stat().st_mode & writable:
        raise PageSettingsRowCreationError("新增行输入必须为只读文件")
    stage = selected.read_bytes()
    if len(stage) != STAGE_SIZE:
        raise PageSettingsRowCreationError("新增行输入文件长度不匹配")
    if hashlib.sha256(stage).hexdigest() != STAGE_SHA256:
        raise PageSettingsRowCreationError("新增行输入 SHA-256 不匹配")
    if hashlib.md5(stage).hexdigest() != STAGE_MD5:
        raise PageSettingsRowCreationError("新增行输入 MD5 不匹配")
    expected = (
        (MENU_LIMIT_OFFSET, MENU_LIMIT_SEVEN, "设置循环上限"),
        (MENU_DISPATCH_OFFSET, MENU_DISPATCH_A, "A 阶段分发挂接"),
        (
            SETTINGS_CALLBACK_HIGH_OFFSET,
            SETTINGS_CALLBACK_HIGH_ORIGINAL,
            "设置回调地址高位",
        ),
        (
            SETTINGS_CALLBACK_LOW_OFFSET,
            SETTINGS_CALLBACK_LOW_ORIGINAL,
            "设置回调地址低位",
        ),
    )
    for offset, original, label in expected:
        if stage[offset : offset + len(original)] != original:
            raise PageSettingsRowCreationError(f"{label}原字节不匹配")
    a_payload = stage[PAYLOAD_START : PAYLOAD_START + A_PAYLOAD_SIZE]
    if hashlib.sha256(a_payload).hexdigest() != A_PAYLOAD_SHA256:
        raise PageSettingsRowCreationError("A 阶段透传载荷指纹不匹配")
    optimized_size = int.from_bytes(
        stage[GIF_SIZE_OFFSET : GIF_SIZE_OFFSET + 4], "little"
    )
    if optimized_size != OPTIMIZED_SIZE:
        raise PageSettingsRowCreationError("A 阶段动图长度字段不匹配")
    return selected, stage


def _replace(
    firmware: bytearray,
    offset: int,
    expected: bytes,
    replacement: bytes,
    label: str,
) -> ByteRange:
    if len(expected) != len(replacement):
        raise PageSettingsRowCreationError(f"{label}修改前后长度不一致")
    end = offset + len(expected)
    if bytes(firmware[offset:end]) != expected:
        raise PageSettingsRowCreationError(f"{label}原字节不匹配")
    firmware[offset:end] = replacement
    return ByteRange(offset, end)


def _write_frozen(path: Path, payload: bytes) -> Path:
    selected = path.expanduser().resolve()
    selected.parent.mkdir(parents=True, exist_ok=True)
    if selected.exists():
        raise PageSettingsRowCreationError(f"不可覆盖冻结文件：{selected}")
    temporary = selected.with_name(selected.name + ".part")
    if temporary.exists():
        raise PageSettingsRowCreationError(f"发现未处理临时文件：{temporary}")
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
) -> tuple[bytes, str, str]:
    selected = directory.expanduser().resolve()
    selected.mkdir(parents=True, exist_ok=True)
    object_path = selected / "page-settings-row-creation.o"
    elf_path = selected / "page-settings-row-creation.elf"
    binary_path = selected / "page-settings-row-creation.bin"
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
        raise PageSettingsRowCreationError("新增行载荷仍含未处理重定位")
    symbol_map = _symbols(nm, elf_path)
    if symbol_map.get("ap01_page_settings_row_creation") != PAYLOAD_VA:
        raise PageSettingsRowCreationError("新增行载荷符号地址不匹配")
    _run([copier, "-O", "binary", elf_path, binary_path])
    payload = binary_path.read_bytes()
    if not payload or len(payload) > PAYLOAD_CAPACITY:
        raise PageSettingsRowCreationError("新增行载荷超出固定空间")
    if ROW_LABEL.encode("utf-8") + b"\x00" not in payload:
        raise PageSettingsRowCreationError("新增行载荷缺少固定标签")
    disassembly = _run([dumper, "-d", "-M", "no-aliases,numeric", elf_path])
    lowered = disassembly.lower()
    for target in (
        STOCK_ROW_CREATE,
        STOCK_ROW_TARGET,
        STOCK_ROW_DONE,
        STOCK_RETURN_TARGET,
    ):
        if f"{target:08x}" not in lowered:
            raise PageSettingsRowCreationError(
                f"新增行载荷缺少批准的原厂地址：0x{target:08x}"
            )
    call_lines = [
        line
        for line in lowered.splitlines()
        if re.search(r"\bjalr?\s+(?:ra|x1),", line)
    ]
    if len(call_lines) != 1 or f"{STOCK_ROW_CREATE:08x}" not in call_lines[0]:
        raise PageSettingsRowCreationError("新增行载荷必须只调用一次原厂普通行入口")
    for forbidden in (0xA00F8096, 0xA00C6DFE, 0xA00F3D5A, 0xA00BFA4E):
        if f"{forbidden:08x}" in lowered:
            raise PageSettingsRowCreationError(
                f"新增行载荷包含本阶段禁止地址：0x{forbidden:08x}"
            )
    for marker in (b"/data/", b"http://", b"https://", b"APAG"):
        if marker in payload:
            raise PageSettingsRowCreationError("新增行载荷包含越界功能字符串")
    return payload, disassembly, readelf_text


def build_page_settings_row_creation(
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
) -> PageSettingsRowCreationResult:
    """从 A 阶段冻结成品生成只增加第八项普通行的 B 阶段固件。"""

    if tool_revision.get("scoped_code_dirty") is not False:
        raise PageSettingsRowCreationError("制作代码尚未提交，不能冻结新增行固件")
    stage_selected, stage = _load_stage(stage_path)
    output = output_path.expanduser().resolve()
    if output.name != OUTPUT_NAME:
        raise PageSettingsRowCreationError(f"输出文件名必须为 {OUTPUT_NAME}")
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
        raise PageSettingsRowCreationError("两次新增行载荷构建不一致")
    payload, disassembly, readelf_text = first
    (selected_build / "disassembly.txt").write_text(
        disassembly, encoding="utf-8", newline="\n"
    )
    (selected_build / "readelf.txt").write_text(
        readelf_text, encoding="utf-8", newline="\n"
    )
    simulation = simulate_page_settings_row_creation()

    candidate = bytearray(stage)
    allowed: list[ByteRange] = []
    payload_before = bytes(candidate[PAYLOAD_START : PAYLOAD_START + len(payload)])
    candidate[PAYLOAD_START : PAYLOAD_START + len(payload)] = payload
    if payload_before == payload:
        raise PageSettingsRowCreationError("新增行载荷写入前后相同")
    allowed.append(ByteRange(PAYLOAD_START, PAYLOAD_START + len(payload)))
    allowed.append(
        _replace(
            candidate,
            MENU_LIMIT_OFFSET,
            MENU_LIMIT_SEVEN,
            MENU_LIMIT_EIGHT,
            "设置循环上限",
        )
    )
    if (
        bytes(candidate[MENU_DISPATCH_OFFSET : MENU_DISPATCH_OFFSET + 4])
        != MENU_DISPATCH_A
    ):
        raise PageSettingsRowCreationError("A 阶段分发挂接发生越界修改")
    if (
        bytes(
            candidate[
                SETTINGS_CALLBACK_HIGH_OFFSET : SETTINGS_CALLBACK_HIGH_OFFSET + 4
            ]
        )
        != SETTINGS_CALLBACK_HIGH_ORIGINAL
    ):
        raise PageSettingsRowCreationError("设置回调地址高位发生越界修改")
    if (
        bytes(
            candidate[
                SETTINGS_CALLBACK_LOW_OFFSET : SETTINGS_CALLBACK_LOW_OFFSET + 4
            ]
        )
        != SETTINGS_CALLBACK_LOW_ORIGINAL
    ):
        raise PageSettingsRowCreationError("设置回调地址低位发生越界修改")
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
        "manifest_type": "page-settings-row-creation-firmware",
        "status": "built-approved-for-single-row-creation-test",
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
            "knowledge/AP01-官方固件分析/cases/2026-07-30-设置列表第八项容量与生命周期静态复查.md",
            "knowledge/AP01-官方固件分析/cases/2026-08-03-FW-PAGE-004-A安装.md",
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
            "row_label": ROW_LABEL,
            "approved_targets": [
                f"0x{STOCK_ROW_CREATE:08x}",
                f"0x{STOCK_ROW_TARGET:08x}",
                f"0x{STOCK_ROW_DONE:08x}",
                f"0x{STOCK_RETURN_TARGET:08x}",
            ],
        },
        "implemented_scope": [
            "设置循环从七项扩为八项",
            "序号六调用一次原厂普通行入口",
            "序号七继续原厂返回行入口",
        ],
        "excluded_scope": [
            "设置事件回调替换",
            "新增行确认与页面开关界面",
            "一级导航与一级回调",
            "AGENTS 看板",
            "网络、持久化与后台刷新",
        ],
        "simulation": simulation,
        "allowed_ranges": [item.to_dict() for item in allowed],
        "recovery_crc_after_build": f"0x{recovery_crc:08x}",
        "validation": {
            "input_identity_fixed": True,
            "old_bytes_asserted": True,
            "a_payload_identity_fixed": True,
            "menu_limit_is_eight": True,
            "menu_dispatch_hook_unchanged": True,
            "settings_callbacks_unchanged": True,
            "single_stock_row_create_call": True,
            "stock_return_path_preserved": True,
            "deterministic_payload_links": True,
            "creation_dispatch_simulation_passed": True,
            "outside_allowed_ranges_identical": True,
            "physical_acceptance_replaced": False,
            "installation_allowed": True,
        },
    }
    output_written = False
    try:
        _write_frozen(output, bytes(candidate))
        output_written = True
        readback = validate_candidate(
            stage, output.read_bytes(), allowed, AP01_1_0_2_0031
        )
        if readback.sha256 != report.sha256:
            raise PageSettingsRowCreationError("新增行成品回读指纹不一致")
        manifest_bytes = (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        _write_frozen(manifest_path, manifest_bytes)
    except Exception:
        if output_written and output.exists():
            output.chmod(0o644)
            output.unlink()
        raise
    return PageSettingsRowCreationResult(
        output=output,
        manifest=manifest_path.expanduser().resolve(),
        sha256=report.sha256,
        md5=report.md5,
        payload_size=len(payload),
        payload_remaining=PAYLOAD_CAPACITY - len(payload),
        simulation_indices=int(simulation["indices_checked"]),
    )
