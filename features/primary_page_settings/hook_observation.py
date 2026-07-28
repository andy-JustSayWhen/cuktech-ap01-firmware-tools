"""构建只复现原厂设置分支行为的空挂接观察固件。"""

from __future__ import annotations

import hashlib
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
from core.firmware_payload_space import PAYLOAD_CAPACITY, PAYLOAD_START


MODULE_DIR = Path(__file__).resolve().parent
SOURCE = MODULE_DIR / "hook_observation.S"
OUTPUT_NAME = "ap01-1.0.2_0031-page-settings-hook-observation.bin"
STAGE_SIZE = 6_804_520
STAGE_SHA256 = "a0f43b8d8214d6649846618098bc13c71815d44642b31c9f949e16765fde2616"
STAGE_MD5 = "a64838d73ccbbe913fc8938505ee7232"
STAGE_PAYLOAD_SIZE = 32_056
PAYLOAD_VA = 0xA02465D0
HOOK_OFFSET = 0x1999DC
HOOK_VA = 0xA01989DC
HOOK_ORIGINAL = bytes.fromhex("638ae70e")
MENU_LIMIT_OFFSET = 0x1999B4
MENU_LIMIT_ORIGINAL = bytes.fromhex("9d47")
SETTINGS_CALLBACK_HIGH_OFFSET = 0x0BE8CC
SETTINGS_CALLBACK_HIGH_ORIGINAL = bytes.fromhex("b7850fa0")
SETTINGS_CALLBACK_LOW_OFFSET = 0x0BE8D4
SETTINGS_CALLBACK_LOW_ORIGINAL = bytes.fromhex("93856509")


class SettingsHookObservationError(RuntimeError):
    """设置列表空挂接成品不满足固定合同。"""


@dataclass(frozen=True)
class SettingsHookObservationResult:
    output: Path
    manifest: Path
    sha256: str
    md5: str
    payload_size: int
    payload_remaining: int


def _run(command: list[Path | str]) -> str:
    try:
        completed = subprocess.run(
            [str(item) for item in command],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise SettingsHookObservationError("无法启动空挂接构建工具") from error
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise SettingsHookObservationError(f"空挂接构建失败：{detail}")
    return completed.stdout


def _load_stage(path: Path) -> tuple[Path, bytes]:
    selected = path.expanduser().resolve(strict=True)
    if not selected.is_file():
        raise SettingsHookObservationError("空挂接输入不是普通文件")
    writable = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    if selected.stat().st_mode & writable:
        raise SettingsHookObservationError("空挂接输入必须为只读文件")
    payload = selected.read_bytes()
    if len(payload) != STAGE_SIZE:
        raise SettingsHookObservationError("空挂接输入文件长度不匹配")
    if hashlib.sha256(payload).hexdigest() != STAGE_SHA256:
        raise SettingsHookObservationError("空挂接输入 SHA-256 不匹配")
    if hashlib.md5(payload).hexdigest() != STAGE_MD5:
        raise SettingsHookObservationError("空挂接输入 MD5 不匹配")
    if payload[HOOK_OFFSET : HOOK_OFFSET + 4] != HOOK_ORIGINAL:
        raise SettingsHookObservationError("原厂设置分支字节不匹配")
    if payload[MENU_LIMIT_OFFSET : MENU_LIMIT_OFFSET + 2] != MENU_LIMIT_ORIGINAL:
        raise SettingsHookObservationError("设置循环上限不是原厂 7 项")
    if (
        payload[
            SETTINGS_CALLBACK_HIGH_OFFSET : SETTINGS_CALLBACK_HIGH_OFFSET + 4
        ]
        != SETTINGS_CALLBACK_HIGH_ORIGINAL
        or payload[
            SETTINGS_CALLBACK_LOW_OFFSET : SETTINGS_CALLBACK_LOW_OFFSET + 4
        ]
        != SETTINGS_CALLBACK_LOW_ORIGINAL
    ):
        raise SettingsHookObservationError("设置事件回调不是上一版原厂路径")
    return selected, payload


def _jump(source: int, target: int) -> bytes:
    offset = target - source
    if offset & 1 or not -(1 << 20) <= offset < (1 << 20):
        raise SettingsHookObservationError("空挂接跳转超出范围")
    immediate = offset & 0x1FFFFF
    word = (
        (((immediate >> 20) & 1) << 31)
        | (((immediate >> 1) & 0x3FF) << 21)
        | (((immediate >> 11) & 1) << 20)
        | (((immediate >> 12) & 0xFF) << 12)
        | 0x6F
    )
    return struct.pack("<I", word)


def _write_frozen(path: Path, payload: bytes) -> Path:
    selected = path.expanduser().resolve()
    selected.parent.mkdir(parents=True, exist_ok=True)
    if selected.exists():
        raise SettingsHookObservationError(f"不可覆盖冻结文件：{selected}")
    temporary = selected.with_name(selected.name + ".part")
    if temporary.exists():
        raise SettingsHookObservationError(f"发现未处理临时文件：{temporary}")
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


def _build_payload(
    build_directory: Path,
    *,
    assembler: Path,
    linker: Path,
    copier: Path,
    readelf: Path,
    nm: Path,
) -> tuple[bytes, int, Path, Path]:
    selected = build_directory.expanduser().resolve()
    selected.mkdir(parents=True, exist_ok=True)
    object_path = selected / "settings-hook-observation.o"
    elf_path = selected / "settings-hook-observation.elf"
    binary_path = selected / "settings-hook-observation.bin"
    runtime_address = PAYLOAD_VA + STAGE_PAYLOAD_SIZE
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
            f"-Ttext=0x{runtime_address:08x}",
            "-e",
            "ap01_page_settings_hook_passthrough",
            "-o",
            elf_path,
            object_path,
        ]
    )
    relocations = _run([readelf, "-r", elf_path])
    if "There are no relocations in this file." not in relocations:
        raise SettingsHookObservationError("空挂接载荷仍含重定位")
    symbols = _run([nm, "-n", elf_path])
    address: int | None = None
    for line in symbols.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == "ap01_page_settings_hook_passthrough":
            address = int(parts[0], 16)
            break
    if address != runtime_address:
        raise SettingsHookObservationError("空挂接入口地址不匹配")
    _run([copier, "-O", "binary", elf_path, binary_path])
    payload = binary_path.read_bytes()
    if not payload or len(payload) > PAYLOAD_CAPACITY - STAGE_PAYLOAD_SIZE:
        raise SettingsHookObservationError("空挂接载荷不在剩余容量内")
    return payload, runtime_address, elf_path, binary_path


def build_settings_hook_observation(
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
    tool_revision: dict[str, object],
) -> SettingsHookObservationResult:
    """从已验收同步固件生成单一设置分支空挂接成品。"""

    stage_selected, stage = _load_stage(stage_path)
    output = output_path.expanduser().resolve()
    if output.name != OUTPUT_NAME:
        raise SettingsHookObservationError(f"输出文件名必须为 {OUTPUT_NAME}")
    payload, runtime_address, elf_path, binary_path = _build_payload(
        build_directory,
        assembler=assembler,
        linker=linker,
        copier=copier,
        readelf=readelf,
        nm=nm,
    )
    payload_offset = PAYLOAD_START + STAGE_PAYLOAD_SIZE
    payload_end = payload_offset + len(payload)
    before_payload = stage[payload_offset:payload_end]
    candidate = bytearray(stage)
    candidate[payload_offset:payload_end] = payload
    candidate[HOOK_OFFSET : HOOK_OFFSET + 4] = _jump(
        HOOK_VA,
        runtime_address,
    )
    recovery_crc = refresh_recovery_crc(candidate, AP01_1_0_2_0031)
    allowed = (
        ByteRange(HOOK_OFFSET, HOOK_OFFSET + 4),
        ByteRange(payload_offset, payload_end),
        ByteRange(
            AP01_1_0_2_0031.recovery_trailer_offset + 36,
            AP01_1_0_2_0031.recovery_trailer_offset + 40,
        ),
    )
    report = validate_candidate(
        stage,
        bytes(candidate),
        allowed,
        AP01_1_0_2_0031,
    )
    manifest: dict[str, object] = {
        "schema_version": 1,
        "manifest_type": "settings-hook-observation-firmware",
        "status": "built-not-approved-for-installation",
        "built_at_beijing": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
            timespec="seconds"
        ),
        "tool": tool_revision,
        "input": {
            "path": str(stage_selected),
            "size": len(stage),
            "sha256": STAGE_SHA256,
            "md5": STAGE_MD5,
            "read_only": True,
            "accepted_payload_size": STAGE_PAYLOAD_SIZE,
        },
        "output": {
            "path": str(output),
            "read_only": True,
            **report.to_dict(),
        },
        "hook": {
            "file_offset": HOOK_OFFSET,
            "file_offset_hex": f"0x{HOOK_OFFSET:x}",
            "runtime_address": f"0x{HOOK_VA:08x}",
            "old_bytes": HOOK_ORIGINAL.hex(),
            "new_bytes": candidate[HOOK_OFFSET : HOOK_OFFSET + 4].hex(),
            "target": f"0x{runtime_address:08x}",
            "behavior": "完全复现原厂序号分支",
        },
        "payload": {
            "file_offset": payload_offset,
            "file_offset_hex": f"0x{payload_offset:x}",
            "runtime_address": f"0x{runtime_address:08x}",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "before_sha256": hashlib.sha256(before_payload).hexdigest(),
            "capacity": PAYLOAD_CAPACITY,
            "remaining": PAYLOAD_CAPACITY - STAGE_PAYLOAD_SIZE - len(payload),
            "relocations": 0,
            "elf": str(elf_path),
            "binary": str(binary_path),
        },
        "implemented_scope": [
            "设置列表原分支空挂接",
            "原厂七项设置创建行为保持",
        ],
        "excluded_scope": [
            "新增设置项",
            "设置事件包装",
            "一级导航过滤",
            "页面开关状态保存",
        ],
        "allowed_ranges": [item.to_dict() for item in allowed],
        "recovery_crc_after_build": f"0x{recovery_crc:08x}",
        "validation": {
            "input_identity_fixed": True,
            "old_bytes_asserted": True,
            "menu_limit_unchanged": True,
            "settings_callback_unchanged": True,
            "payload_fits": True,
            "relocations_zero": True,
            "total_length_preserved": True,
            "outside_allowed_ranges_identical": True,
            "installation_allowed": False,
        },
    }
    output_written = False
    try:
        _write_frozen(output, bytes(candidate))
        output_written = True
        readback = validate_candidate(
            stage,
            output.read_bytes(),
            allowed,
            AP01_1_0_2_0031,
        )
        if readback.sha256 != report.sha256:
            raise SettingsHookObservationError("空挂接成品回读指纹不一致")
        report_bytes = (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        _write_frozen(manifest_path, report_bytes)
    except Exception:
        if output_written and output.exists():
            output.chmod(0o644)
            output.unlink()
        raise
    return SettingsHookObservationResult(
        output=output,
        manifest=manifest_path.expanduser().resolve(),
        sha256=report.sha256,
        md5=report.md5,
        payload_size=STAGE_PAYLOAD_SIZE + len(payload),
        payload_remaining=PAYLOAD_CAPACITY - STAGE_PAYLOAD_SIZE - len(payload),
    )
