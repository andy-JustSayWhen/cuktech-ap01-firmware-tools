"""严格模拟通过后的单次自动安装状态合同。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


SimulationStatus = Literal["pending", "passed", "failed"]
DirectInstallAction = Literal[
    "await-operation-start",
    "run-simulation",
    "upload-and-readback",
    "install-once",
    "query-only",
    "stop",
]


@dataclass(frozen=True)
class DirectInstallSnapshot:
    """一次绑定设备与成品的“制作并刷入”操作快照。"""

    operation_started: bool
    device_identity_frozen: bool
    firmware_identity_frozen: bool
    device_online: bool
    device_idle: bool
    simulation_status: SimulationStatus
    upload_readback_matches: bool | None = None
    install_dispatched: bool = False
    write_state_unknown: bool = False


@dataclass(frozen=True)
class DirectInstallDecision:
    action: DirectInstallAction
    reason: str
    ask_user: bool = False


def decide_direct_install_action(
    snapshot: DirectInstallSnapshot,
) -> DirectInstallDecision:
    """返回下一项自动动作；本合同从不产生二次确认。"""

    if not snapshot.operation_started:
        return DirectInstallDecision(
            "await-operation-start",
            "尚未发起本次制作并刷入操作",
        )
    if snapshot.write_state_unknown:
        return DirectInstallDecision(
            "query-only",
            "已有写入可能下发，只允许查询现状",
        )
    if snapshot.install_dispatched:
        return DirectInstallDecision(
            "query-only",
            "正式安装已经下发一次，只允许查询现状",
        )
    if not snapshot.device_identity_frozen:
        return DirectInstallDecision("stop", "目标设备身份没有冻结")
    if not snapshot.firmware_identity_frozen:
        return DirectInstallDecision("stop", "目标成品身份没有冻结")
    if not snapshot.device_online:
        return DirectInstallDecision("stop", "目标设备当前不在线")
    if not snapshot.device_idle:
        return DirectInstallDecision("stop", "目标设备当前不是更新空闲状态")
    if snapshot.simulation_status == "failed":
        return DirectInstallDecision("stop", "严格刷前交互模拟失败")
    if snapshot.simulation_status == "pending":
        return DirectInstallDecision(
            "run-simulation",
            "先运行与冻结成品绑定的严格刷前交互模拟",
        )
    if snapshot.upload_readback_matches is None:
        return DirectInstallDecision(
            "upload-and-readback",
            "模拟通过，自动上传并完整回读",
        )
    if not snapshot.upload_readback_matches:
        return DirectInstallDecision("stop", "上传对象完整回读不一致")
    return DirectInstallDecision(
        "install-once",
        "模拟与客观门禁全部通过，自动下发一次正式安装",
    )
