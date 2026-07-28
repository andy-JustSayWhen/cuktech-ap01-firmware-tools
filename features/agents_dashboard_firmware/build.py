"""编译并验证 AGENTS 看板第一阶段页面注册载荷。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import struct
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from features.firmware_payload_space import (
    PAYLOAD_CAPACITY,
    PAYLOAD_START,
)


MODULE_DIR = Path(__file__).resolve().parent
SOURCE = MODULE_DIR / "page_registration.S"
LINKER = MODULE_DIR / "page_registration.ld"
XIP_DELTA = 0x9FFFF000
PAYLOAD_VA = XIP_DELTA + PAYLOAD_START
HOOK_VA = 0xA00B2732
HOOK_OFFSET = HOOK_VA - XIP_DELTA
HOOK_ORIGINAL = bytes.fromhex("5285eff02079")
TRAMPOLINE_VA = 0xA001B0AC
TRAMPOLINE_OFFSET = TRAMPOLINE_VA - XIP_DELTA
TRAMPOLINE_ORIGINAL = b"\x00" * 8
EXPECTED_BINUTILS_VERSION = "2.46.1"
REQUIRED_CALLEES = (0xA00C1EC6, 0xA00C0060)


class AgentsDashboardFirmwareError(RuntimeError):
    """AGENTS 看板设备端载荷没有通过构建门禁。"""


@dataclass(frozen=True)
class PayloadResult:
    size: int
    sha256: str
    entry: int
    hook: bytes
    trampoline: bytes
    binary: Path
    elf: Path


def _tool(name: str) -> Path:
    discovered = shutil.which(name)
    if not discovered:
        raise AgentsDashboardFirmwareError(f"缺少构建工具：{name}")
    return Path(discovered).resolve()


def _version(tool: Path) -> str:
    try:
        completed = subprocess.run(
            [str(tool), "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AgentsDashboardFirmwareError(f"无法读取构建工具版本：{tool}") from error
    first_line = completed.stdout.splitlines()[0] if completed.stdout else ""
    if EXPECTED_BINUTILS_VERSION not in first_line:
        raise AgentsDashboardFirmwareError(
            f"构建工具版本不匹配：预期 {EXPECTED_BINUTILS_VERSION}，实际 {first_line}"
        )
    return first_line


def _run(command: list[object], *, capture: bool = False) -> str:
    try:
        completed = subprocess.run(
            [str(item) for item in command],
            check=True,
            capture_output=capture,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AgentsDashboardFirmwareError(
            f"载荷构建命令失败：{Path(str(command[0])).name}"
        ) from error
    return completed.stdout if capture else ""


def _split_absolute(address: int) -> tuple[int, int]:
    low = address & 0xFFF
    if low >= 0x800:
        low -= 0x1000
    return (address - low) >> 12, low


def _encode_jal(source: int, target: int) -> bytes:
    offset = target - source
    if offset & 1 or not -(1 << 20) <= offset < (1 << 20):
        raise AgentsDashboardFirmwareError("页面挂接跳转超出直接跳转范围")
    immediate = offset & 0x1FFFFF
    word = (
        (((immediate >> 20) & 1) << 31)
        | (((immediate >> 1) & 0x3FF) << 21)
        | (((immediate >> 11) & 1) << 20)
        | (((immediate >> 12) & 0xFF) << 12)
        | (1 << 7)
        | 0x6F
    )
    return struct.pack("<I", word)


def _absolute_tail_jump(target: int) -> bytes:
    high, low = _split_absolute(target)
    lui = ((high & 0xFFFFF) << 12) | (5 << 7) | 0x37
    jalr = ((low & 0xFFF) << 20) | (5 << 15) | 0x67
    return struct.pack("<II", lui, jalr)


def _read_stage(path: Path) -> tuple[Path, bytes]:
    selected = path.expanduser().resolve(strict=True)
    if not selected.is_file():
        raise AgentsDashboardFirmwareError(f"阶段固件不是普通文件：{selected}")
    writable_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    if selected.stat().st_mode & writable_bits:
        raise AgentsDashboardFirmwareError(f"阶段固件必须先设为只读：{selected}")
    return selected, selected.read_bytes()


def _symbols(nm: Path, elf: Path) -> dict[str, int]:
    output = _run([nm, "-n", elf], capture=True)
    result: dict[str, int] = {}
    undefined: list[str] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "U":
            undefined.append(parts[1])
        elif len(parts) >= 3:
            try:
                result[parts[-1]] = int(parts[0], 16)
            except ValueError:
                continue
    if undefined:
        raise AgentsDashboardFirmwareError(
            f"载荷存在未解析符号：{', '.join(undefined)}"
        )
    return result


def _write_report(path: Path, document: dict[str, object]) -> None:
    selected = path.expanduser().resolve()
    selected.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = selected.with_name(selected.name + ".part")
    if temporary.exists():
        raise AgentsDashboardFirmwareError(f"发现未处理的临时报告：{temporary}")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, selected)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_page_registration_payload(
    stage_path: Path,
    build_directory: Path,
    report_path: Path,
    *,
    tool_revision: dict[str, object],
) -> dict[str, object]:
    """构建页面注册载荷，但不生成候选固件。"""

    stage_selected, stage = _read_stage(stage_path)
    if stage[HOOK_OFFSET : HOOK_OFFSET + len(HOOK_ORIGINAL)] != HOOK_ORIGINAL:
        raise AgentsDashboardFirmwareError("页面挂接点旧字节不匹配")
    if (
        stage[TRAMPOLINE_OFFSET : TRAMPOLINE_OFFSET + 8]
        != TRAMPOLINE_ORIGINAL
    ):
        raise AgentsDashboardFirmwareError("页面跳板区间不再是全零")

    assembler = _tool("riscv64-elf-as")
    linker = _tool("riscv64-elf-ld")
    copier = _tool("riscv64-elf-objcopy")
    dumper = _tool("riscv64-elf-objdump")
    nm = _tool("riscv64-elf-nm")
    readelf = _tool("riscv64-elf-readelf")
    tool_versions = {
        item.name: _version(item)
        for item in (assembler, linker, copier, dumper, nm, readelf)
    }

    selected = build_directory.expanduser().resolve()
    selected.mkdir(parents=True, exist_ok=True)
    object_path = selected / "page-registration.o"
    elf_path = selected / "page-registration.elf"
    binary_path = selected / "page-registration.bin"
    map_path = selected / "page-registration.map"
    disassembly_path = selected / "page-registration.disassembly.txt"
    readelf_path = selected / "page-registration.readelf.txt"

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
            f"-Map={map_path}",
            "-T",
            LINKER,
            "-o",
            elf_path,
            object_path,
        ]
    )
    _run([copier, "-O", "binary", "-j", ".payload", elf_path, binary_path])
    payload = binary_path.read_bytes()
    if not payload or len(payload) > PAYLOAD_CAPACITY:
        raise AgentsDashboardFirmwareError("页面注册载荷为空或超过固定候选空间")

    symbols = _symbols(nm, elf_path)
    entry = symbols.get("ap01_agents_page_register")
    if entry != PAYLOAD_VA:
        raise AgentsDashboardFirmwareError("页面注册载荷入口地址不匹配")

    disassembly = _run(
        [dumper, "-d", "-M", "no-aliases,numeric", elf_path],
        capture=True,
    )
    for callee in REQUIRED_CALLEES:
        if f"{callee:08x}" not in disassembly.lower():
            raise AgentsDashboardFirmwareError(
                f"载荷缺少已验证原厂调用：0x{callee:08x}"
            )
    disassembly_path.write_text(disassembly, encoding="utf-8")
    readelf_output = _run(
        [readelf, "-h", "-S", "-s", "-r", elf_path],
        capture=True,
    )
    if "There are no relocations in this file." not in readelf_output:
        raise AgentsDashboardFirmwareError("页面注册载荷仍含未处理重定位")
    readelf_path.write_text(readelf_output, encoding="utf-8")

    hook = _encode_jal(HOOK_VA, TRAMPOLINE_VA) + bytes.fromhex("0100")
    trampoline = _absolute_tail_jump(PAYLOAD_VA)
    result = PayloadResult(
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        entry=entry,
        hook=hook,
        trampoline=trampoline,
        binary=binary_path,
        elf=elf_path,
    )
    document: dict[str, object] = {
        "schema_version": 1,
        "report_type": "agents-page-registration-payload",
        "status": "draft-not-approved-for-firmware-output",
        "built_at_beijing": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
            timespec="seconds"
        ),
        "tool": {**tool_revision, "versions": tool_versions},
        "input": {
            "path": str(stage_selected),
            "read_only": True,
        },
        "payload": {
            "file": str(result.binary),
            "file_offset": f"0x{PAYLOAD_START:06x}",
            "runtime_address": f"0x{result.entry:08x}",
            "capacity": PAYLOAD_CAPACITY,
            "size": result.size,
            "sha256": result.sha256,
            "remaining": PAYLOAD_CAPACITY - result.size,
            "required_callees": [f"0x{value:08x}" for value in REQUIRED_CALLEES],
            "relocations": 0,
        },
        "draft_modifications": [
            {
                "name": "AGENTS 页面注册挂接",
                "offset": f"0x{HOOK_OFFSET:06x}",
                "expected_before_hex": HOOK_ORIGINAL.hex(),
                "replacement_hex": result.hook.hex(),
            },
            {
                "name": "AGENTS 页面绝对跳板",
                "offset": f"0x{TRAMPOLINE_OFFSET:06x}",
                "expected_before_hex": TRAMPOLINE_ORIGINAL.hex(),
                "replacement_hex": result.trampoline.hex(),
            },
            {
                "name": "AGENTS 页面注册载荷",
                "offset": f"0x{PAYLOAD_START:06x}",
                "length": result.size,
                "replacement_sha256": result.sha256,
            },
        ],
        "gates": {
            "hook_old_bytes_match": True,
            "trampoline_space_zero": True,
            "payload_fits": True,
            "entry_matches": True,
            "required_callees_present": True,
            "relocations_zero": True,
            "firmware_output_allowed": False,
            "reason": "当前只完成独立页面根对象注册载荷，尚未完成画面、详情事件和刷新",
        },
    }
    _write_report(report_path, document)
    return document
