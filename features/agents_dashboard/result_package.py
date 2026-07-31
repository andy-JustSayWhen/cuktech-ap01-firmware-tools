"""生成、校验并原子发布 AP01 AGENTS 看板四页结果包。"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import struct
import tempfile
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image

from .collector import collect_snapshot
from .renderer import render_all


MAGIC = b"APAG"
VERSION = 2
HEADER_SIZE = 64
PAGE_COUNT = 4
PAGE_MAX_BYTES = 96 * 1024
PACKAGE_MAX_BYTES = 384 * 1024
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
class DeviceCredentials:
    device_id: str
    access_token: str
    secret_key: bytes

    @classmethod
    def generate(cls) -> "DeviceCredentials":
        return cls(
            device_id=secrets.token_hex(4),
            access_token=secrets.token_hex(8),
            secret_key=secrets.token_bytes(32),
        )

    @classmethod
    def from_dict(cls, document: dict[str, object]) -> "DeviceCredentials":
        device_id = document.get("device_id")
        access_token = document.get("access_token")
        secret_hex = document.get("secret_key")
        if (
            document.get("schema_version") != 1
            or not isinstance(device_id, str)
            or len(device_id) != 8
            or not isinstance(access_token, str)
            or len(access_token) != 16
            or not isinstance(secret_hex, str)
            or len(secret_hex) != 64
        ):
            raise ResultPackageError("设备专属配置字段不完整")
        try:
            int(device_id, 16)
            int(access_token, 16)
            secret_key = bytes.fromhex(secret_hex)
        except ValueError as error:
            raise ResultPackageError("设备专属配置必须使用十六进制") from error
        return cls(device_id.lower(), access_token.lower(), secret_key)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "device_id": self.device_id,
            "access_token": self.access_token,
            "secret_key": self.secret_key.hex(),
        }


@dataclass(frozen=True)
class DecodedPackage:
    generation: int
    generated_at: int
    pages: tuple[bytes, ...]


def load_or_create_credentials(path: Path) -> DeviceCredentials:
    selected = path.expanduser().resolve()
    if selected.exists():
        return load_credentials(selected)

    selected.parent.mkdir(parents=True, exist_ok=True)
    credentials = DeviceCredentials.generate()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{selected.name}.", suffix=".tmp", dir=selected.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                credentials.to_dict(),
                stream,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, selected)
        selected.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)
    return credentials


def load_credentials(path: Path) -> DeviceCredentials:
    selected = path.expanduser().resolve()
    if not selected.is_file():
        raise ResultPackageError(
            "设备专属配置不存在；请迁移原配置或先显式初始化"
        )
    try:
        if os.name != "nt" and selected.stat().st_mode & 0o077:
            raise ResultPackageError("设备专属配置权限必须为 600")
        document = json.loads(selected.read_text(encoding="utf-8"))
    except ResultPackageError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ResultPackageError("无法读取设备专属配置") from error
    if not isinstance(document, dict):
        raise ResultPackageError("设备专属配置格式错误")
    return DeviceCredentials.from_dict(document)


def validate_gif(path: Path) -> bytes:
    payload = path.read_bytes()
    if (
        len(payload) > PAGE_MAX_BYTES
        or not payload.startswith(b"GIF89a")
        or not payload.endswith(b"\x3b")
    ):
        raise ResultPackageError("页面必须是带完整结尾且不超过 96 KiB 的 GIF89a")
    try:
        with Image.open(path) as image:
            if image.size != (320, 240) or image.n_frames < 2:
                raise ResultPackageError("页面必须是 320×240 且至少双帧")
            image.seek(image.n_frames - 1)
            image.load()
    except OSError as error:
        raise ResultPackageError("页面无法完整解码") from error
    return payload


def png_to_device_gif(source: Path, output: Path) -> bytes:
    output.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        first = opened.convert("RGB")
    second = first.copy()
    for x in range(316, 320):
        for y in range(236, 240):
            pixel = second.getpixel((x, y))
            second.putpixel(
                (x, y),
                (
                    pixel[0] ^ 0x10,
                    pixel[1] ^ 0x10,
                    pixel[2] ^ 0x10,
                ),
            )
    first.save(
        output,
        format="GIF",
        save_all=True,
        append_images=[second],
        duration=(1000, 1000),
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
    credentials: DeviceCredentials,
) -> bytes:
    _ = credentials
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


def decode_package(payload: bytes, credentials: DeviceCredentials) -> DecodedPackage:
    _ = credentials
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
    credentials: DeviceCredentials,
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
        pages = tuple(
            png_to_device_gif(png_paths[png_name], temporary / gif_name)
            for png_name, gif_name in zip(PNG_NAMES, PAGE_NAMES)
        )
        generated_at = int(time.time())
        package = encode_package(
            pages,
            generation=generation,
            generated_at=generated_at,
            credentials=credentials,
        )
        decode_package(package, credentials)
        temporary_package = temporary / package_path.name
        temporary_package.write_bytes(package)
        with temporary_package.open("rb") as stream:
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
