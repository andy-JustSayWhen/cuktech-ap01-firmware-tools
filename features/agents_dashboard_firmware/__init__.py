"""AP01 AGENTS 看板设备端载荷。"""

from .build import (
    AgentsDashboardFirmwareError,
    ObservationBuildResult,
    build_observation_firmware,
    build_page_registration_payload,
)
from .fallback_assets import (
    FallbackAssetError,
    build_fallback_assets,
)
from .sync_build import (
    CONFIRM_COMPAT_OUTPUT_FILENAME,
    DETAIL_COMPAT_OUTPUT_FILENAME,
    SYNC_OUTPUT_FILENAME,
    SyncFirmwareResult,
    build_sync_firmware,
    build_sync_payload,
)

__all__ = [
    "AgentsDashboardFirmwareError",
    "FallbackAssetError",
    "ObservationBuildResult",
    "build_observation_firmware",
    "build_fallback_assets",
    "build_page_registration_payload",
    "CONFIRM_COMPAT_OUTPUT_FILENAME",
    "DETAIL_COMPAT_OUTPUT_FILENAME",
    "SYNC_OUTPUT_FILENAME",
    "SyncFirmwareResult",
    "build_sync_firmware",
    "build_sync_payload",
]
