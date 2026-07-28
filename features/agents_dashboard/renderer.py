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
    "hero": "Michroma-Regular.ttf",
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


def _sparkline(canvas: Canvas, values: list[int]) -> None:
    if not values:
        return
    left, right = 27.0, 301.0
    top, bottom = 180.0, 224.0
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


def render_overview(snapshot: DashboardSnapshot, fonts: FontBook) -> Image.Image:
    canvas = Canvas(fonts)
    canvas.glow((227, 171, 331, 265), "#9C2200", 22)
    canvas.text((10, 7), "AGENTS 看板", 7, MUTED, "body")

    remaining = snapshot.weekly_remaining_percent
    if remaining is None:
        remaining = 0
    _draw_quality_arc(canvas, (24, 34, 139, 149), -90, 360, remaining, 4.5)
    canvas.text((79, 93), format_integer(remaining), 41, WHITE, "hero", "mm")
    number_bounds = canvas.draw.textbbox(
        (0, 0), format_integer(remaining), font=canvas.fonts.get(41, "hero")
    )
    number_width = (number_bounds[2] - number_bounds[0]) / SCALE
    canvas.text(
        (79 + number_width / 2 + 3, 96),
        "%",
        15,
        WHITE,
        "secondary",
        "lm",
    )
    canvas.text((81, 120), "本周剩余", 7, YELLOW, "emphasis", "mm")

    today = format_token_count(snapshot.today.total_tokens)
    last_30 = format_token_count(snapshot.last_30d_tokens)
    canvas.text((178, 38), "今日消耗", 7, YELLOW, "emphasis")
    _draw_token_pair(canvas, today, 258, 79, 265, (38, 31, 27, 23, 20), 82, 7)
    canvas.text((178, 104), "近30天消耗", 7, ORANGE, "emphasis")
    _draw_token_pair(canvas, last_30, 258, 145, 265, (38, 31, 27, 23, 20), 82, 7)

    canvas.text((16, 170), "近7天消耗", 7, CYAN, "emphasis")
    _sparkline(canvas, [tokens for _, tokens in snapshot.daily_30d[-7:]])
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


def render_weekly(snapshot: DashboardSnapshot, fonts: FontBook) -> Image.Image:
    canvas = Canvas(fonts)
    canvas.glow((240, 168, 330, 257), "#702000", 23)
    canvas.text((10, 7), "周剩余额度", 7, MUTED, "body")

    remaining = snapshot.weekly_remaining_percent or 0
    _draw_gradient_arc(canvas, (10, 28, 164, 170), 155, 230, remaining, 7)
    canvas.text((87, 99), format_integer(remaining), 54, WHITE, "hero", "mm")
    value_width = (
        canvas.draw.textbbox(
            (0, 0),
            format_integer(remaining),
            font=canvas.fonts.get(54, "hero"),
        )[2]
        / SCALE
    )
    canvas.text(
        (87 + value_width / 2 + 2, 103),
        "%",
        18,
        WHITE,
        "secondary",
        "lm",
    )
    canvas.text((87, 128), "本周剩余", 7, MUTED, "body", "mm")

    countdown, reset_time = _countdown(snapshot.weekly_reset_at, snapshot.generated_at)
    canvas.text((227, 43), "下次重置", 7, MUTED, "body")
    countdown_size = _fit_font(
        canvas, countdown, (18, 15, 13), 84, "emphasis"
    )
    canvas.text((227, 60), countdown, countdown_size, YELLOW, "emphasis")
    if reset_time:
        canvas.text((227, 84), reset_time, 7, MUTED, "secondary")
    canvas.draw.rounded_rectangle(
        canvas.rect((226, 104, 308, 124)),
        radius=canvas.s(3),
        outline=CYAN,
        width=canvas.s(1),
    )
    available = (
        "无法获取"
        if snapshot.reset_cards_available is None
        else format_integer(snapshot.reset_cards_available)
    )
    available_text = f"可用重置  {available}"
    available_size = _fit_font(canvas, available_text, (7, 6), 75, "body")
    canvas.text((267, 114), available_text, available_size, CYAN, "body", "mm")

    canvas.line(((10, 146), (308, 146)), "#4A2B08", 0.8)
    cards = list(snapshot.reset_cards[:2])
    if not cards:
        canvas.text(
            (14, 193),
            "当前账号未返回可核验的重置卡数据",
            9,
            DIM,
            "body",
            "lm",
        )
        return canvas.finish()

    for index, card in enumerate(cards):
        y = 173 + index * 35
        canvas.text((14, y), f"重置卡 {index + 1}", 11, WHITE, "secondary", "lm")
        canvas.line(((88, y - 10), (88, y + 10)), YELLOW, 0.8)
        canvas.text((99, y), "剩余", 7, DIM, "body", "lm")
        canvas.text(
            (121, y),
            f"{_remaining_days(card.expires_at, snapshot.generated_at)}天",
            8,
            YELLOW,
            "emphasis",
            "lm",
        )
        canvas.text((165, y), "发放", 7, DIM, "body", "lm")
        canvas.text((188, y), _short_date(card.granted_at), 8, MUTED, "body", "lm")
        canvas.text((238, y), "到期", 7, DIM, "body", "lm")
        canvas.text((261, y), _short_date(card.expires_at), 8, ORANGE, "body", "lm")
        if index == 0 and len(cards) > 1:
            canvas.line(((14, 190), (304, 190)), "#35200B", 0.6)
    return canvas.finish()


def _draw_metric_column(
    canvas: Canvas,
    x: float,
    label: str,
    icon: str,
    icon_color: str,
    display: TokenDisplay,
    mirror: bool = False,
) -> None:
    canvas.icon(icon, (x, 125), 18, icon_color, mirror)
    canvas.text((x + 21, 134), label, 7, MUTED, "body", "lm")
    value_size = _fit_font(canvas, display.value, (30, 24), 82, "secondary")
    canvas.text((x, 169), display.value, value_size, WHITE, "secondary", "ls")
    canvas.text((x, 189), display.unit, 7, MUTED, "body", "ls")


def render_today(snapshot: DashboardSnapshot, fonts: FontBook) -> Image.Image:
    canvas = Canvas(fonts)
    canvas.glow((258, 174, 338, 260), "#7B1C00", 23)
    canvas.text((14, 7), "今日消耗", 7, MUTED, "body")
    canvas.text((14, 25), "总消耗", 7, MUTED, "body")

    total = format_token_count(snapshot.today.total_tokens)
    _draw_token_pair(canvas, total, 144, 92, 153, (56, 48, 45, 42, 36), 134, 9, WHITE, WHITE)

    canvas.line(((240, 22), (240, 100)), "#343535", 0.8)
    canvas.text((258, 21), "请求数", 7, YELLOW, "emphasis")
    request_size = _fit_font(
        canvas,
        format_integer(snapshot.today.request_count),
        (24, 19, 15),
        50,
        "secondary",
    )
    canvas.text(
        (258, 46),
        format_integer(snapshot.today.request_count),
        request_size,
        WHITE,
        "secondary",
        "lm",
    )
    canvas.line(((250, 60), (304, 60)), "#303130", 0.7)
    canvas.text((258, 70), "API成本", 7, ORANGE, "emphasis")
    cost = (
        "无法获取"
        if snapshot.today.api_cost_usd_rounded is None
        else f"${format_integer(snapshot.today.api_cost_usd_rounded)}"
    )
    cost_size = _fit_font(canvas, cost, (16, 13, 11), 52, "secondary")
    canvas.text((258, 91), cost, cost_size, WHITE, "secondary", "lm")

    _draw_metric_column(
        canvas,
        16,
        "新增输入",
        "arrow-circle",
        BLUE,
        format_token_count(snapshot.today.fresh_input_tokens),
        True,
    )
    _draw_metric_column(
        canvas, 119, "输出", "arrow-circle", CYAN, format_token_count(snapshot.today.output_tokens)
    )
    _draw_metric_column(
        canvas, 222, "缓存命中", "cache", YELLOW, format_token_count(snapshot.today.cached_input_tokens)
    )

    canvas.text((15, 211), "缓存命中率", 7, MUTED, "body")
    left, right, y = 15.0, 256.0, 225.0
    canvas.draw.rounded_rectangle(
        canvas.rect((left, y - 3, right, y + 3)),
        radius=canvas.s(3),
        fill=DARK,
    )
    percent = max(0, min(100, snapshot.today.cache_hit_percent))
    completed = (right - left) * percent / 100
    segments = max(1, round(completed))
    for index in range(segments):
        x1 = left + completed * index / segments
        x2 = left + completed * (index + 1) / segments + 0.5
        absolute_percent = percent * (index + 1) / segments
        canvas.draw.rectangle(
            canvas.rect((x1, y - 3, x2, y + 3)),
            fill=quality_color(absolute_percent),
        )
    canvas.text(
        (269, 226),
        f"{percent}%",
        17,
        quality_color(percent),
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
        ("最常用的推理强度", reasoning),
        ("已探索的技能", format_integer(activity.explored_skills)),
        ("使用的技能总数", format_integer(activity.skill_uses)),
        ("任务总数", format_integer(activity.task_count)),
    ]


def render_last_30_days(snapshot: DashboardSnapshot, fonts: FontBook) -> Image.Image:
    canvas = Canvas(fonts)
    canvas.glow((225, 160, 334, 268), "#671800", 25)
    canvas.text((136, 9), "近30天消耗", 7, MUTED, "body")
    canvas.text((23, 38), "累计消耗", 7, MUTED, "body")
    _draw_token_pair(
        canvas,
        format_token_count(snapshot.last_30d_tokens),
        107,
        79,
        115,
        (47, 40, 36, 32, 27, 23, 20),
        100,
        8,
        WHITE,
        WHITE,
    )
    canvas.text((190, 38), "最长任务", 7, MUTED, "body")
    hours_value, minutes_value = divmod(snapshot.activity.longest_task_minutes, 60)
    duration = f"{format_integer(hours_value)}时{minutes_value}分"
    duration_size = _fit_font(canvas, duration, (32, 27, 23), 119, "secondary")
    canvas.text((304, 79), duration, duration_size, WHITE, "secondary", "rs")

    canvas.icon("activity", (21, 98), 11, YELLOW)
    canvas.text((36, 104), "活动洞察", 7, MUTED, "body", "lm")
    canvas.icon("plugin", (178, 98), 11, CYAN)
    canvas.text((193, 104), "常用插件", 7, MUTED, "body", "lm")
    canvas.line(((161, 96), (161, 228)), "#2D2E2D", 0.6)

    rows = _activity_rows(snapshot)
    for index, (label, value) in enumerate(rows):
        y = 126 + index * 23
        canvas.text((23, y), label, 7, MUTED, "body", "lm")
        size = _fit_font(canvas, value, (7.5, 6.5), 68, "body")
        canvas.text((145, y), value, size, MUTED, "body", "rm")

    plugins = list(snapshot.common_plugins)
    for index in range(5):
        y = 126 + index * 23
        if index < len(plugins):
            plugin = plugins[index]
            canvas.text((178, y), plugin.name, 7, MUTED, "body", "lm")
            canvas.text(
                (303, y),
                f"{format_integer(plugin.count)}次",
                7,
                MUTED,
                "body",
                "rm",
            )
        elif index == len(plugins):
            canvas.text((178, y), "暂无更多", 7, DIM, "body", "lm")
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
