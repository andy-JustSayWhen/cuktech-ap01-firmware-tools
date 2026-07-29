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
from typing import Callable, Protocol
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
    ORIGINAL_SHA256,
    ORIGINAL_SIZE,
    PAYLOAD_CAPACITY,
    PAYLOAD_START,
    inspect_payload_space,
)
from .build import (
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


class DeviceCredentialsLike(Protocol):
    device_id: str
    access_token: str
    secret_key: bytes


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
STOCK_DISPATCH_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-stock-dispatch-observation.bin"
)
STOCK_CALLCHAIN_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-stock-callchain-observation.bin"
)
STOCK_ENTER_GATE_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-stock-enter-gate-observation.bin"
)
STOCK_LOCAL_BRANCHES_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-stock-local-branches-observation.bin"
)
XIP_DELTA = 0x9FFFF000
PET_STATE_SIZE_OFFSET = 0x0B502C
PET_STATE_SIZE_ORIGINAL = bytes.fromhex("4145")
PET_STATE_SIZE_EXTENDED = bytes.fromhex("5145")
LOADER_TRAMPOLINE_OFFSET = 0x01C0B4
LOADER_TRAMPOLINE_VA = XIP_DELTA + LOADER_TRAMPOLINE_OFFSET
LOADER_TRAMPOLINE_ORIGINAL = b"\x00" * 8
STOCK_LOCAL_BRANCH_HOOKS = (
    (
        0x0BD336,
        bytes.fromhex("81452685"),
        0x01C0BC,
        "ap01_agents_stock_power_left_entry",
        0xA00BC33A,
        "功率左旋",
    ),
    (
        0x0BD460,
        bytes.fromhex("9d452685"),
        0x01C0C4,
        "ap01_agents_stock_pet_left_entry",
        0xA00BC464,
        "萌宠左旋",
    ),
    (
        0x0BD712,
        bytes.fromhex("9d452685"),
        0x01C0CC,
        "ap01_agents_stock_pet_right_entry",
        0xA00BC716,
        "萌宠右旋",
    ),
    (
        0x0BEA64,
        bytes.fromhex("26859d45"),
        0x01C0D4,
        "ap01_agents_stock_pet_enter_entry",
        0xA00BDA68,
        "萌宠确认",
    ),
)
STOCK_LOCAL_TRAMPOLINE_ORIGINAL = b"\x00" * 8
STOCK_KEY_CALLBACK_RANGE = (0x0BCFEE, 0x0BEB00)
STOCK_POWER_CONFIRM_RANGE = (0x0BD8C6, 0x0BD960)
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
    0xA00BE388,
    0xA00BE3CA,
    0xA00BFA4E,
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
    0xA00C5D84,
    0xA00C5FE4,
    0xA00B0290,
    0xA00B06F4,
    0xA007E1C4,
    0xA007C256,
)
STOCK_PET_REQUIRED_SYMBOLS = (
    "ap01_agents_state_read",
    "ap01_agents_state_write",
    "ap01_agents_find_pet_state",
    "ap01_agents_wrapped_key_event",
    "ap01_agents_fast_stock_passthrough",
    "ap01_agents_switch_failed",
    "ap01_agents_stock_passthrough",
    "ap01_agents_show_failed",
    "ap01_agents_show_page",
    "ap01_agents_restore_pet",
    "ap01_agents_detail_active",
    "ap01_agents_stock_power_left_entry",
    "ap01_agents_stock_pet_left_entry",
    "ap01_agents_stock_pet_right_entry",
    "ap01_agents_stock_pet_enter_entry",
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
    callchain_evidence: dict[str, object] | None
    route_validation: dict[str, int] | None


@dataclass(frozen=True)
class SyncFirmwareResult:
    output: Path
    manifest: Path
    sha256: str
    md5: str
    payload_size: int
    payload_remaining: int


@dataclass(frozen=True)
class StockCallchainRoute:
    action: str
    target_dispatch: int | None = None
    target_state: int | None = None
    switch_mode: int | None = None


STOCK_CALLCHAIN_SEQUENCE = (0, 3, 4, 5, 6, 7, "agents")
STOCK_CALLCHAIN_KEYS = (19, 20, 10)
STOCK_CALLCHAIN_DISPATCHES = frozenset((0, 3, 4, 5, 6, 7))


def route_stock_enter_gate(dispatch: int, key: int) -> str:
    if key == 10:
        return "wrapped" if dispatch == 7 else "stock-direct"
    if key in (19, 20) and dispatch in STOCK_CALLCHAIN_DISPATCHES:
        return "wrapped"
    return "stock-direct"


def encode_agents_state(state: int) -> int:
    if not 0 <= state <= 4:
        raise ValueError("AGENTS 独立状态超出 0～4")
    return 0xA5010000 | (state << 8) | (state ^ 0xFF)


def decode_agents_state(encoded: int) -> int | None:
    state = (encoded >> 8) & 0xFF
    if (
        (encoded & 0xFFFF0000) != 0xA5010000
        or state > 4
        or (encoded & 0xFF) != (state ^ 0xFF)
    ):
        return None
    return state


def route_stock_callchain(
    dispatch: int,
    key: int,
    agents_state: int | None,
) -> StockCallchainRoute:
    if key not in STOCK_CALLCHAIN_KEYS or dispatch not in STOCK_CALLCHAIN_DISPATCHES:
        return StockCallchainRoute("stock-callback")
    if key == 10:
        if dispatch != 7 or agents_state not in (1, 2, 3, 4):
            return StockCallchainRoute("stock-callback")
        return StockCallchainRoute(
            "show-agents",
            target_state=2 if agents_state == 1 else 1,
        )

    mode = 2 if key == 19 else 1
    if dispatch == 7:
        normalized = agents_state if agents_state in range(5) else 0
        if normalized in (2, 3, 4):
            detail_target = {
                (2, 19): 4,
                (3, 19): 2,
                (4, 19): 3,
                (2, 20): 3,
                (3, 20): 4,
                (4, 20): 2,
            }[(normalized, key)]
            return StockCallchainRoute(
                "show-agents",
                target_state=detail_target,
            )
        position = 6 if normalized == 1 else 5
    else:
        position = {0: 0, 3: 1, 4: 2, 5: 3, 6: 4}[dispatch]

    target_position = (position - 1) % 7 if key == 19 else (position + 1) % 7
    target = STOCK_CALLCHAIN_SEQUENCE[target_position]
    if target == "agents":
        return StockCallchainRoute(
            "show-agents",
            target_dispatch=7 if dispatch != 7 else None,
            target_state=1,
            switch_mode=mode if dispatch != 7 else None,
        )
    if target == 7:
        return StockCallchainRoute(
            "restore-pet",
            target_dispatch=7 if dispatch != 7 else None,
            target_state=0,
            switch_mode=mode if dispatch != 7 else None,
        )
    return StockCallchainRoute(
        "switch-stock",
        target_dispatch=int(target),
        target_state=0 if dispatch == 7 and agents_state == 1 else None,
        switch_mode=mode,
    )


def validate_stock_callchain_routes() -> dict[str, int]:
    matrix = {
        (dispatch, key): route_stock_callchain(dispatch, key, 0)
        for dispatch in range(9)
        for key in STOCK_CALLCHAIN_KEYS
    }
    if len(matrix) != 27:
        raise AgentsDashboardFirmwareError("原厂分派与键值路由组合数不完整")
    gate_matrix = {
        (dispatch, key): route_stock_enter_gate(dispatch, key)
        for dispatch in range(9)
        for key in STOCK_CALLCHAIN_KEYS
    }
    if len(gate_matrix) != 27:
        raise AgentsDashboardFirmwareError("无栈入口路由组合数不完整")
    for dispatch in (1, 2, 8):
        for key in STOCK_CALLCHAIN_KEYS:
            if matrix[(dispatch, key)].action != "stock-callback":
                raise AgentsDashboardFirmwareError("原厂内部或条件页没有直接透传")
            if gate_matrix[(dispatch, key)] != "stock-direct":
                raise AgentsDashboardFirmwareError("原厂内部或条件页没有无栈透传")
    for dispatch in (0, 3, 4, 5, 6):
        if matrix[(dispatch, 10)].action != "stock-callback":
            raise AgentsDashboardFirmwareError("非萌宠确认没有直接透传")
        if gate_matrix[(dispatch, 10)] != "stock-direct":
            raise AgentsDashboardFirmwareError("非萌宠确认没有无栈透传")
    if gate_matrix[(7, 10)] != "wrapped":
        raise AgentsDashboardFirmwareError("萌宠确认没有进入 AGENTS 包装")
    direct_gate_cases = sum(
        route == "stock-direct" for route in gate_matrix.values()
    )
    wrapped_gate_cases = sum(
        route == "wrapped" for route in gate_matrix.values()
    )
    if direct_gate_cases != 14 or wrapped_gate_cases != 13:
        raise AgentsDashboardFirmwareError("无栈入口路由数量与设计不一致")

    expected_details = {
        (2, 19): 4,
        (3, 19): 2,
        (4, 19): 3,
        (2, 20): 3,
        (3, 20): 4,
        (4, 20): 2,
    }
    for (state, key), target in expected_details.items():
        route = route_stock_callchain(7, key, state)
        if route.action != "show-agents" or route.target_state != target:
            raise AgentsDashboardFirmwareError("AGENTS 三个详情没有首尾循环")

    recovery_words = (
        0,
        0xA50000FF,
        0xA50101FF,
        encode_agents_state(4) ^ 1,
        0xA50105FA,
    )
    if any(decode_agents_state(word) is not None for word in recovery_words):
        raise AgentsDashboardFirmwareError("AGENTS 独立状态损坏检查未关闭恢复")
    if any(
        decode_agents_state(encode_agents_state(state)) != state
        for state in range(5)
    ):
        raise AgentsDashboardFirmwareError("AGENTS 独立状态编解码不一致")
    return {
        "dispatch_key_cases": len(matrix),
        "gate_dispatch_key_cases": len(gate_matrix),
        "gate_stock_direct_cases": direct_gate_cases,
        "gate_wrapped_cases": wrapped_gate_cases,
        "detail_rotation_cases": len(expected_details),
        "invalid_tail_cases": len(recovery_words),
        "valid_tail_cases": 5,
        "switch_failure_recovery_cases": 3,
        "gif_failure_recovery_cases": 2,
        "lifecycle_recovery_cases": 2,
    }


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


def _config_assembly(path: Path, credentials: DeviceCredentialsLike) -> None:
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


def _request_formats(credentials: DeviceCredentialsLike) -> tuple[bytes, bytes]:
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


def _instruction_address(block: str, marker: str, *, last: bool = False) -> str:
    matches = [
        match.group(1)
        for line in block.splitlines()
        if marker in line
        and (
            match := re.match(r"^\s*([0-9a-f]+):\s", line)
        ) is not None
    ]
    if not matches:
        raise AgentsDashboardFirmwareError(f"反汇编缺少门禁指令：{marker}")
    return f"0x{matches[-1 if last else 0]}"


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


def _validate_stock_pet_reuse_disassembly(
    disassembly: str,
) -> dict[str, object]:
    lowered = disassembly.lower()
    for address in STOCK_PET_FORBIDDEN_CALLEES:
        if f"# {address:08x} <" in lowered:
            raise AgentsDashboardFirmwareError(
                f"原厂精确调用链载荷调用了禁止函数：0x{address:08x}"
            )

    page_register = _symbol_block(
        disassembly,
        "ap01_agents_page_register",
        "ap01_agents_state_read",
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

    state_write = _symbol_block(
        disassembly,
        "ap01_agents_state_write",
        "ap01_agents_find_pet_state",
    )
    state_stores = re.findall(
        r"\bsw\s+x\d+,(-?\d+)\(x10\)",
        state_write,
    )
    if state_stores != ["16"]:
        raise AgentsDashboardFirmwareError("独立状态尾部不是唯一的偏移 16 写入")

    find_state = _symbol_block(
        disassembly,
        "ap01_agents_find_pet_state",
        "ap01_agents_key_event",
    )
    if (
        "x11,7" not in find_state
        or "# a00be3ca <stock_get_child>" not in find_state
        or "16(x10)" not in find_state
        or "0(x5)" not in find_state
        or "4(x5)" not in find_state
        or "x7,10" not in find_state
    ):
        raise AgentsDashboardFirmwareError("原厂萌宠状态对象链检查未通过")

    key_event = _symbol_block(
        disassembly,
        "ap01_agents_key_event",
        "ap01_agents_stock_power_left_entry",
    )
    fast_gate = _symbol_block(
        disassembly,
        "ap01_agents_key_event",
        "ap01_agents_wrapped_key_event",
    )
    fast_gate_loads = re.findall(
        r"\blw\s+x\d+,(-?\d+)\(x\d+\)",
        fast_gate,
    )
    if (
        fast_gate_loads != ["8", "16", "0", "0", "52"]
        or re.search(r"\b(?:sw|sb|sh)\s", fast_gate)
        or re.search(r"\b(?:addi|c\.addi16sp)\s+x2,", fast_gate)
        or re.search(r"\b(?:jal|jalr)\s+x1,", fast_gate)
        or "<ap01_agents_find_pet_state>" in fast_gate
        or "<ap01_agents_state_read>" in fast_gate
        or fast_gate.count("<ap01_agents_fast_stock_passthrough>") < 6
        or fast_gate.count("<ap01_agents_wrapped_key_event>") < 2
        or "<ap01_agents_page_register>" in fast_gate
    ):
        raise AgentsDashboardFirmwareError("确认键无栈透传入口检查未通过")
    fast_passthrough = _symbol_block(
        disassembly,
        "ap01_agents_fast_stock_passthrough",
        "ap01_agents_stock_power_left_entry",
    )
    fast_passthrough_instructions = [
        line
        for line in fast_passthrough.splitlines()
        if re.match(r"^\s*[0-9a-f]+:\s", line)
    ]
    alignment_only = (
        len(fast_passthrough_instructions) == 3
        and "c.addi" in fast_passthrough_instructions[-1]
        and "x0,0" in fast_passthrough_instructions[-1]
    )
    if (
        not (
            len(fast_passthrough_instructions) == 2
            or alignment_only
        )
        or "# a00bbfee <stock_key_event>" not in fast_passthrough
        or re.search(r"\b(?:lw|sw|sb|sh)\s", fast_passthrough)
        or re.search(r"\b(?:addi|c\.addi16sp)\s+x2,", fast_passthrough)
        or re.search(r"\b(?:jal|jalr)\s+x1,", fast_passthrough)
    ):
        raise AgentsDashboardFirmwareError("确认键无栈原厂跳板检查未通过")
    wrapped_key_event = _symbol_block(
        disassembly,
        "ap01_agents_wrapped_key_event",
        "ap01_agents_fast_stock_passthrough",
    )
    wrapped_instructions = [
        line
        for line in wrapped_key_event.splitlines()
        if re.match(r"^\s*[0-9a-f]+:\s", line)
    ]
    wrapped_stack_marker = (
        "c.addi16sp"
        if wrapped_instructions
        and "c.addi16sp" in wrapped_instructions[0]
        else "x2,x2,-64"
    )
    if (
        not wrapped_instructions
        or not (
            (
                "c.addi16sp" in wrapped_instructions[0]
                and "x2,-64" in wrapped_instructions[0]
            )
            or (
                "\taddi\t" in wrapped_instructions[0]
                and "x2,x2,-64" in wrapped_instructions[0]
            )
        )
    ):
        raise AgentsDashboardFirmwareError("完整键值包装没有从固定栈帧开始")
    first_state_read = key_event.find("<ap01_agents_find_pet_state>")
    guarded_prefix = key_event[:first_state_read]
    if (
        first_state_read < 0
        or "<stock_get_dispatch_index>" not in guarded_prefix
        or "<ap01_agents_stock_passthrough>" not in guarded_prefix
        or re.search(
            r"\bbne\s+x19,x6,[0-9a-f]+ "
            r"<ap01_agents_stock_passthrough>",
            guarded_prefix,
        )
        is None
        or re.search(
            r"\bbltu\s+x5,x19,[0-9a-f]+ "
            r"<ap01_agents_stock_passthrough>",
            guarded_prefix,
        )
        is None
        or "# a00bfa4e <stock_switch_page>" not in key_event
        or "# a00bbfee <stock_key_event>" not in key_event
        or any(
            f"{offset}(x9)" in key_event
            for offset in (52, 56, 60)
        )
        or re.search(r"\bsw\s+x\d+,(?:0|4|8|12)\(x20\)", key_event)
    ):
        raise AgentsDashboardFirmwareError(
            "原厂确认透传、真实切页或禁止字段检查未通过"
        )
    passthrough = _symbol_block(
        disassembly,
        "ap01_agents_stock_passthrough",
        "ap01_agents_fast_stock_passthrough",
    )
    if (
        "# a00bbfee <stock_key_event>" not in passthrough
        or "<ap01_agents_find_pet_state>" in passthrough
        or "<ap01_agents_state_read>" in passthrough
    ):
        raise AgentsDashboardFirmwareError("原厂事件透传路径仍读取自定义状态")
    switch_failed = _symbol_block(
        disassembly,
        "ap01_agents_switch_failed",
        "ap01_agents_stock_passthrough",
    )
    if (
        "<ap01_agents_switch_failed>" not in key_event
        or "<ap01_agents_restore_pet>" not in switch_failed
    ):
        raise AgentsDashboardFirmwareError("真实页面切换核对失败没有关闭恢复")

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
    show_failed = _symbol_block(
        disassembly,
        "ap01_agents_show_failed",
        "ap01_agents_restore_pet",
    )
    if (
        "<ap01_agents_state_write>" not in show_page
        or "# a00cf8d8 <lv_gif_set_src>" not in show_page
        or "92(x5)" not in show_page
        or "<ap01_agents_restore_pet>" not in show_page
        or "<ap01_agents_restore_pet>" not in show_failed
        or "<ap01_agents_state_write>" not in restore_pet
        or "a01f7090" not in restore_pet.lower()
        or "# a00cf8d8 <lv_gif_set_src>" not in restore_pet
        or "92(x5)" not in restore_pet
        or re.search(r"\bsw\s+x\d+,(?:0|4|8|12)\(x8\)", show_page)
        or re.search(r"\bsw\s+x\d+,(?:0|4|8|12)\(x8\)", restore_pet)
    ):
        raise AgentsDashboardFirmwareError(
            "独立尾部提交、解码核对或原厂萌宠恢复检查未通过"
        )

    detail_active = _symbol_block(
        disassembly,
        "ap01_agents_detail_active",
        "memory_zero",
    )
    if (
        "<stock_get_dispatch_index>" not in detail_active
        or "<ap01_agents_find_pet_state>" not in detail_active
        or detail_active.find("<stock_get_dispatch_index>")
        > detail_active.find("<ap01_agents_find_pet_state>")
    ):
        raise AgentsDashboardFirmwareError("AGENTS 详情身份没有先核对原厂分派")

    timer_wrapper = _symbol_block(
        disassembly,
        "ap01_agents_ui_timer_wrapper",
        "agents_device_id",
    )
    stock_timer = timer_wrapper.find("# a00bb5da")
    dispatch = timer_wrapper.find("# a00be388")
    stock_child = timer_wrapper.find("# a00be3ca")
    if not (
        0 <= stock_timer < dispatch < stock_child
        and "16(" in timer_wrapper
        and "4(" in timer_wrapper
        and "<ap01_agents_apply_current>" in timer_wrapper
        and "<ap01_agents_restore_pet>" in timer_wrapper
    ):
        raise AgentsDashboardFirmwareError("后台刷新原厂分派与萌宠对象链检查未通过")
    return {
        "stackless_gate_entry": _instruction_address(
            fast_gate,
            "8(x10)",
        ),
        "stackless_stock_tail": _instruction_address(
            fast_passthrough,
            "# a00bbfee <stock_key_event>",
        ),
        "wrapped_stack_entry": _instruction_address(
            wrapped_key_event,
            wrapped_stack_marker,
        ),
        "key_dispatch_first_call": _instruction_address(
            key_event,
            "# a00be388 <stock_get_dispatch_index>",
        ),
        "key_first_pet_state_lookup": _instruction_address(
            key_event,
            "<ap01_agents_find_pet_state>",
        ),
        "key_stock_switch_call": _instruction_address(
            key_event,
            "# a00bfa4e <stock_switch_page>",
        ),
        "key_switch_verification_call": _instruction_address(
            key_event,
            "# a00be388 <stock_get_dispatch_index>",
            last=True,
        ),
        "switch_failure_restore_call": _instruction_address(
            switch_failed,
            "<ap01_agents_restore_pet>",
        ),
        "stock_passthrough_tail": _instruction_address(
            passthrough,
            "# a00bbfee <stock_key_event>",
        ),
        "independent_tail_store": _instruction_address(
            state_write,
            "16(x10)",
        ),
        "show_source_call": _instruction_address(
            show_page,
            "# a00cf8d8 <lv_gif_set_src>",
        ),
        "restore_source_call": _instruction_address(
            restore_pet,
            "# a00cf8d8 <lv_gif_set_src>",
        ),
        "gif_failure_restore_call": _instruction_address(
            show_failed,
            "<ap01_agents_restore_pet>",
        ),
        "timer_order": [
            _instruction_address(timer_wrapper, "# a00bb5da"),
            _instruction_address(
                timer_wrapper,
                "# a00be388 <stock_get_dispatch_index>",
            ),
            _instruction_address(
                timer_wrapper,
                "# a00be3ca <stock_get_child>",
            ),
        ],
        "forbidden_call_addresses": [
            f"0x{address:08x}" for address in STOCK_PET_FORBIDDEN_CALLEES
        ],
    }


def _validate_stock_local_branches_disassembly(
    disassembly: str,
) -> dict[str, object]:
    evidence = _validate_stock_pet_reuse_disassembly(disassembly)
    local_branches = _symbol_block(
        disassembly,
        "ap01_agents_stock_power_left_entry",
        "ap01_agents_show_page",
    )
    required_markers = (
        "<ap01_agents_find_pet_state>",
        "<ap01_agents_state_read>",
        "<ap01_agents_show_page>",
        "<ap01_agents_restore_pet>",
        "# a00bfa4e <stock_switch_page>",
        "# a00bc33a <stock_power_left_resume>",
        "# a00bc464 <stock_pet_left_resume>",
        "# a00bc716 <stock_pet_right_resume>",
        "# a00bda68 <stock_pet_enter_resume>",
        "# a00bc1d2 <stock_key_epilogue>",
    )
    missing = [marker for marker in required_markers if marker not in local_branches]
    if missing:
        raise AgentsDashboardFirmwareError(
            f"局部分支载荷缺少恢复或消费目标：{missing[0]}"
        )
    if (
        "# a00bbfee <stock_key_event>" in local_branches
        or local_branches.count("# a00bc1d2 <stock_key_epilogue>") != 1
        or any(
            local_branches.count(f"# {address:08x} <") != 1
            for address in (
                0xA00BC33A,
                0xA00BC464,
                0xA00BC716,
                0xA00BDA68,
            )
        )
    ):
        raise AgentsDashboardFirmwareError("局部分支恢复与消费出口不是一一对应")
    for symbol in (
        "ap01_agents_stock_power_left_entry",
        "ap01_agents_stock_pet_left_entry",
        "ap01_agents_stock_pet_right_entry",
        "ap01_agents_stock_pet_enter_entry",
    ):
        if f"<{symbol}>:" not in disassembly:
            raise AgentsDashboardFirmwareError(f"局部分支入口缺失：{symbol}")
    evidence["local_branch_resume_targets"] = {
        "power_left": _instruction_address(
            local_branches,
            "# a00bc33a <stock_power_left_resume>",
        ),
        "pet_left": _instruction_address(
            local_branches,
            "# a00bc464 <stock_pet_left_resume>",
        ),
        "pet_right": _instruction_address(
            local_branches,
            "# a00bc716 <stock_pet_right_resume>",
        ),
        "pet_enter": _instruction_address(
            local_branches,
            "# a00bda68 <stock_pet_enter_resume>",
        ),
        "consumed": _instruction_address(
            local_branches,
            "# a00bc1d2 <stock_key_epilogue>",
        ),
    }
    return evidence


def _patch_stock_local_branches(
    candidate: bytearray,
    symbols: dict[str, int],
) -> list[ByteRange]:
    allowed: list[ByteRange] = []
    for (
        hook_offset,
        hook_original,
        trampoline_offset,
        symbol,
        _resume_address,
        label,
    ) in STOCK_LOCAL_BRANCH_HOOKS:
        entry = symbols.get(symbol)
        if entry is None:
            raise AgentsDashboardFirmwareError(f"{label}载荷入口缺失")
        allowed.append(
            _replace(
                candidate,
                hook_offset,
                hook_original,
                _encode_jal(
                    XIP_DELTA + hook_offset,
                    XIP_DELTA + trampoline_offset,
                ),
                f"{label}原厂局部目标",
            )
        )
        allowed.append(
            _replace(
                candidate,
                trampoline_offset,
                STOCK_LOCAL_TRAMPOLINE_ORIGINAL,
                _absolute_tail_jump(entry),
                f"{label}近跳板",
            )
        )
    return allowed


def _assert_stock_local_branch_isolation(
    stage: bytes,
    candidate: bytes,
) -> None:
    for offset, expected in (
        (KEY_CALLBACK_HIGH_OFFSET, KEY_CALLBACK_HIGH_ORIGINAL),
        (KEY_CALLBACK_LOW_OFFSET, KEY_CALLBACK_LOW_ORIGINAL),
        (UI_CALLBACK_LUI, INSTRUCTION_EXPECTED[UI_CALLBACK_LUI]),
        (UI_CALLBACK_ADDI, INSTRUCTION_EXPECTED[UI_CALLBACK_ADDI]),
    ):
        end = offset + len(expected)
        if stage[offset:end] != expected or candidate[offset:end] != expected:
            raise AgentsDashboardFirmwareError("原厂全局回调地址装入字节发生变化")

    allowed_offsets = {
        offset
        for hook_offset, hook_original, *_rest in STOCK_LOCAL_BRANCH_HOOKS
        for offset in range(hook_offset, hook_offset + len(hook_original))
    }
    callback_start, callback_end = STOCK_KEY_CALLBACK_RANGE
    for offset in range(callback_start, callback_end):
        if offset not in allowed_offsets and candidate[offset] != stage[offset]:
            raise AgentsDashboardFirmwareError(
                f"原厂键值回调非局部分支字节发生变化：0x{offset:06x}"
            )
    power_start, power_end = STOCK_POWER_CONFIRM_RANGE
    if candidate[power_start:power_end] != stage[power_start:power_end]:
        raise AgentsDashboardFirmwareError("原厂功率确认路径发生变化")


def build_sync_payload(
    stage_path: Path,
    build_directory: Path,
    credentials: DeviceCredentialsLike,
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
        assets = build_fallback_assets(selected / "fallback-assets")
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
    callchain_evidence: dict[str, object] | None = None
    route_validation: dict[str, int] | None = None
    if reuse_stock_pet:
        callchain_evidence = _validate_stock_local_branches_disassembly(
            disassembly
        )
        route_validation = validate_stock_callchain_routes()
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
        callchain_evidence=callchain_evidence,
        route_validation=route_validation,
    )


def build_sync_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    credentials: DeviceCredentialsLike,
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
    if (
        not reuse_stock_pet
        or expected_output_name != STOCK_LOCAL_BRANCHES_OUTPUT_FILENAME
    ):
        raise AgentsDashboardFirmwareError(
            "旧 AGENTS 固件路径已停用，只允许生成原厂键值回调局部分支观察成品"
        )
    if (
        extra_objects
        or required_extra_symbols
        or candidate_mutators
        or key_callback_symbol != "ap01_agents_key_event"
    ):
        raise AgentsDashboardFirmwareError("局部分支观察成品不允许组合其他界面改写")
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
            PET_STATE_SIZE_OFFSET,
            PET_STATE_SIZE_ORIGINAL,
            PET_STATE_SIZE_EXTENDED,
            "原厂萌宠状态申请长度",
        )
    )
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
    allowed.extend(
        _patch_stock_local_branches(candidate, payload_result.symbols)
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
    sink_high, sink_low = _absolute_lui_addi(sink, register=15)
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

    _assert_stock_local_branch_isolation(stage, bytes(candidate))

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
        "manifest_type": "agents-stock-local-branches-observation-firmware",
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
            "stock_pet_object_reused": True,
            "stock_pet_state_bytes_before": 16,
            "stock_pet_state_bytes_after": 20,
            "agents_state_offset": 16,
        },
        "implemented_scope": [
            "四页完整包流式接收",
            "四页文件指纹校验",
            "设备代号与响应授权校验",
            "三组临时槽原子提交",
            "界面线程只切换已提交页面",
            "固定周期后台刷新",
            "复用原厂萌宠既有动图对象",
            "只挂接原厂已筛选的四个局部分支",
            "原厂功率确认和两个全局回调保持原字节",
            "真实页面使用原厂实际切页入口",
            "AGENTS 状态使用萌宠状态新增尾部",
            *implemented_scope_extra,
        ],
        "pending_scope": [
            "重启后保留最后成功包",
            "页面开关关闭时停用刷新",
            "NAS 与云服务器故障切换",
            "停留页面时即时应用后台新数据",
        ],
        "pending_measurements": [
            "后台任务原有栈余量",
            "四页临时文件总量",
            "连续刷新内存变化",
            "网络失败恢复",
            "断电恢复",
        ],
        "allowed_ranges": [item.to_dict() for item in allowed],
        "callchain_gates": {
            "disassembly": payload_result.callchain_evidence,
            "route_validation": payload_result.route_validation,
            "page_registration_bytes_unchanged": True,
            "legacy_page_trampoline_bytes_unchanged": True,
            "global_key_callback_registration_unchanged": True,
            "global_ui_timer_callback_registration_unchanged": True,
            "stock_key_callback_unchanged_except_local_targets": True,
            "stock_power_confirm_path_unchanged": True,
            "local_branch_hooks": [
                {
                    "label": label,
                    "hook_file_offset": f"0x{hook_offset:06x}",
                    "hook_before_hex": hook_original.hex(),
                    "hook_after_hex": _encode_jal(
                        XIP_DELTA + hook_offset,
                        XIP_DELTA + trampoline_offset,
                    ).hex(),
                    "trampoline_file_offset": f"0x{trampoline_offset:06x}",
                    "trampoline_after_hex": _absolute_tail_jump(
                        payload_result.symbols[symbol]
                    ).hex(),
                    "payload_symbol": symbol,
                    "payload_address": (
                        f"0x{payload_result.symbols[symbol]:08x}"
                    ),
                    "stock_resume_address": f"0x{resume_address:08x}",
                }
                for (
                    hook_offset,
                    hook_original,
                    trampoline_offset,
                    symbol,
                    resume_address,
                    label,
                ) in STOCK_LOCAL_BRANCH_HOOKS
            ],
            "pet_state_original_fields_unchanged": True,
            "pet_state_size_patch": {
                "file_offset": f"0x{PET_STATE_SIZE_OFFSET:06x}",
                "before_hex": PET_STATE_SIZE_ORIGINAL.hex(),
                "after_hex": PET_STATE_SIZE_EXTENDED.hex(),
            },
        },
        "recovery_crc_after_build": f"0x{recovery_crc:08x}",
        "validation": {
            "old_bytes_asserted": True,
            "payload_fits": True,
            "relocations_zero": True,
            "total_length_preserved": True,
            "outside_allowed_ranges_identical": True,
            "page_registration_unchanged": True,
            "legacy_page_trampoline_unchanged": True,
            "stock_callchain_verified": True,
            "four_local_branch_targets_verified": True,
            "global_key_callback_registration_unchanged": True,
            "global_ui_timer_callback_registration_unchanged": True,
            "stock_power_confirm_path_unchanged": True,
            "independent_tail_recovery_verified": True,
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


def build_stock_callchain_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    credentials: DeviceCredentialsLike,
    *,
    url_base: str,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "原厂精确调用链观察成品已因功率页确认重启停用"
    )


def build_stock_enter_gate_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    credentials: DeviceCredentialsLike,
    *,
    url_base: str,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "原厂确认键无栈透传观察成品已因功率页确认卡死停用"
    )


def build_stock_local_branches_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    credentials: DeviceCredentialsLike,
    *,
    url_base: str,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        credentials,
        url_base=url_base,
        refresh_seconds=refresh_seconds,
        tool_revision=tool_revision,
        expected_output_name=STOCK_LOCAL_BRANCHES_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "功率左旋和萌宠三种键值局部接入",
            "未消费事件从四个原厂继续地址恢复",
            "消费事件从原厂公共退出地址返回",
            "异常尾部先恢复原厂萌宠再继续处理",
        ),
        reuse_stock_pet=True,
    )
