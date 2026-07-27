from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TodayUsage:
    total_tokens: int
    fresh_input_tokens: int
    raw_input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    request_count: int
    cache_hit_percent: int
    total_cost: int | None = None


@dataclass(frozen=True)
class ActivityInsights:
    fast_mode_percent: int | None
    reasoning_label: str | None
    reasoning_percent: int | None
    explored_skills: int
    skill_uses: int
    task_count: int
    longest_task_minutes: int


@dataclass(frozen=True)
class PluginUsage:
    name: str
    count: int


@dataclass(frozen=True)
class ResetCard:
    status: str
    granted_at: str | None
    expires_at: str | None
    redeemed_at: str | None


@dataclass(frozen=True)
class DashboardSnapshot:
    generated_at: str
    weekly_remaining_percent: int | None
    weekly_reset_at: str | None
    reset_cards_available: int | None
    reset_cards: tuple[ResetCard, ...]
    today: TodayUsage
    last_30d_tokens: int
    daily_30d: tuple[tuple[str, int], ...]
    activity: ActivityInsights
    common_plugins: tuple[PluginUsage, ...]
    quota_fetched_at: str | None
    reset_cards_fetched_at: str | None
    profile_fetched_at: str | None
    profile_usage_as_of: str | None
    quota_available: bool
    reset_cards_source_available: bool
    profile_available: bool
    local_sessions_available: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
