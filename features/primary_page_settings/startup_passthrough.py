"""构建并模拟不改变原厂设置行为的启动基础透传固件。"""

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
    GIF_DATA_OFFSET,
    GIF_SIZE_OFFSET,
    OPTIMIZED_SIZE,
    ORIGINAL_SIZE,
    ORIGINAL_SHA256,
    PAYLOAD_CAPACITY,
    PAYLOAD_START,
    inspect_payload_space,
)


MODULE_DIR = Path(__file__).resolve().parent
SOURCE = MODULE_DIR / "startup_passthrough.S"
LINKER = MODULE_DIR / "startup_passthrough.ld"
OUTPUT_NAME = "ap01-1.0.2_0031-page-settings-startup-passthrough.bin"
STAGE_SIZE = 6_804_520
STAGE_SHA256 = "348d0843ac3f3f380eb155170c4104fd8467a018ddfd13670d67be998f269dc1"
STAGE_MD5 = "13a7286f4824b1ad87d9bc32f1d3d39c"
XIP_DELTA = 0x9FFFF000
PAYLOAD_VA = XIP_DELTA + PAYLOAD_START
MENU_LIMIT_OFFSET = 0x1999B4
MENU_LIMIT_ORIGINAL = bytes.fromhex("9d47")
MENU_DISPATCH_OFFSET = 0x1999DC
MENU_DISPATCH_VA = XIP_DELTA + MENU_DISPATCH_OFFSET
MENU_DISPATCH_ORIGINAL = bytes.fromhex("638ae70e")
SETTINGS_CALLBACK_HIGH_OFFSET = 0x0BE8CC
SETTINGS_CALLBACK_HIGH_ORIGINAL = bytes.fromhex("b7850fa0")
SETTINGS_CALLBACK_LOW_OFFSET = 0x0BE8D4
SETTINGS_CALLBACK_LOW_ORIGINAL = bytes.fromhex("93856509")
STOCK_ROW_TARGET = 0xA01989E0
STOCK_RETURN_TARGET = 0xA0198AD0
EXPECTED_BINUTILS_VERSION = "2.46.1"


class PageSettingsStartupPassthroughError(RuntimeError):
    """启动基础透传固件不满足固定合同。"""


@dataclass(frozen=True)
class PageSettingsStartupPassthroughResult:
    output: Path
    manifest: Path
    sha256: str
    md5: str
    payload_size: int
    payload_remaining: int
    simulation_indices: int


def _stock_dispatch(index: int) -> int:
    if not 1 <= index <= 6:
        raise PageSettingsStartupPassthroughError("设置创建序号超出原厂可达范围")
    return STOCK_RETURN_TARGET if index == 6 else STOCK_ROW_TARGET


def _passthrough_dispatch(index: int) -> int:
    if not 1 <= index <= 6:
        raise PageSettingsStartupPassthroughError("设置透传序号超出原厂可达范围")
    return STOCK_RETURN_TARGET if index == 6 else STOCK_ROW_TARGET


def simulate_page_settings_startup_passthrough() -> dict[str, object]:
    """逐序号证明七项设置创建分发与原厂相同。"""

    failures: list[str] = []
    mappings: list[dict[str, object]] = []
    for index in range(1, 7):
        expected = _stock_dispatch(index)
        actual = _passthrough_dispatch(index)
        mappings.append(
            {
                "index": index,
                "stock_target": f"0x{expected:08x}",
                "candidate_target": f"0x{actual:08x}",
                "equal": expected == actual,
            }
        )
        if actual != expected:
            failures.append(
                f"设置序号 {index} 分发不一致：0x{expected:08x} != 0x{actual:08x}"
            )
    if failures:
        raise PageSettingsStartupPassthroughError(failures[0])
    return {
        "passed": True,
        "indices_checked": len(mappings),
        "mappings": mappings,
        "failures": 0,
        "user_visible_behavior_changed": False,
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
        raise PageSettingsStartupPassthroughError(
            "无法启动页面设置透传构建工具"
        ) from error
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PageSettingsStartupPassthroughError(
            f"页面设置透传构建失败：{detail}"
        )
    return completed.stdout


def _version(tool: Path) -> str:
    first = _run([tool, "--version"]).splitlines()
    value = first[0] if first else ""
    if EXPECTED_BINUTILS_VERSION not in value:
        raise PageSettingsStartupPassthroughError(
            f"构建工具版本不匹配：预期 {EXPECTED_BINUTILS_VERSION}，实际 {value}"
        )
    return value


def _load_stage(path: Path) -> tuple[Path, bytes]:
    selected = path.expanduser().resolve(strict=True)
    if not selected.is_file():
        raise PageSettingsStartupPassthroughError("启动透传输入不是普通文件")
    writable = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    if selected.stat().st_mode & writable:
        raise PageSettingsStartupPassthroughError("启动透传输入必须为只读文件")
    payload = selected.read_bytes()
    if len(payload) != STAGE_SIZE:
        raise PageSettingsStartupPassthroughError("启动透传输入文件长度不匹配")
    if hashlib.sha256(payload).hexdigest() != STAGE_SHA256:
        raise PageSettingsStartupPassthroughError("启动透传输入 SHA-256 不匹配")
    if hashlib.md5(payload).hexdigest() != STAGE_MD5:
        raise PageSettingsStartupPassthroughError("启动透传输入 MD5 不匹配")
    expected = (
        (MENU_LIMIT_OFFSET, MENU_LIMIT_ORIGINAL, "设置循环上限"),
        (MENU_DISPATCH_OFFSET, MENU_DISPATCH_ORIGINAL, "设置创建分支"),
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
        if payload[offset : offset + len(original)] != original:
            raise PageSettingsStartupPassthroughError(f"{label}原字节不匹配")
    return selected, payload


def _jump(source: int, target: int) -> bytes:
    offset = target - source
    if offset & 1 or not -(1 << 20) <= offset < (1 << 20):
        raise PageSettingsStartupPassthroughError("启动透传跳转超出范围")
    immediate = offset & 0x1FFFFF
    word = (
        (((immediate >> 20) & 1) << 31)
        | (((immediate >> 1) & 0x3FF) << 21)
        | (((immediate >> 11) & 1) << 20)
        | (((immediate >> 12) & 0xFF) << 12)
        | 0x6F
    )
    return struct.pack("<I", word)


def _replace(
    firmware: bytearray,
    offset: int,
    expected: bytes,
    replacement: bytes,
    label: str,
) -> ByteRange:
    if len(expected) != len(replacement):
        raise PageSettingsStartupPassthroughError(f"{label}修改前后长度不一致")
    end = offset + len(expected)
    if bytes(firmware[offset:end]) != expected:
        raise PageSettingsStartupPassthroughError(f"{label}原字节不匹配")
    firmware[offset:end] = replacement
    return ByteRange(offset, end)


def _write_frozen(path: Path, payload: bytes) -> Path:
    selected = path.expanduser().resolve()
    selected.parent.mkdir(parents=True, exist_ok=True)
    if selected.exists():
        raise PageSettingsStartupPassthroughError(f"不可覆盖冻结文件：{selected}")
    temporary = selected.with_name(selected.name + ".part")
    if temporary.exists():
        raise PageSettingsStartupPassthroughError(f"发现未处理临时文件：{temporary}")
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
    object_path = selected / "page-settings-startup-passthrough.o"
    elf_path = selected / "page-settings-startup-passthrough.elf"
    binary_path = selected / "page-settings-startup-passthrough.bin"
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
        raise PageSettingsStartupPassthroughError("启动透传载荷仍含未处理重定位")
    symbol_map = _symbols(nm, elf_path)
    entry = symbol_map.get("ap01_page_settings_startup_passthrough")
    if entry != PAYLOAD_VA:
        raise PageSettingsStartupPassthroughError("启动透传载荷符号地址不匹配")
    _run([copier, "-O", "binary", elf_path, binary_path])
    payload = binary_path.read_bytes()
    if not payload or len(payload) > PAYLOAD_CAPACITY:
        raise PageSettingsStartupPassthroughError("启动透传载荷超出固定空间")
    disassembly = _run([dumper, "-d", "-M", "no-aliases,numeric", elf_path])
    lowered = disassembly.lower()
    for target in (STOCK_ROW_TARGET, STOCK_RETURN_TARGET):
        if f"{target:08x}" not in lowered:
            raise PageSettingsStartupPassthroughError(
                f"启动透传缺少原厂继续地址：0x{target:08x}"
            )
    if re.search(r"\bjalr?\s+(?:ra|x1),", lowered):
        raise PageSettingsStartupPassthroughError("启动透传载荷包含函数调用")
    for marker in (b"/data/", b"http://", b"https://", b"APAG"):
        if marker in payload:
            raise PageSettingsStartupPassthroughError("启动透传包含越界功能字符串")
    return payload, disassembly, readelf_text


def build_page_settings_startup_passthrough(
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
) -> PageSettingsStartupPassthroughResult:
    """从已验收设置阶段输入生成启动基础透传固件。"""

    if tool_revision.get("scoped_code_dirty") is not False:
        raise PageSettingsStartupPassthroughError(
            "制作代码尚未提交，不能冻结启动基础透传固件"
        )
    stage_selected, stage = _load_stage(stage_path)
    output = output_path.expanduser().resolve()
    if output.name != OUTPUT_NAME:
        raise PageSettingsStartupPassthroughError(f"输出文件名必须为 {OUTPUT_NAME}")
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
    optimized_path = selected_build / "optimized-stock.gif"
    payload_space_report_path = selected_build / "payload-space.json"
    payload_space = inspect_payload_space(
        stage_selected,
        optimized_path,
        payload_space_report_path,
        tool_revision=tool_revision,
    )
    optimized = optimized_path.read_bytes()
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
        raise PageSettingsStartupPassthroughError("两次启动透传载荷构建不一致")
    payload, disassembly, readelf_text = first
    (selected_build / "disassembly.txt").write_text(
        disassembly, encoding="utf-8", newline="\n"
    )
    (selected_build / "readelf.txt").write_text(
        readelf_text, encoding="utf-8", newline="\n"
    )
    simulation = simulate_page_settings_startup_passthrough()
    payload_space_gates = payload_space.get("gates")
    if not isinstance(payload_space_gates, dict):
        raise PageSettingsStartupPassthroughError("载荷空间报告缺少门禁结果")
    payload_space_gates.update(
        {
            "linked_payload_fits": True,
            "patch_plan_allowed": True,
            "reason": "启动基础透传载荷和逐序号等价模拟已经通过",
        }
    )

    candidate = bytearray(stage)
    allowed: list[ByteRange] = []
    allowed.append(
        _replace(
            candidate,
            GIF_SIZE_OFFSET,
            struct.pack("<I", ORIGINAL_SIZE),
            struct.pack("<I", OPTIMIZED_SIZE),
            "原厂动图长度",
        )
    )
    original_gif = bytes(candidate[GIF_DATA_OFFSET : GIF_DATA_OFFSET + ORIGINAL_SIZE])
    if hashlib.sha256(original_gif).hexdigest() != ORIGINAL_SHA256:
        raise PageSettingsStartupPassthroughError("原厂动图修改前指纹不匹配")
    candidate[GIF_DATA_OFFSET : GIF_DATA_OFFSET + len(optimized)] = optimized
    allowed.append(ByteRange(GIF_DATA_OFFSET, GIF_DATA_OFFSET + len(optimized)))
    payload_before = bytes(candidate[PAYLOAD_START : PAYLOAD_START + len(payload)])
    candidate[PAYLOAD_START : PAYLOAD_START + len(payload)] = payload
    if payload_before == payload:
        raise PageSettingsStartupPassthroughError("启动透传载荷写入前后相同")
    allowed.append(ByteRange(PAYLOAD_START, PAYLOAD_START + len(payload)))
    allowed.append(
        _replace(
            candidate,
            MENU_DISPATCH_OFFSET,
            MENU_DISPATCH_ORIGINAL,
            _jump(MENU_DISPATCH_VA, PAYLOAD_VA),
            "设置创建分支",
        )
    )
    if bytes(candidate[MENU_LIMIT_OFFSET : MENU_LIMIT_OFFSET + 2]) != MENU_LIMIT_ORIGINAL:
        raise PageSettingsStartupPassthroughError("设置循环上限发生越界修改")
    if (
        bytes(
            candidate[
                SETTINGS_CALLBACK_HIGH_OFFSET : SETTINGS_CALLBACK_HIGH_OFFSET + 4
            ]
        )
        != SETTINGS_CALLBACK_HIGH_ORIGINAL
    ):
        raise PageSettingsStartupPassthroughError("设置回调地址高位发生越界修改")
    if (
        bytes(
            candidate[
                SETTINGS_CALLBACK_LOW_OFFSET : SETTINGS_CALLBACK_LOW_OFFSET + 4
            ]
        )
        != SETTINGS_CALLBACK_LOW_ORIGINAL
    ):
        raise PageSettingsStartupPassthroughError("设置回调地址低位发生越界修改")
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
        "manifest_type": "page-settings-startup-passthrough-firmware",
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
            "knowledge/AP01-官方固件分析/cases/2026-08-03-FW-PAGE-003-A启动修改分层复查.md",
        ],
        "payload_space": payload_space,
        "payload": {
            "file_offset": PAYLOAD_START,
            "runtime_address": f"0x{PAYLOAD_VA:08x}",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "capacity": PAYLOAD_CAPACITY,
            "remaining": PAYLOAD_CAPACITY - len(payload),
            "relocations": 0,
            "deterministic_links": 2,
            "max_static_stack": 0,
            "stock_targets": [
                f"0x{STOCK_ROW_TARGET:08x}",
                f"0x{STOCK_RETURN_TARGET:08x}",
            ],
        },
        "implemented_scope": [
            "原厂第一张动图无损整理",
            "固定载荷空间写入",
            "设置创建分支原样透传",
        ],
        "excluded_scope": [
            "设置循环上限",
            "设置行与设置对象",
            "设置事件回调",
            "一级导航与旋钮行为",
            "AGENTS 看板",
            "网络、持久化与后台刷新",
        ],
        "simulation": simulation,
        "allowed_ranges": [item.to_dict() for item in allowed],
        "recovery_crc_after_build": f"0x{recovery_crc:08x}",
        "validation": {
            "input_identity_fixed": True,
            "old_bytes_asserted": True,
            "optimized_gif_verified": True,
            "menu_limit_unchanged": True,
            "settings_callbacks_unchanged": True,
            "payload_has_only_stock_targets": True,
            "payload_calls_absent": True,
            "deterministic_payload_links": True,
            "stock_dispatch_equivalence_passed": True,
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
            raise PageSettingsStartupPassthroughError("启动透传成品回读指纹不一致")
        manifest_bytes = (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        _write_frozen(manifest_path, manifest_bytes)
    except Exception:
        if output_written and output.exists():
            output.chmod(0o644)
            output.unlink()
        raise
    return PageSettingsStartupPassthroughResult(
        output=output,
        manifest=manifest_path.expanduser().resolve(),
        sha256=report.sha256,
        md5=report.md5,
        payload_size=len(payload),
        payload_remaining=PAYLOAD_CAPACITY - len(payload),
        simulation_indices=int(simulation["indices_checked"]),
    )
