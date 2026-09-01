"""AP01 固件文件的失效即停止校验能力。"""

from __future__ import annotations

import hashlib
import stat
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class FirmwareValidationError(RuntimeError):
    """固件身份、结构或差异不满足门禁。"""


@dataclass(frozen=True)
class ByteRange:
    """左闭右开的文件字节区间。"""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError(f"无效字节区间：{self.start}:{self.end}")

    @property
    def length(self) -> int:
        return self.end - self.start

    def contains(self, offset: int) -> bool:
        return self.start <= offset < self.end

    def overlaps(self, other: ByteRange) -> bool:
        return self.start < other.end and other.start < self.end

    def to_dict(self) -> dict[str, object]:
        return {
            "start": self.start,
            "start_hex": f"0x{self.start:x}",
            "end_exclusive": self.end,
            "end_exclusive_hex": f"0x{self.end:x}",
            "length": self.length,
        }


@dataclass(frozen=True)
class BaselineDefinition:
    """一个精确原厂固件基线的固定身份与结构。"""

    model: str
    version: str
    size: int
    md5: str
    sha256: str
    header_markers: tuple[tuple[int, bytes], ...]
    model_offsets: tuple[int, ...]
    recovery_tag: bytes
    recovery_tag_offsets: tuple[int, ...]
    recovery_trailer_offset: int
    recovery_crc_value: int
    immutable_header_end: int


@dataclass(frozen=True)
class RecoveryTrailer:
    offset: int
    stored_length: int
    stored_crc: int
    calculated_crc: int

    def to_dict(self) -> dict[str, object]:
        return {
            "offset": self.offset,
            "offset_hex": f"0x{self.offset:x}",
            "stored_length": self.stored_length,
            "stored_crc": f"0x{self.stored_crc:08x}",
            "calculated_crc": f"0x{self.calculated_crc:08x}",
        }


@dataclass(frozen=True)
class BaselineReport:
    model: str
    version: str
    size: int
    md5: str
    sha256: str
    model_offsets: tuple[int, ...]
    recovery: RecoveryTrailer

    def to_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "version": self.version,
            "size": self.size,
            "md5": self.md5,
            "sha256": self.sha256,
            "model_offsets": [
                {"offset": value, "offset_hex": f"0x{value:x}"}
                for value in self.model_offsets
            ],
            "recovery": self.recovery.to_dict(),
        }


@dataclass(frozen=True)
class CandidateReport:
    size: int
    md5: str
    sha256: str
    recovery: RecoveryTrailer
    changed_ranges: tuple[ByteRange, ...]
    changed_bytes: int
    outside_allowed_ranges_identical: bool
    immutable_header_identical: bool
    recovery_structure_identical: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "size": self.size,
            "md5": self.md5,
            "sha256": self.sha256,
            "recovery": self.recovery.to_dict(),
            "changed_ranges": [item.to_dict() for item in self.changed_ranges],
            "changed_bytes": self.changed_bytes,
            "outside_allowed_ranges_identical": self.outside_allowed_ranges_identical,
            "immutable_header_identical": self.immutable_header_identical,
            "recovery_structure_identical": self.recovery_structure_identical,
        }


RECOVERY_TAG = b"0x5245434f56455259544147"
RECOVERY_TRAILER_SIZE = 40
RECOVERY_LENGTH_OFFSET = 32
RECOVERY_CRC_OFFSET = 36

AP01_1_0_2_0031 = BaselineDefinition(
    model="njcuk.enstor.ap01",
    version="1.0.2_0031",
    size=6_804_520,
    md5="469a7329d496f81ae8625c4d76ccf56d",
    sha256="8a721fc8ef25458d415b2460e4a251e0503a82f7743fdff85b12612190e5c1cb",
    header_markers=((0x0, b"BFNP"), (0x8, b"FCFG"), (0x64, b"PCFG")),
    model_offsets=(0x4D48, 0x1C2698),
    recovery_tag=RECOVERY_TAG,
    recovery_tag_offsets=(0x1C31C4, 0x67D400),
    recovery_trailer_offset=0x67D400,
    recovery_crc_value=0x7FFD605B,
    immutable_header_end=0x1000,
)

AP01_1_0_2_0041 = BaselineDefinition(
    model="njcuk.enstor.ap01",
    version="1.0.2_0041",
    size=6_769_704,
    md5="3c2d962be82c73860daff903178d9b9e",
    sha256="972db4c136c7ed9e24a83c07c1a7fd62040ca018b08ca285216d26b1fee3c6b9",
    header_markers=((0x0, b"BFNP"), (0x8, b"FCFG"), (0x64, b"PCFG")),
    model_offsets=(0x4F00, 0x257F6C),
    recovery_tag=RECOVERY_TAG,
    recovery_tag_offsets=(0x25A96C, 0x674C00),
    recovery_trailer_offset=0x674C00,
    recovery_crc_value=0x47FB9315,
    immutable_header_end=0x1000,
)


def md5_bytes(data: bytes | bytearray) -> str:
    return hashlib.md5(data).hexdigest()


def sha256_bytes(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def recovery_crc(data: bytes | bytearray) -> int:
    return (zlib.crc32(data, 0xFFFFFFFF) ^ 0xFFFFFFFF) & 0xFFFFFFFF


def _find_all(data: bytes | bytearray, needle: bytes) -> tuple[int, ...]:
    result: list[int] = []
    start = 0
    while True:
        offset = data.find(needle, start)
        if offset < 0:
            return tuple(result)
        result.append(offset)
        start = offset + 1


def _parse_recovery_trailer(
    firmware: bytes | bytearray,
    definition: BaselineDefinition,
) -> RecoveryTrailer:
    offset = definition.recovery_trailer_offset
    if offset + RECOVERY_TRAILER_SIZE != len(firmware):
        raise FirmwareValidationError("文件尾恢复记录位置或固件总长度不匹配")
    if firmware[offset : offset + len(definition.recovery_tag)] != definition.recovery_tag:
        raise FirmwareValidationError("文件尾恢复标记不匹配")

    stored_length = struct.unpack_from(
        ">I", firmware, offset + RECOVERY_LENGTH_OFFSET
    )[0]
    stored_crc = struct.unpack_from("<I", firmware, offset + RECOVERY_CRC_OFFSET)[0]
    calculated_crc = recovery_crc(firmware[:-4])
    if stored_length != len(firmware):
        raise FirmwareValidationError(
            f"文件尾记录长度不匹配：记录 {stored_length}，实际 {len(firmware)}"
        )
    if stored_crc != calculated_crc:
        raise FirmwareValidationError(
            "文件尾恢复校验不匹配："
            f"记录 0x{stored_crc:08x}，重算 0x{calculated_crc:08x}"
        )
    return RecoveryTrailer(
        offset=offset,
        stored_length=stored_length,
        stored_crc=stored_crc,
        calculated_crc=calculated_crc,
    )


def validate_baseline(
    firmware: bytes,
    definition: BaselineDefinition = AP01_1_0_2_0031,
) -> BaselineReport:
    if len(firmware) != definition.size:
        raise FirmwareValidationError(
            f"原厂固件字节数不匹配：预期 {definition.size}，实际 {len(firmware)}"
        )

    actual_md5 = md5_bytes(firmware)
    actual_sha256 = sha256_bytes(firmware)
    if actual_md5 != definition.md5:
        raise FirmwareValidationError(
            f"原厂固件 MD5 不匹配：预期 {definition.md5}，实际 {actual_md5}"
        )
    if actual_sha256 != definition.sha256:
        raise FirmwareValidationError(
            "原厂固件 SHA-256 不匹配："
            f"预期 {definition.sha256}，实际 {actual_sha256}"
        )

    for offset, marker in definition.header_markers:
        if firmware[offset : offset + len(marker)] != marker:
            raise FirmwareValidationError(
                f"文件头固定标记不匹配：位置 0x{offset:x}"
            )

    model_bytes = definition.model.encode("ascii")
    model_offsets = _find_all(firmware, model_bytes)
    if model_offsets != definition.model_offsets:
        raise FirmwareValidationError(
            "设备型号位置不匹配："
            f"预期 {[hex(value) for value in definition.model_offsets]}，"
            f"实际 {[hex(value) for value in model_offsets]}"
        )

    recovery_offsets = _find_all(firmware, definition.recovery_tag)
    if recovery_offsets != definition.recovery_tag_offsets:
        raise FirmwareValidationError(
            "恢复标记位置不匹配："
            f"预期 {[hex(value) for value in definition.recovery_tag_offsets]}，"
            f"实际 {[hex(value) for value in recovery_offsets]}"
        )

    recovery = _parse_recovery_trailer(firmware, definition)
    if recovery.stored_crc != definition.recovery_crc_value:
        raise FirmwareValidationError(
            "原厂文件尾恢复校验基线不匹配："
            f"预期 0x{definition.recovery_crc_value:08x}，"
            f"实际 0x{recovery.stored_crc:08x}"
        )

    return BaselineReport(
        model=definition.model,
        version=definition.version,
        size=len(firmware),
        md5=actual_md5,
        sha256=actual_sha256,
        model_offsets=model_offsets,
        recovery=recovery,
    )


def load_read_only_baseline(
    path: Path,
    definition: BaselineDefinition = AP01_1_0_2_0031,
) -> tuple[bytes, BaselineReport]:
    selected = path.expanduser().resolve(strict=True)
    if not selected.is_file():
        raise FirmwareValidationError(f"原厂固件路径不是普通文件：{selected}")
    writable_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    if selected.stat().st_mode & writable_bits:
        raise FirmwareValidationError(
            f"原厂固件必须先设为只读，当前仍可写：{selected}"
        )
    firmware = selected.read_bytes()
    return firmware, validate_baseline(firmware, definition)


def changed_ranges(
    before: bytes | bytearray,
    after: bytes | bytearray,
) -> tuple[ByteRange, ...]:
    if len(before) != len(after):
        raise FirmwareValidationError("不能比较不同长度的固件")
    result: list[ByteRange] = []
    start: int | None = None
    for offset, (old, new) in enumerate(zip(before, after)):
        if old != new and start is None:
            start = offset
        elif old == new and start is not None:
            result.append(ByteRange(start, offset))
            start = None
    if start is not None:
        result.append(ByteRange(start, len(before)))
    return tuple(result)


def _contains_offset(ranges: Iterable[ByteRange], offset: int) -> bool:
    return any(item.contains(offset) for item in ranges)


def refresh_recovery_crc(
    firmware: bytearray,
    definition: BaselineDefinition = AP01_1_0_2_0031,
) -> int:
    offset = definition.recovery_trailer_offset
    if len(firmware) != definition.size:
        raise FirmwareValidationError("重算恢复校验前，固件总长度已经变化")
    if firmware[offset : offset + len(definition.recovery_tag)] != definition.recovery_tag:
        raise FirmwareValidationError("重算恢复校验前，文件尾恢复标记不匹配")
    stored_length = struct.unpack_from(
        ">I", firmware, offset + RECOVERY_LENGTH_OFFSET
    )[0]
    if stored_length != len(firmware):
        raise FirmwareValidationError("重算恢复校验前，文件尾记录长度不匹配")
    checksum = recovery_crc(firmware[:-4])
    struct.pack_into("<I", firmware, offset + RECOVERY_CRC_OFFSET, checksum)
    _parse_recovery_trailer(firmware, definition)
    return checksum


def validate_candidate(
    baseline: bytes,
    candidate: bytes,
    allowed_ranges: Iterable[ByteRange],
    definition: BaselineDefinition = AP01_1_0_2_0031,
) -> CandidateReport:
    if len(baseline) != definition.size or len(candidate) != definition.size:
        raise FirmwareValidationError("原厂基线或候选成品的总长度不匹配")

    allowed = tuple(allowed_ranges)
    immutable_header = ByteRange(0, definition.immutable_header_end)
    trailer_structure = ByteRange(
        definition.recovery_trailer_offset,
        definition.recovery_trailer_offset + RECOVERY_CRC_OFFSET,
    )
    if baseline[immutable_header.start : immutable_header.end] != candidate[
        immutable_header.start : immutable_header.end
    ]:
        raise FirmwareValidationError("候选成品修改了禁止触碰的文件头区域")
    if baseline[trailer_structure.start : trailer_structure.end] != candidate[
        trailer_structure.start : trailer_structure.end
    ]:
        raise FirmwareValidationError("候选成品修改了文件尾恢复记录结构")

    differences = changed_ranges(baseline, candidate)
    changed_count = 0
    for item in differences:
        changed_count += item.length
        for offset in range(item.start, item.end):
            if not _contains_offset(allowed, offset):
                raise FirmwareValidationError(
                    f"候选成品在允许范围外修改了字节：0x{offset:x}"
                )

    recovery = _parse_recovery_trailer(candidate, definition)
    return CandidateReport(
        size=len(candidate),
        md5=md5_bytes(candidate),
        sha256=sha256_bytes(candidate),
        recovery=recovery,
        changed_ranges=differences,
        changed_bytes=changed_count,
        outside_allowed_ranges_identical=True,
        immutable_header_identical=True,
        recovery_structure_identical=True,
    )
