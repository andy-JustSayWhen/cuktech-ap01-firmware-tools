"""AP01 AGENTS 看板设备端载荷。"""

from .build import (
    AgentsDashboardFirmwareError,
    build_page_registration_payload,
)
from .fallback_assets import (
    FallbackAssetError,
    build_fallback_assets,
)

__all__ = [
    "AgentsDashboardFirmwareError",
    "FallbackAssetError",
    "build_fallback_assets",
    "build_page_registration_payload",
]
