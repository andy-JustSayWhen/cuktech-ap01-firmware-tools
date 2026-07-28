"""AP01 固件载荷空间生成与验证。"""

from .optimizer import (
    GIF_DATA_OFFSET,
    GIF_SIZE_OFFSET,
    OPTIMIZED_SIZE,
    ORIGINAL_SIZE,
    ORIGINAL_SHA256,
    PAYLOAD_CAPACITY,
    PAYLOAD_END,
    PAYLOAD_START,
    FirmwarePayloadSpaceError,
    inspect_payload_space,
)

__all__ = [
    "PAYLOAD_CAPACITY",
    "PAYLOAD_END",
    "PAYLOAD_START",
    "GIF_DATA_OFFSET",
    "GIF_SIZE_OFFSET",
    "OPTIMIZED_SIZE",
    "ORIGINAL_SIZE",
    "ORIGINAL_SHA256",
    "FirmwarePayloadSpaceError",
    "inspect_payload_space",
]
