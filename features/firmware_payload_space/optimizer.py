"""无损优化固定原厂动图并验证载荷空间。"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageSequence


GIF_DATA_OFFSET = 0x57E830
GIF_DESCRIPTOR_OFFSET = GIF_DATA_OFFSET - 28
GIF_SIZE_OFFSET = GIF_DATA_OFFSET - 16
GIF_POINTER_OFFSET = GIF_DATA_OFFSET - 12
NEXT_DESCRIPTOR_OFFSET = 0x5F9174
ORIGINAL_SIZE = 502_081
ORIGINAL_SHA256 = "053b16cc10cff7a52544ab0c495f561b10727f718d0ce6a3efa2f034cda3a9e2"
OPTIMIZED_SIZE = 491_894
OPTIMIZED_SHA256 = "6f09647a3d97baeb10b78f9f08d30cd03e77b437dfe14a17a42489952e2e8b99"
EXPECTED_GIFSICLE_VERSION = "LCDF Gifsicle 1.96"
EXPECTED_POINTER = 0xA057D830
PAYLOAD_START = 0x5F69B0
PAYLOAD_END = NEXT_DESCRIPTOR_OFFSET
PAYLOAD_CAPACITY = PAYLOAD_END - PAYLOAD_START


class FirmwarePayloadSpaceError(RuntimeError):
    """原厂动图或释放出的载荷空间不满足固定门禁。"""


@dataclass(frozen=True)
class GifSnapshot:
    size: tuple[int, int]
    frame_count: int
    loop: int | None
    durations: tuple[int, ...]
    disposals: tuple[int | None, ...]
    rgba_frames: tuple[bytes, ...]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _snapshot(payload: bytes) -> GifSnapshot:
    try:
        image = Image.open(io.BytesIO(payload))
    except Exception as error:
        raise FirmwarePayloadSpaceError("动图无法解码") from error
    durations: list[int] = []
    disposals: list[int | None] = []
    frames: list[bytes] = []
    try:
        for frame in ImageSequence.Iterator(image):
            durations.append(
                int(frame.info.get("duration", image.info.get("duration", 0)))
            )
            disposals.append(getattr(frame, "disposal_method", None))
            frames.append(frame.convert("RGBA").tobytes())
        return GifSnapshot(
            size=image.size,
            frame_count=len(frames),
            loop=image.info.get("loop"),
            durations=tuple(durations),
            disposals=tuple(disposals),
            rgba_frames=tuple(frames),
        )
    finally:
        image.close()


def _read_stage(path: Path) -> tuple[Path, bytes]:
    selected = path.expanduser().resolve(strict=True)
    if not selected.is_file():
        raise FirmwarePayloadSpaceError(f"阶段固件不是普通文件：{selected}")
    writable_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    if selected.stat().st_mode & writable_bits:
        raise FirmwarePayloadSpaceError(f"阶段固件必须先设为只读：{selected}")
    return selected, selected.read_bytes()


def _gifsicle() -> Path:
    discovered = shutil.which("gifsicle")
    if not discovered:
        raise FirmwarePayloadSpaceError("缺少 Gifsicle 1.96")
    selected = Path(discovered).resolve()
    try:
        result = subprocess.run(
            [str(selected), "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise FirmwarePayloadSpaceError("无法读取 Gifsicle 版本") from error
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    if first_line != EXPECTED_GIFSICLE_VERSION:
        raise FirmwarePayloadSpaceError(
            f"Gifsicle 版本不匹配：预期 {EXPECTED_GIFSICLE_VERSION}，实际 {first_line}"
        )
    return selected


def _optimize(source: bytes) -> bytes:
    tool = _gifsicle()
    with tempfile.TemporaryDirectory(prefix="ap01-payload-space-") as selected:
        directory = Path(selected)
        source_path = directory / "source.gif"
        output_path = directory / "optimized.gif"
        source_path.write_bytes(source)
        try:
            subprocess.run(
                [str(tool), "-O3", str(source_path), "-o", str(output_path)],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise FirmwarePayloadSpaceError("原厂动图无损优化失败") from error
        return output_path.read_bytes()


def _write_frozen(path: Path, payload: bytes) -> None:
    selected = path.expanduser().resolve()
    selected.parent.mkdir(parents=True, exist_ok=True)
    if selected.exists():
        raise FirmwarePayloadSpaceError(f"不可覆盖已经存在的冻结文件：{selected}")
    temporary = selected.with_name(selected.name + ".part")
    if temporary.exists():
        raise FirmwarePayloadSpaceError(f"发现未处理的临时文件：{temporary}")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, selected)
        selected.chmod(0o444)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_report(path: Path, document: dict[str, object]) -> None:
    payload = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _write_frozen(path, payload)


def inspect_payload_space(
    stage_path: Path,
    optimized_gif_path: Path,
    report_path: Path,
    *,
    tool_revision: dict[str, object],
) -> dict[str, object]:
    """生成固定优化动图，并证明连续候选空间边界。"""

    stage_selected, firmware = _read_stage(stage_path)
    if len(firmware) < NEXT_DESCRIPTOR_OFFSET:
        raise FirmwarePayloadSpaceError("阶段固件长度不足以包含固定资源")
    stored_size = struct.unpack_from("<I", firmware, GIF_SIZE_OFFSET)[0]
    stored_pointer = struct.unpack_from("<I", firmware, GIF_POINTER_OFFSET)[0]
    if stored_size != ORIGINAL_SIZE:
        raise FirmwarePayloadSpaceError("原厂动图描述中的数据长度不匹配")
    if stored_pointer != EXPECTED_POINTER:
        raise FirmwarePayloadSpaceError("原厂动图描述中的数据指针不匹配")

    original = firmware[GIF_DATA_OFFSET : GIF_DATA_OFFSET + ORIGINAL_SIZE]
    if _sha256(original) != ORIGINAL_SHA256:
        raise FirmwarePayloadSpaceError("原厂动图完整指纹不匹配")
    optimized = _optimize(original)
    if len(optimized) != OPTIMIZED_SIZE:
        raise FirmwarePayloadSpaceError("优化后动图长度不匹配")
    if _sha256(optimized) != OPTIMIZED_SHA256:
        raise FirmwarePayloadSpaceError("优化后动图完整指纹不匹配")

    original_snapshot = _snapshot(original)
    optimized_snapshot = _snapshot(optimized)
    if original_snapshot != optimized_snapshot:
        raise FirmwarePayloadSpaceError("优化前后动图的画面或时序不一致")
    if original_snapshot.size != (320, 240) or original_snapshot.frame_count != 20:
        raise FirmwarePayloadSpaceError("固定动图尺寸或帧数不匹配")
    optimized_end = GIF_DATA_OFFSET + len(optimized)
    aligned_start = (optimized_end + 15) & ~15
    if aligned_start != PAYLOAD_START:
        raise FirmwarePayloadSpaceError("载荷对齐起点不匹配")
    if PAYLOAD_CAPACITY != 10_180:
        raise FirmwarePayloadSpaceError("载荷候选容量不匹配")

    document: dict[str, object] = {
        "schema_version": 1,
        "report_type": "firmware-payload-space-inspection",
        "checked_at_beijing": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
            timespec="seconds"
        ),
        "tool": {
            **tool_revision,
            "gifsicle": EXPECTED_GIFSICLE_VERSION,
        },
        "stage_input": {
            "path": str(stage_selected),
            "read_only": True,
        },
        "resource": {
            "descriptor_offset": f"0x{GIF_DESCRIPTOR_OFFSET:06x}",
            "data_offset": f"0x{GIF_DATA_OFFSET:06x}",
            "data_pointer": f"0x{stored_pointer:08x}",
            "original_size": ORIGINAL_SIZE,
            "original_sha256": ORIGINAL_SHA256,
            "optimized_size": OPTIMIZED_SIZE,
            "optimized_sha256": OPTIMIZED_SHA256,
            "width": original_snapshot.size[0],
            "height": original_snapshot.size[1],
            "frame_count": original_snapshot.frame_count,
            "loop": original_snapshot.loop,
            "pixel_and_timing_equivalent": True,
        },
        "payload_space": {
            "start": f"0x{PAYLOAD_START:06x}",
            "end_exclusive": f"0x{PAYLOAD_END:06x}",
            "capacity": PAYLOAD_CAPACITY,
            "aligned": True,
        },
        "gates": {
            "resource_identity_matches": True,
            "optimizer_output_deterministic": True,
            "pixel_and_timing_equivalent": True,
            "payload_candidate_space_ready": True,
            "linked_payload_fits": False,
            "patch_plan_allowed": False,
            "reason": "设备端载荷尚未完成链接、符号、重定位和调用检查",
        },
    }
    _write_frozen(optimized_gif_path, optimized)
    try:
        _write_report(report_path, document)
    except Exception:
        optimized_gif_path.resolve().chmod(0o644)
        optimized_gif_path.resolve().unlink()
        raise
    return document
