"""生成一级页面开关页的内置图形资源。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 320
HEIGHT = 240
ROWS = ("时钟", "功率", "天气", "日历", "萌宠", "AGENTS 看板", "返回")
ROW_TOP = 42
ROW_STEP = 27
REQUIRED_FONTS = ("MiSans-Regular.ttf", "MiSans-Medium.ttf")


class PageSettingsAssetError(RuntimeError):
    """页面开关资源没有通过格式检查。"""


@dataclass(frozen=True)
class PageSettingsAsset:
    key: str
    path: Path
    size: int
    sha256: str


def _font(directory: Path, name: str, size: int) -> ImageFont.FreeTypeFont:
    path = directory / name
    if not path.is_file():
        raise PageSettingsAssetError(f"缺少页面开关字体：{path}")
    return ImageFont.truetype(str(path), size)


def _two_frame_gif(path: Path, image: Image.Image, colors: int) -> None:
    second = image.copy()
    second.putpixel((image.width - 1, image.height - 1), (16, 16, 16))
    sheet = Image.new("RGB", (image.width, image.height * 2), "#000000")
    sheet.paste(image, (0, 0))
    sheet.paste(second, (0, image.height))
    shared = sheet.quantize(
        colors=colors,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    frames = (
        image.quantize(palette=shared, dither=Image.Dither.NONE),
        second.quantize(palette=shared, dither=Image.Dither.NONE),
    )
    frames[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=[frames[1]],
        loop=0,
        duration=(1000, 1000),
        disposal=2,
        optimize=False,
    )


def _background(font_directory: Path) -> Image.Image:
    title_font = _font(font_directory, "MiSans-Medium.ttf", 13)
    row_font = _font(font_directory, "MiSans-Regular.ttf", 15)
    image = Image.new("RGB", (WIDTH, HEIGHT), "#000000")
    draw = ImageDraw.Draw(image)
    draw.text((12, 9), "开关一级页面", font=title_font, fill="#F2F3F2")
    draw.line((12, 34, 308, 34), fill="#292B2A", width=1)
    for index, label in enumerate(ROWS):
        y = ROW_TOP + index * ROW_STEP
        color = "#D9DBDA" if index < 6 else "#8B8E8C"
        draw.text((24, y), label, font=row_font, fill=color)
        if index < 6:
            draw.rounded_rectangle(
                (284, y + 2, 297, y + 15),
                radius=2,
                outline="#555957",
                width=1,
            )
        if index != len(ROWS) - 1:
            draw.line((24, y + 23, 298, y + 23), fill="#171918", width=1)
    return image


def _marker() -> Image.Image:
    image = Image.new("RGB", (7, 20), "#000000")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((1, 1, 5, 18), radius=2, fill="#00DDF5")
    return image


def _check() -> Image.Image:
    image = Image.new("RGB", (12, 12), "#000000")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 11, 11), radius=2, fill="#5DF300")
    draw.line((2, 6, 5, 9, 10, 2), fill="#081006", width=2)
    return image


def build_page_settings_assets(
    font_directory: Path,
    output_directory: Path,
) -> tuple[PageSettingsAsset, ...]:
    """生成、重读并检查底图、选中标记和勾选标记。"""

    fonts = font_directory.expanduser().resolve()
    missing = [name for name in REQUIRED_FONTS if not (fonts / name).is_file()]
    if missing:
        raise PageSettingsAssetError(f"缺少页面开关字体：{', '.join(missing)}")
    output = output_directory.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    definitions = (
        ("background", _background(fonts), 16),
        ("marker", _marker(), 4),
        ("check", _check(), 4),
    )
    result: list[PageSettingsAsset] = []
    for key, image, colors in definitions:
        path = output / f"page-settings-{key}.gif"
        _two_frame_gif(path, image, colors)
        payload = path.read_bytes()
        try:
            with Image.open(path) as decoded:
                identity = (
                    decoded.info.get("version"),
                    decoded.n_frames,
                    decoded.info.get("loop"),
                    decoded.size,
                )
        except Exception as error:
            raise PageSettingsAssetError(f"页面开关资源无法解码：{path.name}") from error
        if identity != (b"GIF89a", 2, 0, image.size):
            raise PageSettingsAssetError(f"页面开关资源格式不匹配：{path.name}")
        result.append(
            PageSettingsAsset(
                key=key,
                path=path,
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        )
    return tuple(result)
