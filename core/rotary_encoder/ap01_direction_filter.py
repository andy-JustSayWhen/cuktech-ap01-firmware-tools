"""AP01 1.0.2_0031 中途反向边沿过滤合同。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EncoderDirectionFilterContract:
    """描述一个必须由固定工具逐字节复现的旋钮修改区间。"""

    name: str
    section_name: str
    offset: int
    runtime_address: int
    return_runtime_address: int
    expected_before: bytes
    expected_replacement: bytes


AP01_DIRECTION_FILTER = EncoderDirectionFilterContract(
    name="中途反向边沿过滤",
    section_name=".encoder_direction_filter",
    offset=0x108E20,
    runtime_address=0xA0107E20,
    return_runtime_address=0xA0107CBC,
    expected_before=bytes.fromhex("a14d"),
    expected_replacement=bytes.fromhex("71bd"),
)

PRESERVED_ENCODER_LOG_RANGES = (
    (0x108E30, 0x108E52, "旋钮顺时针方向变化日志调用"),
    (0x108F22, 0x108F40, "旋钮逆时针方向变化日志调用"),
    (0x523ED8, 0x523F4C, "旋钮方向变化日志正文"),
)
