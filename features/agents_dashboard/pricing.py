from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


RATE_CARD_VERIFIED_ON = "2026-07-28"
TOKENS_PER_MILLION = Decimal(1_000_000)
LONG_CONTEXT_THRESHOLD = 272_000


@dataclass(frozen=True)
class ApiRateEntry:
    model: str
    official_name: str
    input_rate: Decimal | None
    cached_input_rate: Decimal | None
    cache_write_rate: Decimal | None
    output_rate: Decimal | None
    cache_write_label: str
    long_context_threshold: int | None
    long_context_label: str
    status: str


@dataclass(frozen=True)
class RequestCost:
    exact_usd: Decimal
    long_context: bool


def _rate(
    model: str,
    official_name: str,
    input_rate: str | None,
    cached_input_rate: str | None,
    cache_write_rate: str | None,
    output_rate: str | None,
    cache_write_label: str,
    long_context: bool,
    status: str,
) -> ApiRateEntry:
    return ApiRateEntry(
        model=model,
        official_name=official_name,
        input_rate=Decimal(input_rate) if input_rate is not None else None,
        cached_input_rate=(
            Decimal(cached_input_rate) if cached_input_rate is not None else None
        ),
        cache_write_rate=(
            Decimal(cache_write_rate) if cache_write_rate is not None else None
        ),
        output_rate=Decimal(output_rate) if output_rate is not None else None,
        cache_write_label=cache_write_label,
        long_context_threshold=LONG_CONTEXT_THRESHOLD if long_context else None,
        long_context_label=(
            "输入超过 272,000 时，全部输入 2 倍、输出 1.5 倍"
            if long_context
            else "无附加规则"
        ),
        status=status,
    )


API_RATE_CARD = (
    _rate(
        "gpt-5.6",
        "GPT-5.6 Sol",
        "5.00",
        "0.50",
        "6.25",
        "30.00",
        "$6.25",
        True,
        "可计算",
    ),
    _rate(
        "gpt-5.6-sol",
        "GPT-5.6 Sol",
        "5.00",
        "0.50",
        "6.25",
        "30.00",
        "$6.25",
        True,
        "可计算",
    ),
    _rate(
        "gpt-5.6-terra",
        "GPT-5.6 Terra",
        "2.50",
        "0.25",
        "3.125",
        "15.00",
        "$3.125",
        True,
        "可计算",
    ),
    _rate(
        "gpt-5.6-luna",
        "GPT-5.6 Luna",
        "1.00",
        "0.10",
        "1.25",
        "6.00",
        "$1.25",
        True,
        "可计算",
    ),
    _rate(
        "gpt-5.5",
        "GPT-5.5",
        "5.00",
        "0.50",
        "5.00",
        "30.00",
        "按普通输入",
        True,
        "可计算",
    ),
    _rate(
        "gpt-5.4",
        "GPT-5.4",
        "2.50",
        "0.25",
        "2.50",
        "15.00",
        "按普通输入",
        True,
        "可计算",
    ),
    _rate(
        "gpt-5.4-mini",
        "GPT-5.4 mini",
        "0.75",
        "0.075",
        "0.75",
        "4.50",
        "按普通输入",
        False,
        "可计算",
    ),
    _rate(
        "gpt-5.3-codex",
        "GPT-5.3-Codex",
        "1.75",
        "0.175",
        "1.75",
        "14.00",
        "按普通输入",
        False,
        "可计算",
    ),
    _rate(
        "codex-auto-review",
        "GPT-5.3-Codex",
        "1.75",
        "0.175",
        "1.75",
        "14.00",
        "按普通输入",
        False,
        "可计算",
    ),
    _rate(
        "gpt-5.2",
        "GPT-5.2",
        "1.75",
        "0.175",
        "1.75",
        "14.00",
        "按普通输入",
        False,
        "可计算",
    ),
    _rate(
        "gpt-5.2-codex",
        "GPT-5.2-Codex",
        "1.75",
        "0.175",
        "1.75",
        "14.00",
        "按普通输入",
        False,
        "可计算",
    ),
    _rate(
        "gpt-5.5-cyber",
        "GPT-5.5 Cyber",
        None,
        None,
        None,
        None,
        "未公布",
        False,
        "无法计算",
    ),
    _rate(
        "gpt-5.3-codex-spark",
        "GPT-5.3-Codex-Spark",
        None,
        None,
        None,
        None,
        "未公布",
        False,
        "无法计算",
    ),
)
RATE_BY_MODEL = {entry.model: entry for entry in API_RATE_CARD}


def calculate_request_cost(
    model: str | None,
    input_tokens: int,
    cached_input_tokens: int,
    cache_write_input_tokens: int,
    output_tokens: int,
) -> RequestCost | None:
    if min(
        input_tokens,
        cached_input_tokens,
        cache_write_input_tokens,
        output_tokens,
    ) < 0:
        raise ValueError("Token counts must be non-negative")
    if cached_input_tokens + cache_write_input_tokens > input_tokens:
        raise ValueError("Cached and cache-write tokens exceed input tokens")
    if model is None:
        return None
    entry = RATE_BY_MODEL.get(model.strip().lower())
    if (
        entry is None
        or entry.input_rate is None
        or entry.cached_input_rate is None
        or entry.cache_write_rate is None
        or entry.output_rate is None
    ):
        return None

    ordinary_input_tokens = (
        input_tokens - cached_input_tokens - cache_write_input_tokens
    )
    input_cost = (
        Decimal(ordinary_input_tokens) * entry.input_rate
        + Decimal(cached_input_tokens) * entry.cached_input_rate
        + Decimal(cache_write_input_tokens) * entry.cache_write_rate
    ) / TOKENS_PER_MILLION
    output_cost = (
        Decimal(output_tokens) * entry.output_rate / TOKENS_PER_MILLION
    )
    long_context = (
        entry.long_context_threshold is not None
        and input_tokens > entry.long_context_threshold
    )
    if long_context:
        input_cost *= Decimal(2)
        output_cost *= Decimal("1.5")
    return RequestCost(input_cost + output_cost, long_context)


def round_usd(value: Decimal) -> int:
    if value < 0:
        raise ValueError("Cost must be non-negative")
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def exact_usd_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def markdown_rate_row(entry: ApiRateEntry) -> str:
    def dollars(value: Decimal | None) -> str:
        return f"${value}" if value is not None else "未公布"

    return (
        f"| `{entry.model}` | {entry.official_name} | "
        f"{dollars(entry.input_rate)} | {dollars(entry.cached_input_rate)} | "
        f"{entry.cache_write_label} | {dollars(entry.output_rate)} | "
        f"{entry.long_context_label if entry.input_rate is not None else '未公布'} | "
        f"{entry.status} |"
    )
