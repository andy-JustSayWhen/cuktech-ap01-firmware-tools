"""生成固件内置的四张等待首次同步页面。"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


WIDTH = 320
HEIGHT = 240
FRAME_DURATION_MS = 800
ASSET_DIRECTORY = Path(__file__).resolve().parent / "assets"
PAGE_TITLES = (
    ("overview", "AGENTS 看板"),
    ("weekly", "周剩余额度"),
    ("today", "今日消耗"),
    ("last_30_days", "近30天消耗"),
)
EXPECTED_ASSETS = {
    "overview": (
        6_757,
        "282cb48522a920c4cea84c7517d7d948f90a6e1de122b4155f0181c5fd45904d",
    ),
    "weekly": (
        6_762,
        "43d8b196db000746678bfa06ec34c6eee2fbd137893c6ef8f546225088267dad",
    ),
    "today": (
        6_586,
        "312b91c230598a95bc06a1a7957fe74010b2fd5ab94ea7d8e30e802fb7395237",
    ),
    "last_30_days": (
        6_732,
        "5501b430d78c434757887887c808c909e2cbac53031fabd5a78c203c10b1bb2b",
    ),
}


class FallbackAssetError(RuntimeError):
    """内置等待页面没有通过固定格式门禁。"""


@dataclass(frozen=True)
class FallbackAsset:
    key: str
    title: str
    path: Path
    size: int
    sha256: str


def build_fallback_assets(
    output_directory: Path,
) -> tuple[FallbackAsset, ...]:
    """复制、重读并校验四张冻结的设备等待页面。"""

    selected_output = output_directory.expanduser().resolve()
    selected_output.mkdir(parents=True, exist_ok=True)
    result: list[FallbackAsset] = []
    for key, title in PAGE_TITLES:
        source = ASSET_DIRECTORY / f"fallback-{key}.gif"
        if not source.is_file():
            raise FallbackAssetError(f"缺少冻结等待页面：{source.name}")
        source_payload = source.read_bytes()
        expected_size, expected_sha256 = EXPECTED_ASSETS[key]
        if (
            len(source_payload) != expected_size
            or hashlib.sha256(source_payload).hexdigest() != expected_sha256
        ):
            raise FallbackAssetError(f"冻结等待页面指纹不匹配：{source.name}")
        path = selected_output / f"fallback-{key}.gif"
        shutil.copyfile(source, path)
        payload = path.read_bytes()
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if len(payload) != expected_size or actual_sha256 != expected_sha256:
            raise FallbackAssetError(f"等待页面固定指纹不匹配：{path.name}")
        try:
            with Image.open(path) as decoded:
                durations = tuple(
                    int(decoded.seek(index) or decoded.info.get("duration", 0))
                    for index in range(decoded.n_frames)
                )
                identity = (
                    decoded.size,
                    decoded.n_frames,
                    decoded.info.get("loop"),
                    decoded.info.get("version"),
                    durations,
                )
        except Exception as error:
            raise FallbackAssetError(f"等待页面无法重新解码：{path.name}") from error
        expected = (
            (WIDTH, HEIGHT),
            2,
            0,
            b"GIF89a",
            (FRAME_DURATION_MS, FRAME_DURATION_MS),
        )
        if identity != expected:
            raise FallbackAssetError(f"等待页面格式不匹配：{path.name}")
        result.append(
            FallbackAsset(
                key=key,
                title=title,
                path=path,
                size=len(payload),
                sha256=actual_sha256,
            )
        )
    return tuple(result)
