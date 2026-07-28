"""AP01 一级页面注册与导航证据门禁。"""

from .inspection import (
    PrimaryPageNavigationError,
    decode_jal_target,
    inspect_primary_page_navigation,
)

__all__ = [
    "PrimaryPageNavigationError",
    "decode_jal_target",
    "inspect_primary_page_navigation",
]
