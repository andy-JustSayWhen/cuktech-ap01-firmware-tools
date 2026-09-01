"""制作 0041 基线的本地 AGENTS 看板固件。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import struct
import subprocess
from pathlib import Path

from core.firmware_image import (
    AP01_1_0_2_0041,
    ByteRange,
    load_read_only_baseline,
    refresh_recovery_crc,
    validate_candidate,
)

from .build import (
    AgentsDashboardFirmwareError,
    _absolute_tail_jump,
    _encode_jal,
    _symbols,
    _tool,
    _write_asset_assembly,
    _write_frozen,
)
from .fallback_assets import build_fallback_assets
from .interaction_simulator import InteractionContract, run_interaction_simulation


MODULE_DIR = Path(__file__).resolve().parent
SOURCE = MODULE_DIR / "page_registration.S"
LOCAL_UI_SOURCE = MODULE_DIR / "local_ui_loader.c"
LINKER = MODULE_DIR / "result_loader_0041.ld"
BASELINE = Path("artifacts/firmware/original/ap01-1.0.2_0041.bin")
OUTPUT = Path("artifacts/firmware/第三方固件/AGENTS看板/ap01-1.0.2_0041-opt.bin")
MANIFEST = Path("artifacts/firmware/第三方固件/AGENTS看板/ap01-1.0.2_0041-opt.manifest.json")
BUILD_DIRECTORY = Path("artifacts/build/0041-opt")

XIP_DELTA = 0x9FFFF000
GIF_SIZE_OFFSET = 0x1C5A5C
GIF_DATA_OFFSET = 0x1C5A6C
GIF_ORIGINAL_SIZE = 385_834
GIF_ORIGINAL_SHA256 = "5e656788665f7f0022b0b5500d569a8aae07f4a46b080d033b3cacfa4abc940d"
PAYLOAD_START = 0x214F90
PAYLOAD_CAPACITY = 60_934
PAYLOAD_VA = XIP_DELTA + PAYLOAD_START
PET_STATE_SIZE_OFFSET = 0x05FA48
PET_STATE_SIZE_ORIGINAL = bytes.fromhex("4145")
PET_STATE_SIZE_EXTENDED = bytes.fromhex("5145")
TRAMPOLINES = (0x01C108, 0x01C110, 0x01C118, 0x01C120, 0x01C128)
HOOKS = (
    (0x0B1108, bytes.fromhex("9d452685"), "ap01_agents_stock_pet_left_entry", "萌宠左旋"),
    (0x0B13C2, bytes.fromhex("9d452685"), "ap01_agents_stock_pet_right_entry", "萌宠右旋"),
    (0x0B27EA, bytes.fromhex("26859d45"), "ap01_agents_stock_pet_enter_entry", "萌宠确认"),
    (0x0B0D2C, bytes.fromhex("ef30a03d"), "ap01_agents_primary_page_filter_and_switch", "一级页面过滤"),
    (0x0B159A, bytes.fromhex("e399098c"), "ap01_agents_stock_power_confirm_guard", "功率确认保护"),
)


def _run(command: list[object], *, capture: bool = False) -> str:
    try:
        completed = subprocess.run(
            [str(item) for item in command],
            check=True,
            capture_output=capture,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AgentsDashboardFirmwareError(f"构建命令失败：{command[0]}") from error
    return completed.stdout if capture else ""


def _replace(candidate: bytearray, offset: int, expected: bytes, replacement: bytes, label: str) -> ByteRange:
    end = offset + len(expected)
    if len(expected) != len(replacement) or bytes(candidate[offset:end]) != expected:
        raise AgentsDashboardFirmwareError(f"{label}原字节不匹配")
    candidate[offset:end] = replacement
    return ByteRange(offset, end)


def _write_json(path: Path, document: dict[str, object]) -> None:
    selected = path.resolve()
    selected.parent.mkdir(parents=True, exist_ok=True)
    if selected.exists():
        raise AgentsDashboardFirmwareError(f"不可覆盖已有报告：{selected}")
    temporary = selected.with_name(selected.name + ".part")
    try:
        temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(temporary, selected)
        selected.chmod(stat.S_IREAD)
    finally:
        if temporary.exists():
            temporary.unlink()


def _build_payload(directory: Path) -> tuple[bytes, dict[str, int], Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    assets = build_fallback_assets(directory / "fallback-assets")
    assets_source = directory / "fallback-assets.S"
    _write_asset_assembly(assets_source, assets)
    assembler = _tool("riscv64-elf-as")
    compiler = _tool("riscv64-elf-gcc")
    linker = _tool("riscv64-elf-ld")
    copier = _tool("riscv64-elf-objcopy")
    nm = _tool("riscv64-elf-nm")
    page = directory / "page.o"
    local = directory / "local.o"
    asset = directory / "assets.o"
    elf = directory / "payload.elf"
    binary = directory / "payload.bin"
    _run([assembler, "-march=rv32imac", "-mabi=ilp32", "--defsym", "SYNC_LOADER=1", "--defsym", "STOCK_PET_REUSE=1", "--defsym", "POWER_CONFIRM_GUARD=1", "--defsym", "FIXED_HIDDEN_PRIMARY_PAGES=1", "--defsym", "FIXED_WEATHER_HIDDEN_PRIMARY_PAGES=1", "--defsym", "AP01_0041=1", "-o", page, SOURCE])
    _run([compiler, "-march=rv32imac", "-mabi=ilp32", "-Os", "-ffreestanding", "-fno-builtin", "-fno-pic", "-fno-pie", "-fno-plt", "-fno-stack-protector", "-fno-asynchronous-unwind-tables", "-fno-unwind-tables", "-fno-jump-tables", "-fno-common", "-fno-toplevel-reorder", "-fno-tree-loop-distribute-patterns", "-msmall-data-limit=0", "-Wall", "-Wextra", "-Werror", "-c", LOCAL_UI_SOURCE, "-o", local])
    _run([assembler, "-march=rv32imac", "-mabi=ilp32", "-o", asset, assets_source])
    _run([linker, "-m", "elf32lriscv", "--no-relax", "-T", LINKER, "-o", elf, page, local, asset])
    _run([copier, "-O", "binary", "-j", ".payload", elf, binary])
    payload = binary.read_bytes()
    if not payload or len(payload) > PAYLOAD_CAPACITY:
        raise AgentsDashboardFirmwareError("看板载荷为空或超过 0041 固定空间")
    symbols = _symbols(nm, elf)
    for symbol in (item[2] for item in HOOKS):
        if symbol not in symbols:
            raise AgentsDashboardFirmwareError(f"载荷缺少入口：{symbol}")
    if symbols.get("ap01_agents_page_register") != PAYLOAD_VA:
        raise AgentsDashboardFirmwareError("看板载荷入口地址不匹配")
    return payload, symbols, elf, binary


def _optimize_gif(baseline: bytes, directory: Path) -> bytes:
    original = baseline[GIF_DATA_OFFSET : GIF_DATA_OFFSET + GIF_ORIGINAL_SIZE]
    if hashlib.sha256(original).hexdigest() != GIF_ORIGINAL_SHA256:
        raise AgentsDashboardFirmwareError("0041 原厂首张动图指纹不匹配")
    source = directory / "stock.gif"
    optimized = directory / "optimized.gif"
    source.write_bytes(original)
    _run(["gifsicle", "--no-warnings", "--optimize=3", source, "-o", optimized])
    result = optimized.read_bytes()
    if len(result) != PAYLOAD_START - GIF_DATA_OFFSET:
        raise AgentsDashboardFirmwareError("0041 动图无损优化长度不匹配")
    return result


def build(output: Path = OUTPUT, manifest: Path = MANIFEST, directory: Path = BUILD_DIRECTORY) -> dict[str, object]:
    baseline_path = BASELINE.resolve()
    baseline, baseline_report = load_read_only_baseline(baseline_path, AP01_1_0_2_0041)
    payload, symbols, elf, binary = _build_payload(directory.resolve())
    optimized = _optimize_gif(baseline, directory.resolve())
    candidate = bytearray(baseline)
    allowed = [_replace(candidate, PET_STATE_SIZE_OFFSET, PET_STATE_SIZE_ORIGINAL, PET_STATE_SIZE_EXTENDED, "萌宠状态长度"), _replace(candidate, GIF_SIZE_OFFSET, struct.pack("<I", GIF_ORIGINAL_SIZE), struct.pack("<I", len(optimized)), "首张动图长度")]
    candidate[GIF_DATA_OFFSET : GIF_DATA_OFFSET + len(optimized)] = optimized
    allowed.append(ByteRange(GIF_DATA_OFFSET, GIF_DATA_OFFSET + len(optimized)))
    for (hook_offset, original, symbol, label), trampoline in zip(HOOKS, TRAMPOLINES, strict=True):
        if bytes(candidate[trampoline : trampoline + 8]) != b"\0" * 8:
            raise AgentsDashboardFirmwareError(f"{label}跳转中继区不再全零")
        allowed.append(_replace(candidate, hook_offset, original, _encode_jal(XIP_DELTA + hook_offset, XIP_DELTA + trampoline), label))
        candidate[trampoline : trampoline + 8] = _absolute_tail_jump(symbols[symbol])
        allowed.append(ByteRange(trampoline, trampoline + 8))
    candidate[PAYLOAD_START : PAYLOAD_START + len(payload)] = payload
    allowed.append(ByteRange(PAYLOAD_START, PAYLOAD_START + len(payload)))
    refresh_recovery_crc(candidate, AP01_1_0_2_0041)
    allowed.append(ByteRange(AP01_1_0_2_0041.recovery_trailer_offset + 36, AP01_1_0_2_0041.recovery_trailer_offset + 40))
    report = validate_candidate(baseline, bytes(candidate), allowed, AP01_1_0_2_0041)
    simulation = run_interaction_simulation(InteractionContract(name="FW-PAGE-011", local_hook_labels=tuple(item[3] for item in HOOKS), overview_right_target_dispatch=0, power_left_enters_agents=True, stock_entry_filter_enabled=True, power_confirm_isolated=False, power_confirm_guard_enabled=True, power_confirm_guard_calls_stock_clock=True, page_registration_unchanged=True, global_key_callback_registration_unchanged=True, fixed_shared_pages_enabled=True, fixed_hidden_primary_pages_enabled=True, weather_hidden_primary_page_enabled=True, calendar_skip_direction_correct=True, weather_skip_direction_correct=True))
    if not simulation["summary"]["passed"]:
        raise AgentsDashboardFirmwareError("连续页面事件模拟失败")
    _write_frozen(output, bytes(candidate))
    readback = output.resolve().read_bytes()
    readback_report = validate_candidate(baseline, readback, allowed, AP01_1_0_2_0041)
    document = {"schema_version": 1, "status": "offline-build-passed-not-installed", "input": baseline_report.to_dict(), "output": {"path": str(output), "read_only": True, **readback_report.to_dict()}, "payload": {"path": str(binary), "elf": str(elf), "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "runtime_address": f"0x{PAYLOAD_VA:08x}"}, "implemented_scope": ["AGENTS 看板四张内置页面", "萌宠复用与局部旋钮入口", "一级页面隐藏日历和天气", "功率确认连接保护"], "preserved_0041_features": ["插件屏保类型", "夜间屏幕模式", "蜂鸣器开关", "设备按键快速返回"], "interaction_simulation": simulation, "allowed_ranges": [item.to_dict() for item in allowed]}
    _write_json(manifest, document)
    return document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--build-directory", type=Path, default=BUILD_DIRECTORY)
    options = parser.parse_args()
    document = build(options.output, options.manifest, options.build_directory)
    print(json.dumps(document["output"], ensure_ascii=False))


if __name__ == "__main__":
    main()
