"""生成固件内置的四张等待首次同步页面。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 320
HEIGHT = 240
FRAME_DURATION_MS = 800
PAGE_TITLES = (
    ("overview", "AGENTS 看板"),
    ("weekly", "周剩余额度"),
    ("today", "今日消耗"),
    ("last_30_days", "近30天消耗"),
)
REQUIRED_FONTS = (
    "MiSans-Regular.ttf",
    "MiSans-Medium.ttf",
    "MiSans-Semibold.ttf",
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


def _font(directory: Path, name: str, size: int) -> ImageFont.FreeTypeFont:
    path = directory / name
    if not path.is_file():
        raise FallbackAssetError(f"缺少等待页面字体：{path}")
    return ImageFont.truetype(str(path), size)


def _centered(
    draw: ImageDraw.ImageDraw,
    y: int,
    value: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
) -> None:
    bounds = draw.textbbox((0, 0), value, font=font)
    width = bounds[2] - bounds[0]
    draw.text(((WIDTH - width) // 2, y), value, font=font, fill=fill)


def _frame(
    title: str,
    *,
    title_font: ImageFont.FreeTypeFont,
    main_font: ImageFont.FreeTypeFont,
    note_font: ImageFont.FreeTypeFont,
    active: bool,
) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#000000")
    draw = ImageDraw.Draw(image)
    draw.text((10, 8), title, font=title_font, fill="#B9BBBA")
    draw.line((10, 35, 310, 35), fill="#252625", width=1)
    _centered(draw, 82, "等待首次同步", main_font, "#F5F5F2")
    _centered(draw, 127, "连接服务后自动更新", note_font, "#777A78")
    dot = "#FFD400" if active else "#493F08"
    draw.ellipse((301, 13, 307, 19), fill=dot)
    draw.line((104, 170, 216, 170), fill="#3B3C3B", width=1)
    return image


def _write_gif(
    path: Path,
    frames: tuple[Image.Image, Image.Image],
) -> None:
    palette_sheet = Image.new("RGB", (WIDTH, HEIGHT * 2), "#000000")
    palette_sheet.paste(frames[0], (0, 0))
    palette_sheet.paste(frames[1], (0, HEIGHT))
    shared_palette = palette_sheet.quantize(
        colors=32,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    encoded = tuple(
        frame.quantize(palette=shared_palette, dither=Image.Dither.NONE)
        for frame in frames
    )
    encoded[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=[encoded[1]],
        loop=0,
        duration=(FRAME_DURATION_MS, FRAME_DURATION_MS),
        disposal=2,
        optimize=False,
    )


def build_fallback_assets(
    font_directory: Path,
    output_directory: Path,
) -> tuple[FallbackAsset, ...]:
    """生成、重读并校验四张确定性的设备等待页面。"""

    selected_fonts = font_directory.expanduser().resolve()
    missing = [name for name in REQUIRED_FONTS if not (selected_fonts / name).is_file()]
    if missing:
        raise FallbackAssetError(f"缺少等待页面字体：{', '.join(missing)}")
    title_font = _font(selected_fonts, "MiSans-Semibold.ttf", 11)
    main_font = _font(selected_fonts, "MiSans-Medium.ttf", 27)
    note_font = _font(selected_fonts, "MiSans-Regular.ttf", 12)

    selected_output = output_directory.expanduser().resolve()
    selected_output.mkdir(parents=True, exist_ok=True)
    result: list[FallbackAsset] = []
    for key, title in PAGE_TITLES:
        path = selected_output / f"fallback-{key}.gif"
        frames = (
            _frame(
                title,
                title_font=title_font,
                main_font=main_font,
                note_font=note_font,
                active=False,
            ),
            _frame(
                title,
                title_font=title_font,
                main_font=main_font,
                note_font=note_font,
                active=True,
            ),
        )
        _write_gif(path, frames)
        payload = path.read_bytes()
        expected_size, expected_sha256 = EXPECTED_ASSETS[key]
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
