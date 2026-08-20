"""黄金图回归测试：固定合成快照渲染四页，与黄金图逐像素比对。

DESIGN 依据：ap01-1.0.2_0031-opt.bin技术实现.md 第 7.4 节。
更新黄金图：.venv/Scripts/python.exe -m features.agents_dashboard.test_visual_golden --update
更新前必须先修改 DESIGN 并人工确认新画面与视觉参考相符。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from PIL import Image

from .models import (
    ActivityInsights,
    DashboardSnapshot,
    PluginUsage,
    ResetCard,
    TodayUsage,
)
from .renderer import (
    FontBook,
    render_last_30_days,
    render_overview,
    render_today,
    render_weekly,
)

FONT_DIRECTORY = Path(__file__).resolve().parents[2] / "fonts"
GOLDEN_DIRECTORY = Path(__file__).parent / "testdata" / "golden"

WEAK_DELTA = 12
STRONG_DELTA = 60
STRONG_BUDGET_RATIO = 0.001
WEAK_BUDGET_RATIO = 0.005

GENERATED_AT = "2026-08-19T19:04:05+08:00"


def _synthetic_snapshot() -> DashboardSnapshot:
    daily = (
        ("2026-07-21", 8_100_000),
        ("2026-07-22", 9_400_000),
        ("2026-07-23", 7_800_000),
        ("2026-07-24", 11_200_000),
        ("2026-07-25", 12_600_000),
        ("2026-07-26", 14_900_000),
        ("2026-07-27", 13_700_000),
        ("2026-07-28", 16_800_000),
        ("2026-07-29", 15_300_000),
        ("2026-07-30", 18_600_000),
        ("2026-07-31", 17_900_000),
        ("2026-08-01", 20_400_000),
        ("2026-08-02", 19_100_000),
        ("2026-08-03", 22_700_000),
        ("2026-08-04", 21_500_000),
        ("2026-08-05", 24_800_000),
        ("2026-08-06", 23_600_000),
        ("2026-08-07", 26_200_000),
        ("2026-08-08", 25_400_000),
        ("2026-08-09", 27_900_000),
        ("2026-08-10", 26_800_000),
        ("2026-08-11", 29_300_000),
        ("2026-08-12", 28_100_000),
        ("2026-08-13", 30_600_000),
        ("2026-08-14", 29_800_000),
        ("2026-08-15", 31_200_000),
        ("2026-08-16", 30_900_000),
        ("2026-08-17", 33_400_000),
        ("2026-08-18", 32_100_000),
        ("2026-08-19", 34_600_000),
    )
    return DashboardSnapshot(
        generated_at=GENERATED_AT,
        weekly_remaining_percent=23,
        weekly_reset_at="2026-08-20T11:31:17+08:00",
        reset_cards_available=2,
        reset_cards=(
            ResetCard(
                status="granted",
                granted_at="2026-08-12T05:08:56+08:00",
                expires_at="2026-08-26T05:08:56+08:00",
                redeemed_at=None,
            ),
            ResetCard(
                status="granted",
                granted_at="2026-08-15T10:00:00+08:00",
                expires_at="2026-08-29T10:00:00+08:00",
                redeemed_at=None,
            ),
        ),
        today=TodayUsage(
            total_tokens=16_390_000,
            fresh_input_tokens=660_000,
            raw_input_tokens=22_200_000,
            output_tokens=800_000,
            cached_input_tokens=15_640_000,
            cache_write_input_tokens=90_000,
            reasoning_output_tokens=500_000,
            request_count=153,
            cache_hit_percent=96,
            api_cost_usd="14.15",
            api_cost_usd_rounded=14,
            model_usage=(),
        ),
        last_30d_tokens=16_632_150_400,
        daily_30d=daily,
        activity=ActivityInsights(
            fast_mode_percent=34,
            reasoning_label="高",
            reasoning_percent=36,
            explored_skills=96,
            skill_uses=2_063,
            task_count=5_166,
            longest_task_minutes=1_310,
        ),
        common_plugins=(
            PluginUsage(name="product-design", count=339),
            PluginUsage(name="superpowers", count=210),
            PluginUsage(name="computer-use", count=156),
            PluginUsage(name="browser", count=98),
            PluginUsage(name="chrome", count=77),
        ),
        quota_fetched_at=GENERATED_AT,
        reset_cards_fetched_at=GENERATED_AT,
        profile_fetched_at=GENERATED_AT,
        profile_usage_as_of=GENERATED_AT,
        pricing_verified_on="2026-08-01",
        quota_available=True,
        reset_cards_source_available=True,
        profile_available=True,
        local_sessions_available=True,
    )


def _render_pages() -> dict[str, Image.Image]:
    fonts = FontBook(FONT_DIRECTORY)
    snapshot = _synthetic_snapshot()
    return {
        "01-overview": render_overview(snapshot, fonts),
        "02-weekly": render_weekly(snapshot, fonts),
        "03-today": render_today(snapshot, fonts),
        "04-last-30-days": render_last_30_days(snapshot, fonts),
    }


def _update_golden() -> None:
    GOLDEN_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for name, image in _render_pages().items():
        path = GOLDEN_DIRECTORY / f"{name}.png"
        image.save(path, format="PNG", optimize=True)
        print(f"golden updated: {path}")


class VisualGoldenTests(unittest.TestCase):
    @unittest.skipUnless(
        all((FONT_DIRECTORY / name).is_file() for name in (
            "MiSans-Regular.ttf",
            "MiSans-Medium.ttf",
            "MiSans-Semibold.ttf",
            "MiSans-Bold.ttf",
        )),
        "本机未放置完整看板字体",
    )
    @unittest.skipUnless(
        GOLDEN_DIRECTORY.is_dir(),
        "黄金图未生成，先执行 --update 并人工确认画面",
    )
    def test_four_pages_match_golden_images(self) -> None:
        for name, image in _render_pages().items():
            with self.subTest(page=name):
                golden_path = GOLDEN_DIRECTORY / f"{name}.png"
                golden = Image.open(golden_path).convert("RGB")
                fresh = image.convert("RGB")
                self.assertEqual(
                    fresh.size,
                    golden.size,
                    f"{name} 画布尺寸与黄金图不一致",
                )
                total = fresh.size[0] * fresh.size[1]
                strong = 0
                weak = 0
                for fresh_pixel, golden_pixel in zip(
                    fresh.getdata(), golden.getdata()
                ):
                    delta = max(
                        abs(a - b) for a, b in zip(fresh_pixel, golden_pixel)
                    )
                    if delta > STRONG_DELTA:
                        strong += 1
                    elif delta > WEAK_DELTA:
                        weak += 1
                self.assertLessEqual(
                    strong,
                    total * STRONG_BUDGET_RATIO,
                    f"{name} 有 {strong} 个像素偏差超过 {STRONG_DELTA}/255，"
                    "视觉参数被改动或渲染环境变化。先按 DESIGN 7.4 核对原因，"
                    "确认需要改视觉时先更新 DESIGN，再 --update 重新生成黄金图。",
                )
                self.assertLessEqual(
                    weak,
                    total * WEAK_BUDGET_RATIO,
                    f"{name} 有 {weak} 个像素出现轻微偏差，超出抗锯齿容差。",
                )


if __name__ == "__main__":
    if "--update" in sys.argv:
        _update_golden()
    else:
        unittest.main()
