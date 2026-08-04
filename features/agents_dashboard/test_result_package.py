from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from .result_package import (
    HEADER_SIZE,
    ResultPackageError,
    decode_package,
    encode_package,
    png_to_device_gif,
    weekly_to_device_gif,
)
from .models import ActivityInsights, DashboardSnapshot, ResetCard, TodayUsage
from .renderer import _token_or_unavailable, render_all
from .bridge import BridgeState, start_refresh_worker


def _gif(color: tuple[int, int, int]) -> bytes:
    first = Image.new("RGB", (320, 240), color)
    second = first.copy()
    second.putpixel((319, 239), ((color[0] + 1) % 256, color[1], color[2]))
    target = io.BytesIO()
    first.save(
        target,
        format="GIF",
        save_all=True,
        append_images=[second],
        duration=(1000, 1000),
        loop=0,
        optimize=True,
        disposal=2,
    )
    return target.getvalue()


class ResultPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pages = tuple(
            _gif(color)
            for color in ((0, 0, 0), (10, 20, 30), (40, 50, 60), (70, 80, 90))
        )

    def test_four_pages_round_trip(self) -> None:
        package = encode_package(
            self.pages,
            generation=7,
            generated_at=1_700_000_000,
        )
        decoded = decode_package(package)
        self.assertEqual(decoded.generation, 7)
        self.assertEqual(decoded.pages, self.pages)
        self.assertEqual(package[:4], b"APAG")
        self.assertEqual(package[4:8], b"\x02\x00\x40\x00")
        self.assertEqual(len(package), HEADER_SIZE + sum(map(len, self.pages)))

    def test_changed_body_fails_page_check(self) -> None:
        package = bytearray(
            encode_package(
                self.pages,
                generation=8,
                generated_at=1_700_000_001,
            )
        )
        package[-2] ^= 1
        with self.assertRaisesRegex(ResultPackageError, "文件指纹无效"):
            decode_package(bytes(package))

    def test_png_conversion_is_two_frame_device_gif(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            target = root / "target.gif"
            Image.new("RGB", (320, 240), (1, 2, 3)).save(source)
            payload = png_to_device_gif(source, target)
            self.assertTrue(payload.startswith(b"GIF89a"))
            self.assertTrue(payload.endswith(b"\x3b"))
            with Image.open(target) as image:
                self.assertEqual(image.size, (320, 240))
                self.assertGreaterEqual(image.n_frames, 2)
            self.assertEqual(hashlib.sha256(payload).digest_size, 32)

    def test_all_reset_cards_are_split_across_weekly_frames(self) -> None:
        cards = tuple(
            ResetCard("available", "2026-08-01T00:00:00+08:00", f"2026-08-{10 + index:02d}T00:00:00+08:00", None)
            for index in range(5)
        )
        snapshot = DashboardSnapshot(
            generated_at="2026-08-04T00:00:00+08:00",
            weekly_remaining_percent=50,
            weekly_reset_at="2026-08-10T00:00:00+08:00",
            reset_cards_available=5,
            reset_cards=cards,
            today=TodayUsage(0, 0, 0, 0, 0, 0, 0, 0, 0),
            last_30d_tokens=0,
            daily_30d=(),
            activity=ActivityInsights(None, None, None, 0, 0, 0, 0),
            common_plugins=(),
            quota_fetched_at=None,
            reset_cards_fetched_at=None,
            profile_fetched_at=None,
            profile_usage_as_of=None,
            pricing_verified_on="2026-07-28",
            quota_available=True,
            reset_cards_source_available=True,
            profile_available=False,
            local_sessions_available=False,
        )
        fonts = Path(__file__).resolve().parents[2] / "env/fonts"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "weekly.gif"
            weekly_to_device_gif(snapshot, fonts, target)
            with Image.open(target) as image:
                self.assertEqual(image.n_frames, 3)

    def test_all_sixteen_source_availability_combinations_render(self) -> None:
        snapshot = DashboardSnapshot(
            generated_at="2026-08-04T00:00:00+08:00",
            weekly_remaining_percent=50,
            weekly_reset_at="2026-08-10T00:00:00+08:00",
            reset_cards_available=0,
            reset_cards=(),
            today=TodayUsage(100, 50, 100, 20, 50, 0, 10, 1, 50),
            last_30d_tokens=1000,
            daily_30d=(("2026-08-04", 1000),),
            activity=ActivityInsights(10, "高", 20, 1, 2, 3, 4),
            common_plugins=(),
            quota_fetched_at=None,
            reset_cards_fetched_at=None,
            profile_fetched_at=None,
            profile_usage_as_of=None,
            pricing_verified_on="2026-07-28",
            quota_available=True,
            reset_cards_source_available=True,
            profile_available=True,
            local_sessions_available=True,
        )
        fonts = Path(__file__).resolve().parents[2] / "env/fonts"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for mask in range(16):
                selected = replace(
                    snapshot,
                    quota_available=bool(mask & 1),
                    reset_cards_source_available=bool(mask & 2),
                    profile_available=bool(mask & 4),
                    local_sessions_available=bool(mask & 8),
                )
                paths = render_all(selected, root / str(mask), fonts)
                self.assertEqual(len(paths), 4)
        self.assertEqual(_token_or_unavailable(100, False).value, "无法获取")
        self.assertEqual(_token_or_unavailable(100, True).value, "100")

    def test_bridge_refresh_uses_selected_data_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex_home = root / "codex"
            cache = root / "cache"
            state = BridgeState(
                root / "output",
                root / "fonts",
                codex_home=codex_home,
                cache_directory=cache,
            )
            sources = {
                "quota": True,
                "reset_cards": False,
                "profile": True,
                "local_sessions": True,
            }
            with patch(
                "features.agents_dashboard.bridge.publish_current_result",
                return_value={"data_sources": sources},
            ) as publish:
                state.refresh()
            publish.assert_called_once_with(
                root / "output",
                root / "fonts",
                codex_home=codex_home,
                cache_directory=cache,
            )
            self.assertEqual(state.data_sources, sources)

    def test_health_serves_valid_old_result_while_refresh_is_degraded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            package = encode_package(
                self.pages,
                generation=10,
                generated_at=1_700_000_003,
            )
            (output / "agents-dashboard.apag").write_bytes(package)
            state = BridgeState(output, output)
            state.error = "refresh failed"
            health = json.loads(state.health())
            self.assertTrue(health["ok"])
            self.assertTrue(health["degraded"])
            self.assertEqual(health["error"], "refresh failed")

    def test_saved_result_survives_new_bridge_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            package = encode_package(self.pages, generation=11, generated_at=1_700_000_004)
            (output / "agents-dashboard.apag").write_bytes(package)
            restarted = BridgeState(output, output)
            self.assertTrue(restarted.has_valid_result())
            self.assertEqual(restarted.package_for_request("127.0.0.1")[0], package)

    def test_refresh_thread_failure_keeps_old_result_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            package = encode_package(self.pages, generation=12, generated_at=1_700_000_005)
            (output / "agents-dashboard.apag").write_bytes(package)
            state = BridgeState(output, output)
            with patch("features.agents_dashboard.bridge.threading.Thread", side_effect=RuntimeError("no thread")):
                self.assertIsNone(start_refresh_worker(state, 300))
            self.assertTrue(state.has_valid_result())


if __name__ == "__main__":
    unittest.main()
