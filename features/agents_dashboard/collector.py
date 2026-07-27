from __future__ import annotations

import json
import os
import ssl
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, TypeVar
from zoneinfo import ZoneInfo

from .formatting import round_half_up
from .models import (
    ActivityInsights,
    DashboardSnapshot,
    PluginUsage,
    ResetCard,
    TodayUsage,
)


BEIJING = ZoneInfo("Asia/Shanghai")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIRECTORY = PROJECT_ROOT / "env" / "agents-dashboard-cache"
USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
RESET_CREDITS_URL = "https://chatgpt.com/backend-api/wham/rate-limit-reset-credits"
PROFILE_URL = "https://chatgpt.com/backend-api/wham/profiles/me"
WEEK_SECONDS = 7 * 24 * 60 * 60
QUOTA_CACHE_SECONDS = 5 * 60
PROFILE_CACHE_SECONDS = 6 * 60 * 60
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class CodexAuth:
    access_token: str
    account_id: str


@dataclass(frozen=True)
class QuotaData:
    remaining_percent: int
    reset_at: str | None
    fetched_at: str


@dataclass(frozen=True)
class ResetCardsData:
    available_count: int | None
    cards: tuple[ResetCard, ...]
    fetched_at: str


@dataclass(frozen=True)
class ProfileData:
    daily_usage: tuple[tuple[str, int], ...]
    activity: ActivityInsights
    plugins: tuple[PluginUsage, ...]
    fetched_at: str


@dataclass(frozen=True)
class TodaySessionData:
    raw_input_tokens: int
    fresh_input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    request_count: int
    latest_event_at: str | None
    source_available: bool


@dataclass(frozen=True)
class TokenCounters:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


T = TypeVar("T")


def _iso_beijing(value: datetime) -> str:
    return value.astimezone(BEIJING).isoformat(timespec="seconds")


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    return None


def _rounded_percent(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        result = int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None
    return min(100, max(0, result))


def _load_auth(codex_home: Path) -> CodexAuth:
    auth_path = codex_home / "auth.json"
    try:
        payload = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Codex login data is unavailable") from exc
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        raise RuntimeError("Codex login data has an unexpected shape")
    access_token = tokens.get("access_token")
    account_id = tokens.get("account_id")
    if not isinstance(access_token, str) or not access_token.strip():
        raise RuntimeError("Codex access credential is unavailable")
    if not isinstance(account_id, str) or not account_id.strip():
        raise RuntimeError("Codex account identifier is unavailable")
    return CodexAuth(access_token=access_token.strip(), account_id=account_id.strip())


def _request_json(url: str, auth: CodexAuth, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {auth.access_token}",
            "ChatGPT-Account-Id": auth.account_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "OpenAI-Beta": "codex-1",
            "oai-language": "zh-CN",
            "originator": "Codex Desktop",
            "Referer": "https://chatgpt.com/",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/147.0.0.0 Safari/537.36"
            ),
        },
        method="GET",
    )
    context = ssl.create_default_context()
    default_paths = ssl.get_default_verify_paths()
    certificate_candidates = (
        default_paths.cafile,
        default_paths.openssl_cafile,
        "/etc/ssl/cert.pem",
        "/opt/homebrew/etc/openssl@3/cert.pem",
    )
    for candidate in certificate_candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        try:
            context.load_verify_locations(cafile=candidate)
        except ssl.SSLError:
            continue
        break
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Codex service returned status {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Codex service could not be reached") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise RuntimeError("Codex service response is too large")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Codex service returned invalid data") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Codex service response has an unexpected shape")
    return payload


def _request_with_optional_auth(
    url: str, auth: CodexAuth | None, timeout: float
) -> dict[str, Any]:
    if auth is None:
        raise RuntimeError("Codex login data is unavailable")
    return _request_json(url, auth, timeout)


def _cache_record(path: Path, fetched_at: str, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"fetched_at": fetched_at, "payload": payload}
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _read_cache(path: Path) -> tuple[datetime, dict[str, Any]] | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
        return None
    fetched_at = _parse_datetime(record.get("fetched_at"))
    if fetched_at is None:
        return None
    return fetched_at, record["payload"]


def _cached_fetch(
    path: Path,
    ttl_seconds: int,
    now: datetime,
    fetcher: Callable[[], T],
    decoder: Callable[[dict[str, Any], str], T],
    encoder: Callable[[T], dict[str, Any]],
) -> T | None:
    cached = _read_cache(path)
    if cached is not None:
        cached_at, payload = cached
        age = max(0, int((now.astimezone(timezone.utc) - cached_at.astimezone(timezone.utc)).total_seconds()))
        if age <= ttl_seconds:
            try:
                return decoder(payload, _iso_beijing(cached_at))
            except (KeyError, TypeError, ValueError):
                cached = None
    try:
        result = fetcher()
    except (OSError, RuntimeError, TypeError, ValueError):
        if cached is None:
            return None
        cached_at, payload = cached
        try:
            return decoder(payload, _iso_beijing(cached_at))
        except (KeyError, TypeError, ValueError):
            return None
    _cache_record(path, getattr(result, "fetched_at"), encoder(result))
    return result


def _find_week_window(payload: dict[str, Any]) -> dict[str, Any]:
    rate_limit = payload.get("rate_limit")
    if not isinstance(rate_limit, dict):
        raise ValueError("Missing rate limit")
    for key in ("primary_window", "secondary_window"):
        window = rate_limit.get(key)
        if not isinstance(window, dict):
            continue
        duration = _non_negative_int(window.get("limit_window_seconds"))
        if duration == WEEK_SECONDS:
            return window
    raise ValueError("Missing seven-day quota window")


def _parse_quota_response(payload: dict[str, Any], fetched_at: str) -> QuotaData:
    window = _find_week_window(payload)
    used_percent = _rounded_percent(window.get("used_percent"))
    if used_percent is None:
        raise ValueError("Missing used percentage")
    reset = _parse_datetime(window.get("reset_at"))
    if reset is None:
        after = _non_negative_int(window.get("reset_after_seconds"))
        if after is not None:
            reset = datetime.fromisoformat(fetched_at) + timedelta(seconds=after)
    return QuotaData(
        remaining_percent=100 - used_percent,
        reset_at=_iso_beijing(reset) if reset is not None else None,
        fetched_at=fetched_at,
    )


def _decode_quota(payload: dict[str, Any], fetched_at: str) -> QuotaData:
    remaining = _non_negative_int(payload.get("remaining_percent"))
    if remaining is None or remaining > 100:
        raise ValueError("Invalid cached remaining percentage")
    reset_at = payload.get("reset_at")
    if reset_at is not None and _parse_datetime(reset_at) is None:
        raise ValueError("Invalid cached reset time")
    return QuotaData(remaining, reset_at, fetched_at)


def _encode_quota(data: QuotaData) -> dict[str, Any]:
    return {
        "remaining_percent": data.remaining_percent,
        "reset_at": data.reset_at,
    }


def _normalize_card_time(value: Any) -> str | None:
    parsed = _parse_datetime(value)
    return _iso_beijing(parsed) if parsed is not None else None


def _is_available_card(status: str, expires_at: str | None, now: datetime) -> bool:
    if status.lower() in {"redeemed", "used", "consumed", "expired"}:
        return False
    expires = _parse_datetime(expires_at)
    return expires is None or expires > now


def _parse_reset_response(
    payload: dict[str, Any], fetched_at: str, now: datetime
) -> ResetCardsData:
    raw_cards = payload.get("credits")
    if not isinstance(raw_cards, list):
        raw_cards = []
    cards: list[ResetCard] = []
    for item in raw_cards:
        if not isinstance(item, dict):
            continue
        status_value = item.get("status")
        status = status_value.strip().lower() if isinstance(status_value, str) else "available"
        card = ResetCard(
            status=status,
            granted_at=_normalize_card_time(item.get("granted_at")),
            expires_at=_normalize_card_time(item.get("expires_at")),
            redeemed_at=_normalize_card_time(item.get("redeemed_at")),
        )
        if _is_available_card(card.status, card.expires_at, now):
            cards.append(card)
    available = _non_negative_int(payload.get("available_count"))
    if available is None:
        available = len(cards)
    cards.sort(key=lambda item: item.expires_at or "9999")
    return ResetCardsData(available, tuple(cards), fetched_at)


def _decode_reset_cards(payload: dict[str, Any], fetched_at: str) -> ResetCardsData:
    available = payload.get("available_count")
    if available is not None:
        available = _non_negative_int(available)
        if available is None:
            raise ValueError("Invalid cached reset count")
    raw_cards = payload.get("cards")
    if not isinstance(raw_cards, list):
        raise ValueError("Invalid cached reset cards")
    cards: list[ResetCard] = []
    for item in raw_cards:
        if not isinstance(item, dict) or not isinstance(item.get("status"), str):
            raise ValueError("Invalid cached reset card")
        cards.append(
            ResetCard(
                status=item["status"],
                granted_at=item.get("granted_at"),
                expires_at=item.get("expires_at"),
                redeemed_at=item.get("redeemed_at"),
            )
        )
    return ResetCardsData(available, tuple(cards), fetched_at)


def _encode_reset_cards(data: ResetCardsData) -> dict[str, Any]:
    return {
        "available_count": data.available_count,
        "cards": [asdict(card) for card in data.cards],
    }


def _reasoning_label(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    labels = {
        "low": "低",
        "medium": "中",
        "high": "高",
        "xhigh": "超高",
        "max": "最大",
        "ultra": "极限",
    }
    normalized = value.strip().lower()
    return labels.get(normalized, normalized)


def _required_count(stats: dict[str, Any], key: str) -> int:
    value = _non_negative_int(stats.get(key))
    if value is None:
        raise ValueError(f"Missing profile count: {key}")
    return value


def _parse_profile_response(payload: dict[str, Any], fetched_at: str) -> ProfileData:
    stats = payload.get("stats")
    if not isinstance(stats, dict):
        raise ValueError("Missing profile statistics")
    raw_daily = stats.get("daily_usage_buckets")
    if not isinstance(raw_daily, list):
        raise ValueError("Missing daily usage")
    daily: dict[str, int] = {}
    for item in raw_daily:
        if not isinstance(item, dict) or not isinstance(item.get("start_date"), str):
            continue
        try:
            day = date.fromisoformat(item["start_date"])
        except ValueError:
            continue
        tokens = _non_negative_int(item.get("tokens"))
        if tokens is not None:
            daily[day.isoformat()] = tokens

    longest_seconds = _required_count(stats, "longest_running_turn_sec")
    activity = ActivityInsights(
        fast_mode_percent=_rounded_percent(stats.get("fast_mode_usage_percentage")),
        reasoning_label=_reasoning_label(stats.get("most_used_reasoning_effort")),
        reasoning_percent=_rounded_percent(
            stats.get("most_used_reasoning_effort_percentage")
        ),
        explored_skills=_required_count(stats, "unique_skills_used"),
        skill_uses=_required_count(stats, "total_skills_used"),
        task_count=_required_count(stats, "total_threads"),
        longest_task_minutes=longest_seconds // 60,
    )

    raw_invocations = stats.get("top_invocations")
    plugins: list[PluginUsage] = []
    if isinstance(raw_invocations, list):
        for item in raw_invocations:
            if not isinstance(item, dict) or item.get("type") != "plugin":
                continue
            name = item.get("plugin_name")
            count = _non_negative_int(item.get("usage_count"))
            if not isinstance(name, str) or not name.strip() or count is None:
                continue
            plugins.append(PluginUsage(name=name.strip(), count=count))
            if len(plugins) == 5:
                break
    return ProfileData(tuple(sorted(daily.items())), activity, tuple(plugins), fetched_at)


def _decode_profile(payload: dict[str, Any], fetched_at: str) -> ProfileData:
    raw_daily = payload.get("daily_usage")
    raw_activity = payload.get("activity")
    raw_plugins = payload.get("plugins")
    if not isinstance(raw_daily, list) or not isinstance(raw_activity, dict):
        raise ValueError("Invalid cached profile")
    if not isinstance(raw_plugins, list):
        raise ValueError("Invalid cached plugins")
    daily: list[tuple[str, int]] = []
    for item in raw_daily:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("Invalid cached daily usage")
        day, tokens = item
        if not isinstance(day, str) or _non_negative_int(tokens) is None:
            raise ValueError("Invalid cached daily usage")
        date.fromisoformat(day)
        daily.append((day, int(tokens)))
    activity = ActivityInsights(
        fast_mode_percent=raw_activity.get("fast_mode_percent"),
        reasoning_label=raw_activity.get("reasoning_label"),
        reasoning_percent=raw_activity.get("reasoning_percent"),
        explored_skills=int(raw_activity["explored_skills"]),
        skill_uses=int(raw_activity["skill_uses"]),
        task_count=int(raw_activity["task_count"]),
        longest_task_minutes=int(raw_activity["longest_task_minutes"]),
    )
    plugins = tuple(
        PluginUsage(name=str(item["name"]), count=int(item["count"]))
        for item in raw_plugins
        if isinstance(item, dict)
    )
    return ProfileData(tuple(daily), activity, plugins, fetched_at)


def _encode_profile(data: ProfileData) -> dict[str, Any]:
    return {
        "daily_usage": [[day, tokens] for day, tokens in data.daily_usage],
        "activity": asdict(data.activity),
        "plugins": [asdict(plugin) for plugin in data.plugins],
    }


def fetch_quota(
    auth: CodexAuth | None,
    now: datetime,
    cache_directory: Path,
    timeout: float = 35.0,
) -> QuotaData | None:
    fetched_at = _iso_beijing(now)
    return _cached_fetch(
        cache_directory / "quota.json",
        QUOTA_CACHE_SECONDS,
        now,
        lambda: _parse_quota_response(
            _request_with_optional_auth(USAGE_URL, auth, timeout), fetched_at
        ),
        _decode_quota,
        _encode_quota,
    )


def fetch_reset_cards(
    auth: CodexAuth | None,
    now: datetime,
    cache_directory: Path,
    timeout: float = 35.0,
) -> ResetCardsData | None:
    fetched_at = _iso_beijing(now)
    return _cached_fetch(
        cache_directory / "reset-cards.json",
        QUOTA_CACHE_SECONDS,
        now,
        lambda: _parse_reset_response(
            _request_with_optional_auth(RESET_CREDITS_URL, auth, timeout),
            fetched_at,
            now,
        ),
        _decode_reset_cards,
        _encode_reset_cards,
    )


def fetch_profile(
    auth: CodexAuth | None,
    now: datetime,
    cache_directory: Path,
    timeout: float = 35.0,
) -> ProfileData | None:
    fetched_at = _iso_beijing(now)
    return _cached_fetch(
        cache_directory / "profile.json",
        PROFILE_CACHE_SECONDS,
        now,
        lambda: _parse_profile_response(
            _request_with_optional_auth(PROFILE_URL, auth, timeout), fetched_at
        ),
        _decode_profile,
        _encode_profile,
    )


def _session_files(codex_home: Path) -> tuple[list[Path], bool]:
    files: list[Path] = []
    sources_found = False
    sessions = codex_home / "sessions"
    if sessions.is_dir():
        sources_found = True
        files.extend(sessions.rglob("*.jsonl"))
    archived = codex_home / "archived_sessions"
    if archived.is_dir():
        sources_found = True
        files.extend(
            path
            for path in archived.iterdir()
            if path.is_file() and path.suffix == ".jsonl"
        )
    return sorted(files, key=lambda item: str(item)), sources_found


def _token_counters(value: Any) -> TokenCounters | None:
    if not isinstance(value, dict):
        return None
    input_tokens = _non_negative_int(value.get("input_tokens")) or 0
    cached = _non_negative_int(value.get("cached_input_tokens"))
    if cached is None:
        cached = _non_negative_int(value.get("cache_read_input_tokens")) or 0
    output = _non_negative_int(value.get("output_tokens")) or 0
    return TokenCounters(input_tokens, cached, output)


def _counter_delta(
    previous: TokenCounters | None, current: TokenCounters
) -> TokenCounters:
    if previous is None:
        return current
    return TokenCounters(
        max(0, current.input_tokens - previous.input_tokens),
        max(0, current.cached_input_tokens - previous.cached_input_tokens),
        max(0, current.output_tokens - previous.output_tokens),
    )


def scan_today_sessions(codex_home: Path, now: datetime) -> TodaySessionData:
    files, source_available = _session_files(codex_home)
    today = now.astimezone(BEIJING).date()
    raw_input = 0
    output = 0
    cached = 0
    request_count = 0
    latest: datetime | None = None
    seen_request_ids: set[str] = set()

    for path in files:
        previous: TokenCounters | None = None
        session_id: str | None = None
        event_index = 0
        try:
            stream = path.open("r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with stream:
            for line in stream:
                if not (
                    '"event_msg"' in line
                    or '"turn_context"' in line
                    or '"session_meta"' in line
                ):
                    continue
                if '"event_msg"' in line and '"token_count"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                record_type = record.get("type")
                payload = record.get("payload")
                if record_type == "session_meta" and session_id is None:
                    if isinstance(payload, dict):
                        candidate = (
                            payload.get("session_id")
                            or payload.get("sessionId")
                            or payload.get("id")
                        )
                        if isinstance(candidate, str) and candidate:
                            session_id = candidate
                    continue
                if record_type != "event_msg" or not isinstance(payload, dict):
                    continue
                if payload.get("type") != "token_count":
                    continue
                info = payload.get("info")
                if not isinstance(info, dict):
                    continue
                if "total_token_usage" in info:
                    current = _token_counters(info.get("total_token_usage"))
                    if current is None:
                        continue
                    delta = _counter_delta(previous, current)
                    previous = current
                elif "last_token_usage" in info:
                    delta = _token_counters(info.get("last_token_usage"))
                    if delta is None:
                        continue
                else:
                    continue
                delta = TokenCounters(
                    delta.input_tokens,
                    min(delta.cached_input_tokens, delta.input_tokens),
                    delta.output_tokens,
                )
                if (
                    delta.input_tokens == 0
                    and delta.cached_input_tokens == 0
                    and delta.output_tokens == 0
                ):
                    continue
                event_index += 1
                request_id = f"codex_session:{session_id or 'unknown'}:{event_index}"
                if request_id in seen_request_ids:
                    continue
                seen_request_ids.add(request_id)
                timestamp = _parse_datetime(record.get("timestamp")) or now
                if timestamp.astimezone(BEIJING).date() != today:
                    continue
                raw_input += delta.input_tokens
                cached += delta.cached_input_tokens
                output += delta.output_tokens
                request_count += 1
                latest = timestamp if latest is None else max(latest, timestamp)

    return TodaySessionData(
        raw_input_tokens=raw_input,
        fresh_input_tokens=max(0, raw_input - cached),
        output_tokens=output,
        cached_input_tokens=cached,
        request_count=request_count,
        latest_event_at=_iso_beijing(latest) if latest is not None else None,
        source_available=source_available,
    )


def _empty_activity() -> ActivityInsights:
    return ActivityInsights(
        fast_mode_percent=None,
        reasoning_label=None,
        reasoning_percent=None,
        explored_skills=0,
        skill_uses=0,
        task_count=0,
        longest_task_minutes=0,
    )


def _daily_window(
    profile: ProfileData | None, now: datetime
) -> tuple[tuple[str, int], ...]:
    values = dict(profile.daily_usage) if profile is not None else {}
    current_day = now.astimezone(BEIJING).date()
    first_day = current_day - timedelta(days=29)
    return tuple(
        (
            (first_day + timedelta(days=offset)).isoformat(),
            values.get((first_day + timedelta(days=offset)).isoformat(), 0),
        )
        for offset in range(30)
    )


def collect_snapshot(
    now: datetime | None = None,
    codex_home: Path | None = None,
    cache_directory: Path | None = None,
    quota: QuotaData | None = None,
    reset_cards: ResetCardsData | None = None,
    profile: ProfileData | None = None,
    fetch_remote: bool = True,
) -> DashboardSnapshot:
    current = now or datetime.now(BEIJING)
    if current.tzinfo is None:
        current = current.replace(tzinfo=BEIJING)
    current = current.astimezone(BEIJING)
    home = codex_home or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    cache = cache_directory or DEFAULT_CACHE_DIRECTORY

    with ThreadPoolExecutor(max_workers=4) as executor:
        sessions_future = executor.submit(scan_today_sessions, home, current)
        if fetch_remote and (quota is None or reset_cards is None or profile is None):
            try:
                auth = _load_auth(home)
            except RuntimeError:
                auth = None
            quota_future = (
                executor.submit(fetch_quota, auth, current, cache)
                if quota is None
                else None
            )
            reset_future = (
                executor.submit(fetch_reset_cards, auth, current, cache)
                if reset_cards is None
                else None
            )
            profile_future = (
                executor.submit(fetch_profile, auth, current, cache)
                if profile is None
                else None
            )
            if quota_future is not None:
                quota = quota_future.result()
            if reset_future is not None:
                reset_cards = reset_future.result()
            if profile_future is not None:
                profile = profile_future.result()
        sessions = sessions_future.result()

    daily = _daily_window(profile, current)
    total_today = (
        sessions.fresh_input_tokens
        + sessions.output_tokens
        + sessions.cached_input_tokens
    )
    hit_percent = (
        round_half_up(sessions.cached_input_tokens * 100, sessions.raw_input_tokens)
        if sessions.raw_input_tokens
        else 0
    )
    profile_usage_as_of = (
        max((day for day, _ in profile.daily_usage), default=None)
        if profile is not None
        else None
    )
    return DashboardSnapshot(
        generated_at=_iso_beijing(current),
        weekly_remaining_percent=quota.remaining_percent if quota else None,
        weekly_reset_at=quota.reset_at if quota else None,
        reset_cards_available=(
            reset_cards.available_count if reset_cards is not None else None
        ),
        reset_cards=reset_cards.cards if reset_cards is not None else (),
        today=TodayUsage(
            total_tokens=total_today,
            fresh_input_tokens=sessions.fresh_input_tokens,
            raw_input_tokens=sessions.raw_input_tokens,
            output_tokens=sessions.output_tokens,
            cached_input_tokens=sessions.cached_input_tokens,
            request_count=sessions.request_count,
            cache_hit_percent=hit_percent,
            total_cost=None,
        ),
        last_30d_tokens=sum(tokens for _, tokens in daily),
        daily_30d=daily,
        activity=profile.activity if profile is not None else _empty_activity(),
        common_plugins=profile.plugins if profile is not None else (),
        quota_fetched_at=quota.fetched_at if quota is not None else None,
        reset_cards_fetched_at=(
            reset_cards.fetched_at if reset_cards is not None else None
        ),
        profile_fetched_at=profile.fetched_at if profile is not None else None,
        profile_usage_as_of=profile_usage_as_of,
        quota_available=quota is not None,
        reset_cards_source_available=reset_cards is not None,
        profile_available=profile is not None,
        local_sessions_available=sessions.source_available,
    )
