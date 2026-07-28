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
    PET_OVERLAY_OUTPUT_FILENAME,
    STOCK_CALLCHAIN_OUTPUT_FILENAME,
    STOCK_DISPATCH_OUTPUT_FILENAME,
    STOCK_ENTER_GATE_OUTPUT_FILENAME,
    STOCK_LOCAL_BRANCHES_OUTPUT_FILENAME,
    STOCK_PET_REUSE_OUTPUT_FILENAME,
    SYNC_OUTPUT_FILENAME,
    SyncFirmwareResult,
    build_stock_callchain_firmware,
    build_stock_enter_gate_firmware,
    build_stock_local_branches_firmware,
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
    "PET_OVERLAY_OUTPUT_FILENAME",
    "STOCK_CALLCHAIN_OUTPUT_FILENAME",
    "STOCK_DISPATCH_OUTPUT_FILENAME",
    "STOCK_ENTER_GATE_OUTPUT_FILENAME",
    "STOCK_LOCAL_BRANCHES_OUTPUT_FILENAME",
    "STOCK_PET_REUSE_OUTPUT_FILENAME",
    "SYNC_OUTPUT_FILENAME",
    "SyncFirmwareResult",
    "build_stock_callchain_firmware",
    "build_stock_enter_gate_firmware",
    "build_stock_local_branches_firmware",
    "build_sync_firmware",
    "build_sync_payload",
]
