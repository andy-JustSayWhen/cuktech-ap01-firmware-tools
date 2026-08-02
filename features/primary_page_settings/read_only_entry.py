"""构建并模拟只增加第八项入口的页面开关第一阶段固件。"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
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
SOURCE = MODULE_DIR / "read_only_entry.S"
LINKER = MODULE_DIR / "read_only_entry.ld"
OUTPUT_NAME = "ap01-1.0.2_0031-page-settings-read-only-entry.bin"
STAGE_SIZE = 6_804_520
STAGE_SHA256 = "348d0843ac3f3f380eb155170c4104fd8467a018ddfd13670d67be998f269dc1"
STAGE_MD5 = "13a7286f4824b1ad87d9bc32f1d3d39c"
XIP_DELTA = 0x9FFFF000
PAYLOAD_VA = XIP_DELTA + PAYLOAD_START
MENU_LIMIT_OFFSET = 0x1999B4
MENU_LIMIT_ORIGINAL = bytes.fromhex("9d47")
MENU_LIMIT_EIGHT = bytes.fromhex("a147")
MENU_DISPATCH_OFFSET = 0x1999DC
MENU_DISPATCH_VA = XIP_DELTA + MENU_DISPATCH_OFFSET
MENU_DISPATCH_ORIGINAL = bytes.fromhex("638ae70e")
SETTINGS_CALLBACK_HIGH_OFFSET = 0x0BE8CC
SETTINGS_CALLBACK_HIGH_ORIGINAL = bytes.fromhex("b7850fa0")
SETTINGS_CALLBACK_LOW_OFFSET = 0x0BE8D4
SETTINGS_CALLBACK_LOW_ORIGINAL = bytes.fromhex("93856509")
EXPECTED_BINUTILS_VERSION = "2.46.1"
REQUIRED_CALLEES = (
    0xA00BF7EA,
    0xA00C5D84,
    0xA00C5FE4,
    0xA00F8096,
    0xA0192FB4,
    0xA00C6DFE,
    0xA00F3D5A,
    0xA01989E0,
    0xA0198AD0,
)
FORBIDDEN_CALLEES = (
    0xA00C1EC6,
    0xA00BEBEE,
    0xA007E1C4,
    0xA007C256,
    0xA00BFA4E,
    0xA01930FE,
)


class PageSettingsReadOnlyEntryError(RuntimeError):
    """页面开关只读入口固件不满足固定合同。"""


@dataclass(frozen=True)
class PageSettingsReadOnlyEntryResult:
    output: Path
    manifest: Path
    sha256: str
    md5: str
    payload_size: int
    payload_remaining: int
    simulation_sequences: int


@dataclass(frozen=True)
class _SimulationState:
    index: int
    terminal: str | None = None


def _simulate_step(state: _SimulationState, event: str) -> _SimulationState:
    if state.terminal is not None:
        return state
    if event == "left":
        return _SimulationState(max(0, state.index - 1))
    if event == "right":
        return _SimulationState(min(7, state.index + 1))
    if event != "enter":
        raise PageSettingsReadOnlyEntryError("设置事件模拟收到未知事件")
    if state.index <= 5:
        return _SimulationState(state.index, "stock-detail")
    if state.index == 6:
        return state
    return _SimulationState(state.index, "stock-return")


def simulate_page_settings_read_only_entry() -> dict[str, object]:
    """穷举第一阶段主设置列表事件，失败时拒绝构建。"""

    failures: list[str] = []
    directed = (
        (6, ("right",), 7, None),
        (7, ("left",), 6, None),
        (6, ("enter", "enter"), 6, None),
        (7, ("enter",), 7, "stock-return"),
        (0, ("left",), 0, None),
        (7, ("right",), 7, None),
        (5, ("right", "left", "right"), 6, None),
        (7, ("left", "right", "left"), 6, None),
    )
    for start, events, expected_index, expected_terminal in directed:
        state = _SimulationState(start)
        for event in events:
            state = _simulate_step(state, event)
        if state != _SimulationState(expected_index, expected_terminal):
            failures.append(
                f"定向场景失败：{start} {events} -> {state.index}/{state.terminal}"
            )

    exhaustive = 0
    events = ("left", "right", "enter")
    for start in range(8):
        for sequence in itertools.product(events, repeat=5):
            exhaustive += 1
            state = _SimulationState(start)
            for event in sequence:
                state = _simulate_step(state, event)
                if not 0 <= state.index <= 7:
                    failures.append(
                        f"状态越界：{start} {sequence} -> {state.index}"
                    )
                    break
            if state.terminal not in (None, "stock-detail", "stock-return"):
                failures.append(
                    f"终止状态非法：{start} {sequence} -> {state.terminal}"
                )
    if failures:
        raise PageSettingsReadOnlyEntryError(failures[0])
    return {
        "passed": True,
        "directed_scenarios": len(directed),
        "exhaustive_sequences": exhaustive,
        "sequence_depth": 5,
        "failures": 0,
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
        raise PageSettingsReadOnlyEntryError("无法启动只读入口构建工具") from error
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PageSettingsReadOnlyEntryError(f"只读入口构建失败：{detail}")
    return completed.stdout


def _version(tool: Path) -> str:
    first = _run([tool, "--version"]).splitlines()
    value = first[0] if first else ""
    if EXPECTED_BINUTILS_VERSION not in value:
        raise PageSettingsReadOnlyEntryError(
            f"构建工具版本不匹配：预期 {EXPECTED_BINUTILS_VERSION}，实际 {value}"
        )
    return value


def _load_stage(path: Path) -> tuple[Path, bytes]:
    selected = path.expanduser().resolve(strict=True)
    if not selected.is_file():
        raise PageSettingsReadOnlyEntryError("只读入口输入不是普通文件")
    writable = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    if selected.stat().st_mode & writable:
        raise PageSettingsReadOnlyEntryError("只读入口输入必须为只读文件")
    payload = selected.read_bytes()
    if len(payload) != STAGE_SIZE:
        raise PageSettingsReadOnlyEntryError("只读入口输入文件长度不匹配")
    if hashlib.sha256(payload).hexdigest() != STAGE_SHA256:
        raise PageSettingsReadOnlyEntryError("只读入口输入 SHA-256 不匹配")
    if hashlib.md5(payload).hexdigest() != STAGE_MD5:
        raise PageSettingsReadOnlyEntryError("只读入口输入 MD5 不匹配")
    expected = (
        (MENU_LIMIT_OFFSET, MENU_LIMIT_ORIGINAL, "设置循环上限"),
        (MENU_DISPATCH_OFFSET, MENU_DISPATCH_ORIGINAL, "设置新增行分支"),
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
            raise PageSettingsReadOnlyEntryError(f"{label}原字节不匹配")
    return selected, payload


def _jump(source: int, target: int) -> bytes:
    offset = target - source
    if offset & 1 or not -(1 << 20) <= offset < (1 << 20):
        raise PageSettingsReadOnlyEntryError("只读入口跳转超出范围")
    immediate = offset & 0x1FFFFF
    word = (
        (((immediate >> 20) & 1) << 31)
        | (((immediate >> 1) & 0x3FF) << 21)
        | (((immediate >> 11) & 1) << 20)
        | (((immediate >> 12) & 0xFF) << 12)
        | 0x6F
    )
    return struct.pack("<I", word)


def _absolute_pair(target: int, register: int) -> tuple[bytes, bytes]:
    high = (target + 0x800) >> 12
    low = target - (high << 12)
    lui = ((high & 0xFFFFF) << 12) | (register << 7) | 0x37
    addi = (
        ((low & 0xFFF) << 20)
        | (register << 15)
        | (register << 7)
        | 0x13
    )
    return struct.pack("<I", lui), struct.pack("<I", addi)


def _replace(
    firmware: bytearray,
    offset: int,
    expected: bytes,
    replacement: bytes,
    label: str,
) -> ByteRange:
    if len(expected) != len(replacement):
        raise PageSettingsReadOnlyEntryError(f"{label}修改前后长度不一致")
    end = offset + len(expected)
    if bytes(firmware[offset:end]) != expected:
        raise PageSettingsReadOnlyEntryError(f"{label}原字节不匹配")
    firmware[offset:end] = replacement
    return ByteRange(offset, end)


def _write_frozen(path: Path, payload: bytes) -> Path:
    selected = path.expanduser().resolve()
    selected.parent.mkdir(parents=True, exist_ok=True)
    if selected.exists():
        raise PageSettingsReadOnlyEntryError(f"不可覆盖冻结文件：{selected}")
    temporary = selected.with_name(selected.name + ".part")
    if temporary.exists():
        raise PageSettingsReadOnlyEntryError(f"发现未处理临时文件：{temporary}")
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
    object_path = selected / "page-settings-read-only-entry.o"
    elf_path = selected / "page-settings-read-only-entry.elf"
    binary_path = selected / "page-settings-read-only-entry.bin"
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
        raise PageSettingsReadOnlyEntryError("只读入口载荷仍含未处理重定位")
    symbol_map = _symbols(nm, elf_path)
    menu_entry = symbol_map.get("ap01_page_settings_read_only_menu_dispatch")
    event_entry = symbol_map.get("ap01_page_settings_read_only_event")
    if menu_entry != PAYLOAD_VA or event_entry is None:
        raise PageSettingsReadOnlyEntryError("只读入口载荷符号地址不匹配")
    _run([copier, "-O", "binary", elf_path, binary_path])
    payload = binary_path.read_bytes()
    if not payload or len(payload) > PAYLOAD_CAPACITY:
        raise PageSettingsReadOnlyEntryError("只读入口载荷超出固定空间")
    disassembly = _run([dumper, "-d", "-M", "no-aliases,numeric", elf_path])
    lowered = disassembly.lower()
    for callee in REQUIRED_CALLEES:
        if f"{callee:08x}" not in lowered:
            raise PageSettingsReadOnlyEntryError(
                f"只读入口缺少批准的原厂调用：0x{callee:08x}"
            )
    for callee in FORBIDDEN_CALLEES:
        if f"{callee:08x}" in lowered:
            raise PageSettingsReadOnlyEntryError(
                f"只读入口包含禁止调用：0x{callee:08x}"
            )
    for marker in (b"/data/", b"http://", b"https://", b"APAG"):
        if marker in payload:
            raise PageSettingsReadOnlyEntryError("只读入口包含越界功能字符串")
    return payload, event_entry, disassembly, readelf_text


def build_page_settings_read_only_entry(
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
) -> PageSettingsReadOnlyEntryResult:
    """从已验收设置阶段输入生成第一段只读入口固件。"""

    if tool_revision.get("scoped_code_dirty") is not False:
        raise PageSettingsReadOnlyEntryError("制作代码尚未提交，不能冻结只读入口固件")
    stage_selected, stage = _load_stage(stage_path)
    output = output_path.expanduser().resolve()
    if output.name != OUTPUT_NAME:
        raise PageSettingsReadOnlyEntryError(f"输出文件名必须为 {OUTPUT_NAME}")
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
    if first[:2] != second[:2]:
        raise PageSettingsReadOnlyEntryError("两次只读入口载荷构建不一致")
    payload, event_entry, disassembly, readelf_text = first
    (selected_build / "disassembly.txt").write_text(
        disassembly, encoding="utf-8", newline="\n"
    )
    (selected_build / "readelf.txt").write_text(
        readelf_text, encoding="utf-8", newline="\n"
    )
    simulation = simulate_page_settings_read_only_entry()
    payload_space_gates = payload_space.get("gates")
    if not isinstance(payload_space_gates, dict):
        raise PageSettingsReadOnlyEntryError("载荷空间报告缺少门禁结果")
    payload_space_gates.update(
        {
            "linked_payload_fits": True,
            "patch_plan_allowed": True,
            "reason": "只读入口载荷、固定挂接与严格模拟已经通过",
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
        raise PageSettingsReadOnlyEntryError("原厂动图修改前指纹不匹配")
    candidate[GIF_DATA_OFFSET : GIF_DATA_OFFSET + len(optimized)] = optimized
    allowed.append(ByteRange(GIF_DATA_OFFSET, GIF_DATA_OFFSET + len(optimized)))
    payload_before = bytes(candidate[PAYLOAD_START : PAYLOAD_START + len(payload)])
    candidate[PAYLOAD_START : PAYLOAD_START + len(payload)] = payload
    if payload_before == payload:
        raise PageSettingsReadOnlyEntryError("只读入口载荷写入前后相同")
    allowed.append(ByteRange(PAYLOAD_START, PAYLOAD_START + len(payload)))
    allowed.append(
        _replace(
            candidate,
            MENU_LIMIT_OFFSET,
            MENU_LIMIT_ORIGINAL,
            MENU_LIMIT_EIGHT,
            "设置循环上限",
        )
    )
    allowed.append(
        _replace(
            candidate,
            MENU_DISPATCH_OFFSET,
            MENU_DISPATCH_ORIGINAL,
            _jump(MENU_DISPATCH_VA, PAYLOAD_VA),
            "设置新增行分发",
        )
    )
    callback_high, callback_low = _absolute_pair(event_entry, 11)
    allowed.append(
        _replace(
            candidate,
            SETTINGS_CALLBACK_HIGH_OFFSET,
            SETTINGS_CALLBACK_HIGH_ORIGINAL,
            callback_high,
            "设置回调地址高位",
        )
    )
    allowed.append(
        _replace(
            candidate,
            SETTINGS_CALLBACK_LOW_OFFSET,
            SETTINGS_CALLBACK_LOW_ORIGINAL,
            callback_low,
            "设置回调地址低位",
        )
    )
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
        "manifest_type": "page-settings-read-only-entry-firmware",
        "status": "built-approved-for-single-test-installation",
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
        ],
        "payload_space": payload_space,
        "payload": {
            "file_offset": PAYLOAD_START,
            "runtime_address": f"0x{PAYLOAD_VA:08x}",
            "event_entry": f"0x{event_entry:08x}",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "capacity": PAYLOAD_CAPACITY,
            "remaining": PAYLOAD_CAPACITY - len(payload),
            "relocations": 0,
            "deterministic_links": 2,
            "max_static_stack": 48,
        },
        "implemented_scope": [
            "设置列表新增一个普通行",
            "原厂返回行移到第八项",
            "新增行与返回行之间的两条相邻选择",
            "确认新增行时只消费事件",
        ],
        "excluded_scope": [
            "页面开关对象",
            "页面开关状态读取与保存",
            "一级导航过滤",
            "AGENTS 看板",
            "网络与后台刷新",
        ],
        "simulation": simulation,
        "allowed_ranges": [item.to_dict() for item in allowed],
        "recovery_crc_after_build": f"0x{recovery_crc:08x}",
        "validation": {
            "input_identity_fixed": True,
            "old_bytes_asserted": True,
            "optimized_gif_verified": True,
            "settings_callback_scoped": True,
            "forbidden_calls_absent": True,
            "deterministic_payload_links": True,
            "strict_simulation_passed": True,
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
            raise PageSettingsReadOnlyEntryError("只读入口成品回读指纹不一致")
        manifest_bytes = (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        _write_frozen(manifest_path, manifest_bytes)
    except Exception:
        if output_written and output.exists():
            output.chmod(0o644)
            output.unlink()
        raise
    return PageSettingsReadOnlyEntryResult(
        output=output,
        manifest=manifest_path.expanduser().resolve(),
        sha256=report.sha256,
        md5=report.md5,
        payload_size=len(payload),
        payload_remaining=PAYLOAD_CAPACITY - len(payload),
        simulation_sequences=int(simulation["exhaustive_sequences"]),
    )
