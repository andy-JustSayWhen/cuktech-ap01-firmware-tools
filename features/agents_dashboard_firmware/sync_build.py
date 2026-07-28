"""构建带四页真实数据后台同步的 AP01 实验固件。"""

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
from typing import Callable
from zoneinfo import ZoneInfo

from core.firmware_image import (
    AP01_1_0_2_0031,
    ByteRange,
    refresh_recovery_crc,
    validate_candidate,
)
from features.agents_dashboard.result_package import DeviceCredentials
from features.firmware_payload_space import (
    GIF_DATA_OFFSET,
    GIF_SIZE_OFFSET,
    OPTIMIZED_SIZE,
    ORIGINAL_SHA256,
    ORIGINAL_SIZE,
    PAYLOAD_CAPACITY,
    PAYLOAD_START,
    inspect_payload_space,
)

from .build import (
    FONT_DIRECTORY,
    HOOK_OFFSET,
    HOOK_ORIGINAL,
    KEY_CALLBACK_HIGH_OFFSET,
    KEY_CALLBACK_HIGH_ORIGINAL,
    KEY_CALLBACK_LOW_OFFSET,
    KEY_CALLBACK_LOW_ORIGINAL,
    PAYLOAD_VA,
    SOURCE,
    STAGE_SHA256,
    STAGE_SIZE,
    TRAMPOLINE_OFFSET,
    TRAMPOLINE_ORIGINAL,
    AgentsDashboardFirmwareError,
    _absolute_lui_addi,
    _absolute_tail_jump,
    _encode_jal,
    _read_stage,
    _run,
    _symbols,
    _tool,
    _version,
    _write_asset_assembly,
    _write_frozen,
    _write_report,
)
from .fallback_assets import FallbackAssetError, build_fallback_assets


MODULE_DIR = Path(__file__).resolve().parent
LOADER_SOURCE = MODULE_DIR / "result_loader.c"
LOADER_LINKER = MODULE_DIR / "result_loader.ld"
SYNC_OUTPUT_FILENAME = "ap01-1.0.2_0031-agents-sync-experimental.bin"
DETAIL_COMPAT_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-detail-compat-observation.bin"
)
CONFIRM_COMPAT_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-confirm-compat-observation.bin"
)
PET_OVERLAY_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-pet-overlay-observation.bin"
)
STOCK_PET_REUSE_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-stock-pet-reuse-observation.bin"
)
XIP_DELTA = 0x9FFFF000
LOADER_TRAMPOLINE_OFFSET = 0x01C0B4
LOADER_TRAMPOLINE_VA = XIP_DELTA + LOADER_TRAMPOLINE_OFFSET
LOADER_TRAMPOLINE_ORIGINAL = b"\x00" * 8
UI_CALLBACK_LUI = 0x0B37E4
UI_CALLBACK_ADDI = 0x0B37EE
SINK_CALLBACK_LUI = 0x0B7D92
SINK_CALLBACK_ADDI = 0x0B7D96
HTTP_PERFORM_CALL = 0x0B82C0
SUCCESS_TIMER_LUI = 0x0B7F86
SUCCESS_TIMER_ADDI = 0x0B7F8A
SUCCESS_TIMER_REM = 0x0B7F8E
SUCCESS_TIMER_BASE_ADDI = 0x0B7F92
SUCCESS_TIMER_ADD = 0x0B7FB0
FAILURE_BACKOFF_STORE = 0x0B7D5A
EXPECTED_GCC_VERSION = "16.1.0"
URL_REGIONS = (
    (0x1EE968, 40, b"https://iot.cuktech.net/api/weather2?\0", "位置天气地址"),
    (
        0x1EE990,
        44,
        b"%slocid=%s&mac=%s&timestamp=%lld&token=%s\0",
        "位置天气格式",
    ),
    (0x1EEA00, 40, b"https://iot.cuktech.net/api/weather?\0", "城市天气地址"),
    (
        0x1EEA28,
        48,
        b"%scity=%s&adm=%s&mac=%s&timestamp=%lld&token=%s\0",
        "城市天气格式",
    ),
)
INSTRUCTION_EXPECTED = {
    UI_CALLBACK_LUI: bytes.fromhex("37b50ba0"),
    UI_CALLBACK_ADDI: bytes.fromhex("1305a55d"),
    SINK_CALLBACK_LUI: bytes.fromhex("b7670ba0"),
    SINK_CALLBACK_ADDI: bytes.fromhex("9387672d"),
    HTTP_PERFORM_CALL: bytes.fromhex("ef10a23f"),
    SUCCESS_TIMER_LUI: bytes.fromhex("b7f73600"),
    SUCCESS_TIMER_ADDI: bytes.fromhex("138917e8"),
    SUCCESS_TIMER_REM: bytes.fromhex("33692503"),
    SUCCESS_TIMER_BASE_ADDI: bytes.fromhex("938707e8"),
    SUCCESS_TIMER_ADD: bytes.fromhex("3e99"),
    FAILURE_BACKOFF_STORE: bytes.fromhex("23a6f9cc"),
}
REQUIRED_SYMBOLS = (
    "ap01_agents_page_register",
    "ap01_agents_key_event",
    "ap01_agents_sink",
    "ap01_agents_webclient_wrapper",
    "ap01_agents_apply_current",
    "ap01_agents_ui_timer_wrapper",
    "agents_device_id",
    "agents_secret_key",
)
LEGACY_REQUIRED_CALLEES = (
    0xA00BB5DA,
    0xA00C5D84,
    0xA00C5FE4,
    0xA00CF8D8,
    0xA00D86BA,
    0xA003F448,
    0xA0026788,
    0xA003F5F4,
    0xA0027D94,
    0xA007E1C4,
    0xA007C256,
)
STOCK_PET_REQUIRED_CALLEES = (
    0xA00BB5DA,
    0xA00C5D84,
    0xA00CF8D8,
    0xA00D86BA,
    0xA003F448,
    0xA0026788,
    0xA003F5F4,
    0xA0027D94,
)
STOCK_PET_FORBIDDEN_CALLEES = (
    0xA00C1EC6,
    0xA01930FE,
    0xA00BEBEE,
    0xA007E1C4,
    0xA007C256,
)
STOCK_PET_REQUIRED_SYMBOLS = (
    "ap01_agents_find_pet_state",
    "ap01_agents_show_page",
    "ap01_agents_restore_pet",
    "ap01_agents_detail_active",
)


@dataclass(frozen=True)
class SyncPayloadResult:
    binary: Path
    elf: Path
    size: int
    sha256: str
    symbols: dict[str, int]
    optimized_source: Path
    payload_space_report: Path
    maximum_static_stack: int
    stack_usage_report: Path


@dataclass(frozen=True)
class SyncFirmwareResult:
    output: Path
    manifest: Path
    sha256: str
    md5: str
    payload_size: int
    payload_remaining: int


def _gcc_version(tool: Path) -> str:
    try:
        completed = subprocess.run(
            [str(tool), "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AgentsDashboardFirmwareError("无法读取设备端编译器版本") from error
    first = completed.stdout.splitlines()[0] if completed.stdout else ""
    if EXPECTED_GCC_VERSION not in first:
        raise AgentsDashboardFirmwareError(
            f"设备端编译器版本不匹配：预期 {EXPECTED_GCC_VERSION}，实际 {first}"
        )
    return first


def _config_assembly(path: Path, credentials: DeviceCredentials) -> None:
    device = credentials.device_id.encode("ascii").ljust(16, b"\0")
    lines = [
        '    .section .rodata, "a", @progbits',
        "    .balign 4",
        "    .global agents_device_id",
        "agents_device_id:",
        "    .byte " + ",".join(f"0x{value:02x}" for value in device),
        "    .global agents_secret_key",
        "agents_secret_key:",
        "    .byte "
        + ",".join(f"0x{value:02x}" for value in credentials.secret_key),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _replace_fixed_region(
    firmware: bytearray,
    offset: int,
    capacity: int,
    expected: bytes,
    replacement: bytes,
    label: str,
) -> ByteRange:
    if len(expected) > capacity or len(replacement) + 1 > capacity:
        raise AgentsDashboardFirmwareError(f"{label} 超出固定区域")
    actual = bytes(firmware[offset : offset + len(expected)])
    if actual != expected:
        raise AgentsDashboardFirmwareError(f"{label} 修改前旧字节不匹配")
    firmware[offset : offset + capacity] = replacement + b"\0" * (
        capacity - len(replacement)
    )
    return ByteRange(offset, offset + capacity)


def _replace(
    firmware: bytearray,
    offset: int,
    expected: bytes,
    replacement: bytes,
    label: str,
) -> ByteRange:
    if len(expected) != len(replacement):
        raise AgentsDashboardFirmwareError(f"{label} 修改前后长度不一致")
    end = offset + len(expected)
    if bytes(firmware[offset:end]) != expected:
        raise AgentsDashboardFirmwareError(f"{label} 修改前旧字节不匹配")
    firmware[offset:end] = replacement
    return ByteRange(offset, end)


def _request_formats(credentials: DeviceCredentials) -> tuple[bytes, bytes]:
    compact_device = credentials.device_id[-4:]
    compact_token = credentials.access_token[-12:]
    location = (
        f"%s%.0s%.0s?d={compact_device}&t={compact_token}&n=%lld"
    ).encode("ascii")
    city = (
        f"%s%.0s%.0s%.0s?d={compact_device}&t={compact_token}&n=%lld"
    ).encode("ascii")
    if len(location) + 1 > 44 or len(city) + 1 > 48:
        raise AgentsDashboardFirmwareError("设备授权请求格式超过原厂固定区域")
    return location, city


def _symbol_block(disassembly: str, start: str, end: str) -> str:
    marker = f"<{start}>:"
    end_marker = f"<{end}>:"
    if marker not in disassembly or end_marker not in disassembly:
        raise AgentsDashboardFirmwareError(f"静态反汇编缺少函数：{start}")
    return disassembly.split(marker, 1)[1].split(end_marker, 1)[0]


def _validate_pet_overlay_disassembly(disassembly: str) -> None:
    page_register = _symbol_block(
        disassembly,
        "ap01_agents_page_register",
        "ap01_agents_delete_event",
    )
    create_marker = "# a00c1ec6 <lv_obj_create>"
    create_offsets = [
        offset
        for offset in range(len(page_register))
        if page_register.startswith(create_marker, offset)
    ]
    malloc_offset = page_register.find("# a007e1c4 <malloc>")
    pet_lookup_offset = page_register.find("# a00c5d84 <lv_obj_get_child>")
    if (
        len(create_offsets) != 2
        or pet_lookup_offset < 0
        or malloc_offset < 0
        or not pet_lookup_offset < create_offsets[0] < malloc_offset < create_offsets[1]
        or "x11,7" not in page_register
        or "x10,x0,32" not in page_register
    ):
        raise AgentsDashboardFirmwareError(
            "AGENTS 覆盖层父对象、状态大小或原厂详情创建顺序未通过"
        )

    find_state = _symbol_block(
        disassembly,
        "ap01_agents_find_state",
        "ap01_agents_key_event",
    )
    if (
        "x11,7" not in find_state
        or "# a00c5fe4 <lv_obj_get_child_count>" not in find_state
        or "28(x5)" not in find_state
    ):
        raise AgentsDashboardFirmwareError("AGENTS 覆盖层查找边界未通过")

    key_event = _symbol_block(
        disassembly,
        "ap01_agents_key_event",
        "ap01_agents_detail_active",
    )
    if (
        "52(x9)" in key_event
        or "<ap01_agents_find_state>" not in key_event
        or key_event.count("# a00bf942 <lv_obj_set_x>") < 5
        or "# a00bbfee <stock_key_event>" not in key_event
    ):
        raise AgentsDashboardFirmwareError("AGENTS 虚拟导航或原厂事件透传未通过")

    timer_wrapper = _symbol_block(
        disassembly,
        "ap01_agents_ui_timer_wrapper",
        "agents_device_id",
    )
    if (
        "x11,7" not in timer_wrapper
        or "# a00c5fe4 <lv_obj_get_child_count>" not in timer_wrapper
        or "<ap01_agents_apply_current>" not in timer_wrapper
    ):
        raise AgentsDashboardFirmwareError("AGENTS 覆盖层刷新对象检查未通过")


def _validate_stock_pet_reuse_disassembly(disassembly: str) -> None:
    lowered = disassembly.lower()
    for address in STOCK_PET_FORBIDDEN_CALLEES:
        if f"# {address:08x} <" in lowered:
            raise AgentsDashboardFirmwareError(
                f"原厂萌宠复用载荷调用了禁止函数：0x{address:08x}"
            )

    page_register = _symbol_block(
        disassembly,
        "ap01_agents_page_register",
        "ap01_agents_find_pet_state",
    )
    page_instructions = [
        line
        for line in page_register.splitlines()
        if re.match(r"^\s*[0-9a-f]+:\s", line)
    ]
    if (
        not 1 <= len(page_instructions) <= 2
        or not (
            "c.jr" in page_instructions[0]
            and "x1" in page_instructions[0]
            or "jalr" in page_instructions[0]
            and "x0,0(x1)" in page_instructions[0]
        )
        or any("c.addi" not in line or "x0,0" not in line
               for line in page_instructions[1:])
    ):
        raise AgentsDashboardFirmwareError("页面注册入口不是单指令空返回")

    find_state = _symbol_block(
        disassembly,
        "ap01_agents_find_pet_state",
        "ap01_agents_key_event",
    )
    if (
        "x11,7" not in find_state
        or "# a00c5d84 <lv_obj_get_child>" not in find_state
        or "16(x10)" not in find_state
        or "0(x5)" not in find_state
        or "4(x5)" not in find_state
        or "x7,10" not in find_state
    ):
        raise AgentsDashboardFirmwareError("原厂萌宠状态对象链检查未通过")

    key_event = _symbol_block(
        disassembly,
        "ap01_agents_key_event",
        "ap01_agents_show_page",
    )
    first_state_read = key_event.find("<ap01_agents_find_pet_state>")
    guard = re.search(
        r"(?:c\.li|addi)\s+x6(?:,x0)?,7"
        r".*?bne\s+x10,x6,([0-9a-f]+)",
        key_event[:first_state_read],
        re.DOTALL,
    )
    if (
        first_state_read < 0
        or "<window_get_active>" not in key_event[:first_state_read]
        or guard is None
        or "52(x9)" in key_event
        or "52(x18)" in key_event
        or re.search(r"\bsw\s+x\d+,12\(x18\)", key_event) is not None
        or key_event.count("<ap01_agents_restore_pet>") != 2
        or "# a00bbfee <stock_key_event>" not in key_event
    ):
        raise AgentsDashboardFirmwareError(
            "原厂确认透传、离开恢复或虚拟状态写入检查未通过"
        )
    stock_target = guard.group(1)
    stock_marker = re.search(
        rf"^\s*{re.escape(stock_target)}:\s",
        key_event,
        re.MULTILINE,
    )
    if stock_marker is None:
        raise AgentsDashboardFirmwareError("非萌宠确认透传目标不存在")
    stock_block = key_event[stock_marker.start() :]
    if (
        "# a00bbfee <stock_key_event>" not in stock_block
        or "<ap01_agents_find_pet_state>" in stock_block
    ):
        raise AgentsDashboardFirmwareError("非萌宠确认未直接透传原厂回调")

    show_page = _symbol_block(
        disassembly,
        "ap01_agents_show_page",
        "ap01_agents_restore_pet",
    )
    restore_pet = _symbol_block(
        disassembly,
        "ap01_agents_restore_pet",
        "ap01_agents_detail_active",
    )
    if (
        len(re.findall(r"\bsw\s+x\d+,12\(x8\)", show_page)) != 1
        or "1fffffff" not in show_page
        or "# a00cf8d8 <lv_gif_set_src>" not in show_page
        or len(re.findall(r"\bsw\s+x\d+,12\(x8\)", restore_pet)) != 1
        or "1fffffff" not in restore_pet
        or "a01f7090" not in restore_pet.lower()
        or "# a00cf8d8 <lv_gif_set_src>" not in restore_pet
    ):
        raise AgentsDashboardFirmwareError(
            "高三位虚拟状态或原厂萌宠数据源恢复检查未通过"
        )

    timer_wrapper = _symbol_block(
        disassembly,
        "ap01_agents_ui_timer_wrapper",
        "agents_device_id",
    )
    if (
        "x11,7" not in timer_wrapper
        or "16(" not in timer_wrapper
        or "4(" not in timer_wrapper
        or "<ap01_agents_apply_current>" not in timer_wrapper
        or "# a00c5fe4 <lv_obj_get_child_count>" in timer_wrapper
    ):
        raise AgentsDashboardFirmwareError("后台刷新原厂萌宠对象链检查未通过")


def build_sync_payload(
    stage_path: Path,
    build_directory: Path,
    credentials: DeviceCredentials,
    *,
    tool_revision: dict[str, object],
    extra_objects: tuple[Path, ...] = (),
    required_extra_symbols: tuple[str, ...] = (),
    reuse_stock_pet: bool = False,
) -> SyncPayloadResult:
    stage_selected, stage = _read_stage(stage_path)
    if len(stage) != STAGE_SIZE or hashlib.sha256(stage).hexdigest() != STAGE_SHA256:
        raise AgentsDashboardFirmwareError("已验收设置菜单阶段成品身份不匹配")
    selected = build_directory.expanduser().resolve()
    selected.mkdir(parents=True, exist_ok=True)
    optimized_source = selected / "optimized-source.gif"
    payload_space_report = selected / "payload-space-report.json"
    inspect_payload_space(
        stage_selected,
        optimized_source,
        payload_space_report,
        tool_revision=tool_revision,
    )
    try:
        assets = build_fallback_assets(
            FONT_DIRECTORY,
            selected / "fallback-assets",
        )
    except FallbackAssetError as error:
        raise AgentsDashboardFirmwareError(str(error)) from error

    assembler = _tool("riscv64-elf-as")
    linker = _tool("riscv64-elf-ld")
    gcc = _tool("riscv64-elf-gcc")
    copier = _tool("riscv64-elf-objcopy")
    dumper = _tool("riscv64-elf-objdump")
    nm = _tool("riscv64-elf-nm")
    readelf = _tool("riscv64-elf-readelf")
    _version(assembler)
    _version(linker)
    _version(copier)
    _version(dumper)
    _version(nm)
    _version(readelf)
    _gcc_version(gcc)

    page_object = selected / "page-registration.o"
    loader_object = selected / "result-loader.o"
    assets_source = selected / "fallback-assets.S"
    assets_object = selected / "fallback-assets.o"
    config_source = selected / "device-config.S"
    config_object = selected / "device-config.o"
    elf = selected / "agents-sync.elf"
    binary = selected / "agents-sync.bin"
    map_path = selected / "agents-sync.map"
    disassembly_path = selected / "agents-sync.disassembly.txt"
    readelf_path = selected / "agents-sync.readelf.txt"
    _write_asset_assembly(assets_source, assets)
    _config_assembly(config_source, credentials)

    resolved_extra_objects: list[Path] = []
    for item in extra_objects:
        resolved = item.expanduser().resolve(strict=True)
        if not resolved.is_file():
            raise AgentsDashboardFirmwareError(f"组合目标文件无效：{resolved}")
        resolved_extra_objects.append(resolved)

    assembler_arguments = [
        assembler,
        "-march=rv32imac",
        "-mabi=ilp32",
        "--defsym",
        "SYNC_LOADER=1",
    ]
    if reuse_stock_pet:
        assembler_arguments.extend(["--defsym", "STOCK_PET_REUSE=1"])
    assembler_arguments.extend(["-o", page_object, SOURCE])
    _run(assembler_arguments)
    _run(
        [
            gcc,
            "-march=rv32imac",
            "-mabi=ilp32",
            "-Os",
            "-ffreestanding",
            "-fno-builtin",
            "-fno-pic",
            "-fno-pie",
            "-fno-plt",
            "-fno-stack-protector",
            "-fno-asynchronous-unwind-tables",
            "-fno-unwind-tables",
            "-fno-jump-tables",
            "-fno-common",
            "-fno-toplevel-reorder",
            "-fno-tree-loop-distribute-patterns",
            "-fstack-usage",
            "-msmall-data-limit=0",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-c",
            LOADER_SOURCE,
            "-o",
            loader_object,
        ]
    )
    _run(
        [
            assembler,
            "-march=rv32imac",
            "-mabi=ilp32",
            "-o",
            assets_object,
            assets_source,
        ]
    )
    _run(
        [
            assembler,
            "-march=rv32imac",
            "-mabi=ilp32",
            "-o",
            config_object,
            config_source,
        ]
    )
    _run(
        [
            linker,
            "-m",
            "elf32lriscv",
            "--no-relax",
            f"-Map={map_path}",
            "-T",
            LOADER_LINKER,
            "-o",
            elf,
            page_object,
            loader_object,
            config_object,
            *resolved_extra_objects,
            assets_object,
        ]
    )
    _run([copier, "-O", "binary", "-j", ".payload", elf, binary])
    payload = binary.read_bytes()
    if not payload or len(payload) > PAYLOAD_CAPACITY:
        raise AgentsDashboardFirmwareError("同步载荷为空或超过固定候选空间")
    symbols = _symbols(nm, elf)
    selected_required_symbols = REQUIRED_SYMBOLS + required_extra_symbols
    if reuse_stock_pet:
        selected_required_symbols += STOCK_PET_REQUIRED_SYMBOLS
    for name in selected_required_symbols:
        address = symbols.get(name)
        if address is None or not PAYLOAD_VA <= address < PAYLOAD_VA + len(payload):
            raise AgentsDashboardFirmwareError(f"同步载荷符号缺失或越界：{name}")
    if symbols["ap01_agents_page_register"] != PAYLOAD_VA:
        raise AgentsDashboardFirmwareError("页面注册入口不在固定载荷起点")

    disassembly = _run(
        [dumper, "-d", "-M", "no-aliases,numeric", elf],
        capture=True,
    )
    required_callees = (
        STOCK_PET_REQUIRED_CALLEES
        if reuse_stock_pet
        else LEGACY_REQUIRED_CALLEES
    )
    for address in required_callees:
        if f"{address:08x}" not in disassembly.lower():
            raise AgentsDashboardFirmwareError(
                f"同步载荷缺少已定位原厂调用：0x{address:08x}"
            )
    if reuse_stock_pet:
        _validate_stock_pet_reuse_disassembly(disassembly)
    else:
        _validate_pet_overlay_disassembly(disassembly)
    disassembly_path.write_text(disassembly, encoding="utf-8")
    readelf_output = _run(
        [readelf, "-h", "-S", "-s", "-r", elf],
        capture=True,
    )
    if "There are no relocations in this file." not in readelf_output:
        raise AgentsDashboardFirmwareError("同步载荷仍含未处理重定位")
    readelf_path.write_text(readelf_output, encoding="utf-8")
    stack_usage_path = loader_object.with_suffix(".su")
    try:
        stack_lines = stack_usage_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise AgentsDashboardFirmwareError("缺少设备端静态栈用量报告") from error
    stack_values: list[int] = []
    for line in stack_lines:
        parts = line.split("\t")
        if len(parts) != 3 or parts[2] != "static":
            raise AgentsDashboardFirmwareError("设备端存在无法固定的动态栈用量")
        try:
            stack_values.append(int(parts[1]))
        except ValueError as error:
            raise AgentsDashboardFirmwareError("设备端静态栈报告格式错误") from error
    maximum_static_stack = max(stack_values, default=0)
    if maximum_static_stack > 768:
        raise AgentsDashboardFirmwareError("设备端单函数静态栈超过 768 字节")
    return SyncPayloadResult(
        binary=binary,
        elf=elf,
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        symbols=symbols,
        optimized_source=optimized_source,
        payload_space_report=payload_space_report,
        maximum_static_stack=maximum_static_stack,
        stack_usage_report=stack_usage_path,
    )


def build_sync_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    credentials: DeviceCredentials,
    *,
    url_base: str,
    refresh_seconds: int,
    tool_revision: dict[str, object],
    extra_objects: tuple[Path, ...] = (),
    required_extra_symbols: tuple[str, ...] = (),
    key_callback_symbol: str = "ap01_agents_key_event",
    candidate_mutators: tuple[
        Callable[[bytearray, dict[str, int]], list[ByteRange]], ...
    ] = (),
    expected_output_name: str = SYNC_OUTPUT_FILENAME,
    implemented_scope_extra: tuple[str, ...] = (),
    reuse_stock_pet: bool = False,
) -> SyncFirmwareResult:
    if tool_revision.get("scoped_code_dirty") is not False:
        raise AgentsDashboardFirmwareError("制作代码尚未提交，不能冻结同步实验成品")
    output = output_path.expanduser().resolve()
    if output.name != expected_output_name:
        raise AgentsDashboardFirmwareError(
            f"同步实验成品文件名必须是 {expected_output_name}"
        )
    try:
        url_bytes = url_base.encode("ascii")
    except UnicodeEncodeError as error:
        raise AgentsDashboardFirmwareError("同步服务地址必须是 ASCII") from error
    if (
        not url_base.startswith("http://")
        or not url_base.endswith("/a")
        or len(url_bytes) + 1 > 40
    ):
        raise AgentsDashboardFirmwareError(
            "同步服务地址必须是以 /a 结尾且不超过 39 字节的局域网 HTTP 地址"
        )
    if not 10 <= refresh_seconds <= 7200:
        raise AgentsDashboardFirmwareError("刷新周期必须在 10～7200 秒之间")

    stage_selected, stage = _read_stage(stage_path)
    payload_result = build_sync_payload(
        stage_selected,
        build_directory,
        credentials,
        tool_revision=tool_revision,
        extra_objects=extra_objects,
        required_extra_symbols=required_extra_symbols,
        reuse_stock_pet=reuse_stock_pet,
    )
    payload = payload_result.binary.read_bytes()
    optimized = payload_result.optimized_source.read_bytes()
    candidate = bytearray(stage)
    allowed: list[ByteRange] = []

    allowed.append(
        _replace(
            candidate,
            GIF_SIZE_OFFSET,
            struct.pack("<I", ORIGINAL_SIZE),
            struct.pack("<I", OPTIMIZED_SIZE),
            "原厂第一张动图数据长度",
        )
    )
    original_gif = bytes(
        candidate[GIF_DATA_OFFSET : GIF_DATA_OFFSET + ORIGINAL_SIZE]
    )
    if hashlib.sha256(original_gif).hexdigest() != ORIGINAL_SHA256:
        raise AgentsDashboardFirmwareError("原厂第一张动图修改前指纹不匹配")
    candidate[GIF_DATA_OFFSET : GIF_DATA_OFFSET + len(optimized)] = optimized
    allowed.append(ByteRange(GIF_DATA_OFFSET, GIF_DATA_OFFSET + len(optimized)))

    if reuse_stock_pet:
        if (
            bytes(candidate[HOOK_OFFSET : HOOK_OFFSET + len(HOOK_ORIGINAL)])
            != HOOK_ORIGINAL
            or bytes(
                candidate[
                    TRAMPOLINE_OFFSET :
                    TRAMPOLINE_OFFSET + len(TRAMPOLINE_ORIGINAL)
                ]
            )
            != TRAMPOLINE_ORIGINAL
        ):
            raise AgentsDashboardFirmwareError(
                "页面注册点或旧页面跳板不等于已验收设置固件"
            )
    else:
        page_hook = _encode_jal(
            HOOK_OFFSET + XIP_DELTA,
            TRAMPOLINE_OFFSET + XIP_DELTA,
        )
        page_hook += bytes.fromhex("0100")
        allowed.append(
            _replace(candidate, HOOK_OFFSET, HOOK_ORIGINAL, page_hook, "页面挂接")
        )
        allowed.append(
            _replace(
                candidate,
                TRAMPOLINE_OFFSET,
                TRAMPOLINE_ORIGINAL,
                _absolute_tail_jump(PAYLOAD_VA),
                "页面跳板",
            )
        )
    key_event = payload_result.symbols.get(key_callback_symbol)
    if key_event is None:
        raise AgentsDashboardFirmwareError(
            f"一级键值组合入口缺失：{key_callback_symbol}"
        )
    key_high, key_low = _absolute_lui_addi(key_event, register=11)
    allowed.append(
        _replace(
            candidate,
            KEY_CALLBACK_HIGH_OFFSET,
            KEY_CALLBACK_HIGH_ORIGINAL,
            key_high,
            "一级键值回调地址高位",
        )
    )

    for mutate in candidate_mutators:
        allowed.extend(mutate(candidate, payload_result.symbols))
    allowed.append(
        _replace(
            candidate,
            KEY_CALLBACK_LOW_OFFSET,
            KEY_CALLBACK_LOW_ORIGINAL,
            key_low,
            "一级键值回调地址低位",
        )
    )

    if (
        bytes(
            candidate[
                LOADER_TRAMPOLINE_OFFSET :
                LOADER_TRAMPOLINE_OFFSET + len(LOADER_TRAMPOLINE_ORIGINAL)
            ]
        )
        != LOADER_TRAMPOLINE_ORIGINAL
    ):
        raise AgentsDashboardFirmwareError("后台同步跳板区间不再是全零")
    web_wrapper = payload_result.symbols["ap01_agents_webclient_wrapper"]
    allowed.append(
        _replace(
            candidate,
            LOADER_TRAMPOLINE_OFFSET,
            LOADER_TRAMPOLINE_ORIGINAL,
            _absolute_tail_jump(web_wrapper),
            "后台同步跳板",
        )
    )
    sink = payload_result.symbols["ap01_agents_sink"]
    ui_timer = payload_result.symbols["ap01_agents_ui_timer_wrapper"]
    sink_high, sink_low = _absolute_lui_addi(sink, register=15)
    ui_high, ui_low = _absolute_lui_addi(ui_timer, register=10)
    allowed.append(
        _replace(
            candidate,
            SINK_CALLBACK_LUI,
            INSTRUCTION_EXPECTED[SINK_CALLBACK_LUI],
            sink_high,
            "下载回调地址高位",
        )
    )
    allowed.append(
        _replace(
            candidate,
            SINK_CALLBACK_ADDI,
            INSTRUCTION_EXPECTED[SINK_CALLBACK_ADDI],
            sink_low,
            "下载回调地址低位",
        )
    )
    allowed.append(
        _replace(
            candidate,
            UI_CALLBACK_LUI,
            INSTRUCTION_EXPECTED[UI_CALLBACK_LUI],
            ui_high,
            "界面定时回调地址高位",
        )
    )
    allowed.append(
        _replace(
            candidate,
            UI_CALLBACK_ADDI,
            INSTRUCTION_EXPECTED[UI_CALLBACK_ADDI],
            ui_low,
            "界面定时回调地址低位",
        )
    )
    allowed.append(
        _replace(
            candidate,
            HTTP_PERFORM_CALL,
            INSTRUCTION_EXPECTED[HTTP_PERFORM_CALL],
            _encode_jal(
                XIP_DELTA + HTTP_PERFORM_CALL,
                LOADER_TRAMPOLINE_VA,
            ),
            "后台网络调用",
        )
    )

    refresh_ms = refresh_seconds * 1000
    timer_high, timer_low = _absolute_lui_addi(refresh_ms, register=18)
    for offset, replacement, label in (
        (SUCCESS_TIMER_LUI, timer_high, "刷新周期高位"),
        (SUCCESS_TIMER_ADDI, timer_low, "刷新周期低位"),
        (SUCCESS_TIMER_REM, bytes.fromhex("13000000"), "刷新随机余数"),
        (
            SUCCESS_TIMER_BASE_ADDI,
            bytes.fromhex("13000000"),
            "刷新随机基数",
        ),
        (SUCCESS_TIMER_ADD, bytes.fromhex("0100"), "刷新随机相加"),
        (
            FAILURE_BACKOFF_STORE,
            bytes.fromhex("13000000"),
            "失败退避增长写入",
        ),
    ):
        allowed.append(
            _replace(
                candidate,
                offset,
                INSTRUCTION_EXPECTED[offset],
                replacement,
                label,
            )
        )

    location_format, city_format = _request_formats(credentials)
    replacements = (url_bytes, location_format, url_bytes, city_format)
    for (offset, capacity, expected, label), replacement in zip(
        URL_REGIONS,
        replacements,
    ):
        allowed.append(
            _replace_fixed_region(
                candidate,
                offset,
                capacity,
                expected,
                replacement,
                label,
            )
        )

    payload_before = bytes(candidate[PAYLOAD_START : PAYLOAD_START + len(payload)])
    if payload_before == payload:
        raise AgentsDashboardFirmwareError("同步载荷写入前后完全相同")
    candidate[PAYLOAD_START : PAYLOAD_START + len(payload)] = payload
    allowed.append(ByteRange(PAYLOAD_START, PAYLOAD_START + len(payload)))

    recovery_crc = refresh_recovery_crc(candidate, AP01_1_0_2_0031)
    allowed.append(
        ByteRange(
            AP01_1_0_2_0031.recovery_trailer_offset + 36,
            AP01_1_0_2_0031.recovery_trailer_offset + 40,
        )
    )
    report = validate_candidate(
        stage,
        bytes(candidate),
        allowed,
        AP01_1_0_2_0031,
    )
    manifest: dict[str, object] = {
        "schema_version": 1,
        "manifest_type": "agents-sync-experimental-firmware",
        "status": "built-not-approved-for-installation",
        "built_at_beijing": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
            timespec="seconds"
        ),
        "tool": tool_revision,
        "input": {
            "path": str(stage_selected),
            "size": len(stage),
            "sha256": hashlib.sha256(stage).hexdigest(),
            "read_only": True,
        },
        "output": {
            "path": str(output),
            "read_only": True,
            **report.to_dict(),
        },
        "device_specific": True,
        "credentials_embedded": True,
        "credentials_disclosed": False,
        "transport": {
            "url_base": url_base,
            "refresh_seconds": refresh_seconds,
            "failure_retry_seconds": 30,
            "request_device_id_suffix_length": 4,
            "request_access_token_suffix_length": 12,
        },
        "payload": {
            "file_offset": f"0x{PAYLOAD_START:06x}",
            "runtime_address": f"0x{PAYLOAD_VA:08x}",
            "size": payload_result.size,
            "sha256": payload_result.sha256,
            "capacity": PAYLOAD_CAPACITY,
            "remaining": PAYLOAD_CAPACITY - payload_result.size,
            "relocations": 0,
            "maximum_static_stack": payload_result.maximum_static_stack,
            "download_state_stack_bytes": 540,
            "download_state_heap_bytes": 0,
            "stock_pet_object_reused": reuse_stock_pet,
        },
        "implemented_scope": [
            "四页完整包流式接收",
            "四页文件指纹校验",
            "设备代号与响应授权校验",
            "三组临时槽原子提交",
            "界面线程只切换已提交页面",
            "五分钟后台刷新",
            *implemented_scope_extra,
        ],
        "pending_scope": [
            "重启后保留最后成功包",
            "页面开关关闭时停用刷新",
            "NAS 与云服务器故障切换",
        ],
        "pending_measurements": [
            "后台任务原有栈余量",
            "四页临时文件总量",
            "连续刷新内存变化",
            "网络失败恢复",
            "断电恢复",
        ],
        "allowed_ranges": [item.to_dict() for item in allowed],
        "recovery_crc_after_build": f"0x{recovery_crc:08x}",
        "validation": {
            "old_bytes_asserted": True,
            "payload_fits": True,
            "relocations_zero": True,
            "total_length_preserved": True,
            "outside_allowed_ranges_identical": True,
            "page_registration_unchanged": reuse_stock_pet,
            "installation_allowed": False,
        },
    }
    output_written = False
    try:
        _write_frozen(output, bytes(candidate))
        output_written = True
        readback_report = validate_candidate(
            stage,
            output.read_bytes(),
            allowed,
            AP01_1_0_2_0031,
        )
        if readback_report.sha256 != report.sha256:
            raise AgentsDashboardFirmwareError("同步实验成品回读指纹不一致")
        _write_report(manifest_path, manifest)
        manifest_path.expanduser().resolve().chmod(0o444)
    except Exception:
        if output_written and output.exists():
            output.chmod(0o644)
            output.unlink()
        raise
    return SyncFirmwareResult(
        output=output,
        manifest=manifest_path.expanduser().resolve(),
        sha256=report.sha256,
        md5=report.md5,
        payload_size=payload_result.size,
        payload_remaining=PAYLOAD_CAPACITY - payload_result.size,
    )
