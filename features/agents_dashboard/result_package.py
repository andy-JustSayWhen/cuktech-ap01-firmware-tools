"""生成、校验并原子发布 AP01 AGENTS 看板四页结果包。"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image

from .collector import collect_snapshot
from .renderer import FontBook, render_all, render_weekly_batches


MAGIC = b"APAG"
VERSION = 2
HEADER_SIZE = 64
PAGE_COUNT = 4
PAGE_MAX_BYTES = 96 * 1024
PACKAGE_MAX_BYTES = 384 * 1024
DEVICE_GIF_COLORS = 256
STATIC_FRAME_DURATION_MS = 600_000
PAGE_NAMES = (
    "01-overview.gif",
    "02-weekly.gif",
    "03-today.gif",
    "04-last-30-days.gif",
)
PNG_NAMES = (
    "01-概览-真实数据.png",
    "02-周剩余额度-真实数据.png",
    "03-今日消耗-真实数据.png",
    "04-近30天消耗-真实数据.png",
)


class ResultPackageError(RuntimeError):
    """四页结果包不符合固定协议。"""


@dataclass(frozen=True)
class DecodedPackage:
    generation: int
    generated_at: int
    pages: tuple[bytes, ...]


def _skip_gif_sub_blocks(payload: bytes, cursor: int) -> int:
    while True:
        if cursor >= len(payload):
            raise ResultPackageError("页面数据块被截断")
        size = payload[cursor]
        cursor += 1
        if size == 0:
            return cursor
        cursor += size
        if cursor > len(payload):
            raise ResultPackageError("页面数据块被截断")


def _gif_color_table_sizes(payload: bytes) -> tuple[int, ...]:
    if len(payload) < 14 or not payload.startswith(b"GIF89a"):
        raise ResultPackageError("页面文件头无效")
    sizes: list[int] = []
    screen_flags = payload[10]
    cursor = 13
    if screen_flags & 0x80:
        size = 1 << ((screen_flags & 0x07) + 1)
        sizes.append(size)
        cursor += size * 3

    while cursor < len(payload):
        marker = payload[cursor]
        if marker == 0x3B:
            if cursor != len(payload) - 1:
                raise ResultPackageError("页面结尾后存在多余数据")
            return tuple(sizes)
        if marker == 0x21:
            if cursor + 2 > len(payload):
                raise ResultPackageError("页面扩展块被截断")
            cursor = _skip_gif_sub_blocks(payload, cursor + 2)
            continue
        if marker != 0x2C or cursor + 10 > len(payload):
            raise ResultPackageError("页面图像块无效")
        image_flags = payload[cursor + 9]
        cursor += 10
        if image_flags & 0x80:
            size = 1 << ((image_flags & 0x07) + 1)
            sizes.append(size)
            cursor += size * 3
        if cursor >= len(payload):
            raise ResultPackageError("页面图像数据被截断")
        cursor = _skip_gif_sub_blocks(payload, cursor + 1)
    raise ResultPackageError("页面缺少完整结尾")


def validate_gif(path: Path) -> bytes:
    payload = path.read_bytes()
    if (
        len(payload) > PAGE_MAX_BYTES
        or not payload.startswith(b"GIF89a")
        or not payload.endswith(b"\x3b")
    ):
        raise ResultPackageError("页面必须是带完整结尾且不超过 96 KiB 的 GIF89a")
    table_sizes = _gif_color_table_sizes(payload)
    if not table_sizes or any(size > DEVICE_GIF_COLORS for size in table_sizes):
        raise ResultPackageError("页面每帧色表必须不超过 256 项")
    try:
        with Image.open(path) as image:
            if image.size != (320, 240) or image.n_frames < 2:
                raise ResultPackageError("页面必须是 320×240 且至少双帧")
            image.seek(image.n_frames - 1)
            image.load()
    except OSError as error:
        raise ResultPackageError("页面无法完整解码") from error
    return payload


def _second_device_frame(first: Image.Image) -> Image.Image:
    if first.mode != "P":
        raise ResultPackageError("第二帧必须从已量化首帧生成")
    palette = first.getpalette()
    colors = first.getcolors()
    if palette is None or not colors:
        raise ResultPackageError("已量化首帧缺少调色板")

    source_index = int(first.getpixel((319, 239)))
    source_rgb = tuple(palette[source_index * 3 : source_index * 3 + 3])
    candidates: list[tuple[int, int]] = []
    for _, index in colors:
        candidate_rgb = tuple(palette[index * 3 : index * 3 + 3])
        if index == source_index or candidate_rgb == source_rgb:
            continue
        distance = sum(
            (source_channel - candidate_channel) ** 2
            for source_channel, candidate_channel in zip(source_rgb, candidate_rgb)
        )
        candidates.append((distance, index))
    if candidates:
        target_index = min(candidates)[1]
    else:
        target_index = 1 if source_index != 1 else 0
        target_rgb = tuple(channel ^ 0x10 for channel in source_rgb)
        palette[target_index * 3 : target_index * 3 + 3] = target_rgb
        first.putpalette(palette)
    second = first.copy()
    second.putpixel((319, 239), target_index)
    return second


def _quantize_device_frame(frame: Image.Image) -> Image.Image:
    rgb = frame.convert("RGB")
    colors = rgb.getcolors(maxcolors=DEVICE_GIF_COLORS + 1)
    if colors is None or len(colors) > DEVICE_GIF_COLORS:
        return rgb.quantize(
            colors=DEVICE_GIF_COLORS,
            method=Image.Quantize.MEDIANCUT,
            dither=Image.Dither.NONE,
        )
    ordered = sorted((color for _, color in colors))
    color_to_index = {color: index for index, color in enumerate(ordered)}
    palette: list[int] = []
    for color in ordered:
        palette.extend(color)
    palette.extend([0] * (DEVICE_GIF_COLORS * 3 - len(palette)))
    paletted = Image.new("P", rgb.size)
    paletted.putpalette(palette)
    data = rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata()
    paletted.putdata([color_to_index[color] for color in data])
    return paletted


def png_to_device_gif(source: Path, output: Path) -> bytes:
    output.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        first = opened.convert("RGB")
    first = _quantize_device_frame(first)
    second = _second_device_frame(first)
    first.save(
        output,
        format="GIF",
        save_all=True,
        append_images=[second],
        duration=(STATIC_FRAME_DURATION_MS, STATIC_FRAME_DURATION_MS),
        loop=0,
        optimize=True,
        disposal=2,
    )
    return validate_gif(output)


def weekly_to_device_gif(snapshot, font_directory: Path, output: Path) -> bytes:
    output.parent.mkdir(parents=True, exist_ok=True)
    frames = render_weekly_batches(snapshot, FontBook(font_directory))
    frames = [_quantize_device_frame(frames[0])]
    frames.append(_second_device_frame(frames[0]))
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=tuple(STATIC_FRAME_DURATION_MS for _ in frames),
        loop=0,
        optimize=True,
        disposal=2,
    )
    return validate_gif(output)


def encode_package(
    pages: Iterable[bytes],
    *,
    generation: int,
    generated_at: int,
) -> bytes:
    selected = tuple(pages)
    if len(selected) != PAGE_COUNT:
        raise ResultPackageError("完整结果必须恰好包含四页")
    if not 0 < generation <= 0x7FFFFFFF:
        raise ResultPackageError("结果代号超出允许范围")
    if generated_at <= 0:
        raise ResultPackageError("生成时间无效")
    for page in selected:
        if (
            len(page) > PAGE_MAX_BYTES
            or not page.startswith(b"GIF89a")
            or not page.endswith(b"\x3b")
        ):
            raise ResultPackageError("结果包页面格式或长度无效")

    body = b"".join(selected)
    total_size = HEADER_SIZE + len(body)
    if total_size > PACKAGE_MAX_BYTES:
        raise ResultPackageError("完整结果包超过 384 KiB")
    header = bytearray(HEADER_SIZE)
    struct.pack_into(
        "<4sHHIIQII",
        header,
        0,
        MAGIC,
        VERSION,
        HEADER_SIZE,
        generation,
        total_size,
        generated_at,
        PAGE_COUNT,
        0,
    )
    struct.pack_into("<4I", header, 32, *(len(page) for page in selected))
    struct.pack_into(
        "<4I",
        header,
        48,
        *(zlib.crc32(page) & 0xFFFFFFFF for page in selected),
    )
    return bytes(header) + body


def decode_package(payload: bytes) -> DecodedPackage:
    if len(payload) < HEADER_SIZE or len(payload) > PACKAGE_MAX_BYTES:
        raise ResultPackageError("完整结果包长度无效")
    try:
        (
            magic,
            version,
            header_size,
            generation,
            total_size,
            generated_at,
            page_count,
            reserved,
        ) = struct.unpack_from("<4sHHIIQII", payload, 0)
        lengths = struct.unpack_from("<4I", payload, 32)
        checks = struct.unpack_from("<4I", payload, 48)
    except struct.error as error:
        raise ResultPackageError("完整结果包头被截断") from error
    if (
        magic != MAGIC
        or version != VERSION
        or header_size != HEADER_SIZE
        or page_count != PAGE_COUNT
        or reserved != 0
        or total_size != len(payload)
        or generation == 0
    ):
        raise ResultPackageError("完整结果包头字段无效")
    if sum(lengths) != len(payload) - HEADER_SIZE:
        raise ResultPackageError("四页长度与整包长度不一致")

    pages: list[bytes] = []
    cursor = HEADER_SIZE
    for index, length in enumerate(lengths):
        if length > PAGE_MAX_BYTES:
            raise ResultPackageError("单页超过 96 KiB")
        page = payload[cursor : cursor + length]
        cursor += length
        if (
            not page.startswith(b"GIF89a")
            or not page.endswith(b"\x3b")
            or (zlib.crc32(page) & 0xFFFFFFFF) != checks[index]
        ):
            raise ResultPackageError("页面格式或文件指纹无效")
        pages.append(page)
    return DecodedPackage(generation, generated_at, tuple(pages))


def next_generation(existing_package: Path) -> int:
    now = int(time.time()) & 0x7FFFFFFF
    if not existing_package.is_file():
        return max(1, now)
    try:
        payload = existing_package.read_bytes()[:12]
        magic, version, header_size, previous = struct.unpack("<4sHHI", payload)
    except (OSError, struct.error):
        return max(1, now)
    if magic != MAGIC or version != VERSION or header_size != HEADER_SIZE:
        return max(1, now)
    candidate = max(now, previous + 1)
    return 1 if candidate > 0x7FFFFFFF else candidate


def publish_current_result(
    output_directory: Path,
    font_directory: Path,
    *,
    codex_home: Path | None = None,
    cache_directory: Path | None = None,
) -> dict[str, object]:
    selected = output_directory.expanduser().resolve()
    selected.mkdir(parents=True, exist_ok=True)
    package_path = selected / "agents-dashboard.apag"
    generation = next_generation(package_path)
    with tempfile.TemporaryDirectory(prefix=".agents-dashboard.", dir=selected) as name:
        temporary = Path(name)
        snapshot = collect_snapshot(
            codex_home=codex_home,
            cache_directory=cache_directory,
        )
        png_paths = render_all(snapshot, temporary, font_directory)
        pages_list = [
            png_to_device_gif(png_paths[PNG_NAMES[0]], temporary / PAGE_NAMES[0]),
            weekly_to_device_gif(snapshot, font_directory, temporary / PAGE_NAMES[1]),
            png_to_device_gif(png_paths[PNG_NAMES[2]], temporary / PAGE_NAMES[2]),
            png_to_device_gif(png_paths[PNG_NAMES[3]], temporary / PAGE_NAMES[3]),
        ]
        pages = tuple(pages_list)
        generated_at = int(time.time())
        package = encode_package(
            pages,
            generation=generation,
            generated_at=generated_at,
        )
        decode_package(package)
        temporary_package = temporary / package_path.name
        temporary_package.write_bytes(package)
        with temporary_package.open("rb+") as stream:
            os.fsync(stream.fileno())
        for name in PAGE_NAMES:
            os.replace(temporary / name, selected / name)
        manifest = {
            "schema_version": 1,
            "generation": generation,
            "generated_at": snapshot.generated_at,
            "package_bytes": len(package),
            "package_sha256": hashlib.sha256(package).hexdigest(),
            "data_sources": {
                "quota": snapshot.quota_available,
                "reset_cards": snapshot.reset_cards_source_available,
                "profile": snapshot.profile_available,
                "local_sessions": snapshot.local_sessions_available,
            },
            "pages": [
                {
                    "name": name,
                    "bytes": len(page),
                    "sha256": hashlib.sha256(page).hexdigest(),
                }
                for name, page in zip(PAGE_NAMES, pages)
            ],
        }
        manifest_path = temporary / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(manifest_path, selected / "manifest.json")
        os.replace(temporary_package, package_path)
    return manifest
