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


MODULE_DIR = Path(__file__).resolve().parent
LOADER_SOURCE = MODULE_DIR / "result_loader.c"
LOCAL_UI_LOADER_SOURCE = MODULE_DIR / "local_ui_loader.c"
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
LOW_STACK_LOCAL_BRANCHES_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-low-stack-local-branches-candidate.bin"
)
LOCAL_UI_POWER_SAFE_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-local-ui-power-safe.bin"
)
LOCAL_UI_STOCK_RESUME_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-local-ui-stock-resume.bin"
)
LOCAL_UI_STOCK_SAFE_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-local-ui-stock-safe.bin"
)
LOCAL_UI_BASE_SAFE_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-base-safe.bin"
)
LIVE_DATA_BASE_SAFE_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-live-data-base-safe.bin"
)
LIVE_DATA_REFERENCE_COMPLETE_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-live-data-reference-complete.bin"
)
LIVE_DATA_LOW_STACK_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-live-data-low-stack.bin"
)
LIVE_DATA_LOCATION_INDEPENDENT_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-live-data-location-independent.bin"
)
LIVE_DATA_VALIDATED_PACKAGE_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-live-data-validated-package.bin"
)
LIVE_DATA_ENDPOINT_FAILOVER_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-live-data-endpoint-failover.bin"
)
LIVE_DATA_FIXED_PRIMARY_PAGES_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-live-data-fixed-primary-pages-v2.bin"
)
LIVE_DATA_WEATHER_COEXISTENCE_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-live-data-weather-coexistence.bin"
)
LIVE_DATA_WEATHER_ROUND_ROBIN_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-live-data-weather-round-robin.bin"
)
LIVE_DATA_ROUND_DIAGNOSTIC_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-live-data-round-diagnostic.bin"
)
LIVE_DATA_DOWNLOAD_DIAGNOSTIC_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-download-diagnostic.bin"
)
LIVE_DATA_RESULT_DIAGNOSTIC_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-result-diagnostic.bin"
)
LIVE_DATA_PUBLISH_DIAGNOSTIC_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-publish-diagnostic.bin"
)
LIVE_DATA_ADOPTION_DIAGNOSTIC_OUTPUT_FILENAME = "ap01-1.0.2_0031-agents-adoption-diagnostic.bin"
LIVE_DATA_STABLE_ADOPTION_OUTPUT_FILENAME = "ap01-1.0.2_0031-agents-stable-adoption.bin"
LIVE_DATA_WEATHER_AGENTS_DUAL_REQUEST_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-weather-agents-dual-request.bin"
)
LIVE_DATA_STOCK_HTTPS_DUAL_REQUEST_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-stock-https-dual-request.bin"
)
LIVE_DATA_WEATHER_PRESERVED_DUAL_REQUEST_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-weather-preserved-dual-request.bin"
)
LIVE_DATA_WEATHER_STOCK_FIRST_DUAL_REQUEST_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-weather-stock-first-dual-request.bin"
)
LIVE_DATA_WEATHER_SOLO_REQUEST_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-weather-solo-request.bin"
)
LIVE_DATA_STOCK_HTTPS_UNTOUCHED_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-stock-https-untouched.bin"
)
LIVE_DATA_POST_WEATHER_FETCH_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-post-weather-fetch.bin"
)
LIVE_DATA_LOCATION_SLOT_DASHBOARD_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-location-slot-dashboard.bin"
)
LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-weather-hidden-dashboard.bin"
)
LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_V2_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-agents-weather-hidden-dashboard-v2.bin"
)
PUBLIC_FIRMWARE_OUTPUT_FILENAME = "ap01-1.0.2_0031-opt.bin"
PERSONALIZED_FIRMWARE_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-opt-personalized.bin"
)
OPT_INTEGRATION_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-opt-integration-candidate.bin"
)
OPT_REWRITE_OUTPUT_FILENAME = (
    "ap01-1.0.2_0031-opt-rewrite-candidate.bin"
)
XIP_DELTA = 0x9FFFF000
PET_STATE_SIZE_OFFSET = 0x0B502C
PET_STATE_SIZE_ORIGINAL = bytes.fromhex("4145")
PET_STATE_SIZE_EXTENDED = bytes.fromhex("5145")
LOADER_TRAMPOLINE_OFFSET = 0x01C0B4
LOADER_TRAMPOLINE_VA = XIP_DELTA + LOADER_TRAMPOLINE_OFFSET
LOADER_TRAMPOLINE_ORIGINAL = b"\x00" * 8
LOCATION_TRAMPOLINE_OFFSET = 0x01C0E4
LOCATION_TRAMPOLINE_VA = XIP_DELTA + LOCATION_TRAMPOLINE_OFFSET
LOCATION_TRAMPOLINE_ORIGINAL = b"\x00" * 8
POST_WEATHER_FETCH_HOOK = 0x0B825A
POST_WEATHER_FETCH_HOOK_ORIGINAL = bytes.fromhex("aa8b0325")
POST_WEATHER_FETCH_TRAMPOLINE_OFFSET = 0x01C0EC
POST_WEATHER_FETCH_TRAMPOLINE_VA = XIP_DELTA + POST_WEATHER_FETCH_TRAMPOLINE_OFFSET
POST_WEATHER_FETCH_TRAMPOLINE_ORIGINAL = b"\x00" * 8
POST_WEATHER_FETCH_RESUME_VA = 0xA00B7260
STOCK_LOCAL_BRANCH_HOOKS = (
    (
        0x0BD460,
        bytes.fromhex("9d452685"),
        0x01C0BC,
        "ap01_agents_stock_pet_left_entry",
        0xA00BC464,
        "萌宠左旋",
    ),
    (
        0x0BD712,
        bytes.fromhex("9d452685"),
        0x01C0C4,
        "ap01_agents_stock_pet_right_entry",
        0xA00BC716,
        "萌宠右旋",
    ),
    (
        0x0BEA64,
        bytes.fromhex("26859d45"),
        0x01C0CC,
        "ap01_agents_stock_pet_enter_entry",
        0xA00BDA68,
        "萌宠确认",
    ),
)
OPT_PAGE_FILTER_HOOK = (
    0x0BD092,
    bytes.fromhex("ef30d01b"),
    0x01C0D4,
    "ap01_primary_page_filter_and_switch",
    0xA00BC096,
    "一级切页过滤",
)
LOCAL_UI_SHARED_PAGE_FILTER_HOOK = (
    0x0BD092,
    bytes.fromhex("ef30d01b"),
    0x01C0D4,
    "ap01_agents_primary_page_filter_and_switch",
    0xA00BC096,
    "共享序号切页过滤",
)
LOCAL_UI_POWER_CONFIRM_GUARD_HOOK = (
    0x0BD8C6,
    bytes.fromhex("e3160a90"),
    0x01C0DC,
    "ap01_agents_stock_power_confirm_guard",
    0xA00BC8CA,
    "功率确认连接保护",
)
STOCK_LOCAL_TRAMPOLINE_ORIGINAL = b"\x00" * 8
STOCK_KEY_CALLBACK_RANGE = (0x0BCFEE, 0x0BEB00)
STOCK_POWER_CONFIRM_RANGE = (0x0BD8C6, 0x0BD960)
UI_CALLBACK_LUI = 0x0B37E4
UI_CALLBACK_ADDI = 0x0B37EE
SINK_CALLBACK_LUI = 0x0B7D92
SINK_CALLBACK_ADDI = 0x0B7D96
HTTPS_PERFORM_CALL = 0x0B8256
HTTP_PERFORM_CALL = 0x0B82C0
LOCATION_LOOKUP_CALL = 0x0B7DD4
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
    HTTPS_PERFORM_CALL: bytes.fromhex("ef104246"),
    HTTP_PERFORM_CALL: bytes.fromhex("ef10a23f"),
    POST_WEATHER_FETCH_HOOK: POST_WEATHER_FETCH_HOOK_ORIGINAL,
    LOCATION_LOOKUP_CALL: bytes.fromhex("ef507fe1"),
    SUCCESS_TIMER_LUI: bytes.fromhex("b7f73600"),
    SUCCESS_TIMER_ADDI: bytes.fromhex("138917e8"),
    SUCCESS_TIMER_REM: bytes.fromhex("33692503"),
    SUCCESS_TIMER_BASE_ADDI: bytes.fromhex("938707e8"),
    SUCCESS_TIMER_ADD: bytes.fromhex("3e99"),
    FAILURE_BACKOFF_STORE: bytes.fromhex("23a6f9cc"),
}
REQUIRED_SYMBOLS = (
    "ap01_agents_page_register",
    "ap01_agents_sink",
    "ap01_agents_location_stub",
    "ap01_agents_webclient_wrapper",
    "ap01_agents_apply_current",
    "ap01_agents_ui_timer_wrapper",
    "ap01_agents_loader_end_marker",
)
LOCAL_UI_REQUIRED_SYMBOLS = (
    "ap01_agents_page_register",
    "ap01_agents_apply_current",
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
    0xA007E1C4,
    0xA007C256,
)
LOCAL_UI_REQUIRED_CALLEES = (
    0xA00BE388,
    0xA00BE3CA,
    0xA00CF8D8,
)
LOCAL_UI_POWER_GUARD_REQUIRED_CALLEES = (
    0xA00B16A4,
    0xA0193862,
    0xA00BC8CA,
    0xA00BC1D2,
)
LOCAL_UI_FORBIDDEN_CALLEES = (
    0xA00BB5DA,
    0xA00D86BA,
    0xA003F448,
    0xA0026788,
    0xA003F5F4,
    0xA0027D94,
)
LOCAL_UI_FORBIDDEN_SYMBOLS = (
    "ap01_agents_sink",
    "ap01_agents_webclient_wrapper",
    "ap01_agents_ui_timer_wrapper",
)
STOCK_PET_FORBIDDEN_CALLEES = (
    0xA00C1EC6,
    0xA01930FE,
    0xA00BEBEE,
    0xA00C5D84,
    0xA00C5FE4,
    0xA00B0290,
    0xA00B0570,
    0xA00B06F4,
    0xA00BBFEE,
    0xA007E1C4,
    0xA007C256,
)
STOCK_PET_REQUIRED_SYMBOLS = (
    "ap01_agents_state_read",
    "ap01_agents_state_write",
    "ap01_agents_find_pet_state",
    "ap01_agents_show_failed",
    "ap01_agents_show_page",
    "ap01_agents_restore_pet",
    "ap01_agents_close_for_stock_resume",
    "ap01_agents_primary_page_filter_and_switch",
    "ap01_agents_detail_active",
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
class StockLocalBranchRoute:
    action: str
    target_dispatch: int | None = None
    target_state: int | None = None
    switch_mode: int | None = None


def _manifest_completeness(document: dict[str, object]) -> dict[str, object]:
    transport = document.get("transport")
    validation = document.get("validation")
    missing_items: list[str] = []

    if not isinstance(transport, dict):
        missing_items.append("缺少设备端取数配置")
        transport = {}
    if not isinstance(validation, dict):
        missing_items.append("缺少安装许可校验结果")
        validation = {}

    if document.get("status") == "requires-endpoint-personalization":
        missing_items.append(
            "缺少服务端地址，需要根据用户实时局域网 IPv4 制作个人固件；"
            "刷机前应一次填入 1～10 个可用服务端地址"
        )
    if document.get("device_specific") is not True:
        missing_items.append("不是按当前用户设备和电脑地址生成的个人固件")
    if transport.get("enabled") is not True:
        missing_items.append("设备端取数程序未启用")
    if transport.get("endpoint_configuration_required") is True:
        missing_items.append("构建清单标记仍需要服务端地址")
    if not transport.get("endpoint_priority"):
        missing_items.append("没有写入真实服务端地址")
    if validation.get("installation_allowed") is not True:
        missing_items.append("构建清单未允许一次测试安装")

    return {
        "complete": not missing_items,
        "missing_items": missing_items,
    }


def _endpoint_personalization(
    *,
    endpoint_failover_candidate: bool,
    endpoint_urls: tuple[str, ...],
) -> dict[str, object]:
    if not endpoint_failover_candidate:
        return {
            "supported": False,
            "required_before_install": False,
            "multiple_addresses_supported": False,
            "min_endpoint_count": 0,
            "max_endpoint_count": 0,
            "current_endpoint_count": 0,
            "current_endpoints": [],
            "future_change_policy": "该固件清单未声明可通过服务端地址个人化",
        }

    return {
        "supported": True,
        "required_before_install": not endpoint_urls,
        "multiple_addresses_supported": True,
        "min_endpoint_count": 1,
        "max_endpoint_count": 10,
        "current_endpoint_count": len(endpoint_urls),
        "current_endpoints": list(endpoint_urls),
        "configuration_file": "env/agents-dashboard.env",
        "hosts_key": "AP01_AGENTS_HOSTS",
        "port_key": "AP01_AGENTS_PORT",
        "address_entry_rule": (
            "AP01_AGENTS_HOSTS 填写 1～10 个不同局域网 IPv4，"
            "按设备访问优先级用英文逗号分隔；AP01_AGENTS_PORT 填写共用端口"
        ),
        "preflash_prompt": (
            "刷机前必须询问用户：除了当前电脑，还有没有 NAS、备用电脑或云端跳板等"
            "也要让 AP01 拉取数据的服务端地址；有的话一次填入"
        ),
        "future_change_policy": (
            "如果本次只写入一个地址，将来新增电脑或服务端地址时，"
            "需要用新的地址列表重新制作个人固件并重新刷机"
        ),
    }


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


def route_stock_local_branch(
    branch: str,
    agents_state: int | None,
    *,
    pet_enabled: bool = True,
    agents_enabled: bool = True,
) -> StockLocalBranchRoute:
    if branch not in ("pet-left", "pet-right", "pet-enter"):
        raise ValueError("未知的原厂萌宠局部分支")
    if agents_state not in range(5):
        return StockLocalBranchRoute("restore-then-stock")

    if branch == "pet-enter":
        if agents_state == 0:
            return StockLocalBranchRoute("stock-resume")
        return StockLocalBranchRoute(
            "show-agents",
            target_state=2 if agents_state == 1 else 1,
        )

    if agents_state in (2, 3, 4):
        target = {
            ("pet-left", 2): 4,
            ("pet-left", 3): 2,
            ("pet-left", 4): 3,
            ("pet-right", 2): 3,
            ("pet-right", 3): 4,
            ("pet-right", 4): 2,
        }[(branch, agents_state)]
        return StockLocalBranchRoute("show-agents", target_state=target)

    if branch == "pet-left":
        if agents_state == 0:
            return StockLocalBranchRoute("stock-resume")
        if pet_enabled:
            return StockLocalBranchRoute("restore-pet", target_state=0)
        return StockLocalBranchRoute(
            "switch-stock",
            target_dispatch=6,
            target_state=0,
            switch_mode=2,
        )

    if agents_state == 0:
        if not agents_enabled:
            return StockLocalBranchRoute("stock-resume")
        return StockLocalBranchRoute(
            "show-agents",
            target_state=1,
        )
    return StockLocalBranchRoute(
        "close-then-stock-resume",
        target_state=0,
    )


def validate_stock_local_branch_routes() -> dict[str, int]:
    branches = ("pet-left", "pet-right", "pet-enter")
    matrix = {
        (branch, state): route_stock_local_branch(branch, state)
        for branch in branches
        for state in range(5)
    }
    expected_details = {
        ("pet-left", 2): 4,
        ("pet-left", 3): 2,
        ("pet-left", 4): 3,
        ("pet-right", 2): 3,
        ("pet-right", 3): 4,
        ("pet-right", 4): 2,
    }
    for (branch, state), target in expected_details.items():
        route = matrix[(branch, state)]
        if route.action != "show-agents" or route.target_state != target:
            raise AgentsDashboardFirmwareError("AGENTS 三个详情没有首尾循环")
    if matrix[("pet-left", 0)].action != "stock-resume":
        raise AgentsDashboardFirmwareError("原厂萌宠左键未保持原继续路径")
    if matrix[("pet-right", 0)].target_state != 1:
        raise AgentsDashboardFirmwareError("萌宠右键没有进入 AGENTS 概览")
    if (
        matrix[("pet-right", 1)].action != "close-then-stock-resume"
        or matrix[("pet-right", 1)].target_dispatch is not None
        or matrix[("pet-right", 1)].switch_mode is not None
    ):
        raise AgentsDashboardFirmwareError("AGENTS 概览右键没有交还原厂右旋分支")
    if matrix[("pet-enter", 0)].action != "stock-resume":
        raise AgentsDashboardFirmwareError("原厂萌宠确认未保持原继续路径")
    if route_stock_local_branch(
        "pet-left",
        1,
        pet_enabled=False,
    ).target_dispatch != 6:
        raise AgentsDashboardFirmwareError("萌宠关闭后的左向目标不正确")
    if route_stock_local_branch(
        "pet-right",
        0,
        agents_enabled=False,
    ).action != "stock-resume":
        raise AgentsDashboardFirmwareError("AGENTS 关闭后没有恢复原厂右键路径")

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
        "local_branch_state_cases": len(matrix),
        "detail_rotation_cases": len(expected_details),
        "disabled_page_cases": 2,
        "invalid_tail_cases": len(recovery_words),
        "valid_tail_cases": 5,
        "switch_failure_recovery_cases": 1,
        "overview_right_stock_resume_cases": 1,
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


def _request_formats() -> tuple[bytes, bytes]:
    location = b"%s"
    city = b"%s"
    if len(location) + 1 > 44 or len(city) + 1 > 48:
        raise AgentsDashboardFirmwareError("天气请求格式超过原厂固定区域")
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
        "ap01_agents_loader_end_marker",
    )
    if (
        "x11,7" not in timer_wrapper
        or "# a00c5fe4 <lv_obj_get_child_count>" not in timer_wrapper
        or "<ap01_agents_apply_current>" not in timer_wrapper
    ):
        raise AgentsDashboardFirmwareError("AGENTS 覆盖层刷新对象检查未通过")


def _validate_stock_pet_reuse_disassembly(
    disassembly: str,
    *,
    integration_mode: bool = False,
    local_ui_only: bool = False,
    weather_coexistence: bool = False,
    weather_success_requires_stock: bool = False,
    weather_stock_first: bool = False,
    location_slot_dashboard: bool = False,
    disable_download: bool = False,
) -> dict[str, object]:
    lowered = disassembly.lower()
    if "<ap01_agents_key_event>:" in lowered:
        raise AgentsDashboardFirmwareError("优化载荷仍链接了已停用的一级总键值包装")
    for address in (0xA00B0290, 0xA00B0570, 0xA00B06F4, 0xA00BBFEE):
        if f"# {address:08x} <" in lowered:
            raise AgentsDashboardFirmwareError(
                f"优化载荷仍调用了已停用入口：0x{address:08x}"
            )
    if not integration_mode:
        for address in STOCK_PET_FORBIDDEN_CALLEES:
            if not local_ui_only and address in (0xA007E1C4, 0xA007C256):
                continue
            if f"# {address:08x} <" in lowered:
                raise AgentsDashboardFirmwareError(
                    f"原厂精确调用链载荷调用了禁止函数：0x{address:08x}"
                )

    if not local_ui_only:
        location_stub = _symbol_block(
            disassembly,
            "ap01_agents_location_stub",
            "ap01_agents_webclient_wrapper",
        )
        store_base = "x8" if weather_coexistence else "x10"
        store_offsets = {
            int(match.group(1))
            for match in re.finditer(
                rf"\bsb\s+x\d+,(\d+)\({store_base}\)",
                location_stub,
            )
        }
        success_return = (
            "c.li\tx9,1" in location_stub and "c.mv\tx10,x9" in location_stub
            if weather_coexistence
            else (
                "addi\tx10,x0,1" in location_stub
                or "c.li\tx10,1" in location_stub
            )
        )
        location_calls = re.search(r"\bjal\s+x1,|\bjalr\s+x1,", location_stub)
        if location_slot_dashboard:
            protected_store_offsets = store_offsets | {
                int(match.group(1))
                for match in re.finditer(
                    r"\bsb\s+x\d+,(\d+)\(x10\)",
                    location_stub,
                )
            }
            zero_default_return = (
                "c.li\tx8,0" in location_stub
                or "c.li\tx10,0" in location_stub
                or "addi\tx10,x0,0" in location_stub
            )
            success_return = (
                "c.li\tx8,1" in location_stub
                or "c.li\tx10,1" in location_stub
                or "addi\tx10,x0,1" in location_stub
            )
            returns_saved_value = (
                "c.mv\tx10,x8" in location_stub
                or zero_default_return
                and success_return
            )
            if (
                not weather_coexistence
                or protected_store_offsets != set(range(10))
                or not zero_default_return
                or not success_return
                or not returns_saved_value
                or "<fw_stock_weather_city_present>" not in location_stub
                or "<fw_stock_location_lookup>" in location_stub
            ):
                raise AgentsDashboardFirmwareError(
                    "位置槽看板桥接没有隔离城市天气与看板占位路径"
                )
        elif weather_stock_first:
            protected_store_offsets = store_offsets | {
                int(match.group(1))
                for match in re.finditer(
                    r"\bsb\s+x\d+,(\d+)\(x10\)",
                    location_stub,
                )
            }
            zero_default_return = "c.li\tx8,0" in location_stub
            success_return = "c.li\tx8,1" in location_stub
            returns_saved_value = "c.mv\tx10,x8" in location_stub
            if (
                not weather_coexistence
                or protected_store_offsets
                or not zero_default_return
                or not success_return
                or not returns_saved_value
            ):
                raise AgentsDashboardFirmwareError(
                    "原厂天气优先位置桥接仍存在占位位置写入"
                )
            if "TRANSPORT_MODE_AGENTS_RETRY_WEATHER" in location_stub:
                raise AgentsDashboardFirmwareError(
                    "原厂天气优先位置桥接仍存在看板-only 分轮"
                )
        elif weather_success_requires_stock:
            protected_store_offsets = store_offsets | {
                int(match.group(1))
                for match in re.finditer(
                    r"\bsb\s+x\d+,(\d+)\(x10\)",
                    location_stub,
                )
            }
            zero_default_return = "c.li\tx8,0" in location_stub
            success_return = "c.li\tx8,1" in location_stub
            returns_saved_value = "c.mv\tx10,x8" in location_stub
            if (
                not weather_coexistence
                or protected_store_offsets != set(range(10))
                or not zero_default_return
                or not success_return
                or not returns_saved_value
            ):
                raise AgentsDashboardFirmwareError(
                    "天气保护位置桥接没有区分原厂天气成功与后备路径"
                )
        elif (
            store_offsets != set(range(10))
            or not success_return
            or not weather_coexistence and location_calls
        ):
            raise AgentsDashboardFirmwareError(
                "位置占位入口没有保持十字节有界写入和成功返回"
            )
        if weather_coexistence:
            required_helpers = ["<fw_stock_weather_city_present>"]
            if not location_slot_dashboard:
                required_helpers.insert(0, "<fw_stock_location_lookup>")
            if not weather_stock_first and not location_slot_dashboard:
                required_helpers.append("<fw_stock_weather_uptime_ms>")
            for helper in required_helpers:
                if helper not in location_stub:
                    raise AgentsDashboardFirmwareError(
                        "天气共存位置桥接缺少原厂状态调用"
                    )
            if not location_slot_dashboard:
                stock_lookup = _symbol_block(
                    disassembly,
                    "fw_stock_location_lookup",
                    (
                        "fw_stock_weather_city_present"
                        if weather_stock_first
                        else "fw_stock_weather_uptime_ms"
                    ),
                )
                if "# a00acbea <" not in stock_lookup:
                    raise AgentsDashboardFirmwareError(
                        "天气共存位置桥接没有调用原厂位置入口"
                    )
        web_wrapper = _symbol_block(
            disassembly,
            "ap01_agents_webclient_wrapper",
            "ap01_agents_apply_current",
        )
        download_marker = "<ap01_agents_download_package>:"
        if download_marker not in disassembly:
            raise AgentsDashboardFirmwareError("后台下载辅助入口缺失")
        web_wrapper += disassembly.split(download_marker, 1)[1]
        malloc_wrapper = _symbol_block(disassembly, "fw_malloc", "fw_free")
        free_wrapper = _symbol_block(
            disassembly,
            "fw_free",
            "fw_webclient_perform",
        )
        expected_heap_calls = 0 if disable_download else 1
        if (
            web_wrapper.count("<fw_malloc>") != expected_heap_calls
            or web_wrapper.count("<fw_free>") != expected_heap_calls
        ):
            raise AgentsDashboardFirmwareError(
                "后台下载包装的申请或释放下载状态次数不符合 DESIGN"
            )
        for address, helper in (
            (0xA007E1C4, malloc_wrapper),
            (0xA007C256, free_wrapper),
        ):
            marker = f"# {address:08x} <"
            if helper.count(marker) != 1:
                raise AgentsDashboardFirmwareError(
                    f"后台下载包装没有唯一调用内存入口：0x{address:08x}"
                )
            if disassembly.count(marker) != helper.count(marker):
                raise AgentsDashboardFirmwareError(
                    f"后台下载以外调用了内存入口：0x{address:08x}"
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
        "ap01_agents_stock_pet_left_entry",
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

    show_page = _symbol_block(
        disassembly,
        "ap01_agents_show_page",
        "ap01_agents_restore_pet",
    )
    restore_pet = _symbol_block(
        disassembly,
        "ap01_agents_restore_pet",
        "ap01_agents_close_for_stock_resume",
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
        "ap01_agents_apply_current" if local_ui_only else "memory_zero",
    )
    if (
        "<stock_get_dispatch_index>" not in detail_active
        or "<ap01_agents_find_pet_state>" not in detail_active
        or detail_active.find("<stock_get_dispatch_index>")
        > detail_active.find("<ap01_agents_find_pet_state>")
    ):
        raise AgentsDashboardFirmwareError("AGENTS 详情身份没有先核对原厂分派")

    evidence: dict[str, object] = {
        "retired_total_key_wrapper_absent": True,
        "retired_window_navigation_absent": True,
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
        "forbidden_call_addresses": [
            f"0x{address:08x}" for address in STOCK_PET_FORBIDDEN_CALLEES
        ],
    }
    if not local_ui_only:
        evidence["transport_heap_calls_scoped"] = True
        evidence["weather_coexistence_verified"] = weather_coexistence
    if local_ui_only:
        for symbol in LOCAL_UI_FORBIDDEN_SYMBOLS:
            if f"<{symbol}>:" in lowered:
                raise AgentsDashboardFirmwareError(
                    f"局部界面载荷仍包含后台符号：{symbol}"
                )
        for address in LOCAL_UI_FORBIDDEN_CALLEES:
            if f"# {address:08x} <" in lowered:
                raise AgentsDashboardFirmwareError(
                    f"局部界面载荷仍调用后台函数：0x{address:08x}"
                )
        evidence["transport_symbols_absent"] = True
        evidence["transport_callees_absent"] = True
        return evidence

    timer_wrapper = _symbol_block(
        disassembly,
        "ap01_agents_ui_timer_wrapper",
        "ap01_agents_loader_end_marker",
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
    evidence["timer_order"] = [
        _instruction_address(timer_wrapper, "# a00bb5da"),
        _instruction_address(
            timer_wrapper,
            "# a00be388 <stock_get_dispatch_index>",
        ),
        _instruction_address(
            timer_wrapper,
            "# a00be3ca <stock_get_child>",
        ),
    ]
    return evidence


def _validate_stock_local_branches_disassembly(
    disassembly: str,
    *,
    integration_mode: bool = False,
    shared_page_filter: bool = False,
    fixed_hidden_primary_pages: bool = False,
    power_confirm_guard: bool = False,
    local_ui_only: bool = False,
    weather_coexistence: bool = False,
    weather_success_requires_stock: bool = False,
    weather_stock_first: bool = False,
    location_slot_dashboard: bool = False,
    weather_hidden_primary_page: bool = False,
    disable_download: bool = False,
) -> dict[str, object]:
    evidence = _validate_stock_pet_reuse_disassembly(
        disassembly,
        integration_mode=integration_mode,
        local_ui_only=local_ui_only,
        weather_coexistence=weather_coexistence,
        weather_success_requires_stock=weather_success_requires_stock,
        weather_stock_first=weather_stock_first,
        location_slot_dashboard=location_slot_dashboard,
        disable_download=disable_download,
    )
    local_branches = _symbol_block(
        disassembly,
        "ap01_agents_stock_pet_left_entry",
        "ap01_agents_show_page",
    )
    required_markers = (
        "<ap01_agents_find_pet_state>",
        "<ap01_agents_state_read>",
        "<ap01_agents_show_page>",
        "<ap01_agents_restore_pet>",
        "# a00bc464 <stock_pet_left_resume>",
        "# a00bc716 <stock_pet_right_resume>",
        "# a00bda68 <stock_pet_enter_resume>",
        "# a00bc1d2 <stock_key_epilogue>",
    )
    if integration_mode:
        required_markers += ("# a00bfa4e <stock_switch_page>",)
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
                0xA00BC464,
                0xA00BC716,
                0xA00BDA68,
            )
        )
    ):
        raise AgentsDashboardFirmwareError("局部分支恢复与消费出口不是一一对应")
    if (
        not integration_mode
        and not fixed_hidden_primary_pages
        and "# a00bfa4e <stock_switch_page>" in local_branches
    ):
        raise AgentsDashboardFirmwareError(
            "AGENTS 概览右旋仍直接调用切页函数，没有交还原厂分支"
        )
    close_for_resume = _symbol_block(
        disassembly,
        "ap01_agents_close_for_stock_resume",
        "ap01_agents_primary_page_filter_and_switch",
    )
    if (
        "<ap01_agents_close_for_stock_resume>" not in local_branches
        or "<ap01_agents_state_write>" not in close_for_resume
        or "# a00cf8d8 <lv_gif_set_src>" in close_for_resume
        or "<ap01_agents_restore_pet>" in close_for_resume
    ):
        raise AgentsDashboardFirmwareError(
            "AGENTS 概览离开路径没有只关闭状态后交还原厂"
        )
    if fixed_hidden_primary_pages:
        first_close = local_branches.find(
            "<ap01_agents_close_for_stock_resume>"
        )
        first_switch = local_branches.find(
            "# a00bfa4e <stock_switch_page>"
        )
        if (
            local_branches.count(
                "<ap01_agents_close_for_stock_resume>"
            ) != 2
            or not 0 <= first_close < first_switch
            or "<ap01_agents_restore_pet>" in local_branches[
                first_close:first_switch
            ]
        ):
            raise AgentsDashboardFirmwareError(
                "看板到设置的切页前仍会恢复萌宠数据源"
            )
        evidence["overview_left_gif_preserved_until_switch"] = True
    for symbol in (
        "ap01_agents_stock_pet_left_entry",
        "ap01_agents_stock_pet_right_entry",
        "ap01_agents_stock_pet_enter_entry",
    ):
        if f"<{symbol}>:" not in disassembly:
            raise AgentsDashboardFirmwareError(f"局部分支入口缺失：{symbol}")
    if integration_mode:
        page_filter = _symbol_block(
            disassembly,
            "ap01_primary_page_filter_and_switch",
            "ap01_page_settings_find_state",
        )
        if (
            "# a00bfa4e <stock_switch_page>" not in page_filter
            or "<ap01_page_settings_load_mask>" not in page_filter
            or "<ap01_agents_find_pet_state>" not in page_filter
            or "<ap01_agents_show_page>" not in page_filter
            or "<ap01_agents_restore_pet>" not in page_filter
        ):
            raise AgentsDashboardFirmwareError("一级切页过滤调用链检查未通过")
        agents_only = "\n".join(
            (
                _symbol_block(
                    disassembly,
                    "ap01_agents_state_read",
                    "ap01_agents_sink",
                ),
                _symbol_block(
                    disassembly,
                    "ap01_agents_ui_timer_wrapper",
                    "ap01_page_settings_menu_dispatch",
                ),
            )
        ).lower()
        for address in STOCK_PET_FORBIDDEN_CALLEES:
            if f"# {address:08x} <" in agents_only:
                raise AgentsDashboardFirmwareError(
                    f"AGENTS 路径调用了禁止函数：0x{address:08x}"
                )
        evidence["page_filter_callchain"] = {
            "mask_load": _instruction_address(
                page_filter,
                "<ap01_page_settings_load_mask>",
            ),
            "stock_switch": _instruction_address(
                page_filter,
                "# a00bfa4e <stock_switch_page>",
            ),
            "switch_verification": _instruction_address(
                page_filter,
                "# a00be388 <stock_get_dispatch_index>",
            ),
            "failure_restore": _instruction_address(
                page_filter,
                "<ap01_agents_restore_pet>",
                last=True,
            ),
        }
    if shared_page_filter:
        page_filter = _symbol_block(
            disassembly,
            "ap01_agents_primary_page_filter_and_switch",
            "ap01_agents_detail_active",
        )
        required_filter_markers = (
            "<ap01_agents_find_pet_state>",
            "<ap01_agents_show_page>",
            "<ap01_agents_restore_pet>",
            "# a00bfa4e <stock_switch_page>",
            "# a00be388 <stock_get_dispatch_index>",
        )
        missing_filter = [
            marker for marker in required_filter_markers
            if marker not in page_filter
        ]
        if missing_filter:
            raise AgentsDashboardFirmwareError(
                f"共享序号切页过滤缺少原厂调用：{missing_filter[0]}"
            )
        expected_switch_calls = 2 if fixed_hidden_primary_pages else 1
        if page_filter.count("# a00bfa4e <stock_switch_page>") != expected_switch_calls:
            raise AgentsDashboardFirmwareError(
                "共享序号切页过滤调用原厂切页入口的数量不匹配"
            )
        if fixed_hidden_primary_pages:
            direction_one = page_filter.find("c.li\tx5,1")
            direction_two = page_filter.find("c.li\tx5,2", direction_one + 1)
            if weather_hidden_primary_page:
                target_seven = page_filter.find("c.li\tx9,7", direction_two + 1)
                target_three = page_filter.find("c.li\tx9,3", target_seven + 1)
                weather_target = page_filter.find("c.li\tx5,5")
                weather_seven = page_filter.find("c.li\tx9,7", weather_target + 1)
                weather_three = page_filter.find("c.li\tx9,3", weather_seven + 1)
                if not (
                    0 <= direction_one
                    < direction_two
                    < target_seven
                    < target_three
                    and 0 <= weather_target < weather_seven < weather_three
                ):
                    raise AgentsDashboardFirmwareError(
                        "天气隐藏跳过目标与原厂方向不匹配"
                    )
                evidence["calendar_skip_direction_verified"] = True
                evidence["weather_skip_direction_verified"] = True
            else:
                target_five = page_filter.find("c.li\tx9,5", direction_two + 1)
                target_three = page_filter.find("c.li\tx9,3", target_five + 1)
                if not (
                    0 <= direction_one < direction_two < target_five < target_three
                ):
                    raise AgentsDashboardFirmwareError(
                        "日历双向跳过目标与原厂方向不匹配"
                    )
                evidence["calendar_skip_direction_verified"] = True
        evidence["shared_page_filter_callchain"] = {
            "stock_switch": _instruction_address(
                page_filter,
                "# a00bfa4e <stock_switch_page>",
            ),
            "switch_verification": _instruction_address(
                page_filter,
                "# a00be388 <stock_get_dispatch_index>",
            ),
            "show_agents": _instruction_address(
                page_filter,
                "<ap01_agents_show_page>",
            ),
            "restore_pet": _instruction_address(
                page_filter,
                "<ap01_agents_restore_pet>",
            ),
        }
    if power_confirm_guard:
        power_guard = _symbol_block(
            disassembly,
            "ap01_agents_stock_power_confirm_guard",
            "ap01_agents_detail_active",
        )
        required_guard_markers = (
            "# a00b16a4 <stock_set_dev_port_num>",
            "# a0193862 <stock_theme_change_home_page>",
            "# a00bc8ca <stock_power_confirm_resume>",
            "# a00bc1d2 <stock_key_epilogue>",
        )
        missing_guard = [
            marker for marker in required_guard_markers
            if marker not in power_guard
        ]
        if missing_guard:
            raise AgentsDashboardFirmwareError(
                f"功率确认连接保护缺少原厂调用：{missing_guard[0]}"
            )
        if any(power_guard.count(marker) != 1 for marker in required_guard_markers):
            raise AgentsDashboardFirmwareError(
                "功率确认连接保护的原厂调用或继续地址不是一一对应"
            )
        for state_marker in (
            "62fc4cd8",
            "62fcaa00",
            "bne\tx20,x0",
            "x11,3",
        ):
            if state_marker not in power_guard:
                raise AgentsDashboardFirmwareError(
                    f"功率确认连接保护缺少状态断言：{state_marker}"
                )
        evidence["power_confirm_guard_callchain"] = {
            "set_port_offline": _instruction_address(
                power_guard,
                "# a00b16a4 <stock_set_dev_port_num>",
            ),
            "switch_to_clock": _instruction_address(
                power_guard,
                "# a0193862 <stock_theme_change_home_page>",
            ),
            "stock_power_resume": _instruction_address(
                power_guard,
                "# a00bc8ca <stock_power_confirm_resume>",
            ),
            "stock_key_epilogue": _instruction_address(
                power_guard,
                "# a00bc1d2 <stock_key_epilogue>",
            ),
        }
    evidence["local_branch_resume_targets"] = {
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
    evidence["overview_right_stock_resume_only"] = not integration_mode
    evidence["overview_right_closes_state_without_gif_reset"] = True
    return evidence


def _patch_stock_local_branches(
    candidate: bytearray,
    symbols: dict[str, int],
    *,
    integration_mode: bool = False,
    shared_page_filter: bool = False,
    power_confirm_guard: bool = False,
) -> list[ByteRange]:
    allowed: list[ByteRange] = []
    hooks = STOCK_LOCAL_BRANCH_HOOKS
    if integration_mode:
        hooks = (*hooks, OPT_PAGE_FILTER_HOOK)
    elif shared_page_filter:
        hooks = (*hooks, LOCAL_UI_SHARED_PAGE_FILTER_HOOK)
    if power_confirm_guard:
        hooks = (*hooks, LOCAL_UI_POWER_CONFIRM_GUARD_HOOK)
    for (
        hook_offset,
        hook_original,
        trampoline_offset,
        symbol,
        _resume_address,
        label,
    ) in hooks:
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
    *,
    integration_mode: bool = False,
    shared_page_filter: bool = False,
    power_confirm_guard: bool = False,
    ui_timer_wrapper: bool = False,
    additional_allowed: tuple[ByteRange, ...] = (),
) -> None:
    callback_regions = [
        (KEY_CALLBACK_HIGH_OFFSET, KEY_CALLBACK_HIGH_ORIGINAL),
        (KEY_CALLBACK_LOW_OFFSET, KEY_CALLBACK_LOW_ORIGINAL),
    ]
    if not ui_timer_wrapper:
        callback_regions.extend(
            (
                (UI_CALLBACK_LUI, INSTRUCTION_EXPECTED[UI_CALLBACK_LUI]),
                (UI_CALLBACK_ADDI, INSTRUCTION_EXPECTED[UI_CALLBACK_ADDI]),
            )
        )
    for offset, expected in callback_regions:
        end = offset + len(expected)
        if stage[offset:end] != expected or candidate[offset:end] != expected:
            raise AgentsDashboardFirmwareError("原厂全局回调地址装入字节发生变化")

    hooks = STOCK_LOCAL_BRANCH_HOOKS
    if integration_mode:
        hooks = (*hooks, OPT_PAGE_FILTER_HOOK)
    elif shared_page_filter:
        hooks = (*hooks, LOCAL_UI_SHARED_PAGE_FILTER_HOOK)
    if power_confirm_guard:
        hooks = (*hooks, LOCAL_UI_POWER_CONFIRM_GUARD_HOOK)
    allowed_offsets = {
        offset
        for hook_offset, hook_original, *_rest in hooks
        for offset in range(hook_offset, hook_offset + len(hook_original))
    }
    for region in additional_allowed:
        allowed_offsets.update(range(region.start, region.end))
    callback_start, callback_end = STOCK_KEY_CALLBACK_RANGE
    for offset in range(callback_start, callback_end):
        if offset not in allowed_offsets and candidate[offset] != stage[offset]:
            raise AgentsDashboardFirmwareError(
                f"原厂键值回调非局部分支字节发生变化：0x{offset:06x}"
            )
    power_start, power_end = STOCK_POWER_CONFIRM_RANGE
    if (
        not power_confirm_guard
        and candidate[power_start:power_end] != stage[power_start:power_end]
    ):
        raise AgentsDashboardFirmwareError("原厂功率确认路径发生变化")


def _assert_stock_transport_unchanged(stage: bytes, candidate: bytes) -> None:
    if (
        stage[
            LOADER_TRAMPOLINE_OFFSET :
            LOADER_TRAMPOLINE_OFFSET + len(LOADER_TRAMPOLINE_ORIGINAL)
        ]
        != LOADER_TRAMPOLINE_ORIGINAL
        or candidate[
            LOADER_TRAMPOLINE_OFFSET :
            LOADER_TRAMPOLINE_OFFSET + len(LOADER_TRAMPOLINE_ORIGINAL)
        ]
        != LOADER_TRAMPOLINE_ORIGINAL
    ):
        raise AgentsDashboardFirmwareError("后台同步跳板不再保持原字节")
    if (
        stage[
            LOCATION_TRAMPOLINE_OFFSET :
            LOCATION_TRAMPOLINE_OFFSET + len(LOCATION_TRAMPOLINE_ORIGINAL)
        ]
        != LOCATION_TRAMPOLINE_ORIGINAL
        or candidate[
            LOCATION_TRAMPOLINE_OFFSET :
            LOCATION_TRAMPOLINE_OFFSET + len(LOCATION_TRAMPOLINE_ORIGINAL)
        ]
        != LOCATION_TRAMPOLINE_ORIGINAL
    ):
        raise AgentsDashboardFirmwareError("位置占位跳板不再保持原字节")
    for offset, expected in INSTRUCTION_EXPECTED.items():
        end = offset + len(expected)
        if stage[offset:end] != expected or candidate[offset:end] != expected:
            raise AgentsDashboardFirmwareError(
                f"原厂后台指令区发生变化：0x{offset:06x}"
            )
    for offset, capacity, expected, label in URL_REGIONS:
        original = expected.ljust(capacity, b"\0")
        end = offset + capacity
        if stage[offset:end] != original or candidate[offset:end] != original:
            raise AgentsDashboardFirmwareError(f"原厂{label}发生变化")


def _patch_stock_transport(
    candidate: bytearray,
    symbols: dict[str, int],
    *,
    url_base: str,
    refresh_seconds: int,
    location_independent: bool,
    weather_coexistence: bool = False,
    patch_stock_https_call: bool = False,
    post_weather_fetch: bool = False,
    location_slot_dashboard: bool = False,
) -> list[ByteRange]:
    allowed: list[ByteRange] = []
    url_bytes = url_base.encode("ascii")
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
    web_wrapper = symbols["ap01_agents_webclient_wrapper"]
    allowed.append(
        _replace(
            candidate,
            LOADER_TRAMPOLINE_OFFSET,
            LOADER_TRAMPOLINE_ORIGINAL,
            _absolute_tail_jump(web_wrapper),
            "后台同步跳板",
        )
    )
    if not location_independent:
        raise AgentsDashboardFirmwareError("真实数据固件必须解除天气位置依赖")
    if (
        bytes(
            candidate[
                LOCATION_TRAMPOLINE_OFFSET :
                LOCATION_TRAMPOLINE_OFFSET + len(LOCATION_TRAMPOLINE_ORIGINAL)
            ]
        )
        != LOCATION_TRAMPOLINE_ORIGINAL
    ):
        raise AgentsDashboardFirmwareError("位置占位跳板区间不再是全零")
    location_stub = symbols["ap01_agents_location_stub"]
    allowed.append(
        _replace(
            candidate,
            LOCATION_TRAMPOLINE_OFFSET,
            LOCATION_TRAMPOLINE_ORIGINAL,
            _absolute_tail_jump(location_stub),
            "位置占位跳板",
        )
    )
    allowed.append(
        _replace(
            candidate,
            LOCATION_LOOKUP_CALL,
            INSTRUCTION_EXPECTED[LOCATION_LOOKUP_CALL],
            _encode_jal(
                XIP_DELTA + LOCATION_LOOKUP_CALL,
                LOCATION_TRAMPOLINE_VA,
            ),
            "位置取得调用",
        )
    )
    ui_wrapper = symbols["ap01_agents_ui_timer_wrapper"]
    ui_high, ui_low = _absolute_lui_addi(ui_wrapper, register=10)
    allowed.append(
        _replace(
            candidate,
            UI_CALLBACK_LUI,
            INSTRUCTION_EXPECTED[UI_CALLBACK_LUI],
            ui_high,
            "界面定时包装地址高位",
        )
    )
    allowed.append(
        _replace(
            candidate,
            UI_CALLBACK_ADDI,
            INSTRUCTION_EXPECTED[UI_CALLBACK_ADDI],
            ui_low,
            "界面定时包装地址低位",
        )
    )
    if not weather_coexistence:
        sink = symbols["ap01_agents_sink"]
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
    if patch_stock_https_call:
        allowed.append(
            _replace(
                candidate,
                HTTPS_PERFORM_CALL,
                INSTRUCTION_EXPECTED[HTTPS_PERFORM_CALL],
                _encode_jal(
                    XIP_DELTA + HTTPS_PERFORM_CALL,
                    LOADER_TRAMPOLINE_VA,
                ),
                "原厂 HTTPS 网络调用",
            )
        )
    if post_weather_fetch:
        entry = symbols["ap01_agents_post_weather_fetch_entry"]
        if (
            bytes(
                candidate[
                    POST_WEATHER_FETCH_TRAMPOLINE_OFFSET :
                    POST_WEATHER_FETCH_TRAMPOLINE_OFFSET
                    + len(POST_WEATHER_FETCH_TRAMPOLINE_ORIGINAL)
                ]
            )
            != POST_WEATHER_FETCH_TRAMPOLINE_ORIGINAL
        ):
            raise AgentsDashboardFirmwareError("天气后置看板近跳板区间不再是全零")
        allowed.append(
            _replace(
                candidate,
                POST_WEATHER_FETCH_HOOK,
                POST_WEATHER_FETCH_HOOK_ORIGINAL,
                _encode_jal(
                    XIP_DELTA + POST_WEATHER_FETCH_HOOK,
                    POST_WEATHER_FETCH_TRAMPOLINE_VA,
                ),
                "原厂天气返回后置看板入口",
            )
        )
        allowed.append(
            _replace(
                candidate,
                POST_WEATHER_FETCH_TRAMPOLINE_OFFSET,
                POST_WEATHER_FETCH_TRAMPOLINE_ORIGINAL,
                _absolute_tail_jump(entry),
                "原厂天气返回后置看板近跳板",
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

    if location_slot_dashboard:
        location_format, _city_format = _request_formats()
        replacements = (url_bytes, location_format)
        for (offset, capacity, expected, label), replacement in zip(
            URL_REGIONS[:2],
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
    elif not weather_coexistence:
        location_format, city_format = _request_formats()
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
    return allowed


def build_sync_payload(
    stage_path: Path,
    build_directory: Path,
    *,
    tool_revision: dict[str, object],
    extra_objects: tuple[Path, ...] = (),
    required_extra_symbols: tuple[str, ...] = (),
    reuse_stock_pet: bool = False,
    integration_mode: bool = False,
    shared_page_filter: bool = False,
    fixed_hidden_primary_pages: bool = False,
    weather_hidden_primary_page: bool = False,
    power_confirm_guard: bool = False,
    local_ui_only: bool = False,
    endpoint_urls: tuple[str, ...] = (),
    endpoint_timeout_seconds: int = 0,
    disable_dashboard_download: bool = False,
    weather_coexistence: bool = False,
    weather_dual_request: bool = False,
    weather_success_requires_stock: bool = False,
    weather_stock_first: bool = False,
    weather_solo_request: bool = False,
    post_weather_fetch: bool = False,
    location_slot_dashboard: bool = False,
    round_diagnostic: bool = False,
    download_diagnostic: bool = False,
    result_diagnostic: bool = False,
    publish_diagnostic: bool = False,
    adoption_diagnostic: bool = False,
    standalone_timer: bool = False,
    refresh_seconds: int = 300,
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
    loader_object = selected / (
        "local-ui-loader.o" if local_ui_only else "result-loader.o"
    )
    endpoint_header = selected / "endpoint-config.h"
    endpoint_lines = [
        f"#define AP01_AGENTS_ENDPOINT_COUNT {len(endpoint_urls)}u",
        (
            "#define AP01_AGENTS_DISABLE_DOWNLOAD "
            f"{1 if disable_dashboard_download else 0}u"
        ),
        (
            "#define AP01_AGENTS_ENDPOINT_TIMEOUT_SECONDS "
            f"{endpoint_timeout_seconds}u"
        ),
        (
            "#define AP01_AGENTS_WEATHER_COEXISTENCE "
            f"{1 if weather_coexistence else 0}u"
        ),
        (
            "#define AP01_AGENTS_WEATHER_DUAL_REQUEST "
            f"{1 if weather_dual_request else 0}u"
        ),
        (
            "#define AP01_AGENTS_WEATHER_SUCCESS_REQUIRES_STOCK "
            f"{1 if weather_success_requires_stock else 0}u"
        ),
        (
            "#define AP01_AGENTS_STOCK_WEATHER_FIRST "
            f"{1 if weather_stock_first else 0}u"
        ),
        (
            "#define AP01_AGENTS_WEATHER_SOLO_REQUEST "
            f"{1 if weather_solo_request else 0}u"
        ),
        (
            "#define AP01_AGENTS_POST_WEATHER_FETCH "
            f"{1 if post_weather_fetch else 0}u"
        ),
        (
            "#define AP01_AGENTS_LOCATION_SLOT_DASHBOARD "
            f"{1 if location_slot_dashboard else 0}u"
        ),
        (
            "#define AP01_AGENTS_ROUND_DIAGNOSTIC "
            f"{1 if round_diagnostic else 0}u"
        ),
        (
            "#define AP01_AGENTS_DOWNLOAD_DIAGNOSTIC "
            f"{1 if download_diagnostic else 0}u"
        ),
        (
            "#define AP01_AGENTS_RESULT_DIAGNOSTIC "
            f"{1 if result_diagnostic else 0}u"
        ),
        (
            "#define AP01_AGENTS_PUBLISH_DIAGNOSTIC "
            f"{1 if publish_diagnostic else 0}u"
        ),
        f"#define AP01_AGENTS_ADOPTION_DIAGNOSTIC {1 if adoption_diagnostic else 0}u",
    ]
    if standalone_timer:
        endpoint_lines.append("#define AP01_AGENTS_STANDALONE_TIMER 1u")
        endpoint_lines.append(
            f"#define AP01_AGENTS_REFRESH_SECONDS {refresh_seconds}u"
        )
    for index, endpoint in enumerate(endpoint_urls, start=1):
        endpoint_lines.append(
            f'#define AP01_AGENTS_ENDPOINT_{index} "{endpoint}"'
        )
    endpoint_header.write_text("\n".join(endpoint_lines) + "\n", encoding="ascii")
    assets_source = selected / "fallback-assets.S"
    assets_object = selected / "fallback-assets.o"
    elf = selected / "agents-sync.elf"
    binary = selected / "agents-sync.bin"
    map_path = selected / "agents-sync.map"
    disassembly_path = selected / "agents-sync.disassembly.txt"
    readelf_path = selected / "agents-sync.readelf.txt"
    _write_asset_assembly(assets_source, assets)
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
    if integration_mode:
        assembler_arguments.extend(["--defsym", "OPT_INTEGRATION=1"])
    if power_confirm_guard:
        assembler_arguments.extend(["--defsym", "POWER_CONFIRM_GUARD=1"])
    if fixed_hidden_primary_pages:
        assembler_arguments.extend(
            ["--defsym", "FIXED_HIDDEN_PRIMARY_PAGES=1"]
        )
    if weather_hidden_primary_page:
        if not fixed_hidden_primary_pages:
            raise AgentsDashboardFirmwareError("天气隐藏必须基于固定隐藏一级页")
        assembler_arguments.extend(
            ["--defsym", "FIXED_WEATHER_HIDDEN_PRIMARY_PAGES=1"]
        )
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
            "-include",
            endpoint_header,
            "-c",
            LOCAL_UI_LOADER_SOURCE if local_ui_only else LOADER_SOURCE,
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
            *resolved_extra_objects,
            assets_object,
        ]
    )
    _run([copier, "-O", "binary", "-j", ".payload", elf, binary])
    payload = binary.read_bytes()
    if not payload or len(payload) > PAYLOAD_CAPACITY:
        raise AgentsDashboardFirmwareError("同步载荷为空或超过固定候选空间")
    symbols = _symbols(nm, elf)
    selected_required_symbols = (
        LOCAL_UI_REQUIRED_SYMBOLS if local_ui_only else REQUIRED_SYMBOLS
    ) + required_extra_symbols
    if reuse_stock_pet:
        selected_required_symbols += STOCK_PET_REQUIRED_SYMBOLS
    if post_weather_fetch:
        selected_required_symbols += ("ap01_agents_post_weather_fetch_entry",)
    if standalone_timer:
        selected_required_symbols += (
            "ap01_agents_standalone_timer_ensure",
            "ap01_agents_standalone_timer_cb",
        )
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
    if round_diagnostic or download_diagnostic or result_diagnostic or publish_diagnostic or adoption_diagnostic:
        diagnostic_symbols = [
            "agents_diagnostic_set_source",
            "agents_diagnostic_show",
        ]
        if not result_diagnostic and not publish_diagnostic and not adoption_diagnostic:
            diagnostic_symbols.append("agents_diagnostic_advance")
        else:
            diagnostic_symbols.extend(
                ["write_record_diagnostic"] if publish_diagnostic or adoption_diagnostic else
                ["agents_result_diagnostic_perform", "agents_result_diagnostic_write_record"]
            )
        for symbol in diagnostic_symbols:
            if f"<{symbol}>:" not in disassembly:
                raise AgentsDashboardFirmwareError(
                    f"分轮诊断符号缺失：{symbol}"
                )
        download_block = _symbol_block(
            disassembly,
            "ap01_agents_download_package",
            "ap01_agents_webclient_wrapper",
        )
        if download_diagnostic or result_diagnostic or publish_diagnostic or adoption_diagnostic:
            location_block = _symbol_block(
                disassembly,
                "ap01_agents_location_stub",
                "ap01_agents_webclient_wrapper",
            )
            wrapper_block = _symbol_block(
                disassembly,
                "ap01_agents_webclient_wrapper",
                "ap01_agents_apply_current",
            )
            download_points_valid = (
                (
                    download_block.count("<agents_diagnostic_advance>") >= 3
                    if download_diagnostic
                    else download_block.count("<write_record_diagnostic>") == 1
                    and "<agents_result_diagnostic_perform>" not in download_block
                    if publish_diagnostic or adoption_diagnostic
                    else download_block.count(
                        "<agents_result_diagnostic_perform>"
                    ) == 1
                    and download_block.count(
                        "<agents_result_diagnostic_write_record>"
                    ) == 1
                    and "<agents_diagnostic_advance>" not in download_block
                )
            )
            if (
                not download_points_valid
                or "<agents_diagnostic_advance>" in location_block
                or "<agents_diagnostic_advance>" in wrapper_block
            ):
                raise AgentsDashboardFirmwareError("下载诊断写入点范围不符合 DESIGN")
        else:
            diagnostic_blocks = (
                _symbol_block(
                    disassembly,
                    "ap01_agents_location_stub",
                    "ap01_agents_webclient_wrapper",
                ),
                _symbol_block(
                    disassembly,
                    "ap01_agents_webclient_wrapper",
                    "ap01_agents_apply_current",
                ),
                download_block,
            )
            if any("<agents_diagnostic_advance>" not in block for block in diagnostic_blocks):
                raise AgentsDashboardFirmwareError("分轮诊断三个阶段写入点不完整")
        timer_block = _symbol_block(
            disassembly,
            "ap01_agents_ui_timer_wrapper",
            "ap01_agents_loader_end_marker",
        )
        if "<agents_diagnostic_show>" not in timer_block:
            raise AgentsDashboardFirmwareError("分轮诊断屏端导出入口缺失")
    if post_weather_fetch:
        post_entry = _symbol_block(
            disassembly,
            "ap01_agents_post_weather_fetch_entry",
            "ap01_agents_webclient_wrapper",
        )
        if (
            "c.mv\tx23,x10" not in post_entry
            or "addi\tx10,x8,-436" not in post_entry
            or "<ap01_agents_post_weather_download>" not in post_entry
            or "lw\tx10,1904(x18)" not in post_entry
            or "lui\tx5,0xa00b7" not in post_entry
            or "addi\tx5,x5,608" not in post_entry
            or "c.jr\tx5" not in post_entry
        ):
            raise AgentsDashboardFirmwareError("天气后置看板入口反汇编不符合 DESIGN")
    if standalone_timer:
        timer_cb_block = _symbol_block(
            disassembly,
            "ap01_agents_standalone_timer_cb",
            "ap01_agents_standalone_timer_ensure",
        )
        ensure_tail = disassembly.split(
            "<ap01_agents_standalone_timer_ensure>:", 1
        )[1]
        ensure_block = re.split(r"\n[0-9a-f]+ <", ensure_tail, maxsplit=1)[0]
        passthrough_wrapper = _symbol_block(
            disassembly,
            "ap01_agents_webclient_wrapper",
            "ap01_agents_apply_current",
        )
        ensure_caller = _symbol_block(
            disassembly,
            "ap01_agents_ui_timer_wrapper",
            "ap01_agents_loader_end_marker",
        )
        if (
            timer_cb_block.count("<fw_malloc>") != 2
            or timer_cb_block.count("<fw_free>") != 2
            or timer_cb_block.count("<ap01_agents_download_package>") != 1
            or timer_cb_block.count("<fw_stock_timer_schedule>") != 1
            or ensure_block.count("<fw_malloc>") != 1
            or ensure_block.count("<fw_stock_timer_init>") != 1
            or ensure_block.count("<fw_stock_timer_schedule>") != 1
            or "<ap01_agents_download_package>" in passthrough_wrapper
            or "<ap01_agents_standalone_timer_ensure>" not in ensure_caller
        ):
            raise AgentsDashboardFirmwareError(
                "独立取包定时器注册或回调反汇编不符合 DESIGN"
            )
    if local_ui_only:
        required_callees = LOCAL_UI_REQUIRED_CALLEES
        if power_confirm_guard:
            required_callees += LOCAL_UI_POWER_GUARD_REQUIRED_CALLEES
    else:
        required_callees = (
            STOCK_PET_REQUIRED_CALLEES
            if reuse_stock_pet
            else LEGACY_REQUIRED_CALLEES
        )
        if weather_coexistence and not location_slot_dashboard:
            required_callees += (0xA00ACBEA,)
    for address in required_callees:
        if f"{address:08x}" not in disassembly.lower():
            raise AgentsDashboardFirmwareError(
                f"同步载荷缺少已定位原厂调用：0x{address:08x}"
            )
    callchain_evidence: dict[str, object] | None = None
    route_validation: dict[str, int] | None = None
    if reuse_stock_pet:
        callchain_evidence = _validate_stock_local_branches_disassembly(
            disassembly,
            integration_mode=integration_mode,
            shared_page_filter=shared_page_filter,
            fixed_hidden_primary_pages=fixed_hidden_primary_pages,
            power_confirm_guard=power_confirm_guard,
            local_ui_only=local_ui_only,
            weather_coexistence=weather_coexistence,
            weather_success_requires_stock=weather_success_requires_stock,
            weather_stock_first=weather_stock_first,
            location_slot_dashboard=location_slot_dashboard,
            weather_hidden_primary_page=weather_hidden_primary_page,
            disable_download=disable_dashboard_download,
        )
        if local_ui_only:
            if b"/tmp/" in payload:
                raise AgentsDashboardFirmwareError(
                    "局部界面载荷仍包含临时文件路径"
                )
            callchain_evidence["temporary_paths_absent"] = True
        route_validation = validate_stock_local_branch_routes()
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
    *,
    tool_revision: dict[str, object],
    url_base: str = "",
    refresh_seconds: int = 0,
    extra_objects: tuple[Path, ...] = (),
    required_extra_symbols: tuple[str, ...] = (),
    candidate_mutators: tuple[
        Callable[[bytearray, dict[str, int]], list[ByteRange]], ...
    ] = (),
    expected_output_name: str = SYNC_OUTPUT_FILENAME,
    accepted_output_names: tuple[str, ...] = (),
    implemented_scope_extra: tuple[str, ...] = (),
    reuse_stock_pet: bool = False,
    local_ui_only: bool = False,
    shared_page_filter: bool = False,
    fixed_hidden_primary_pages: bool = False,
    weather_hidden_primary_page: bool = False,
    power_confirm_guard: bool = False,
    interaction_name: str = "FW-AGENTS-008",
    endpoint_urls: tuple[str, ...] = (),
    endpoint_timeout_seconds: int = 0,
    weather_coexistence: bool = False,
    round_diagnostic: bool = False,
    download_diagnostic: bool = False,
    result_diagnostic: bool = False,
    publish_diagnostic: bool = False,
    adoption_diagnostic: bool = False,
    location_slot_dashboard: bool = False,
    standalone_timer: bool = False,
) -> SyncFirmwareResult:
    if tool_revision.get("scoped_code_dirty") is not False:
        raise AgentsDashboardFirmwareError("制作代码尚未提交，不能冻结同步实验成品")
    output = output_path.expanduser().resolve()
    integration_mode = False
    if output.name not in (expected_output_name, *accepted_output_names):
        raise AgentsDashboardFirmwareError(
            "固件输出文件名不符合当前制作类型"
        )
    live_data_enabled = expected_output_name in (
        LIVE_DATA_LOCATION_INDEPENDENT_OUTPUT_FILENAME,
        LIVE_DATA_VALIDATED_PACKAGE_OUTPUT_FILENAME,
        LIVE_DATA_ENDPOINT_FAILOVER_OUTPUT_FILENAME,
        LIVE_DATA_FIXED_PRIMARY_PAGES_OUTPUT_FILENAME,
        LIVE_DATA_WEATHER_ROUND_ROBIN_OUTPUT_FILENAME,
        LIVE_DATA_ROUND_DIAGNOSTIC_OUTPUT_FILENAME,
        LIVE_DATA_DOWNLOAD_DIAGNOSTIC_OUTPUT_FILENAME,
        LIVE_DATA_RESULT_DIAGNOSTIC_OUTPUT_FILENAME,
        LIVE_DATA_PUBLISH_DIAGNOSTIC_OUTPUT_FILENAME,
        LIVE_DATA_ADOPTION_DIAGNOSTIC_OUTPUT_FILENAME,
        LIVE_DATA_STABLE_ADOPTION_OUTPUT_FILENAME,
        LIVE_DATA_WEATHER_AGENTS_DUAL_REQUEST_OUTPUT_FILENAME,
        LIVE_DATA_STOCK_HTTPS_DUAL_REQUEST_OUTPUT_FILENAME,
        LIVE_DATA_WEATHER_PRESERVED_DUAL_REQUEST_OUTPUT_FILENAME,
        LIVE_DATA_WEATHER_STOCK_FIRST_DUAL_REQUEST_OUTPUT_FILENAME,
        LIVE_DATA_WEATHER_SOLO_REQUEST_OUTPUT_FILENAME,
        LIVE_DATA_STOCK_HTTPS_UNTOUCHED_OUTPUT_FILENAME,
        LIVE_DATA_POST_WEATHER_FETCH_OUTPUT_FILENAME,
        LIVE_DATA_LOCATION_SLOT_DASHBOARD_OUTPUT_FILENAME,
        LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_OUTPUT_FILENAME,
        LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_V2_OUTPUT_FILENAME,
    )
    validated_package_candidate = (
        expected_output_name == LIVE_DATA_VALIDATED_PACKAGE_OUTPUT_FILENAME
    )
    endpoint_failover_candidate = (
        expected_output_name in (
            LIVE_DATA_ENDPOINT_FAILOVER_OUTPUT_FILENAME,
            LIVE_DATA_FIXED_PRIMARY_PAGES_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_ROUND_ROBIN_OUTPUT_FILENAME,
            LIVE_DATA_ROUND_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_DOWNLOAD_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_RESULT_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_PUBLISH_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_ADOPTION_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_STABLE_ADOPTION_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_AGENTS_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_STOCK_HTTPS_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_PRESERVED_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_STOCK_FIRST_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_SOLO_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_STOCK_HTTPS_UNTOUCHED_OUTPUT_FILENAME,
            LIVE_DATA_POST_WEATHER_FETCH_OUTPUT_FILENAME,
            LIVE_DATA_LOCATION_SLOT_DASHBOARD_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_V2_OUTPUT_FILENAME,
        )
    )
    fixed_primary_pages_candidate = (
        expected_output_name
        in (
            LIVE_DATA_FIXED_PRIMARY_PAGES_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_ROUND_ROBIN_OUTPUT_FILENAME,
            LIVE_DATA_ROUND_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_DOWNLOAD_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_RESULT_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_PUBLISH_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_ADOPTION_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_STABLE_ADOPTION_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_AGENTS_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_STOCK_HTTPS_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_PRESERVED_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_STOCK_FIRST_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_SOLO_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_STOCK_HTTPS_UNTOUCHED_OUTPUT_FILENAME,
            LIVE_DATA_POST_WEATHER_FETCH_OUTPUT_FILENAME,
            LIVE_DATA_LOCATION_SLOT_DASHBOARD_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_V2_OUTPUT_FILENAME,
        )
    )
    weather_coexistence_candidate = (
        expected_output_name in (
            LIVE_DATA_WEATHER_ROUND_ROBIN_OUTPUT_FILENAME,
            LIVE_DATA_ROUND_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_DOWNLOAD_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_RESULT_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_PUBLISH_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_ADOPTION_DIAGNOSTIC_OUTPUT_FILENAME,
            LIVE_DATA_STABLE_ADOPTION_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_AGENTS_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_STOCK_HTTPS_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_PRESERVED_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_STOCK_FIRST_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_SOLO_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_STOCK_HTTPS_UNTOUCHED_OUTPUT_FILENAME,
            LIVE_DATA_POST_WEATHER_FETCH_OUTPUT_FILENAME,
            LIVE_DATA_LOCATION_SLOT_DASHBOARD_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_V2_OUTPUT_FILENAME,
        )
    )
    weather_dual_request_candidate = (
        expected_output_name
        in (
            LIVE_DATA_WEATHER_AGENTS_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_STOCK_HTTPS_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_PRESERVED_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_STOCK_FIRST_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_SOLO_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_STOCK_HTTPS_UNTOUCHED_OUTPUT_FILENAME,
            LIVE_DATA_POST_WEATHER_FETCH_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_V2_OUTPUT_FILENAME,
        )
    )
    weather_solo_request_candidate = (
        expected_output_name == LIVE_DATA_WEATHER_SOLO_REQUEST_OUTPUT_FILENAME
    )
    stock_https_dual_request_candidate = (
        expected_output_name
        in (
            LIVE_DATA_STOCK_HTTPS_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_PRESERVED_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_STOCK_FIRST_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_SOLO_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_V2_OUTPUT_FILENAME,
        )
    )
    weather_preserved_dual_request_candidate = (
        expected_output_name
        in (
            LIVE_DATA_WEATHER_PRESERVED_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_STOCK_FIRST_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_SOLO_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_STOCK_HTTPS_UNTOUCHED_OUTPUT_FILENAME,
            LIVE_DATA_POST_WEATHER_FETCH_OUTPUT_FILENAME,
            LIVE_DATA_LOCATION_SLOT_DASHBOARD_OUTPUT_FILENAME,
        )
    )
    post_weather_fetch_candidate = (
        expected_output_name == LIVE_DATA_POST_WEATHER_FETCH_OUTPUT_FILENAME
    )
    location_slot_dashboard_candidate = (
        expected_output_name == LIVE_DATA_LOCATION_SLOT_DASHBOARD_OUTPUT_FILENAME
    )
    weather_stock_first_dual_request_candidate = (
        expected_output_name
        in (
            LIVE_DATA_WEATHER_STOCK_FIRST_DUAL_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_WEATHER_SOLO_REQUEST_OUTPUT_FILENAME,
            LIVE_DATA_STOCK_HTTPS_UNTOUCHED_OUTPUT_FILENAME,
            LIVE_DATA_POST_WEATHER_FETCH_OUTPUT_FILENAME,
        )
    )
    allowed_variants = {
        (
            LOCAL_UI_STOCK_RESUME_OUTPUT_FILENAME,
            True,
            False,
            False,
            False,
            "FW-AGENTS-008",
        ),
        (
            LOCAL_UI_BASE_SAFE_OUTPUT_FILENAME,
            True,
            True,
            False,
            True,
            "FW-AGENTS-010",
        ),
        (
            LIVE_DATA_LOCATION_INDEPENDENT_OUTPUT_FILENAME,
            False,
            True,
            False,
            True,
            "FW-AGENTS-014",
        ),
        (
            LIVE_DATA_VALIDATED_PACKAGE_OUTPUT_FILENAME,
            False,
            True,
            False,
            True,
            "FW-AGENTS-014",
        ),
        (
            LIVE_DATA_ENDPOINT_FAILOVER_OUTPUT_FILENAME,
            False,
            True,
            False,
            True,
            "FW-AGENTS-014",
        ),
        (
            LIVE_DATA_FIXED_PRIMARY_PAGES_OUTPUT_FILENAME,
            False,
            True,
            True,
            True,
            "FW-PAGE-011",
        ),
        (
            LIVE_DATA_WEATHER_ROUND_ROBIN_OUTPUT_FILENAME,
            False,
            True,
            True,
            True,
            "FW-PAGE-011",
        ),
        (
            LIVE_DATA_ROUND_DIAGNOSTIC_OUTPUT_FILENAME,
            False,
            True,
            True,
            True,
            "FW-PAGE-011",
        ),
        (
            LIVE_DATA_DOWNLOAD_DIAGNOSTIC_OUTPUT_FILENAME,
            False,
            True,
            True,
            True,
            "FW-PAGE-011",
        ),
        (
            LIVE_DATA_RESULT_DIAGNOSTIC_OUTPUT_FILENAME,
            False,
            True,
            True,
            True,
            "FW-PAGE-011",
        ),
        (
            LIVE_DATA_PUBLISH_DIAGNOSTIC_OUTPUT_FILENAME,
            False, True, True, True, "FW-PAGE-011",
        ),
        (LIVE_DATA_ADOPTION_DIAGNOSTIC_OUTPUT_FILENAME, False, True, True, True, "FW-PAGE-011"),
        (LIVE_DATA_STABLE_ADOPTION_OUTPUT_FILENAME, False, True, True, True, "FW-PAGE-011"),
        (LIVE_DATA_WEATHER_AGENTS_DUAL_REQUEST_OUTPUT_FILENAME, False, True, True, True, "FW-PAGE-011"),
        (LIVE_DATA_STOCK_HTTPS_DUAL_REQUEST_OUTPUT_FILENAME, False, True, True, True, "FW-PAGE-011"),
        (LIVE_DATA_WEATHER_PRESERVED_DUAL_REQUEST_OUTPUT_FILENAME, False, True, True, True, "FW-PAGE-011"),
        (LIVE_DATA_WEATHER_STOCK_FIRST_DUAL_REQUEST_OUTPUT_FILENAME, False, True, True, True, "FW-PAGE-011"),
        (LIVE_DATA_WEATHER_SOLO_REQUEST_OUTPUT_FILENAME, False, True, True, True, "FW-PAGE-011"),
        (LIVE_DATA_STOCK_HTTPS_UNTOUCHED_OUTPUT_FILENAME, False, True, True, True, "FW-PAGE-011"),
        (LIVE_DATA_POST_WEATHER_FETCH_OUTPUT_FILENAME, False, True, True, True, "FW-PAGE-011"),
        (LIVE_DATA_LOCATION_SLOT_DASHBOARD_OUTPUT_FILENAME, False, True, True, True, "FW-PAGE-011"),
        (LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_OUTPUT_FILENAME, False, True, True, True, "FW-PAGE-011"),
        (LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_V2_OUTPUT_FILENAME, False, True, True, True, "FW-PAGE-011"),
    }
    if (
        not reuse_stock_pet
        or (
            expected_output_name,
            local_ui_only,
            shared_page_filter,
            fixed_hidden_primary_pages,
            power_confirm_guard,
            interaction_name,
        ) not in allowed_variants
    ):
        raise AgentsDashboardFirmwareError(
            "AGENTS 固件参数不属于已记录的局部分支方案"
        )
    if live_data_enabled:
        if not 10 <= refresh_seconds <= 7200:
            raise AgentsDashboardFirmwareError("刷新周期必须在 10～7200 秒之间")
    if live_data_enabled and (not endpoint_failover_candidate or endpoint_urls):
        try:
            url_bytes = url_base.encode("ascii")
        except UnicodeEncodeError as error:
            raise AgentsDashboardFirmwareError("局域网取包地址必须是 ASCII") from error
        if not url_base.startswith("http://") or len(url_bytes) + 1 > 40:
            raise AgentsDashboardFirmwareError(
                "局域网取包地址必须使用 HTTP 且不超过 39 字节"
            )
    if endpoint_failover_candidate:
        if endpoint_urls:
            if not 1 <= len(endpoint_urls) <= 10:
                raise AgentsDashboardFirmwareError("顺序取数地址必须配置 1～10 项")
            if len(set(endpoint_urls)) != len(endpoint_urls):
                raise AgentsDashboardFirmwareError("顺序取数地址不能重复")
            for endpoint in endpoint_urls:
                try:
                    endpoint_bytes = endpoint.encode("ascii")
                except UnicodeEncodeError as error:
                    raise AgentsDashboardFirmwareError(
                        "顺序取数地址必须使用 ASCII"
                    ) from error
                if not endpoint.startswith("http://") or len(endpoint_bytes) + 1 > 40:
                    raise AgentsDashboardFirmwareError(
                        "顺序取数地址必须使用 HTTP 且不超过 39 字节"
                    )
                if any(
                    character.isspace() or character in {'"', "\\"}
                    for character in endpoint
                ):
                    raise AgentsDashboardFirmwareError(
                        "顺序取数地址不能包含空白、引号或反斜杠"
                    )
            if not 1 <= endpoint_timeout_seconds <= 30:
                raise AgentsDashboardFirmwareError(
                    "单地址无进展超时必须在 1～30 秒之间"
                )
            url_base = endpoint_urls[0]
        elif endpoint_timeout_seconds != 0:
            raise AgentsDashboardFirmwareError("无地址公开固件的超时值必须是 0")
    elif endpoint_urls or endpoint_timeout_seconds:
        raise AgentsDashboardFirmwareError("单地址候选不能携带顺序取数配置")
    if not integration_mode and (
        extra_objects or required_extra_symbols or candidate_mutators
    ):
        raise AgentsDashboardFirmwareError("局部分支观察成品不允许组合其他界面改写")
    stage_selected, stage = _read_stage(stage_path)
    payload_result = build_sync_payload(
        stage_selected,
        build_directory,
        tool_revision=tool_revision,
        extra_objects=extra_objects,
        required_extra_symbols=required_extra_symbols,
        reuse_stock_pet=reuse_stock_pet,
        integration_mode=integration_mode,
        shared_page_filter=shared_page_filter,
        fixed_hidden_primary_pages=fixed_hidden_primary_pages,
        weather_hidden_primary_page=weather_hidden_primary_page,
        power_confirm_guard=power_confirm_guard,
        local_ui_only=local_ui_only,
        endpoint_urls=endpoint_urls,
        endpoint_timeout_seconds=endpoint_timeout_seconds,
        disable_dashboard_download=(
            endpoint_failover_candidate and not endpoint_urls
        ),
        weather_coexistence=weather_coexistence_candidate,
        weather_dual_request=weather_dual_request_candidate,
        weather_success_requires_stock=weather_preserved_dual_request_candidate,
        weather_stock_first=weather_stock_first_dual_request_candidate,
        weather_solo_request=weather_solo_request_candidate,
        post_weather_fetch=post_weather_fetch_candidate,
        location_slot_dashboard=location_slot_dashboard_candidate,
        round_diagnostic=round_diagnostic,
        download_diagnostic=download_diagnostic,
        result_diagnostic=result_diagnostic,
        publish_diagnostic=publish_diagnostic,
        adoption_diagnostic=adoption_diagnostic,
        standalone_timer=standalone_timer,
        refresh_seconds=refresh_seconds,
    )
    stack_limit = 96 if interaction_name in ("FW-AGENTS-014", "FW-PAGE-011") else 320
    if payload_result.maximum_static_stack > stack_limit:
        raise AgentsDashboardFirmwareError(
            f"低栈局部分支候选的单函数静态栈超过 {stack_limit} 字节"
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
        _patch_stock_local_branches(
            candidate,
            payload_result.symbols,
            integration_mode=integration_mode,
            shared_page_filter=shared_page_filter,
            power_confirm_guard=power_confirm_guard,
        )
    )
    mutator_ranges: list[ByteRange] = []
    for mutator in candidate_mutators:
        changed = mutator(candidate, payload_result.symbols)
        mutator_ranges.extend(changed)
        allowed.extend(changed)

    if live_data_enabled:
        transport_ranges = _patch_stock_transport(
            candidate,
            payload_result.symbols,
            url_base=url_base,
            refresh_seconds=refresh_seconds,
            location_independent=True,
            weather_coexistence=weather_coexistence_candidate,
            patch_stock_https_call=stock_https_dual_request_candidate,
            post_weather_fetch=post_weather_fetch_candidate,
            location_slot_dashboard=location_slot_dashboard_candidate,
        )
        allowed.extend(transport_ranges)
    else:
        _assert_stock_transport_unchanged(stage, bytes(candidate))

    _assert_stock_local_branch_isolation(
        stage,
        bytes(candidate),
        integration_mode=integration_mode,
        shared_page_filter=shared_page_filter,
        power_confirm_guard=power_confirm_guard,
        ui_timer_wrapper=live_data_enabled,
        additional_allowed=tuple(mutator_ranges),
    )

    from .interaction_simulator import (
        InteractionContract,
        run_interaction_simulation,
    )

    active_hooks = STOCK_LOCAL_BRANCH_HOOKS
    if shared_page_filter:
        active_hooks = (*active_hooks, LOCAL_UI_SHARED_PAGE_FILTER_HOOK)
    if power_confirm_guard:
        active_hooks = (*active_hooks, LOCAL_UI_POWER_CONFIRM_GUARD_HOOK)
    local_hook_labels = tuple(item[-1] for item in active_hooks)
    overview_right_route = route_stock_local_branch("pet-right", 1)
    interaction_simulation = run_interaction_simulation(
        InteractionContract(
            name=interaction_name,
            local_hook_labels=local_hook_labels,
            overview_right_target_dispatch=(
                0
                if shared_page_filter
                else overview_right_route.target_dispatch
            ),
            power_left_enters_agents=shared_page_filter,
            stock_entry_filter_enabled=(
                integration_mode or shared_page_filter
            ),
            power_confirm_isolated=not power_confirm_guard,
            power_confirm_guard_enabled=power_confirm_guard,
            power_confirm_guard_calls_stock_clock=power_confirm_guard,
            page_registration_unchanged=True,
            global_key_callback_registration_unchanged=True,
            fixed_shared_pages_enabled=shared_page_filter,
            fixed_hidden_primary_pages_enabled=fixed_hidden_primary_pages,
            weather_hidden_primary_page_enabled=weather_hidden_primary_page,
            calendar_skip_direction_correct=bool(
                payload_result.callchain_evidence.get(
                    "calendar_skip_direction_verified"
                )
            ),
            overview_left_preserves_gif_until_switch=(
                bool(
                    payload_result.callchain_evidence.get(
                        "overview_left_gif_preserved_until_switch"
                    )
                )
            ),
        ),
        route_stock_local_branch,
    )
    if not interaction_simulation["summary"]["passed"]:
        first_failure = interaction_simulation["failures"][0]
        raise AgentsDashboardFirmwareError(
            "刷前连续页面事件模拟未通过："
            f"{first_failure['message']}；"
            "当前方案不得生成待刷固件"
        )

    payload_before = bytes(candidate[PAYLOAD_START : PAYLOAD_START + len(payload)])
    if payload_before == payload:
        raise AgentsDashboardFirmwareError("同步载荷写入前后完全相同")
    candidate[PAYLOAD_START : PAYLOAD_START + len(payload)] = payload
    allowed.append(ByteRange(PAYLOAD_START, PAYLOAD_START + len(payload)))
    if not live_data_enabled:
        _assert_stock_transport_unchanged(stage, bytes(candidate))

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
    public_release = output.name == PUBLIC_FIRMWARE_OUTPUT_FILENAME
    manifest_input_path = (
        str(Path("artifacts/firmware") / stage_selected.name)
        if public_release
        else str(stage_selected)
    )
    manifest_output_path = (
        str(Path("artifacts/firmware") / output.name)
        if public_release
        else str(output)
    )
    manifest: dict[str, object] = {
        "schema_version": 1,
        "manifest_type": (
            "agents-weather-agents-dual-request-firmware"
            if expected_output_name == LIVE_DATA_WEATHER_AGENTS_DUAL_REQUEST_OUTPUT_FILENAME
            else "agents-location-slot-dashboard-firmware"
            if expected_output_name == LIVE_DATA_LOCATION_SLOT_DASHBOARD_OUTPUT_FILENAME
            else "agents-weather-hidden-dashboard-firmware"
            if expected_output_name == LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_OUTPUT_FILENAME
            else "agents-weather-hidden-dashboard-v2-firmware"
            if expected_output_name == LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_V2_OUTPUT_FILENAME
            else "agents-post-weather-fetch-firmware"
            if expected_output_name == LIVE_DATA_POST_WEATHER_FETCH_OUTPUT_FILENAME
            else "agents-stock-https-untouched-firmware"
            if expected_output_name == LIVE_DATA_STOCK_HTTPS_UNTOUCHED_OUTPUT_FILENAME
            else "agents-weather-solo-request-firmware"
            if weather_solo_request_candidate
            else "agents-weather-stock-first-dual-request-firmware"
            if weather_stock_first_dual_request_candidate
            else "agents-weather-preserved-dual-request-firmware"
            if weather_preserved_dual_request_candidate
            else "agents-stock-https-dual-request-firmware"
            if expected_output_name == LIVE_DATA_STOCK_HTTPS_DUAL_REQUEST_OUTPUT_FILENAME
            else "agents-stable-adoption-firmware"
            if expected_output_name == LIVE_DATA_STABLE_ADOPTION_OUTPUT_FILENAME
            else "agents-adoption-diagnostic-firmware" if adoption_diagnostic
            else "agents-publish-diagnostic-firmware" if publish_diagnostic
            else "agents-result-diagnostic-firmware"
            if result_diagnostic
            else "agents-download-diagnostic-firmware"
            if download_diagnostic
            else "agents-live-data-round-diagnostic-firmware"
            if round_diagnostic
            else "agents-live-data-weather-round-robin-firmware"
            if weather_coexistence_candidate
            else "agents-live-data-fixed-primary-pages-v2-firmware"
            if fixed_primary_pages_candidate
            else "agents-live-data-endpoint-failover-firmware"
            if endpoint_failover_candidate
            else "agents-live-data-validated-package-firmware"
            if validated_package_candidate
            else (
                "agents-live-data-location-independent-firmware"
                if live_data_enabled
                else (
                    "agents-local-ui-base-safe-firmware"
                    if power_confirm_guard
                    else "agents-local-ui-stock-resume-firmware"
                )
            )
        ),
        "status": (
            "requires-endpoint-personalization"
            if endpoint_failover_candidate and not endpoint_urls
            else
            "approved-for-one-test-installation"
            if fixed_primary_pages_candidate or location_slot_dashboard_candidate
            else "built-not-approved-for-installation"
            if endpoint_failover_candidate
            else "approved-for-one-test-installation"
            if power_confirm_guard
            else "built-not-approved-for-installation"
        ),
        "built_at_beijing": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
            timespec="seconds"
        ),
        "tool": tool_revision,
        "input": {
            "path": manifest_input_path,
            "size": len(stage),
            "sha256": hashlib.sha256(stage).hexdigest(),
            "read_only": True,
        },
        "output": {
            "path": manifest_output_path,
            "read_only": True,
            **report.to_dict(),
        },
        "device_specific": bool(endpoint_urls),
        "endpoint_personalization": _endpoint_personalization(
            endpoint_failover_candidate=endpoint_failover_candidate,
            endpoint_urls=endpoint_urls,
        ),
        "transport": {
            "enabled": (
                live_data_enabled
                and not (endpoint_failover_candidate and not endpoint_urls)
            ),
            "url_base": (
                url_base
                if live_data_enabled
                and not (endpoint_failover_candidate and not endpoint_urls)
                else None
            ),
            "refresh_seconds": refresh_seconds if live_data_enabled else None,
            "stock_loader_trampoline_unchanged": not live_data_enabled,
            "stock_download_callback_unchanged": (
                not live_data_enabled or weather_coexistence_candidate
            ),
            "stock_network_call_unchanged": not live_data_enabled,
            "stock_timers_unchanged": not live_data_enabled,
            "stock_request_regions_unchanged": (
                not live_data_enabled
                or (
                    weather_coexistence_candidate
                    and not location_slot_dashboard_candidate
                )
            ),
            "stock_ui_timer_callback_unchanged": not live_data_enabled,
            "location_request_format": (
                "%s" if location_slot_dashboard_candidate
                else "stock" if weather_coexistence_candidate
                else "%s" if live_data_enabled else None
            ),
            "city_request_format": (
                "stock" if weather_coexistence_candidate
                else "%s" if live_data_enabled else None
            ),
            "ui_timer_wrapper_enabled": live_data_enabled,
            "shared_device_configuration_used": False,
            "weather_location_dependency_removed": (
                live_data_enabled and not weather_coexistence_candidate
            ),
            "stock_weather_preserved": weather_coexistence_candidate,
            "agents_location_fallback_enabled": weather_coexistence_candidate,
            "weather_and_agents_results_isolated": weather_coexistence_candidate,
            "weather_and_agents_round_robin": (
                weather_coexistence_candidate and not weather_dual_request_candidate
            ),
            "weather_and_agents_dual_request": (
                weather_dual_request_candidate and not weather_solo_request_candidate
            ),
            "weather_solo_request": weather_solo_request_candidate,
            "stock_https_network_call_patched": stock_https_dual_request_candidate,
            "weather_success_requires_stock_weather_request": (
                weather_preserved_dual_request_candidate
            ),
            "weather_stock_first": weather_stock_first_dual_request_candidate,
            "post_weather_fetch_enabled": post_weather_fetch_candidate,
            "location_slot_dashboard_enabled": location_slot_dashboard_candidate,
            "stock_location_weather_slot_repurposed_for_dashboard": (
                location_slot_dashboard_candidate
            ),
            "stock_city_weather_request_regions_preserved": (
                weather_coexistence_candidate
            ),
            "stock_weather_request_regions_preserved": (
                weather_coexistence_candidate
                and not location_slot_dashboard_candidate
            ),
            "round_diagnostic_enabled": round_diagnostic,
            "download_diagnostic_enabled": download_diagnostic,
            "result_diagnostic_enabled": result_diagnostic,
            "publish_diagnostic_enabled": publish_diagnostic,
            "adoption_diagnostic_enabled": adoption_diagnostic,
            "single_business_result_per_round": (
                weather_coexistence_candidate
                and (
                    not weather_dual_request_candidate
                    or weather_solo_request_candidate
                )
            ),
            "location_placeholder_transmitted": False,
            "gif_structural_validation": live_data_enabled,
            "gif_trailer_validation": live_data_enabled,
            "single_frame_rejected": live_data_enabled,
            "unpublished_slot_cleared_on_failure": live_data_enabled,
            "download_state_bytes": 136 if live_data_enabled else None,
            "endpoint_configuration_required": (
                endpoint_failover_candidate and not endpoint_urls
            ),
            "endpoint_failover_enabled": (
                endpoint_failover_candidate and bool(endpoint_urls)
            ),
            "endpoint_priority": list(endpoint_urls),
            "endpoint_timeout_seconds": (
                endpoint_timeout_seconds
                if endpoint_failover_candidate and endpoint_urls
                else None
            ),
            "retry_starts_at_first_endpoint": (
                endpoint_failover_candidate and bool(endpoint_urls)
            ),
            "fixed_hidden_primary_pages": (
                (
                    ["calendar", "weather", "pet"]
                    if weather_hidden_primary_page
                    else ["calendar", "pet"]
                )
                if fixed_primary_pages_candidate else []
            ),
            "weather_hidden_primary_page": weather_hidden_primary_page,
            "standalone_timer_enabled": standalone_timer,
            "standalone_timer_refresh_seconds": (
                refresh_seconds if standalone_timer else None
            ),
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
            "local_ui_only": local_ui_only,
            "transport_symbols_linked": live_data_enabled,
            "stock_pet_object_reused": True,
            "stock_pet_state_bytes_before": 16,
            "stock_pet_state_bytes_after": 20,
            "agents_state_offset": 16,
        },
        "implemented_scope": [
            "四张指纹固定的内置页面",
            "复用原厂萌宠既有动图对象",
            "只挂接原厂已筛选的三个萌宠局部分支",
            "AGENTS 概览作为萌宠与功率之间的逻辑一级页",
            "周报、今日和近 30 天作为三个二级页",
            (
                "功率确认只增加连接与数据有效性局部保护"
                if power_confirm_guard
                else "原厂功率确认和两个全局回调保持原字节"
            ),
            (
                "原厂调度分轮执行天气与四页完整包请求"
                if weather_coexistence_candidate
                else "原厂天气后台任务复用为四页完整包取包"
                if live_data_enabled
                else "原厂后台网络回调、调用、定时和请求区保持原字节"
            ),
            "AGENTS 概览右旋恢复萌宠后交还原厂右旋继续地址",
            "AGENTS 状态使用萌宠状态新增尾部",
            *implemented_scope_extra,
        ],
        "pending_scope": [
            *([] if live_data_enabled else ["四页在线取数与后台刷新"]),
            "重启后保留最后成功页面",
            "页面开关关闭时停用刷新",
            *(
                []
                if endpoint_failover_candidate and endpoint_urls
                else ["跨服务端自动切换"]
            ),
            *([] if live_data_enabled else ["停留页面时即时应用后台新数据"]),
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
            "global_ui_timer_callback_registration_unchanged": (
                not live_data_enabled
            ),
            "global_ui_timer_calls_stock_first": live_data_enabled,
            "stock_key_callback_unchanged_except_local_targets": True,
            "stock_power_confirm_path_unchanged": not power_confirm_guard,
            "stock_power_confirm_entry_guarded": power_confirm_guard,
            "power_confirm_guard_calls_stock_clock": power_confirm_guard,
            "stock_transport_paths_unchanged": not live_data_enabled,
            "stock_transport_scoped_patch": live_data_enabled,
            "stock_location_lookup_scoped_patch": live_data_enabled,
            "stock_weather_request_regions_preserved": (
                weather_coexistence_candidate and not location_slot_dashboard_candidate
            ),
            "stock_city_weather_request_regions_preserved": (
                weather_coexistence_candidate
            ),
            "stock_location_weather_slot_repurposed_for_dashboard": (
                location_slot_dashboard_candidate
            ),
            "stock_weather_sink_registration_preserved": (
                weather_coexistence_candidate
            ),
            "stock_https_webclient_call": (
                {
                    "call_file_offset": f"0x{HTTPS_PERFORM_CALL:06x}",
                    "call_before_hex": INSTRUCTION_EXPECTED[
                        HTTPS_PERFORM_CALL
                    ].hex(),
                    "call_after_hex": _encode_jal(
                        XIP_DELTA + HTTPS_PERFORM_CALL,
                        LOADER_TRAMPOLINE_VA,
                    ).hex(),
                    "trampoline_file_offset": (
                        f"0x{LOADER_TRAMPOLINE_OFFSET:06x}"
                    ),
                    "trampoline_after_hex": _absolute_tail_jump(
                        payload_result.symbols["ap01_agents_webclient_wrapper"]
                    ).hex(),
                    "payload_symbol": "ap01_agents_webclient_wrapper",
                    "payload_address": (
                        "0x"
                        f"{payload_result.symbols['ap01_agents_webclient_wrapper']:08x}"
                    ),
                }
                if stock_https_dual_request_candidate
                else None
            ),
            "post_weather_fetch": (
                {
                    "hook_file_offset": f"0x{POST_WEATHER_FETCH_HOOK:06x}",
                    "hook_before_hex": POST_WEATHER_FETCH_HOOK_ORIGINAL.hex(),
                    "hook_after_hex": _encode_jal(
                        XIP_DELTA + POST_WEATHER_FETCH_HOOK,
                        POST_WEATHER_FETCH_TRAMPOLINE_VA,
                    ).hex(),
                    "trampoline_file_offset": (
                        f"0x{POST_WEATHER_FETCH_TRAMPOLINE_OFFSET:06x}"
                    ),
                    "trampoline_after_hex": _absolute_tail_jump(
                        payload_result.symbols[
                            "ap01_agents_post_weather_fetch_entry"
                        ]
                    ).hex(),
                    "payload_symbol": "ap01_agents_post_weather_fetch_entry",
                    "resume_address": f"0x{POST_WEATHER_FETCH_RESUME_VA:08x}",
                }
                if post_weather_fetch_candidate
                else None
            ),
            "stock_location_lookup": (
                {
                    "call_file_offset": f"0x{LOCATION_LOOKUP_CALL:06x}",
                    "call_before_hex": INSTRUCTION_EXPECTED[
                        LOCATION_LOOKUP_CALL
                    ].hex(),
                    "call_after_hex": _encode_jal(
                        XIP_DELTA + LOCATION_LOOKUP_CALL,
                        LOCATION_TRAMPOLINE_VA,
                    ).hex(),
                    "trampoline_file_offset": (
                        f"0x{LOCATION_TRAMPOLINE_OFFSET:06x}"
                    ),
                    "trampoline_after_hex": _absolute_tail_jump(
                        payload_result.symbols["ap01_agents_location_stub"]
                    ).hex(),
                    "payload_symbol": "ap01_agents_location_stub",
                    "payload_address": (
                        "0x"
                        f"{payload_result.symbols['ap01_agents_location_stub']:08x}"
                    ),
                }
                if live_data_enabled
                else None
            ),
            "overview_right_stock_resume_only": True,
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
                ) in active_hooks
            ],
            "pet_state_original_fields_unchanged": True,
            "pet_state_size_patch": {
                "file_offset": f"0x{PET_STATE_SIZE_OFFSET:06x}",
                "before_hex": PET_STATE_SIZE_ORIGINAL.hex(),
                "after_hex": PET_STATE_SIZE_EXTENDED.hex(),
            },
        },
        "interaction_simulation": interaction_simulation,
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
            "three_local_branch_targets_verified": True,
            "page_filter_switch_call_verified": (
                integration_mode or shared_page_filter
            ),
            "calendar_skip_direction_verified": (
                bool(
                    payload_result.callchain_evidence.get(
                        "calendar_skip_direction_verified"
                    )
                )
            ),
            "weather_skip_direction_verified": (
                bool(
                    payload_result.callchain_evidence.get(
                        "weather_skip_direction_verified"
                    )
                )
            ),
            "overview_left_gif_preserved_until_switch": (
                bool(
                    payload_result.callchain_evidence.get(
                        "overview_left_gif_preserved_until_switch"
                    )
                )
            ),
            "global_key_callback_registration_unchanged": True,
            "global_ui_timer_callback_registration_unchanged": (
                not live_data_enabled
            ),
            "global_ui_timer_calls_stock_first": live_data_enabled,
            "stock_power_confirm_path_unchanged": not power_confirm_guard,
            "stock_power_confirm_entry_guarded": power_confirm_guard,
            "stock_transport_paths_unchanged": not live_data_enabled,
            "transport_symbols_absent": not live_data_enabled,
            "transport_symbols_present": live_data_enabled,
            "stock_location_lookup_scoped_patch": live_data_enabled,
            "shared_device_configuration_absent": True,
            "independent_tail_recovery_verified": True,
            "installation_allowed": (
                not public_release
                and (
                    fixed_primary_pages_candidate
                    or location_slot_dashboard_candidate
                    or power_confirm_guard and not endpoint_failover_candidate
                )
            ),
        },
    }
    manifest["completeness"] = _manifest_completeness(manifest)
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
    *,
    url_base: str,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "旧原厂局部分支观察成品已因物理验收失败停用"
    )


def build_low_stack_local_branches_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    url_base: str,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "低栈局部分支成品已因功率页确认重启停用"
    )


def build_local_ui_power_safe_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "功率路径隔离版已因功率页确认卡住停用"
    )


def build_local_ui_stock_resume_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        expected_output_name=LOCAL_UI_STOCK_RESUME_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "萌宠左旋、右旋和确认三个局部分支接入",
            "未消费事件从三个原厂继续地址恢复",
            "消费事件从原厂公共退出地址返回",
            "异常尾部先恢复原厂萌宠再继续处理",
            "AGENTS 概览右旋不直接调用切页函数",
            "载荷不链接后台下载、网络包装和界面同步定时入口",
        ),
        reuse_stock_pet=True,
        local_ui_only=True,
    )


def build_local_ui_stock_safe_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "FW-AGENTS-009 已因缺少基座生命周期保护停用"
    )


def build_local_ui_base_safe_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        expected_output_name=LOCAL_UI_BASE_SAFE_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "AGENTS 概览离开时只关闭独立状态尾",
            "原厂萌宠右旋继续地址负责既有动图收尾和目标选择",
            "功率专用分支完成后才在统一切页点进入 AGENTS",
            "返回共享序号时按原方向恢复萌宠或显示 AGENTS",
            "非共享序号的原厂切页参数保持不变",
            "功率确认先核对原厂设备端口数和功率汇总数据指针",
            "失效功率页复用原厂离线切页入口回到时钟",
            "载荷不链接后台下载、网络包装和界面同步定时入口",
        ),
        reuse_stock_pet=True,
        local_ui_only=True,
        shared_page_filter=True,
        power_confirm_guard=True,
        interaction_name="FW-AGENTS-010",
    )


def build_live_data_base_safe_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    url_base: str,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "FW-AGENTS-011 已因安装后无设备取包请求停用"
    )


def build_live_data_reference_complete_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    url_base: str,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "FW-AGENTS-012 已因安装后无设备取包请求停用"
    )


def build_live_data_low_stack_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    url_base: str,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "FW-AGENTS-013 已因安装后无设备取包请求停用"
    )


def build_live_data_location_independent_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
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
        tool_revision=tool_revision,
        url_base=url_base,
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_LOCATION_INDEPENDENT_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "64 字节四页包流式接收与逐页损坏检查",
            "三组内存临时槽原子提交",
            "固定局域网地址五分钟后台取包",
            "两个原厂天气格式区严格只写百分号 s",
            "界面定时包装先调用原厂入口再应用已提交页面",
            "进入概览与切换详情时主动应用已提交页面",
            "不链接任何设备共享配置",
            "四页下载状态使用原厂内存申请与释放入口且不占后台任务栈",
            "位置占位入口解除局域网取包对原厂天气位置的依赖",
        ),
        reuse_stock_pet=True,
        local_ui_only=False,
        shared_page_filter=True,
        power_confirm_guard=True,
        interaction_name="FW-AGENTS-014",
    )


def build_live_data_validated_package_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
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
        tool_revision=tool_revision,
        url_base=url_base,
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_VALIDATED_PACKAGE_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "64 字节四页包流式接收与逐页损坏检查",
            "三组内存临时槽原子提交",
            "固定局域网地址五分钟后台取包",
            "两个原厂天气格式区严格只写百分号 s",
            "界面定时包装先调用原厂入口再应用已提交页面",
            "进入概览与切换详情时主动应用已提交页面",
            "不链接任何设备共享配置",
            "四页下载状态使用原厂内存申请与释放入口且不占后台任务栈",
            "位置占位入口解除局域网取包对原厂天气位置的依赖",
            "每页完成动图结构、结束标记与至少双帧检查",
            "任一失败清空当轮未发布槽的四页文件",
        ),
        reuse_stock_pet=True,
        local_ui_only=False,
        shared_page_filter=True,
        power_confirm_guard=True,
        interaction_name="FW-AGENTS-014",
    )


def build_live_data_endpoint_failover_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        url_base=endpoints[0] if endpoints else "",
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_ENDPOINT_FAILOVER_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "按构建配置顺序尝试已核实的局域网地址",
            "首个完整合法结果成功后停止本轮后续请求",
            "单地址失败清理当轮未发布槽后继续下一地址",
            "全部地址失败时保留最后成功结果",
        ),
        reuse_stock_pet=True,
        shared_page_filter=True,
        power_confirm_guard=True,
        interaction_name="FW-AGENTS-014",
        endpoint_urls=endpoints,
        endpoint_timeout_seconds=endpoint_timeout_seconds,
    )


def build_live_data_fixed_primary_pages_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        url_base=endpoints[0] if endpoints else "",
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_FIXED_PRIMARY_PAGES_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "按构建配置顺序尝试已核实的数据地址",
            "日历与萌宠状态固定跳过且保留原厂对象",
            "共享序号七在两个方向均直接显示 AGENTS 概览",
            "设置页不增加页面开关或持久化记录",
        ),
        reuse_stock_pet=True,
        shared_page_filter=True,
        fixed_hidden_primary_pages=True,
        power_confirm_guard=True,
        interaction_name="FW-PAGE-011",
        endpoint_urls=endpoints,
        endpoint_timeout_seconds=endpoint_timeout_seconds,
    )


def build_live_data_weather_coexistence_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "FW-AGENTS-017 已因天气恢复但看板未发布停用"
    )


def build_live_data_weather_round_robin_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "FW-AGENTS-018 已因真机没有发出看板请求停用"
    )


def build_live_data_round_diagnostic_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "FW-AGENTS-019 已完成真机分轮阶段观测，不得再次构建"
    )


def build_live_data_download_diagnostic_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "FW-AGENTS-020 已完成真机下载阶段观测，不得再次构建"
    )


def build_live_data_result_diagnostic_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "FW-AGENTS-021 已完成真机返回结果观测，不得再次构建"
    )


def build_live_data_publish_diagnostic_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError("FW-AGENTS-022 已完成真机发布记录观测，不得再次构建")

def build_live_data_adoption_diagnostic_firmware(stage_path: Path, output_path: Path, manifest_path: Path, build_directory: Path, *, endpoints: tuple[str, ...], endpoint_timeout_seconds: int, refresh_seconds: int, tool_revision: dict[str, object]) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        url_base=endpoints[0] if endpoints else "",
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_ADOPTION_DIAGNOSTIC_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "看板轮与天气轮分别使用原厂调度创建的新对象",
            "看板发布后交回失败以触发下一轮天气请求",
            "原厂位置失败时交还已就绪的城市后备分支",
            "天气位置暂不可用时只为看板取包提供有界占位",
            "原厂天气地址、格式和接收入口保持原字节",
            "按构建配置顺序尝试已核实的数据地址",
            "同一轮不得混合执行天气与看板请求",
            "日历与萌宠状态固定跳过且保留原厂对象",
        ),
        reuse_stock_pet=True,
        shared_page_filter=True,
        fixed_hidden_primary_pages=True,
        power_confirm_guard=True,
        interaction_name="FW-PAGE-011",
        endpoint_urls=endpoints,
        endpoint_timeout_seconds=endpoint_timeout_seconds,
        weather_coexistence=True,
        adoption_diagnostic=True,
    )


def build_live_data_stable_adoption_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        url_base=endpoints[0] if endpoints else "",
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_STABLE_ADOPTION_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "看板轮与天气轮分别使用原厂调度创建的新对象",
            "看板发布后交回失败以触发下一轮天气请求",
            "原厂位置失败时交还已就绪的城市后备分支",
            "天气位置暂不可用时只为看板取包提供有界占位",
            "原厂天气地址、格式和接收入口保持原字节",
            "按构建配置顺序尝试已核实的数据地址",
            "同一轮不得混合执行天气与看板请求",
            "日历与萌宠状态固定跳过且保留原厂对象",
            "发布与采用记录一致时不切换动图数据源",
        ),
        reuse_stock_pet=True,
        shared_page_filter=True,
        fixed_hidden_primary_pages=True,
        power_confirm_guard=True,
        interaction_name="FW-PAGE-011",
        endpoint_urls=endpoints,
        endpoint_timeout_seconds=endpoint_timeout_seconds,
        weather_coexistence=True,
    )


def build_live_data_weather_agents_dual_request_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        url_base=endpoints[0] if endpoints else "",
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_WEATHER_AGENTS_DUAL_REQUEST_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "天气网络执行后继续按地址优先级取得看板包",
            "看板结果不覆盖天气返回值和响应状态",
            "退出前恢复原厂地址、超时、接收入口和接收参数",
            "原厂天气地址、格式和接收入口保持原字节",
            "发布与采用记录一致时不切换动图数据源",
            "日历与萌宠状态固定跳过且保留原厂对象",
        ),
        reuse_stock_pet=True,
        shared_page_filter=True,
        fixed_hidden_primary_pages=True,
        power_confirm_guard=True,
        interaction_name="FW-PAGE-011",
        endpoint_urls=endpoints,
        endpoint_timeout_seconds=endpoint_timeout_seconds,
        weather_coexistence=True,
    )


def build_live_data_stock_https_dual_request_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        url_base=endpoints[0] if endpoints else "",
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_STOCK_HTTPS_DUAL_REQUEST_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "原厂 HTTPS 天气路径和直达网络路径都进入同一包装入口",
            "天气网络执行后继续按地址优先级取得看板包",
            "看板结果不覆盖天气返回值和响应状态",
            "退出前恢复原厂地址、超时、接收入口和接收参数",
            "原厂天气地址、格式和接收入口保持原字节",
            "发布与采用记录一致时不切换动图数据源",
            "日历与萌宠状态固定跳过且保留原厂对象",
        ),
        reuse_stock_pet=True,
        shared_page_filter=True,
        fixed_hidden_primary_pages=True,
        power_confirm_guard=True,
        interaction_name="FW-PAGE-011",
        endpoint_urls=endpoints,
        endpoint_timeout_seconds=endpoint_timeout_seconds,
        weather_coexistence=True,
    )


def build_live_data_weather_hidden_dashboard_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    raise AgentsDashboardFirmwareError(
        "FW-AGENTS-033 已因右滑偶发回退和运行时间重置停用"
    )


def build_live_data_weather_hidden_dashboard_v2_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
    standalone_timer: bool = False,
) -> SyncFirmwareResult:
    output_name = (
        PERSONALIZED_FIRMWARE_OUTPUT_FILENAME
        if endpoints
        else PUBLIC_FIRMWARE_OUTPUT_FILENAME
    )
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        url_base=endpoints[0] if endpoints else "",
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_WEATHER_HIDDEN_DASHBOARD_V2_OUTPUT_FILENAME,
        accepted_output_names=(output_name,),
        implemented_scope_extra=(
            "原厂 HTTPS 天气路径和直达网络路径都进入同一包装入口",
            (
                "公开固件不包含地址且不发起看板取包"
                if not endpoints
                else "看板取包由独立定时器按周期执行，与天气任务解耦"
                if standalone_timer
                else "天气网络执行后继续按地址优先级取得看板包"
            ),
            (
                "原厂天气请求按原字节执行并原样返回"
                if standalone_timer
                else "看板结果不覆盖原厂网络返回值和响应状态"
            ),
            "一级页面导航跳过天气后直接落到 AGENTS 共用序号",
            "发布与采用记录一致时不切换动图数据源",
        ),
        reuse_stock_pet=True,
        shared_page_filter=True,
        fixed_hidden_primary_pages=True,
        weather_hidden_primary_page=True,
        power_confirm_guard=True,
        interaction_name="FW-PAGE-011",
        endpoint_urls=endpoints,
        endpoint_timeout_seconds=endpoint_timeout_seconds,
        weather_coexistence=True,
        standalone_timer=standalone_timer,
    )


def build_live_data_weather_preserved_dual_request_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        url_base=endpoints[0] if endpoints else "",
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_WEATHER_PRESERVED_DUAL_REQUEST_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "原厂 HTTPS 天气路径和直达网络路径都进入同一包装入口",
            "天气网络执行后继续按地址优先级取得看板包",
            "看板结果不覆盖天气返回值和响应状态",
            "没有原厂天气请求时看板成功不得伪装成天气成功",
            "原厂天气地址、格式和接收入口保持原字节",
            "发布与采用记录一致时不切换动图数据源",
            "日历与萌宠状态固定跳过且保留原厂对象",
        ),
        reuse_stock_pet=True,
        shared_page_filter=True,
        fixed_hidden_primary_pages=True,
        power_confirm_guard=True,
        interaction_name="FW-PAGE-011",
        endpoint_urls=endpoints,
        endpoint_timeout_seconds=endpoint_timeout_seconds,
        weather_coexistence=True,
    )


def build_live_data_weather_stock_first_dual_request_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        url_base=endpoints[0] if endpoints else "",
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_WEATHER_STOCK_FIRST_DUAL_REQUEST_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "原厂 HTTPS 天气路径和直达网络路径都进入同一包装入口",
            "天气网络执行后继续按地址优先级取得看板包",
            "看板结果不覆盖天气返回值和响应状态",
            "没有原厂天气请求时看板成功不得伪装成天气成功",
            "天气任务不再写入 000000000 占位位置",
            "原厂位置失败时交还原厂城市后备路径",
            "原厂天气地址、格式和接收入口保持原字节",
            "发布与采用记录一致时不切换动图数据源",
            "日历与萌宠状态固定跳过且保留原厂对象",
        ),
        reuse_stock_pet=True,
        shared_page_filter=True,
        fixed_hidden_primary_pages=True,
        power_confirm_guard=True,
        interaction_name="FW-PAGE-011",
        endpoint_urls=endpoints,
        endpoint_timeout_seconds=endpoint_timeout_seconds,
        weather_coexistence=True,
    )


def build_live_data_weather_solo_request_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        url_base=endpoints[0] if endpoints else "",
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_WEATHER_SOLO_REQUEST_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "原厂 HTTPS 天气路径和直达网络路径都进入同一包装入口",
            "天气网络执行后立即返回原厂天气结果",
            "天气任务不再同轮复用网络上下文取得看板包",
            "没有原厂天气请求时看板成功不得伪装成天气成功",
            "天气任务不再写入 000000000 占位位置",
            "原厂位置失败时交还原厂城市后备路径",
            "原厂天气地址、格式和接收入口保持原字节",
            "发布与采用记录一致时不切换动图数据源",
            "日历与萌宠状态固定跳过且保留原厂对象",
        ),
        reuse_stock_pet=True,
        shared_page_filter=True,
        fixed_hidden_primary_pages=True,
        power_confirm_guard=True,
        interaction_name="FW-PAGE-011",
        endpoint_urls=endpoints,
        endpoint_timeout_seconds=endpoint_timeout_seconds,
        weather_coexistence=True,
    )


def build_live_data_stock_https_untouched_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        url_base=endpoints[0] if endpoints else "",
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_STOCK_HTTPS_UNTOUCHED_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "原厂 HTTPS 天气执行调用保持原字节",
            "直达网络执行入口继续进入看板包装入口",
            "没有原厂天气请求时看板成功不得伪装成天气成功",
            "天气任务不再写入 000000000 占位位置",
            "原厂位置失败时交还原厂城市后备路径",
            "原厂天气地址、格式和接收入口保持原字节",
            "发布与采用记录一致时不切换动图数据源",
            "日历与萌宠状态固定跳过且保留原厂对象",
        ),
        reuse_stock_pet=True,
        shared_page_filter=True,
        fixed_hidden_primary_pages=True,
        power_confirm_guard=True,
        interaction_name="FW-PAGE-011",
        endpoint_urls=endpoints,
        endpoint_timeout_seconds=endpoint_timeout_seconds,
        weather_coexistence=True,
    )


def build_live_data_post_weather_fetch_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        url_base=endpoints[0] if endpoints else "",
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_POST_WEATHER_FETCH_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "原厂 HTTPS 天气执行调用保持原字节",
            "原厂 HTTPS 天气调用返回后执行看板取包",
            "后置取包恢复原厂天气响应状态和接收字段",
            "没有原厂天气请求时看板成功不得伪装成天气成功",
            "天气任务不再写入 000000000 占位位置",
            "原厂位置失败时交还原厂城市后备路径",
            "原厂天气地址、格式和接收入口保持原字节",
            "发布与采用记录一致时不切换动图数据源",
            "日历与萌宠状态固定跳过且保留原厂对象",
        ),
        reuse_stock_pet=True,
        shared_page_filter=True,
        fixed_hidden_primary_pages=True,
        power_confirm_guard=True,
        interaction_name="FW-PAGE-011",
        endpoint_urls=endpoints,
        endpoint_timeout_seconds=endpoint_timeout_seconds,
        weather_coexistence=True,
    )


def build_live_data_location_slot_dashboard_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    endpoints: tuple[str, ...],
    endpoint_timeout_seconds: int,
    refresh_seconds: int,
    tool_revision: dict[str, object],
) -> SyncFirmwareResult:
    return build_sync_firmware(
        stage_path,
        output_path,
        manifest_path,
        build_directory,
        tool_revision=tool_revision,
        url_base=endpoints[0] if endpoints else "",
        refresh_seconds=refresh_seconds,
        expected_output_name=LIVE_DATA_LOCATION_SLOT_DASHBOARD_OUTPUT_FILENAME,
        implemented_scope_extra=(
            "原厂 HTTPS 天气执行调用保持原字节",
            "位置天气地址槽改为看板 HTTP 地址",
            "城市天气地址和格式保持原字节",
            "看板轮只通过直达网络入口进入包装入口",
            "天气轮只交还原厂城市后备分支",
            "天气任务不复用看板网络上下文",
            "发布与采用记录一致时不切换动图数据源",
            "日历与萌宠状态固定跳过且保留原厂对象",
        ),
        reuse_stock_pet=True,
        shared_page_filter=True,
        fixed_hidden_primary_pages=True,
        power_confirm_guard=True,
        interaction_name="FW-PAGE-011",
        endpoint_urls=endpoints,
        endpoint_timeout_seconds=endpoint_timeout_seconds,
        weather_coexistence=True,
        location_slot_dashboard=True,
    )
