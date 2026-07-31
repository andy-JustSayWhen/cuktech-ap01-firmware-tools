"""AP01 网页刷机功能公开入口。"""

from .install_policy import (
    DirectInstallDecision,
    DirectInstallSnapshot,
    decide_direct_install_action,
)

__all__ = [
    "DirectInstallDecision",
    "DirectInstallSnapshot",
    "decide_direct_install_action",
]
