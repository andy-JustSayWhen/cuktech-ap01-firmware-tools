from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont

from .formatting import TokenDisplay, format_integer, format_token_count
from .models import DashboardSnapshot


WIDTH = 320
HEIGHT = 240
SCALE = 4
SYSTEM_OVERLAY_SAFE_BOTTOM = 60
SYSTEM_OVERLAY_TIME_BOX = (19, 17, 75, 33)
SYSTEM_OVERLAY_DATE_BOX = (253, 16, 316, 37)
SYSTEM_OVERLAY_TITLE_HALF_WIDTH = 60
SYSTEM_OVERLAY_TITLE_HALF_HEIGHT = 12
SYSTEM_OVERLAY_TITLE_X_OFFSET = -3
PAGE_TITLE_X = (
    (SYSTEM_OVERLAY_TIME_BOX[2] + SYSTEM_OVERLAY_DATE_BOX[0]) / 2
    + SYSTEM_OVERLAY_TITLE_X_OFFSET
)
PAGE_TITLE_Y = (
    (SYSTEM_OVERLAY_TIME_BOX[1] + SYSTEM_OVERLAY_TIME_BOX[3])
    + (SYSTEM_OVERLAY_DATE_BOX[1] + SYSTEM_OVERLAY_DATE_BOX[3])
) / 4
SYSTEM_OVERLAY_TITLE_BOX = (
    round(PAGE_TITLE_X - SYSTEM_OVERLAY_TITLE_HALF_WIDTH),
    round(PAGE_TITLE_Y - SYSTEM_OVERLAY_TITLE_HALF_HEIGHT),
    round(PAGE_TITLE_X + SYSTEM_OVERLAY_TITLE_HALF_WIDTH),
    round(PAGE_TITLE_Y + SYSTEM_OVERLAY_TITLE_HALF_HEIGHT),
)
PAGE_TITLE_SIZE = 14
BACKGROUND = "#000000"
WHITE = "#F5F5F2"
MUTED = "#B9BBBA"
DIM = "#777A78"
DARK = "#252625"
YELLOW = "#FFD400"
CYAN = "#00D5FF"
BLUE = "#13B8FF"
ORANGE = "#FF7A00"
RED = "#FF2228"
GREEN = "#58F20D"
ICON_DIR = Path(__file__).parent / "assets" / "icons"
FONT_ROLE_FILES = {
    "hero": "MiSans-Bold.ttf",
    "secondary": "MiSans-Medium.ttf",
    "body": "MiSans-Semibold.ttf",
    "emphasis": "MiSans-Bold.ttf",
}


class FontBook:
    def __init__(self, directory: Path):
        paths = {
            role: directory / filename
            for role, filename in FONT_ROLE_FILES.items()
        }
        missing = [path.name for path in paths.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Missing required dashboard fonts: {', '.join(missing)}")
        self.paths = paths

    def get(self, size: float, role: str = "body") -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(self.paths[role]), round(size * SCALE))


class Canvas:
    def __init__(self, fonts: FontBook):
        self.fonts = fonts
        self.image = Image.new("RGBA", (WIDTH * SCALE, HEIGHT * SCALE), BACKGROUND)
        self.draw = ImageDraw.Draw(self.image)

    @staticmethod
    def s(value: float) -> int:
        return round(value * SCALE)

    @classmethod
    def rect(cls, values: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        return tuple(cls.s(value) for value in values)  # type: ignore[return-value]

    def text(
        self,
        xy: tuple[float, float],
        value: str,
        size: float,
        color: str = WHITE,
        role: str = "body",
        anchor: str | None = None,
    ) -> tuple[int, int, int, int]:
        if "." in value and any(character.isdigit() for character in value):
            raise ValueError(f"Decimal text is not allowed: {value}")
        font = self.fonts.get(size, role)
        position = (self.s(xy[0]), self.s(xy[1]))
        bounds = self.draw.textbbox(position, value, font=font, anchor=anchor)
        if bounds[0] < 0 or bounds[1] < 0 or bounds[2] > WIDTH * SCALE or bounds[3] > HEIGHT * SCALE:
            raise ValueError(f"Text is outside the canvas: {value}")
        self.draw.text(position, value, font=font, fill=color, anchor=anchor)
        return bounds

    def line(
        self,
        points: Iterable[tuple[float, float]],
        fill: str,
        width: float = 1,
    ) -> None:
        self.draw.line(
            [(self.s(x), self.s(y)) for x, y in points],
            fill=fill,
            width=max(1, self.s(width)),
            joint="curve",
        )

    def icon(
        self,
        name: str,
        xy: tuple[float, float],
        size: float,
        color: str,
        mirror: bool = False,
    ) -> None:
        path = ICON_DIR / f"{name}.png"
        if not path.is_file():
            raise FileNotFoundError(f"Missing icon: {path.name}")
        target = self.s(size)
        with Image.open(path).convert("RGBA") as source:
            if mirror:
                source = source.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            source = source.resize((target, target), Image.Resampling.LANCZOS)
            alpha = source.getchannel("A")
            tinted = Image.new("RGBA", source.size, ImageColor.getrgb(color) + (255,))
            tinted.putalpha(alpha)
            self.image.alpha_composite(tinted, (self.s(xy[0]), self.s(xy[1])))

    def glow(self, bounds: tuple[float, float, float, float], color: str, blur: float) -> None:
        layer = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
        layer_draw = ImageDraw.Draw(layer)
        layer_draw.ellipse(self.rect(bounds), fill=ImageColor.getrgb(color) + (160,))
        layer = layer.filter(ImageFilter.GaussianBlur(self.s(blur)))
        self.image.alpha_composite(layer)

    def finish(self) -> Image.Image:
        return self.image.convert("RGB").resize(
            (WIDTH, HEIGHT), Image.Resampling.LANCZOS
        )


def _mix(first: str, second: str, amount: float) -> tuple[int, int, int]:
    left = ImageColor.getrgb(first)
    right = ImageColor.getrgb(second)
    bounded = max(0.0, min(1.0, amount))
    return tuple(round(a + (b - a) * bounded) for a, b in zip(left, right))


def quality_color(percent: float) -> tuple[int, int, int]:
    stops = ((0.0, RED), (35.0, ORANGE), (62.0, YELLOW), (100.0, GREEN))
    bounded = max(0.0, min(100.0, percent))
    for (start, start_color), (end, end_color) in zip(stops, stops[1:]):
        if bounded <= end:
            return _mix(start_color, end_color, (bounded - start) / (end - start))
    return ImageColor.getrgb(GREEN)


def _draw_gradient_arc(
    canvas: Canvas,
    bounds: tuple[float, float, float, float],
    start: float,
    span: float,
    percent: int,
    width: float,
) -> None:
    bounded = max(0, min(100, percent))
    canvas.draw.arc(canvas.rect(bounds), start=start, end=start + span, fill=DARK, width=canvas.s(width))
    completed = span * bounded / 100
    segments = max(1, math.ceil(completed / 2))
    for index in range(segments):
        first = start + completed * index / segments
        second = start + completed * (index + 1) / segments + 0.45
        absolute_percent = bounded * (index + 1) / segments
        canvas.draw.arc(
            canvas.rect(bounds),
            start=first,
            end=second,
            fill=quality_color(absolute_percent),
            width=canvas.s(width),
        )


def _draw_quality_arc(
    canvas: Canvas,
    bounds: tuple[float, float, float, float],
    start: float,
    span: float,
    percent: int,
    width: float,
) -> None:
    bounded = max(0, min(100, percent))
    canvas.draw.arc(
        canvas.rect(bounds),
        start=start,
        end=start + span,
        fill=DARK,
        width=canvas.s(width),
    )
    canvas.draw.arc(
        canvas.rect(bounds),
        start=start,
        end=start + span * bounded / 100,
        fill=quality_color(bounded),
        width=canvas.s(width),
    )


def _fit_font(
    canvas: Canvas,
    value: str,
    sizes: tuple[float, ...],
    max_width: float,
    role: str = "hero",
) -> float:
    for size in sizes:
        font = canvas.fonts.get(size, role)
        bounds = canvas.draw.textbbox((0, 0), value, font=font)
        if bounds[2] - bounds[0] <= canvas.s(max_width):
            return size
    raise ValueError(f"Value does not fit its slot: {value}")


def _draw_token_pair(
    canvas: Canvas,
    display: TokenDisplay,
    value_right: float,
    baseline: float,
    unit_x: float,
    value_sizes: tuple[float, ...],
    max_value_width: float,
    unit_size: float,
    color: str = WHITE,
    unit_color: str = MUTED,
) -> None:
    size = _fit_font(canvas, display.value, value_sizes, max_value_width, "hero")
    canvas.text(
        (value_right, baseline),
        display.value,
        size,
        color,
        "hero",
        "rs",
    )
    canvas.text(
        (unit_x, baseline - 1),
        display.unit,
        unit_size,
        unit_color,
        "body",
        "ls",
    )


def _draw_page_title(canvas: Canvas, title: str) -> None:
    canvas.text((PAGE_TITLE_X, PAGE_TITLE_Y), title, PAGE_TITLE_SIZE, MUTED, "body", "mm")


def _sparkline(
    canvas: Canvas,
    values: list[int],
    *,
    left: float = 27.0,
    right: float = 301.0,
    top: float = 180.0,
    bottom: float = 224.0,
) -> None:
    if not values:
        return
    minimum = min(values)
    maximum = max(values)
    spread = max(1, maximum - minimum)
    points = [
        (
            left + (right - left) * index / max(1, len(values) - 1),
            bottom - (value - minimum) * (bottom - top) / spread,
        )
        for index, value in enumerate(values)
    ]
    colors = (BLUE, CYAN, "#BCE43A", YELLOW, "#FFAA00", ORANGE, RED)
    for index in range(len(points) - 1):
        canvas.line((points[index], points[index + 1]), colors[min(index, 6)], 1.5)
    for index, point in enumerate(points):
        radius = 2.3
        canvas.draw.ellipse(
            canvas.rect((point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius)),
            fill=colors[min(index, 6)],
        )


def _token_or_unavailable(value: int, available: bool) -> TokenDisplay:
    return format_token_count(value) if available else TokenDisplay("无法获取", "")


def render_overview(snapshot: DashboardSnapshot, fonts: FontBook) -> Image.Image:
    canvas = Canvas(fonts)
    canvas.glow((227, 171, 331, 265), "#9C2200", 22)
    _draw_page_title(canvas, "AGENTS 看板")

    remaining = snapshot.weekly_remaining_percent
    remaining_value = remaining if remaining is not None and snapshot.quota_available else 0
    remaining_text = format_integer(remaining_value) if snapshot.quota_available and remaining is not None else "无法获取"
    _draw_quality_arc(canvas, (12, 63, 132, 183), -90, 360, remaining_value, 5)
    canvas.text((72, 86), "本周剩余", 13.5, YELLOW, "emphasis", "mm")
    remaining_size = _fit_font(canvas, remaining_text, (44, 31, 24, 18, 14), 92, "hero")
    canvas.text((65, 132), remaining_text, remaining_size, WHITE, "hero", "mm")
    if snapshot.quota_available and remaining is not None:
        canvas.text((117, 122), "%", 14, WHITE, "secondary", "mm")

    today = _token_or_unavailable(snapshot.today.total_tokens, snapshot.local_sessions_available)
    last_30 = _token_or_unavailable(snapshot.last_30d_tokens, snapshot.profile_available)
    canvas.text((156, 63), "今日消耗", 12, YELLOW, "emphasis", "lt")
    _draw_token_pair(
        canvas,
        today,
        258,
        110,
        265,
        (38, 31, 27, 23, 20, 19),
        82,
        10.5,
    )
    canvas.text((156, 123), "近30天消耗", 12, ORANGE, "emphasis", "lt")
    _draw_token_pair(
        canvas,
        last_30,
        258,
        170,
        265,
        (38, 31, 27, 23, 20, 19),
        82,
        10.5,
    )

    canvas.text((16, 184), "近7天消耗", 12, CYAN, "emphasis", "lt")
    _sparkline(
        canvas,
        [tokens for _, tokens in snapshot.daily_30d[-7:]],
        left=22,
        right=292,
        top=197,
        bottom=226,
    )
    return canvas.finish()


def _countdown(reset_at: str | None, generated_at: str) -> tuple[str, str]:
    if not reset_at:
        return "无法获取", ""
    reset = datetime.fromisoformat(reset_at)
    generated = datetime.fromisoformat(generated_at)
    seconds = max(0, int((reset - generated).total_seconds()))
    hours = (seconds + 3_599) // 3_600
    days, remaining_hours = divmod(hours, 24)
    reset_text = (
        f"{reset.month:02d}月{reset.day:02d}日 "
        f"{reset.hour:02d}:{reset.minute:02d}"
    )
    return f"{days}天{remaining_hours}小时", reset_text


def _short_timestamp(value: str | None) -> str:
    if not value:
        return "无法获取"
    parsed = datetime.fromisoformat(value)
    return f"{parsed.month:02d}月{parsed.day:02d}日 {parsed.hour:02d}:{parsed.minute:02d}"


def _short_date(value: str | None) -> str:
    if not value:
        return "--/--"
    parsed = datetime.fromisoformat(value)
    return f"{parsed.month:02d}/{parsed.day:02d}"


def _remaining_days(value: str | None, generated_at: str) -> str:
    if not value:
        return "--"
    expires = datetime.fromisoformat(value)
    generated = datetime.fromisoformat(generated_at)
    seconds = max(0, int((expires - generated).total_seconds()))
    return format_integer((seconds + 86_399) // 86_400)


def render_weekly(
    snapshot: DashboardSnapshot,
    fonts: FontBook,
    *,
    card_offset: int = 0,
) -> Image.Image:
    canvas = Canvas(fonts)
    canvas.glow((240, 168, 330, 257), "#702000", 23)
    _draw_page_title(canvas, "周剩余额度")

    remaining = snapshot.weekly_remaining_percent
    remaining_value = remaining if remaining is not None and snapshot.quota_available else 0
    remaining_text = format_integer(remaining_value) if snapshot.quota_available and remaining is not None else "无法获取"
    _draw_gradient_arc(canvas, (2, 62, 158, 218), 160, 220, remaining_value, 7)
    canvas.text((83, 87), "本周剩余", 15, YELLOW, "emphasis", "mm")
    remaining_size = _fit_font(canvas, remaining_text, (58, 40, 32, 24, 18), 124, "hero")
    canvas.text((75, 139), remaining_text, remaining_size, WHITE, "hero", "mm")
    if snapshot.quota_available and remaining is not None:
        canvas.text((136, 128), "%", 16, WHITE, "secondary", "mm")

    countdown, reset_time = _countdown(snapshot.weekly_reset_at, snapshot.generated_at)
    canvas.text((210, 63), "下次重置", 12, MUTED, "emphasis", "lt")
    countdown_size = _fit_font(
        canvas, countdown, (18, 15, 13), 84, "emphasis"
    )
    canvas.text((210, 88), countdown, countdown_size, YELLOW, "emphasis")
    if reset_time:
        canvas.text((210, 112), reset_time, 10.5, MUTED, "secondary")
    canvas.draw.rounded_rectangle(
        canvas.rect((207, 132, 309, 154)),
        radius=canvas.s(3),
        outline=CYAN,
        width=canvas.s(1.3),
    )
    available = (
        "无法获取"
        if snapshot.reset_cards_available is None
        else format_integer(snapshot.reset_cards_available)
    )
    available_text = f"可用重置  {available}"
    available_size = _fit_font(canvas, available_text, (11, 10.5, 10), 94, "body")
    canvas.text((258, 143), available_text, available_size, CYAN, "body", "mm")

    canvas.line(((18, 172), (302, 172)), "#4A2B08", 0.8)
    cards = list(snapshot.reset_cards[card_offset : card_offset + 2])
    if not cards:
        canvas.text(
            (14, 198),
            "当前账号未返回可核验的重置卡数据",
            11.5,
            DIM,
            "body",
            "lm",
        )
        return canvas.finish()

    for index, card in enumerate(cards):
        y = 187 + index * 23
        canvas.text((14, y), f"重置卡 {card_offset + index + 1}", 12.5, WHITE, "secondary", "lm")
        canvas.line(((84, y - 9), (84, y + 9)), YELLOW, 0.8)
        canvas.text((92, y), "剩余", 10.5, DIM, "body", "lm")
        canvas.text(
            (117, y),
            f"{_remaining_days(card.expires_at, snapshot.generated_at)}天",
            10.5,
            YELLOW,
            "emphasis",
            "lm",
        )
        canvas.text((151, y), "发放", 10.5, DIM, "body", "lm")
        canvas.text((176, y), _short_date(card.granted_at), 10.5, MUTED, "body", "lm")
        canvas.text((224, y), "到期", 10.5, DIM, "body", "lm")
        canvas.text((249, y), _short_date(card.expires_at), 10.5, ORANGE, "body", "lm")
        if index == 0 and len(cards) > 1:
            canvas.line(((14, 199), (304, 199)), "#35200B", 0.6)
    return canvas.finish()


def render_weekly_batches(snapshot: DashboardSnapshot, fonts: FontBook) -> list[Image.Image]:
    count = max(1, (len(snapshot.reset_cards) + 1) // 2)
    return [render_weekly(snapshot, fonts, card_offset=index * 2) for index in range(count)]


def _draw_metric_column(
    canvas: Canvas,
    x: float,
    label: str,
    icon: str,
    icon_color: str,
    display: TokenDisplay,
    mirror: bool = False,
    y_offset: float = 0.0,
    value_sizes: tuple[float, ...] = (27, 23, 18, 14, 12, 10),
) -> None:
    canvas.icon(icon, (x, 125 + y_offset), 18, icon_color, mirror)
    canvas.text((x + 21, 134 + y_offset), label, 11.5, MUTED, "body", "lm")
    value_size = _fit_font(canvas, display.value, value_sizes, 82, "secondary")
    canvas.text((x, 169 + y_offset), display.value, value_size, WHITE, "secondary", "ls")
    canvas.text((x, 189 + y_offset), display.unit, 10.5, MUTED, "body", "ls")


def render_today(snapshot: DashboardSnapshot, fonts: FontBook) -> Image.Image:
    canvas = Canvas(fonts)
    canvas.glow((258, 174, 338, 260), "#7B1C00", 23)
    _draw_page_title(canvas, "今日消耗")
    canvas.text((14, 63), "总消耗", 12, MUTED, "body", "lt")

    total = _token_or_unavailable(snapshot.today.total_tokens, snapshot.local_sessions_available)
    total_size = _fit_font(
        canvas,
        total.value,
        (52, 46, 42, 38, 34, 30),
        134,
        "hero",
    )
    canvas.text((148, 104), total.value, total_size, WHITE, "hero", "rs")
    canvas.text((148, 121), total.unit, 10.5, WHITE, "body", "rs")

    canvas.line(((176, 65), (176, 124)), "#343535", 0.8)
    canvas.text((194, 63), "请求数", 12, YELLOW, "emphasis", "lt")
    request_size = _fit_font(
        canvas,
        format_integer(snapshot.today.request_count) if snapshot.local_sessions_available else "无法获取",
        (24, 20, 16, 12, 10),
        56,
        "secondary",
    )
    canvas.text(
        (194, 98),
        format_integer(snapshot.today.request_count) if snapshot.local_sessions_available else "无法获取",
        request_size,
        WHITE,
        "secondary",
        "lm",
    )
    canvas.text((260, 63), "API成本", 12, ORANGE, "emphasis", "lt")
    cost = (
        "无法获取"
        if snapshot.today.api_cost_usd_rounded is None or not snapshot.local_sessions_available
        else f"${format_integer(snapshot.today.api_cost_usd_rounded)}"
    )
    cost_size = _fit_font(canvas, cost, (16, 13, 11), 52, "secondary")
    canvas.text((260, 98), cost, cost_size, WHITE, "secondary", "lm")

    _draw_metric_column(
        canvas,
        16,
        "新增输入",
        "arrow-circle",
        BLUE,
        _token_or_unavailable(snapshot.today.fresh_input_tokens, snapshot.local_sessions_available),
        True,
        0,
    )
    _draw_metric_column(
        canvas,
        119,
        "输出",
        "arrow-circle",
        CYAN,
        _token_or_unavailable(snapshot.today.output_tokens, snapshot.local_sessions_available),
        False,
        0,
    )
    _draw_metric_column(
        canvas,
        222,
        "缓存命中",
        "cache",
        YELLOW,
        _token_or_unavailable(snapshot.today.cached_input_tokens, snapshot.local_sessions_available),
        False,
        0,
        (25, 21, 17, 14, 12, 10),
    )

    canvas.text((15, 199), "缓存命中率", 11.5, MUTED, "body", "lt")
    left, right, y = 15.0, 254.0, 212.0
    canvas.draw.rounded_rectangle(
        canvas.rect((left, y - 3, right, y + 3)),
        radius=canvas.s(3),
        fill=DARK,
    )
    percent = max(0, min(100, snapshot.today.cache_hit_percent)) if snapshot.local_sessions_available else 0
    completed = (right - left) * percent / 100
    completed_pixels = max(0, round(completed))
    bar_top = canvas.s(y - 3)
    bar_bottom = canvas.s(y + 3)
    for offset in range(completed_pixels):
        x1 = canvas.s(left) + offset * SCALE
        x2 = x1 + SCALE - 1
        absolute_percent = percent * (offset + 0.5) / max(1, completed_pixels)
        canvas.draw.rectangle(
            (x1, bar_top, x2, bar_bottom),
            fill=quality_color(absolute_percent),
        )
    cache_text = f"{percent}%" if snapshot.local_sessions_available else "无法获取"
    cache_size = _fit_font(canvas, cache_text, (14, 12, 10, 9), 42, "emphasis")
    canvas.text(
        (267, 212),
        cache_text,
        cache_size,
        quality_color(percent) if snapshot.local_sessions_available else DIM,
        "emphasis",
        "lm",
    )
    return canvas.finish()


def _activity_rows(snapshot: DashboardSnapshot) -> list[tuple[str, str]]:
    activity = snapshot.activity
    fast = "无法获取" if activity.fast_mode_percent is None else f"{activity.fast_mode_percent}%"
    if activity.reasoning_label is None or activity.reasoning_percent is None:
        reasoning = "无法获取"
    else:
        reasoning = f"{activity.reasoning_label} · {activity.reasoning_percent}%"
    return [
        ("快速模式", fast),
        ("常用推理强度", reasoning),
        ("已探索的技能", format_integer(activity.explored_skills)),
        ("使用的技能总数", format_integer(activity.skill_uses)),
        ("任务总数", format_integer(activity.task_count)),
    ]


def render_last_30_days(snapshot: DashboardSnapshot, fonts: FontBook) -> Image.Image:
    canvas = Canvas(fonts)
    canvas.glow((225, 160, 334, 268), "#671800", 25)
    _draw_page_title(canvas, "近30天消耗")
    canvas.text((23, 63), "累计消耗", 16, MUTED, "body", "lt")
    _draw_token_pair(
        canvas,
        _token_or_unavailable(snapshot.last_30d_tokens, snapshot.profile_available),
        107,
        112,
        115,
        (47, 40, 36, 32, 27, 23, 20),
        100,
        9,
        WHITE,
        WHITE,
    )
    canvas.text((192, 63), "最长任务", 16, MUTED, "body", "lt")
    hours_value, minutes_value = divmod(snapshot.activity.longest_task_minutes, 60)
    if snapshot.profile_available:
        duration_text = f"{format_integer(hours_value)}时{minutes_value}分"
        duration_size = _fit_font(canvas, duration_text, (24, 22, 20, 18, 16), 105, "secondary")
        canvas.text((300, 112), duration_text, duration_size, WHITE, "secondary", "rs")
    else:
        duration_size = _fit_font(canvas, "无法获取", (23, 18, 14), 105, "secondary")
        canvas.text((300, 112), "无法获取", duration_size, WHITE, "secondary", "rs")

    canvas.icon("activity", (19, 122), 14, YELLOW)
    canvas.text((38, 130), "活动洞察", 15, MUTED, "emphasis", "lm")
    canvas.icon("plugin", (162, 122), 14, CYAN)
    canvas.text((181, 130), "常用插件", 15, MUTED, "emphasis", "lm")
    canvas.line(((150, 121), (150, 231)), "#242524", 0.5)

    rows = _activity_rows(snapshot)
    for index, (label, value) in enumerate(rows):
        y = 151 + index * 18
        label_size = _fit_font(canvas, label, (11.5, 11, 10.5), 82, "body")
        canvas.text((21, y), label, label_size, MUTED, "body", "lm")
        size = _fit_font(canvas, value, (11.5, 11, 10.5), 48, "body")
        canvas.text((143, y), value, size, MUTED, "body", "rm")

    plugins = list(snapshot.common_plugins)
    for index in range(5):
        y = 151 + index * 18
        if index < len(plugins):
            plugin = plugins[index]
            plugin_size = _fit_font(canvas, plugin.name, (11.5, 11, 10.5), 94, "body")
            canvas.text((162, y), plugin.name, plugin_size, MUTED, "body", "lm")
            canvas.text(
                (304, y),
                f"{format_integer(plugin.count)}次",
                11.5,
                MUTED,
                "body",
                "rm",
            )
        elif index == len(plugins):
            canvas.text((162, y), "暂无更多", 11.5, DIM, "body", "lm")
    return canvas.finish()


def render_all(
    snapshot: DashboardSnapshot,
    output_directory: Path,
    font_directory: Path,
) -> dict[str, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    fonts = FontBook(font_directory)
    pages = {
        "01-概览-真实数据.png": render_overview(snapshot, fonts),
        "02-周剩余额度-真实数据.png": render_weekly(snapshot, fonts),
        "03-今日消耗-真实数据.png": render_today(snapshot, fonts),
        "04-近30天消耗-真实数据.png": render_last_30_days(snapshot, fonts),
    }
    written: dict[str, Path] = {}
    for name, image in pages.items():
        path = output_directory / name
        image.save(path, format="PNG", optimize=True)
        written[name] = path
    return written
