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

from core.firmware_image import (
    AP01_1_0_2_0031,
    ByteRange,
    refresh_recovery_crc,
    validate_candidate,
)
from features.firmware_payload_space import (
    GIF_DATA_OFFSET,
    GIF_SIZE_OFFSET,
    OPTIMIZED_SIZE,
    ORIGINAL_SIZE,
    ORIGINAL_SHA256,
    PAYLOAD_CAPACITY,
    PAYLOAD_START,
    inspect_payload_space,
)
from .fallback_assets import (
    FallbackAsset,
    FallbackAssetError,
    build_fallback_assets,
)


MODULE_DIR = Path(__file__).resolve().parent
SOURCE = MODULE_DIR / "page_registration.S"
LINKER = MODULE_DIR / "page_registration.ld"
OBSERVATION_APPROVAL = MODULE_DIR / "observation_approval_record.json"
FONT_DIRECTORY = MODULE_DIR.parents[1] / "env/fonts"
XIP_DELTA = 0x9FFFF000
PAYLOAD_VA = XIP_DELTA + PAYLOAD_START
HOOK_VA = 0xA00B2732
HOOK_OFFSET = HOOK_VA - XIP_DELTA
HOOK_ORIGINAL = bytes.fromhex("5285eff02079")
TRAMPOLINE_VA = 0xA001B0AC
TRAMPOLINE_OFFSET = TRAMPOLINE_VA - XIP_DELTA
TRAMPOLINE_ORIGINAL = b"\x00" * 8
KEY_CALLBACK_HIGH_OFFSET = 0x0B3838
KEY_CALLBACK_HIGH_ORIGINAL = bytes.fromhex("b7c50ba0")
KEY_CALLBACK_LOW_OFFSET = 0x0B3842
KEY_CALLBACK_LOW_ORIGINAL = bytes.fromhex("9385e5fe")
EXPECTED_BINUTILS_VERSION = "2.46.1"
REQUIRED_CALLEES = (
    0xA00C1EC6,
    0xA00BEBEE,
    0xA00C0060,
    0xA00C5D84,
    0xA01AA0B6,
    0xA01930FE,
    0xA00CF8D8,
    0xA00BF7EA,
    0xA00B06F4,
    0xA007E1C4,
    0xA007C256,
    0xA00BBFEE,
)
EXPECTED_PAYLOAD_SIZE = 27_472
EXPECTED_PAYLOAD_SHA256 = (
    "0ef5f27dbf2e37014d3523667e2b597d88a226f4ca2d416dcae79e6b8e9ed910"
)
OBSERVATION_OUTPUT_FILENAME = "ap01-1.0.2_0031-agents-observation.bin"
STAGE_SIZE = 6_804_520
STAGE_SHA256 = "348d0843ac3f3f380eb155170c4104fd8467a018ddfd13670d67be998f269dc1"


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


@dataclass(frozen=True)
class ObservationBuildResult:
    output: Path
    manifest: Path
    sha256: str
    md5: str
    recovery_crc: int


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


def _absolute_lui_addi(target: int, register: int) -> tuple[bytes, bytes]:
    high, low = _split_absolute(target)
    lui = ((high & 0xFFFFF) << 12) | (register << 7) | 0x37
    addi = (
        ((low & 0xFFF) << 20)
        | (register << 15)
        | (register << 7)
        | 0x13
    )
    return struct.pack("<I", lui), struct.pack("<I", addi)


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


def _write_asset_assembly(
    path: Path,
    assets: tuple[FallbackAsset, ...],
) -> None:
    lines = [
        '    .section .assets, "a", @progbits',
        "    .balign 4",
    ]
    for asset in assets:
        selected = str(asset.path)
        if '"' in selected or "\n" in selected:
            raise AgentsDashboardFirmwareError("等待页面路径包含汇编不允许的字符")
        symbol = f"agents_fallback_{asset.key}"
        lines.extend(
            (
                f"    .global {symbol}_descriptor",
                f"{symbol}_descriptor:",
                "    .word 0x00000119",
                "    .word 0",
                "    .word 0",
                f"    .word {symbol}_end - {symbol}_data",
                f"    .word {symbol}_data",
                "    .word 0",
                "    .word 0",
                f"{symbol}_data:",
                f'    .incbin "{selected}"',
                f"{symbol}_end:",
                "    .balign 4",
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


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


def _write_frozen(path: Path, payload: bytes) -> None:
    selected = path.expanduser().resolve()
    if selected.exists():
        raise AgentsDashboardFirmwareError(f"不可覆盖已经存在的观察成品：{selected}")
    selected.parent.mkdir(parents=True, exist_ok=True)
    temporary = selected.with_name(selected.name + ".part")
    if temporary.exists():
        raise AgentsDashboardFirmwareError(f"发现未处理的临时成品：{temporary}")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.read_bytes() != payload:
            raise AgentsDashboardFirmwareError("观察成品写后回读不一致")
        os.replace(temporary, selected)
        selected.chmod(0o444)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_observation_approval(output_sha256: str) -> dict[str, object]:
    try:
        document = json.loads(OBSERVATION_APPROVAL.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AgentsDashboardFirmwareError("无法读取真机观察安装批准记录") from error
    expected = {
        "schema_version": 1,
        "status": "approved-for-one-installation",
        "target_model": AP01_1_0_2_0031.model,
        "target_version": AP01_1_0_2_0031.version,
        "output_filename": OBSERVATION_OUTPUT_FILENAME,
        "output_sha256": output_sha256,
        "installation_consumed_at_beijing": None,
    }
    for field, value in expected.items():
        if document.get(field) != value:
            raise AgentsDashboardFirmwareError(f"真机观察批准记录字段不匹配：{field}")
    risk_override = document.get("risk_override")
    if not isinstance(risk_override, list) or len(risk_override) != 4:
        raise AgentsDashboardFirmwareError("真机观察批准记录必须固定四项风险跳过范围")
    return document


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
    if (
        stage[
            KEY_CALLBACK_HIGH_OFFSET : KEY_CALLBACK_HIGH_OFFSET
            + len(KEY_CALLBACK_HIGH_ORIGINAL)
        ]
        != KEY_CALLBACK_HIGH_ORIGINAL
        or stage[
            KEY_CALLBACK_LOW_OFFSET : KEY_CALLBACK_LOW_OFFSET
            + len(KEY_CALLBACK_LOW_ORIGINAL)
        ]
        != KEY_CALLBACK_LOW_ORIGINAL
    ):
        raise AgentsDashboardFirmwareError("一级键值回调地址旧字节不匹配")

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
    optimized_source_path = selected / "optimized-source.gif"
    payload_space_report_path = selected / "payload-space-report.json"
    payload_space_report = inspect_payload_space(
        stage_path,
        optimized_source_path,
        payload_space_report_path,
        tool_revision=tool_revision,
    )
    object_path = selected / "page-registration.o"
    asset_object_path = selected / "fallback-assets.o"
    asset_source_path = selected / "fallback-assets.S"
    try:
        assets = build_fallback_assets(
            FONT_DIRECTORY,
            selected / "fallback-assets",
        )
    except FallbackAssetError as error:
        raise AgentsDashboardFirmwareError(str(error)) from error
    _write_asset_assembly(asset_source_path, assets)
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
            assembler,
            "-march=rv32imac",
            "-mabi=ilp32",
            "-o",
            asset_object_path,
            asset_source_path,
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
            asset_object_path,
        ]
    )
    _run([copier, "-O", "binary", "-j", ".payload", elf_path, binary_path])
    payload = binary_path.read_bytes()
    if not payload or len(payload) > PAYLOAD_CAPACITY:
        raise AgentsDashboardFirmwareError("页面注册载荷为空或超过固定候选空间")
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    if (
        len(payload) != EXPECTED_PAYLOAD_SIZE
        or payload_sha256 != EXPECTED_PAYLOAD_SHA256
    ):
        raise AgentsDashboardFirmwareError("页面与等待资源载荷固定指纹不匹配")

    symbols = _symbols(nm, elf_path)
    entry = symbols.get("ap01_agents_page_register")
    if entry != PAYLOAD_VA:
        raise AgentsDashboardFirmwareError("页面注册载荷入口地址不匹配")
    key_event = symbols.get("ap01_agents_key_event")
    if key_event is None:
        raise AgentsDashboardFirmwareError("AGENTS 键值包装入口符号缺失")
    for asset in assets:
        symbol = f"agents_fallback_{asset.key}"
        descriptor = symbols.get(f"{symbol}_descriptor")
        data = symbols.get(f"{symbol}_data")
        end = symbols.get(f"{symbol}_end")
        if None in (descriptor, data, end):
            raise AgentsDashboardFirmwareError(
                f"等待页面描述符号缺失：{asset.key}"
            )
        assert descriptor is not None and data is not None and end is not None
        descriptor_offset = descriptor - PAYLOAD_VA
        if (
            descriptor_offset < 0
            or descriptor_offset + 28 > len(payload)
            or end - data != asset.size
        ):
            raise AgentsDashboardFirmwareError(
                f"等待页面描述边界不匹配：{asset.key}"
            )
        header, _, _, size, pointer, _, _ = struct.unpack_from(
            "<7I", payload, descriptor_offset
        )
        if header != 0x119 or size != asset.size or pointer != data:
            raise AgentsDashboardFirmwareError(
                f"等待页面描述内容不匹配：{asset.key}"
            )

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
    key_callback_high, key_callback_low = _absolute_lui_addi(
        key_event,
        register=11,
    )
    result = PayloadResult(
        size=len(payload),
        sha256=payload_sha256,
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
        "optimized_source_resource": {
            "file": str(optimized_source_path),
            "report": str(payload_space_report_path),
            "data_offset": f"0x{GIF_DATA_OFFSET:06x}",
            "size_offset": f"0x{GIF_SIZE_OFFSET:06x}",
            "original_size": ORIGINAL_SIZE,
            "optimized_size": OPTIMIZED_SIZE,
            "optimized_sha256": payload_space_report["resource"][
                "optimized_sha256"
            ],
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
        "fallback_assets": [
            {
                "key": asset.key,
                "title": asset.title,
                "file": str(asset.path),
                "size": asset.size,
                "sha256": asset.sha256,
                "width": 320,
                "height": 240,
                "frames": 2,
                "frame_duration_ms": 800,
            }
            for asset in assets
        ],
        "draft_modifications": [
            {
                "name": "原厂第一张动图数据长度",
                "offset": f"0x{GIF_SIZE_OFFSET:06x}",
                "expected_before_hex": struct.pack("<I", ORIGINAL_SIZE).hex(),
                "replacement_hex": struct.pack("<I", OPTIMIZED_SIZE).hex(),
            },
            {
                "name": "原厂第一张动图无损优化结果",
                "offset": f"0x{GIF_DATA_OFFSET:06x}",
                "length": OPTIMIZED_SIZE,
                "replacement_sha256": payload_space_report["resource"][
                    "optimized_sha256"
                ],
            },
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
                "name": "一级键值回调包装地址高位",
                "offset": f"0x{KEY_CALLBACK_HIGH_OFFSET:06x}",
                "expected_before_hex": KEY_CALLBACK_HIGH_ORIGINAL.hex(),
                "replacement_hex": key_callback_high.hex(),
            },
            {
                "name": "一级键值回调包装地址低位",
                "offset": f"0x{KEY_CALLBACK_LOW_OFFSET:06x}",
                "expected_before_hex": KEY_CALLBACK_LOW_ORIGINAL.hex(),
                "replacement_hex": key_callback_low.hex(),
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
            "key_callback_old_bytes_match": True,
            "payload_fits": True,
            "entry_matches": True,
            "key_event_entry_present": True,
            "required_callees_present": True,
            "fallback_descriptors_valid": True,
            "relocations_zero": True,
            "firmware_output_allowed": False,
            "reason": "当前完成独立页面、四张内置等待页、概览显示和详情旋钮事件，尚未完成刷新",
        },
    }
    _write_report(report_path, document)
    return document


def build_observation_firmware(
    stage_path: Path,
    output_path: Path,
    manifest_path: Path,
    build_directory: Path,
    *,
    tool_revision: dict[str, object],
) -> ObservationBuildResult:
    """把已验证页面载荷组合成专用测试设备的首次真机观察成品。"""

    if tool_revision.get("scoped_code_dirty") is not False:
        raise AgentsDashboardFirmwareError("制作代码尚未提交，不能冻结真机观察成品")
    output = output_path.expanduser().resolve()
    if output.name != OBSERVATION_OUTPUT_FILENAME:
        raise AgentsDashboardFirmwareError(
            f"观察成品文件名必须是 {OBSERVATION_OUTPUT_FILENAME}"
        )
    stage_selected, stage = _read_stage(stage_path)
    if (
        len(stage) != STAGE_SIZE
        or hashlib.sha256(stage).hexdigest() != STAGE_SHA256
    ):
        raise AgentsDashboardFirmwareError("已验收设置菜单阶段成品身份不匹配")

    selected_build = build_directory.expanduser().resolve()
    payload_report_path = selected_build / "payload-report.json"
    payload_report = build_page_registration_payload(
        stage_selected,
        selected_build / "payload",
        payload_report_path,
        tool_revision=tool_revision,
    )
    payload = Path(str(payload_report["payload"]["file"])).read_bytes()
    optimized = Path(
        str(payload_report["optimized_source_resource"]["file"])
    ).read_bytes()
    draft = payload_report["draft_modifications"]
    if not isinstance(draft, list) or len(draft) != 7:
        raise AgentsDashboardFirmwareError("页面载荷修改清单结构不匹配")

    candidate = bytearray(stage)

    def replace(
        offset: int,
        expected: bytes,
        replacement: bytes,
        name: str,
    ) -> ByteRange:
        end = offset + len(expected)
        if len(expected) != len(replacement):
            raise AgentsDashboardFirmwareError(f"{name} 修改前后长度不一致")
        if bytes(candidate[offset:end]) != expected:
            raise AgentsDashboardFirmwareError(f"{name} 修改前旧字节不匹配")
        candidate[offset:end] = replacement
        return ByteRange(offset, end)

    allowed: list[ByteRange] = []
    allowed.append(
        replace(
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
    allowed.append(
        replace(
            HOOK_OFFSET,
            HOOK_ORIGINAL,
            bytes.fromhex(draft[2]["replacement_hex"]),
            "页面挂接",
        )
    )
    allowed.append(
        replace(
            TRAMPOLINE_OFFSET,
            TRAMPOLINE_ORIGINAL,
            bytes.fromhex(draft[3]["replacement_hex"]),
            "页面跳板",
        )
    )
    allowed.append(
        replace(
            KEY_CALLBACK_HIGH_OFFSET,
            KEY_CALLBACK_HIGH_ORIGINAL,
            bytes.fromhex(draft[4]["replacement_hex"]),
            "一级键值回调地址高位",
        )
    )
    allowed.append(
        replace(
            KEY_CALLBACK_LOW_OFFSET,
            KEY_CALLBACK_LOW_ORIGINAL,
            bytes.fromhex(draft[5]["replacement_hex"]),
            "一级键值回调地址低位",
        )
    )
    payload_before = bytes(candidate[PAYLOAD_START : PAYLOAD_START + len(payload)])
    candidate[PAYLOAD_START : PAYLOAD_START + len(payload)] = payload
    if payload_before == payload:
        raise AgentsDashboardFirmwareError("页面载荷写入前后完全相同")
    allowed.append(ByteRange(PAYLOAD_START, PAYLOAD_START + len(payload)))

    recovery_crc = refresh_recovery_crc(candidate, AP01_1_0_2_0031)
    recovery_range = ByteRange(
        AP01_1_0_2_0031.recovery_trailer_offset + 36,
        AP01_1_0_2_0031.recovery_trailer_offset + 40,
    )
    allowed.append(recovery_range)
    candidate_report = validate_candidate(
        stage,
        bytes(candidate),
        allowed,
        AP01_1_0_2_0031,
    )
    approval = _load_observation_approval(candidate_report.sha256)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "manifest_type": "agents-observation-firmware",
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
            **candidate_report.to_dict(),
        },
        "payload_report": str(payload_report_path),
        "approval": approval,
        "allowed_ranges": [item.to_dict() for item in allowed],
        "recovery_crc_after_build": f"0x{recovery_crc:08x}",
        "implemented_scope": [
            "AGENTS 一级页面",
            "四张内置等待页",
            "概览进入详情",
            "三个详情首尾循环",
            "返回概览",
        ],
        "pending_measurements": [
            "任务栈上限",
            "接收与解码缓冲峰值",
            "/data 可用空间",
            "连续刷新内存变化",
            "断电恢复结果",
        ],
        "validation": {
            "old_bytes_asserted": True,
            "total_length_preserved": True,
            "immutable_header_preserved": True,
            "recovery_structure_preserved": True,
            "outside_allowed_ranges_identical": True,
            "installation_scope": "专用测试设备单次真机观察",
        },
    }
    output_written = False
    try:
        _write_frozen(output, bytes(candidate))
        output_written = True
        readback = output.read_bytes()
        readback_report = validate_candidate(
            stage,
            readback,
            allowed,
            AP01_1_0_2_0031,
        )
        if readback_report.sha256 != candidate_report.sha256:
            raise AgentsDashboardFirmwareError("观察成品回读指纹不一致")
        _write_report(manifest_path, manifest)
        manifest_path.expanduser().resolve().chmod(0o444)
    except Exception:
        if output_written and output.exists():
            output.chmod(0o644)
            output.unlink()
        raise
    return ObservationBuildResult(
        output=output,
        manifest=manifest_path.expanduser().resolve(),
        sha256=candidate_report.sha256,
        md5=candidate_report.md5,
        recovery_crc=recovery_crc,
    )
