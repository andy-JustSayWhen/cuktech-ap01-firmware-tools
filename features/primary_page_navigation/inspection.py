"""复核 AP01 当前版本一级窗口创建与导航调用关系。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.firmware_image import AP01_1_0_2_0031, load_read_only_baseline


XIP_DELTA = 0x9FFFF000
DISPLAY_PROCESS_ENTRY = 0xA00B2420
NAVIGATION_ENTRY = 0xA00B08FC
PAGE_HOOK_ADDRESS = 0xA00B2732
PAGE_HOOK_ORIGINAL = bytes.fromhex("5285eff02079")
DISPLAY_ENTRY_ORIGINAL = bytes.fromhex(
    "0571232e111c232c811c232a911c80132328211d2324411d2326311d2322511d"
)
NAVIGATION_ENTRY_ORIGINAL = bytes.fromhex(
    "011122cc4ac806ce26ca001037c528a0130585f22e89efe0f04c85476315f502"
)


class PrimaryPageNavigationError(RuntimeError):
    """一级页面注册或导航证据与当前固件不匹配。"""


@dataclass(frozen=True)
class CallContract:
    name: str
    source: int
    target: int
    expected: bytes

    @property
    def offset(self) -> int:
        return self.source - XIP_DELTA

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "source_address": f"0x{self.source:08x}",
            "file_offset": f"0x{self.offset:06x}",
            "target_address": f"0x{self.target:08x}",
            "instruction_hex": self.expected.hex(),
        }


WINDOW_CREATE_CALLS = (
    CallContract("功率窗口对象", 0xA00B2602, 0xA00C1EC6, bytes.fromhex("eff0500c")),
    CallContract("时间窗口对象", 0xA00B2696, 0xA00C1EC6, bytes.fromhex("eff01003")),
    CallContract("日期窗口对象", 0xA00B26B4, 0xA00C1EC6, bytes.fromhex("eff03001")),
    CallContract("天气窗口对象", 0xA00B26D4, 0xA00C1EC6, bytes.fromhex("eff0207f")),
    CallContract("设置窗口对象", 0xA00B26F4, 0xA00C1EC6, bytes.fromhex("eff0207d")),
    CallContract("萌宠窗口对象", 0xA00B2714, 0xA00C1EC6, bytes.fromhex("eff0207b")),
    CallContract("米家详情对象", 0xA00B2734, 0xA00C1EC6, bytes.fromhex("eff02079")),
)

CONTROL_CALLS = (
    CallContract("创建一级窗口容器", 0xA00B248A, 0xA00C1E3E, bytes.fromhex("eff0501b")),
    CallContract("初始化统计窗口数量", 0xA00B27B0, 0xA00C5FE4, bytes.fromhex("ef305103")),
    CallContract("导航读取当前序号一", 0xA00B0934, 0xA00B0290, bytes.fromhex("eff0df95")),
    CallContract("导航按序号切换", 0xA00B093E, 0xA00B06F4, bytes.fromhex("eff07fdb")),
    CallContract("左向再次读取当前序号", 0xA00B0962, 0xA00B0290, bytes.fromhex("eff0ff92")),
    CallContract("左向读取窗口数量", 0xA00B0974, 0xA00B0570, bytes.fromhex("eff0dfbf")),
    CallContract("右向读取当前序号", 0xA00B0982, 0xA00B0290, bytes.fromhex("eff0ff90")),
    CallContract("右向读取窗口数量", 0xA00B0990, 0xA00B0570, bytes.fromhex("eff01fbe")),
)


def decode_jal_target(instruction: bytes, source: int) -> tuple[int, int]:
    """解码一条四字节直接跳转指令的目标和返回寄存器。"""

    if len(instruction) != 4:
        raise ValueError("直接跳转指令必须是四字节")
    word = struct.unpack("<I", instruction)[0]
    if word & 0x7F != 0x6F:
        raise ValueError("当前字节不是直接跳转指令")
    destination_register = (word >> 7) & 0x1F
    immediate = (
        ((word >> 31) & 1) << 20
        | ((word >> 21) & 0x3FF) << 1
        | ((word >> 20) & 1) << 11
        | ((word >> 12) & 0xFF) << 12
    )
    if immediate & (1 << 20):
        immediate -= 1 << 21
    return source + immediate, destination_register


def _require_read_only(path: Path, label: str) -> tuple[Path, bytes]:
    selected = path.expanduser().resolve(strict=True)
    if not selected.is_file():
        raise PrimaryPageNavigationError(f"{label}不是普通文件：{selected}")
    writable_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    if selected.stat().st_mode & writable_bits:
        raise PrimaryPageNavigationError(f"{label}必须先设为只读：{selected}")
    return selected, selected.read_bytes()


def _slice(firmware: bytes, runtime_address: int, length: int) -> bytes:
    offset = runtime_address - XIP_DELTA
    return firmware[offset : offset + length]


def _verify_call(firmware: bytes, contract: CallContract) -> None:
    actual = _slice(firmware, contract.source, 4)
    if actual != contract.expected:
        raise PrimaryPageNavigationError(
            f"{contract.name}旧字节不匹配：0x{contract.offset:06x}"
        )
    target, destination_register = decode_jal_target(actual, contract.source)
    if target != contract.target or destination_register != 1:
        raise PrimaryPageNavigationError(f"{contract.name}调用目标不匹配")


def _write_report(path: Path, document: dict[str, object]) -> None:
    selected = path.expanduser().resolve()
    selected.parent.mkdir(parents=True, exist_ok=True)
    temporary = selected.with_name(selected.name + ".part")
    if temporary.exists():
        raise PrimaryPageNavigationError(f"发现未处理的临时报告：{temporary}")
    payload = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, selected)
    finally:
        if temporary.exists():
            temporary.unlink()


def inspect_primary_page_navigation(
    original_path: Path,
    stage_path: Path,
    report_path: Path,
    *,
    tool_revision: dict[str, object],
) -> dict[str, object]:
    """检查原厂链路及阶段输入未触碰这些区间。"""

    original, baseline = load_read_only_baseline(original_path, AP01_1_0_2_0031)
    stage_selected, stage = _require_read_only(stage_path, "已验收阶段输入")
    if len(stage) != len(original):
        raise PrimaryPageNavigationError("已验收阶段输入总字节数不匹配")

    if _slice(original, DISPLAY_PROCESS_ENTRY, len(DISPLAY_ENTRY_ORIGINAL)) != (
        DISPLAY_ENTRY_ORIGINAL
    ):
        raise PrimaryPageNavigationError("显示初始化入口旧字节不匹配")
    if _slice(original, NAVIGATION_ENTRY, len(NAVIGATION_ENTRY_ORIGINAL)) != (
        NAVIGATION_ENTRY_ORIGINAL
    ):
        raise PrimaryPageNavigationError("一级导航入口旧字节不匹配")
    if _slice(original, PAGE_HOOK_ADDRESS, len(PAGE_HOOK_ORIGINAL)) != (
        PAGE_HOOK_ORIGINAL
    ):
        raise PrimaryPageNavigationError("新增页面挂接候选旧字节不匹配")

    contracts = WINDOW_CREATE_CALLS + CONTROL_CALLS
    for contract in contracts:
        _verify_call(original, contract)

    checked_regions = (
        (DISPLAY_PROCESS_ENTRY, len(DISPLAY_ENTRY_ORIGINAL)),
        (NAVIGATION_ENTRY, len(NAVIGATION_ENTRY_ORIGINAL)),
        (PAGE_HOOK_ADDRESS, len(PAGE_HOOK_ORIGINAL)),
        *((contract.source, 4) for contract in contracts),
    )
    for address, length in checked_regions:
        if _slice(stage, address, length) != _slice(original, address, length):
            raise PrimaryPageNavigationError(
                f"已验收阶段输入改动了页面导航证据区间：0x{address:08x}"
            )

    document: dict[str, object] = {
        "schema_version": 1,
        "report_type": "primary-page-navigation-inspection",
        "checked_at_beijing": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
            timespec="seconds"
        ),
        "tool": tool_revision,
        "original": {
            "path": str(original_path.expanduser().resolve()),
            "sha256": baseline.sha256,
        },
        "stage_input": {
            "path": str(stage_selected),
            "sha256": hashlib.sha256(stage).hexdigest(),
            "checked_regions_identical_to_original": True,
        },
        "display_process_entry": f"0x{DISPLAY_PROCESS_ENTRY:08x}",
        "window_create_calls": [item.to_dict() for item in WINDOW_CREATE_CALLS],
        "control_calls": [item.to_dict() for item in CONTROL_CALLS],
        "page_hook_candidate": {
            "runtime_address": f"0x{PAGE_HOOK_ADDRESS:08x}",
            "file_offset": f"0x{PAGE_HOOK_ADDRESS - XIP_DELTA:06x}",
            "original_hex": PAGE_HOOK_ORIGINAL.hex(),
            "before_window_count_commit": PAGE_HOOK_ADDRESS < 0xA00B27B0,
        },
        "gates": {
            "page_registration_evidence_ready": True,
            "dynamic_navigation_evidence_ready": True,
            "stage_regions_preserved": True,
            "payload_space_proven": False,
            "patch_plan_allowed": False,
            "reason": "新增载荷所在文件区间尚未证明未使用且可执行",
        },
    }
    _write_report(report_path, document)
    return document
