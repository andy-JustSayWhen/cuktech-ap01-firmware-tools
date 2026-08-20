from __future__ import annotations

from dataclasses import dataclass


MAX_TOKEN_VALUE = 100_000_000_000


@dataclass(frozen=True)
class TokenDisplay:
    value: str
    unit: str

    @property
    def text(self) -> str:
        return f"{self.value} {self.unit}"


def round_half_up(numerator: int, denominator: int) -> int:
    if numerator < 0 or denominator <= 0:
        raise ValueError("round_half_up requires a non-negative value and positive divisor")
    return (numerator + denominator // 2) // denominator


def format_token_count(tokens: int) -> TokenDisplay:
    if not isinstance(tokens, int) or isinstance(tokens, bool):
        raise TypeError("Token count must be an integer")
    if tokens < 0 or tokens >= MAX_TOKEN_VALUE:
        raise ValueError("Token count is outside the supported range")

    if tokens < 10_000:
        return TokenDisplay(f"{tokens:,}", "Token")

    if tokens < 100_000_000:
        value = round_half_up(tokens, 10_000)
        if value < 10_000:
            return TokenDisplay(f"{value:,}", "万 Token")

    value = round_half_up(tokens, 100_000_000)
    return TokenDisplay(f"{value:,}", "亿 Token")


def format_integer(value: int) -> str:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("Displayed count must be a non-negative integer")
    return f"{value:,}"


def format_duration(minutes: int) -> tuple[str, str]:
    if minutes < 0:
        raise ValueError("Duration must be non-negative")
    hours, remainder = divmod(minutes, 60)
    return f"{hours:,}", f"时 {remainder} 分"
