"""AGENTS 看板运行数据目录。"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_FONT_DIRECTORY = PROJECT_ROOT / "fonts"


def default_output_directory(
    *, platform: str | None = None, home: Path | None = None
) -> Path:
    selected_platform = sys.platform if platform is None else platform
    selected_home = Path.home() if home is None else home
    if selected_platform == "darwin":
        return (
            selected_home
            / "Library"
            / "Application Support"
            / "Cuktech"
            / "AP01"
            / "agents-dashboard"
        )
    return PROJECT_ROOT / "artifacts" / "agents-dashboard"


def default_cache_directory(
    *, platform: str | None = None, home: Path | None = None
) -> Path:
    selected_platform = sys.platform if platform is None else platform
    selected_home = Path.home() if home is None else home
    if selected_platform == "darwin":
        return (
            selected_home
            / "Library"
            / "Caches"
            / "Cuktech"
            / "AP01"
            / "agents-dashboard"
        )
    return selected_home / ".cuktech" / "AP01" / "agents-dashboard-cache"


def default_font_directory(
    *, platform: str | None = None, home: Path | None = None
) -> Path:
    selected_platform = sys.platform if platform is None else platform
    selected_home = Path.home() if home is None else home
    if selected_platform == "darwin":
        return (
            selected_home
            / "Library"
            / "Application Support"
            / "Cuktech"
            / "AP01"
            / "fonts"
        )
    return selected_home / ".cuktech" / "AP01" / "fonts"


DEFAULT_OUTPUT_DIRECTORY = default_output_directory()
DEFAULT_CACHE_DIRECTORY = default_cache_directory()
DEFAULT_FONT_DIRECTORY = default_font_directory()
