from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .collector import collect_snapshot
from .renderer import render_all


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "reference" / "image" / "DESIGN" / "AP01-AGENTS看板" / "真实数据"
)
DEFAULT_FONTS = PROJECT_ROOT / "env" / "fonts"
EFFECT_DIRECTORY = DEFAULT_OUTPUT.parent
COMPARISON_NAME = "效果图-真实图-四页对照.png"
COMPARISON_SPECS = (
    ("01-概览-v5.png", "01-概览-真实数据.png"),
    ("02-周剩余额度-v3.png", "02-周剩余额度-真实数据.png"),
    ("03-今日消耗-v4.png", "03-今日消耗-真实数据.png"),
    ("04-近30天消耗-v5.png", "04-近30天消耗-真实数据.png"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(128 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _render_comparison(
    output: Path,
    written: dict[str, Path],
    font_directory: Path,
) -> Path:
    width = 660
    label_height = 17
    row_height = label_height + 240
    image = Image.new("RGB", (width, row_height * len(COMPARISON_SPECS)), "black")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_directory / "MiSans-Regular.ttf"), 13)
    for index, (effect_name, actual_name) in enumerate(COMPARISON_SPECS, start=1):
        row_y = (index - 1) * row_height
        effect_path = EFFECT_DIRECTORY / effect_name
        actual_path = written[actual_name]
        with Image.open(effect_path) as effect:
            image.paste(effect.convert("RGB"), (0, row_y + label_height))
        with Image.open(actual_path) as actual:
            image.paste(actual.convert("RGB"), (335, row_y + label_height))
        draw.text((5, row_y), f"页面 {index} · 效果图", font=font, fill=(190, 190, 190))
        draw.text(
            (340, row_y),
            f"页面 {index} · 本机真实数据",
            font=font,
            fill=(190, 190, 190),
        )
    path = output / COMPARISON_NAME
    image.save(path, format="PNG", optimize=True)
    return path


def generate(output: Path = DEFAULT_OUTPUT, font_directory: Path = DEFAULT_FONTS) -> dict:
    snapshot = collect_snapshot()
    written = render_all(snapshot, output, font_directory)
    written[COMPARISON_NAME] = _render_comparison(
        output, written, font_directory
    )
    snapshot_path = output / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    files = [
        {
            "name": name,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for name, path in written.items()
    ]
    readme = [
        "# AGENTS 看板本机真实数据对照",
        "",
        f"- 生成时间：`{snapshot.generated_at}`",
        "- 画布：`320×240`",
        "- 字体：主数字使用 Michroma，其余文字使用 MiSans",
        (
            "- 字段口径：见 "
            "[`SPEC-DASHBOARD-021` 至 `SPEC-DASHBOARD-028`]"
            "(../../../../SPEC.md#spec-dashboard-fields)"
        ),
        (
            "- 原始字段、取数方法与安全边界：见 "
            "[`DESIGN` 第 7.4 节]"
            "(../../../../DESIGN/AP01-1.0.2_0031-opt.bin.md#74-本机真实数据采集)"
        ),
        (
            "- 模型单价与费用公式：见 "
            "[`Codex 模型 API 计费表`](../../../../Codex-模型API计费表.md)"
        ),
        f"- 计费表核验日期：`{snapshot.pricing_verified_on}`",
        "- 用途：与已确认效果图比较；不是固件资源，也不是 PNG 真机验证结果",
        "",
        "## 文件",
        "",
        "| 文件 | 字节数 | SHA-256 |",
        "| --- | ---: | --- |",
    ]
    readme.extend(
        f"| `{item['name']}` | {item['bytes']:,} | `{item['sha256']}` |"
        for item in files
    )
    readme.extend(
        [
            "",
            "数据快照见 [`snapshot.json`](snapshot.json)。",
            "",
        ]
    )
    (output / "README.md").write_text("\n".join(readme), encoding="utf-8")
    return snapshot.to_dict()


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 AP01 AGENTS 看板本机真实数据对照图")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--font-directory", type=Path, default=DEFAULT_FONTS)
    arguments = parser.parse_args()
    snapshot = generate(arguments.output, arguments.font_directory)
    print(
        json.dumps(
            {
                "generated_at": snapshot["generated_at"],
                "weekly_remaining_percent": snapshot["weekly_remaining_percent"],
                "today_total_tokens": snapshot["today"]["total_tokens"],
                "today_api_cost_usd": snapshot["today"]["api_cost_usd"],
                "last_30d_tokens": snapshot["last_30d_tokens"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
