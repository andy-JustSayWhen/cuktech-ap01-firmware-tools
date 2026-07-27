from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from .collector import (
    ProfileData,
    QuotaData,
    ResetCardsData,
    _encode_profile,
    _encode_quota,
    _encode_reset_cards,
    _cache_record,
    _parse_profile_response,
    _parse_quota_response,
    _parse_reset_response,
    collect_snapshot,
    scan_today_sessions,
)
from .formatting import format_token_count
from .models import (
    ActivityInsights,
    DashboardSnapshot,
    PluginUsage,
    ResetCard,
    TodayUsage,
)
from .pricing import (
    API_RATE_CARD,
    calculate_request_cost,
    markdown_rate_row,
    round_usd,
)
from .renderer import FONT_ROLE_FILES, FontBook, _countdown, render_all


BEIJING = ZoneInfo("Asia/Shanghai")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FONT_DIRECTORY = PROJECT_ROOT / "env" / "fonts"


class FormattingTests(unittest.TestCase):
    def test_required_token_boundaries(self) -> None:
        expected = {
            9_000: ("9,000", "Token"),
            164_000: ("16", "万 Token"),
            99_995_000: ("1", "亿 Token"),
            500_000_000: ("5", "亿 Token"),
            1_000_000_000: ("10", "亿 Token"),
            2_000_000_000: ("20", "亿 Token"),
            99_999_999_999: ("1,000", "亿 Token"),
        }
        for raw, result in expected.items():
            with self.subTest(raw=raw):
                display = format_token_count(raw)
                self.assertEqual((display.value, display.unit), result)
                self.assertNotIn(".", display.text)


class CollectorTests(unittest.TestCase):
    @staticmethod
    def _write_session(path: Path) -> None:
        records = [
            {
                "timestamp": "2026-07-28T00:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "019fa40e-5160-7d51-8824-5ed0b8d26b33"},
            },
            {
                "timestamp": "2026-07-28T00:01:00.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "thread_settings_applied",
                    "thread_settings": {"model": "gpt-5.6-sol"},
                },
            },
            {
                "timestamp": "2026-07-28T00:02:00.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 8_000,
                            "output_tokens": 1_000,
                            "cached_input_tokens": 4_000,
                            "cache_write_input_tokens": 1_000,
                            "reasoning_output_tokens": 200,
                        }
                    },
                },
            },
            {
                "timestamp": "2026-07-28T00:03:00.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 10_000,
                            "output_tokens": 1_500,
                            "cached_input_tokens": 5_000,
                            "cache_write_input_tokens": 1_500,
                            "reasoning_output_tokens": 300,
                        }
                    },
                },
            },
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
            encoding="utf-8",
        )

    @staticmethod
    def _write_one_request_session(
        path: Path,
        session_id: str,
        model: str,
        input_tokens: int,
        cached_input_tokens: int,
        cache_write_input_tokens: int,
        output_tokens: int,
    ) -> None:
        records = [
            {
                "timestamp": "2026-07-28T00:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": session_id},
            },
            {
                "timestamp": "2026-07-28T00:01:00.000Z",
                "type": "turn_context",
                "payload": {"model": model},
            },
            {
                "timestamp": "2026-07-28T00:02:00.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": input_tokens,
                            "cached_input_tokens": cached_input_tokens,
                            "cache_write_input_tokens": cache_write_input_tokens,
                            "output_tokens": output_tokens,
                        }
                    },
                },
            },
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(
                json.dumps(record, separators=(",", ":")) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )

    def test_cc_switch_3161_session_math_and_duplicate_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            active = home / "sessions" / "2026" / "07" / "28" / (
                "rollout-2026-07-28T08-00-00-"
                "019fa40e-5160-7d51-8824-5ed0b8d26b33.jsonl"
            )
            archived = home / "archived_sessions" / active.name
            self._write_session(active)
            self._write_session(archived)

            data = scan_today_sessions(
                home, datetime(2026, 7, 28, 8, 5, tzinfo=BEIJING)
            )

            self.assertTrue(data.source_available)
            self.assertEqual(data.raw_input_tokens, 10_000)
            self.assertEqual(data.fresh_input_tokens, 5_000)
            self.assertEqual(data.output_tokens, 1_500)
            self.assertEqual(data.cached_input_tokens, 5_000)
            self.assertEqual(data.cache_write_input_tokens, 1_500)
            self.assertEqual(data.reasoning_output_tokens, 300)
            self.assertEqual(data.request_count, 2)
            self.assertEqual(len(data.model_usage), 1)
            self.assertEqual(data.model_usage[0].model, "gpt-5.6-sol")
            self.assertEqual(data.model_usage[0].api_cost_usd, Decimal("0.074375"))

    def test_api_rate_card_and_long_context_math(self) -> None:
        standard = calculate_request_cost(
            "gpt-5.6-sol",
            input_tokens=200_000,
            cached_input_tokens=100_000,
            cache_write_input_tokens=20_000,
            output_tokens=20_000,
        )
        self.assertIsNotNone(standard)
        assert standard is not None
        self.assertFalse(standard.long_context)
        self.assertEqual(standard.exact_usd, Decimal("1.175"))
        self.assertEqual(round_usd(standard.exact_usd), 1)

        long_context = calculate_request_cost(
            "gpt-5.6-sol",
            input_tokens=300_000,
            cached_input_tokens=100_000,
            cache_write_input_tokens=20_000,
            output_tokens=10_000,
        )
        self.assertIsNotNone(long_context)
        assert long_context is not None
        self.assertTrue(long_context.long_context)
        self.assertEqual(long_context.exact_usd, Decimal("2.600"))
        self.assertIsNone(
            calculate_request_cost(
                "gpt-5.3-codex-spark",
                input_tokens=1_000,
                cached_input_tokens=0,
                cache_write_input_tokens=0,
                output_tokens=100,
            )
        )

    def test_multiple_models_are_summed_before_final_rounding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self._write_one_request_session(
                home / "sessions" / "sol.jsonl",
                "sol-session",
                "gpt-5.6-sol",
                0,
                0,
                0,
                16_000,
            )
            self._write_one_request_session(
                home / "sessions" / "terra.jsonl",
                "terra-session",
                "gpt-5.6-terra",
                0,
                0,
                0,
                32_000,
            )

            snapshot = collect_snapshot(
                now=datetime(2026, 7, 28, 8, 5, tzinfo=BEIJING),
                codex_home=home,
                fetch_remote=False,
            )

            self.assertEqual(snapshot.today.api_cost_usd, "0.96")
            self.assertEqual(snapshot.today.api_cost_usd_rounded, 1)
            self.assertEqual(
                tuple(item.api_cost_usd for item in snapshot.today.model_usage),
                ("0.48", "0.48"),
            )

    def test_missing_api_billing_field_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            session = home / "sessions" / "missing-cache-write.jsonl"
            self._write_one_request_session(
                session,
                "missing-cache-write",
                "gpt-5.6-sol",
                10_000,
                5_000,
                0,
                1_000,
            )
            content = session.read_text(encoding="utf-8")
            session.write_text(
                content.replace('"cache_write_input_tokens":0,', ""),
                encoding="utf-8",
            )

            snapshot = collect_snapshot(
                now=datetime(2026, 7, 28, 8, 5, tzinfo=BEIJING),
                codex_home=home,
                fetch_remote=False,
            )

            self.assertEqual(snapshot.today.total_tokens, 11_000)
            self.assertIsNone(snapshot.today.api_cost_usd)
            self.assertIsNone(snapshot.today.api_cost_usd_rounded)

    def test_api_rate_implementation_matches_authoritative_document(self) -> None:
        document = (
            PROJECT_ROOT / "reference" / "Codex-模型API计费表.md"
        ).read_text(encoding="utf-8")
        for entry in API_RATE_CARD:
            with self.subTest(model=entry.model):
                self.assertIn(markdown_rate_row(entry), document)

    def test_official_response_mapping_matches_reference_apps(self) -> None:
        now = datetime(2026, 7, 28, 8, 5, tzinfo=BEIJING)
        fetched_at = now.isoformat(timespec="seconds")
        quota = _parse_quota_response(
            {
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 67,
                        "limit_window_seconds": 604_800,
                        "reset_at": 1_785_611_915,
                    },
                    "secondary_window": None,
                }
            },
            fetched_at,
        )
        resets = _parse_reset_response(
            {
                "available_count": 2,
                "credits": [
                    {
                        "status": "available",
                        "granted_at": "2026-07-12T21:08:56Z",
                        "expires_at": "2026-08-11T21:08:56Z",
                        "redeemed_at": None,
                    }
                ],
            },
            fetched_at,
            now,
        )
        profile = _parse_profile_response(
            {
                "stats": {
                    "daily_usage_buckets": [
                        {"start_date": "2026-07-27", "tokens": 2_000_000}
                    ],
                    "fast_mode_usage_percentage": 37.5,
                    "most_used_reasoning_effort": "high",
                    "most_used_reasoning_effort_percentage": 43.2,
                    "unique_skills_used": 86,
                    "total_skills_used": 1_392,
                    "total_threads": 4_129,
                    "longest_running_turn_sec": 78_607,
                    "top_invocations": [
                        {
                            "type": "plugin",
                            "plugin_name": "browser",
                            "usage_count": 172,
                        }
                    ],
                }
            },
            fetched_at,
        )

        self.assertEqual(quota.remaining_percent, 33)
        self.assertEqual(resets.available_count, 2)
        self.assertEqual(len(resets.cards), 1)
        self.assertEqual(profile.activity.fast_mode_percent, 38)
        self.assertEqual(profile.activity.reasoning_label, "高")
        self.assertEqual(profile.activity.reasoning_percent, 43)
        self.assertEqual(profile.plugins, (PluginUsage("browser", 172),))

    def test_snapshot_uses_independent_sources_and_safe_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            session = home / "sessions" / "2026" / "07" / "28" / (
                "rollout-2026-07-28T08-00-00-"
                "019fa40e-5160-7d51-8824-5ed0b8d26b33.jsonl"
            )
            self._write_session(session)
            fetched_at = "2026-07-28T08:00:00+08:00"
            quota = QuotaData(33, "2026-08-02T03:18:35+08:00", fetched_at)
            resets = ResetCardsData(
                1,
                (
                    ResetCard(
                        "available",
                        "2026-07-13T05:08:56+08:00",
                        "2026-08-12T05:08:56+08:00",
                        None,
                    ),
                ),
                fetched_at,
            )
            profile = ProfileData(
                (("2026-07-27", 2_000_000),),
                ActivityInsights(38, "高", 43, 86, 1_392, 4_129, 1_310),
                (PluginUsage("browser", 172),),
                fetched_at,
            )

            snapshot = collect_snapshot(
                now=datetime(2026, 7, 28, 8, 5, tzinfo=BEIJING),
                codex_home=home,
                quota=quota,
                reset_cards=resets,
                profile=profile,
                fetch_remote=False,
            )

            self.assertEqual(snapshot.today.total_tokens, 11_500)
            self.assertEqual(snapshot.today.fresh_input_tokens, 5_000)
            self.assertEqual(snapshot.today.raw_input_tokens, 10_000)
            self.assertEqual(snapshot.today.cache_hit_percent, 50)
            self.assertEqual(snapshot.today.cache_write_input_tokens, 1_500)
            self.assertEqual(snapshot.today.reasoning_output_tokens, 300)
            self.assertEqual(snapshot.today.api_cost_usd, "0.074375")
            self.assertEqual(snapshot.today.api_cost_usd_rounded, 0)
            self.assertEqual(snapshot.today.model_usage[0].cache_write_input_tokens, 1_500)
            self.assertEqual(snapshot.last_30d_tokens, 2_000_000)
            serialized = json.dumps(snapshot.to_dict(), ensure_ascii=False)
            for forbidden in (
                str(home),
                "access_token",
                "refresh_token",
                "account_id",
                "email",
            ):
                self.assertNotIn(forbidden, serialized)

            normalized_cache = json.dumps(
                {
                    "quota": _encode_quota(quota),
                    "resets": _encode_reset_cards(resets),
                    "profile": _encode_profile(profile),
                },
                ensure_ascii=False,
            )
            self.assertNotIn("access_token", normalized_cache)
            self.assertNotIn("account_id", normalized_cache)

    def test_collector_has_no_reference_app_storage_dependency(self) -> None:
        source = (Path(__file__).parent / "collector.py").read_text(encoding="utf-8")
        for forbidden in (
            ".cc-switch",
            ".antigravity_cockpit",
            "Cockpit Tools.app",
            "CC Switch.app",
            "/Applications/ChatGPT.app",
        ):
            self.assertNotIn(forbidden, source)

    def test_missing_login_uses_last_safe_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "codex"
            cache = root / "cache"
            fetched_at = "2026-07-27T08:00:00+08:00"
            quota = QuotaData(33, "2026-08-02T03:18:35+08:00", fetched_at)
            resets = ResetCardsData(0, (), fetched_at)
            profile = ProfileData(
                (("2026-07-27", 2_000_000),),
                ActivityInsights(38, "高", 43, 86, 1_392, 4_129, 1_310),
                (),
                fetched_at,
            )
            _cache_record(cache / "quota.json", fetched_at, _encode_quota(quota))
            _cache_record(
                cache / "reset-cards.json", fetched_at, _encode_reset_cards(resets)
            )
            _cache_record(cache / "profile.json", fetched_at, _encode_profile(profile))

            snapshot = collect_snapshot(
                now=datetime(2026, 7, 28, 8, 5, tzinfo=BEIJING),
                codex_home=home,
                cache_directory=cache,
            )

            self.assertEqual(snapshot.weekly_remaining_percent, 33)
            self.assertEqual(snapshot.last_30d_tokens, 2_000_000)
            self.assertTrue(snapshot.quota_available)
            self.assertTrue(snapshot.profile_available)


class RendererTests(unittest.TestCase):
    def test_font_roles_use_four_distinct_weights(self) -> None:
        self.assertEqual(
            FONT_ROLE_FILES,
            {
                "hero": "MiSans-Regular.ttf",
                "secondary": "MiSans-Medium.ttf",
                "body": "MiSans-Semibold.ttf",
                "emphasis": "MiSans-Bold.ttf",
            },
        )
        self.assertEqual(len(set(FONT_ROLE_FILES.values())), 4)

    def test_reset_time_is_not_lost_by_platform_locale(self) -> None:
        countdown, reset_time = _countdown(
            "2026-08-02T03:18:35+08:00",
            "2026-07-28T03:57:27+08:00",
        )
        self.assertEqual(countdown, "5天0小时")
        self.assertEqual(reset_time, "08月02日 03:18")

    def test_missing_fonts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                FontBook(Path(directory))

    @unittest.skipUnless(
        all((FONT_DIRECTORY / name).is_file() for name in FONT_ROLE_FILES.values()),
        "本机未放置完整 MiSans 字重",
    )
    def test_font_role_ink_increases_with_hierarchy(self) -> None:
        fonts = FontBook(FONT_DIRECTORY)
        ink = [
            sum(fonts.get(7, role).getmask("活动洞察请求数"))
            for role in ("hero", "secondary", "body", "emphasis")
        ]
        self.assertEqual(ink, sorted(ink))
        self.assertEqual(len(set(ink)), 4)

    @unittest.skipUnless(
        all((FONT_DIRECTORY / name).is_file() for name in FONT_ROLE_FILES.values()),
        "本机未放置完整 MiSans 字重",
    )
    def test_four_pages_are_exact_size_and_rgb(self) -> None:
        snapshot = DashboardSnapshot(
            generated_at="2026-07-28T08:00:00+08:00",
            weekly_remaining_percent=33,
            weekly_reset_at="2026-08-02T03:18:35+08:00",
            reset_cards_available=2,
            reset_cards=(
                ResetCard(
                    "available",
                    "2026-07-13T05:08:56+08:00",
                    "2026-08-12T05:08:56+08:00",
                    None,
                ),
                ResetCard(
                    "available",
                    "2026-07-14T01:27:38+08:00",
                    "2026-08-13T01:27:38+08:00",
                    None,
                ),
            ),
            today=TodayUsage(
                total_tokens=2_000_000_000,
                fresh_input_tokens=1_000_000_000,
                raw_input_tokens=1_900_000_000,
                output_tokens=500_000_000,
                cached_input_tokens=900_000_000,
                cache_write_input_tokens=100_000_000,
                reasoning_output_tokens=250_000_000,
                request_count=1_234,
                cache_hit_percent=47,
                api_cost_usd="1234.49",
                api_cost_usd_rounded=1_234,
            ),
            last_30d_tokens=99_999_999_999,
            daily_30d=tuple(
                (f"2026-07-{index:02d}", index * 1_000) for index in range(1, 31)
            ),
            activity=ActivityInsights(
                fast_mode_percent=38,
                reasoning_label="高",
                reasoning_percent=43,
                explored_skills=86,
                skill_uses=1_392,
                task_count=4_129,
                longest_task_minutes=1_310,
            ),
            common_plugins=(
                PluginUsage("superpowers", 308),
                PluginUsage("browser", 172),
                PluginUsage("computer-use", 127),
                PluginUsage("product-design", 102),
                PluginUsage("github", 73),
            ),
            quota_fetched_at="2026-07-28T08:00:00+08:00",
            reset_cards_fetched_at="2026-07-28T08:00:00+08:00",
            profile_fetched_at="2026-07-28T08:00:00+08:00",
            profile_usage_as_of="2026-07-27",
            pricing_verified_on="2026-07-28",
            quota_available=True,
            reset_cards_source_available=True,
            profile_available=True,
            local_sessions_available=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            paths = render_all(snapshot, Path(directory), FONT_DIRECTORY)
            self.assertEqual(len(paths), 4)
            for path in paths.values():
                with Image.open(path) as image:
                    self.assertEqual(image.size, (320, 240))
                    self.assertEqual(image.mode, "RGB")
