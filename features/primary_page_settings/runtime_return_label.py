"""从 A 阶段构建用户进入设置后更新原厂返回行文字的固件。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.firmware_image import AP01_1_0_2_0031, ByteRange, refresh_recovery_crc, validate_candidate
from core.firmware_payload_space import PAYLOAD_CAPACITY, PAYLOAD_START
from features.agents_dashboard_firmware.build import _absolute_tail_jump, _encode_jal
from .return_row_label import (
    A_PAYLOAD_SHA256, A_PAYLOAD_SIZE, MENU_DISPATCH_A, MENU_DISPATCH_OFFSET,
    MENU_LIMIT_OFFSET, MENU_LIMIT_SEVEN, PAYLOAD_VA, ROW_LABEL,
    SETTINGS_CALLBACK_HIGH_OFFSET, SETTINGS_CALLBACK_HIGH_ORIGINAL,
    SETTINGS_CALLBACK_LOW_OFFSET, SETTINGS_CALLBACK_LOW_ORIGINAL,
    _load_stage, _run, _symbols, _version, _write_frozen,
    PageSettingsReturnRowLabelError,
)

MODULE_DIR = Path(__file__).resolve().parent
SOURCE = MODULE_DIR / "runtime_return_label.S"
LINKER = MODULE_DIR / "runtime_return_label.ld"
OUTPUT_NAME = "ap01-1.0.2_0031-page-settings-runtime-return-label.bin"
USER_CALL_OFFSET = 0x0BE9E6
USER_CALL_ORIGINAL = bytes.fromhex("efa0fd6e")
USER_CALL_VA = 0xA00BD9E6
TRAMPOLINE_OFFSET = 0x01C0B4
TRAMPOLINE_VA = 0xA001B0B4
TRAMPOLINE_ORIGINAL = b"\0" * 8


def build_page_settings_runtime_return_label(stage_path: Path, output_path: Path,
        manifest_path: Path, build_directory: Path, *, assembler: Path, linker: Path,
        copier: Path, readelf: Path, nm: Path, dumper: Path,
        tool_revision: dict[str, object]):
    if tool_revision.get("scoped_code_dirty") is not False:
        raise PageSettingsReturnRowLabelError("制作代码尚未提交，不能冻结运行期返回行文字固件")
    stage_selected, stage = _load_stage(stage_path)
    output = output_path.expanduser().resolve()
    if output.name != OUTPUT_NAME:
        raise PageSettingsReturnRowLabelError(f"输出文件名必须为 {OUTPUT_NAME}")
    versions = {name: _version(tool) for name, tool in {
        "assembler": assembler, "linker": linker, "copier": copier,
        "readelf": readelf, "nm": nm, "dumper": dumper}.items()}

    def payload_once(directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        obj, elf, binary = directory / "payload.o", directory / "payload.elf", directory / "payload.bin"
        _run([assembler, "-march=rv32imac", "-mabi=ilp32", "-o", obj, SOURCE])
        _run([linker, "-m", "elf32lriscv", "--no-relax", "-T", LINKER, "-o", elf, obj])
        relocs = _run([readelf, "-r", elf])
        if "There are no relocations" not in relocs:
            raise PageSettingsReturnRowLabelError("运行期返回行载荷仍含重定位")
        symbols = _symbols(nm, elf)
        wrapper = symbols.get("ap01_page_settings_runtime_return_label")
        if wrapper is None:
            raise PageSettingsReturnRowLabelError("运行期返回行包装入口缺失")
        _run([copier, "-O", "binary", elf, binary])
        payload = binary.read_bytes()
        if len(payload) > PAYLOAD_CAPACITY or hashlib.sha256(payload[:A_PAYLOAD_SIZE]).hexdigest() != A_PAYLOAD_SHA256:
            raise PageSettingsReturnRowLabelError("运行期载荷未保留 A 阶段透传入口或超出空间")
        return payload, wrapper

    root = build_directory.expanduser().resolve()
    first, second = payload_once(root / "first"), payload_once(root / "second")
    if first != second:
        raise PageSettingsReturnRowLabelError("两次运行期返回行载荷构建不一致")
    payload, wrapper = first
    candidate = bytearray(stage)
    allowed: list[ByteRange] = []
    if bytes(candidate[USER_CALL_OFFSET:USER_CALL_OFFSET + 4]) != USER_CALL_ORIGINAL:
        raise PageSettingsReturnRowLabelError("用户进入设置调用原字节不匹配")
    candidate[USER_CALL_OFFSET:USER_CALL_OFFSET + 4] = _encode_jal(USER_CALL_VA, TRAMPOLINE_VA)
    allowed.append(ByteRange(USER_CALL_OFFSET, USER_CALL_OFFSET + 4))
    if bytes(candidate[TRAMPOLINE_OFFSET:TRAMPOLINE_OFFSET + 8]) != TRAMPOLINE_ORIGINAL:
        raise PageSettingsReturnRowLabelError("运行期返回行近跳板原字节不匹配")
    candidate[TRAMPOLINE_OFFSET:TRAMPOLINE_OFFSET + 8] = _absolute_tail_jump(wrapper)
    allowed.append(ByteRange(TRAMPOLINE_OFFSET, TRAMPOLINE_OFFSET + 8))
    candidate[PAYLOAD_START:PAYLOAD_START + len(payload)] = payload
    allowed.append(ByteRange(PAYLOAD_START, PAYLOAD_START + len(payload)))
    for offset, expected in ((MENU_LIMIT_OFFSET, MENU_LIMIT_SEVEN), (MENU_DISPATCH_OFFSET, MENU_DISPATCH_A),
            (SETTINGS_CALLBACK_HIGH_OFFSET, SETTINGS_CALLBACK_HIGH_ORIGINAL),
            (SETTINGS_CALLBACK_LOW_OFFSET, SETTINGS_CALLBACK_LOW_ORIGINAL)):
        if bytes(candidate[offset:offset + len(expected)]) != expected:
            raise PageSettingsReturnRowLabelError("运行期返回行禁止区发生变化")
    crc = refresh_recovery_crc(candidate, AP01_1_0_2_0031)
    allowed.append(ByteRange(AP01_1_0_2_0031.recovery_trailer_offset + 36, AP01_1_0_2_0031.recovery_trailer_offset + 40))
    report = validate_candidate(stage, bytes(candidate), allowed, AP01_1_0_2_0031)
    manifest = {"schema_version": 1, "manifest_type": "page-settings-runtime-return-label-firmware",
        "status": "approved-for-one-test-installation", "tool": {**tool_revision, "versions": versions},
        "input": {"path": str(stage_selected), "read_only": True},
        "output": {"path": str(output), "read_only": True, **report.to_dict()},
        "payload": {"size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            "remaining": PAYLOAD_CAPACITY - len(payload), "wrapper": f"0x{wrapper:08x}", "label": ROW_LABEL},
        "allowed_ranges": [item.to_dict() for item in allowed],
        "validation": {"startup_call_unchanged": True, "seven_items_unchanged": True,
            "settings_callbacks_unchanged": True, "deterministic_links": True,
            "outside_allowed_ranges_identical": True, "installation_allowed": True},
        "recovery_crc_after_build": f"0x{crc:08x}"}
    _write_frozen(output, bytes(candidate))
    _write_frozen(manifest_path, (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    return output, manifest_path.expanduser().resolve(), report.sha256, report.md5
