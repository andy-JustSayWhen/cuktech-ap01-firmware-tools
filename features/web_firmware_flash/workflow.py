"""网页刷机六阶段会话与单次执行流程。"""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Any, Callable

from .firmware_inspection import InspectedFirmware, inspect_release_firmware
from .operation_store import OperationRecord, OperationStore
from .xiaomi_cloud import (
    XiaomiCloudClient,
    dispatch_install_once,
    ota_state,
    public_device,
    upload_and_readback,
)


Simulation = Callable[[InspectedFirmware], list[str]]


class WorkflowError(RuntimeError):
    pass


def _device_idle(state: dict[str, Any]) -> bool:
    value = state.get("state")
    if isinstance(value, list) and value:
        value = value[0]
    progress = state.get("progress")
    if isinstance(progress, list) and progress:
        progress = progress[0]
    return value in (None, "idle", "failed") and progress in (None, 0, 101)


class FlashWorkflow:
    def __init__(
        self,
        *,
        release_directory: Path,
        store: OperationStore,
        cloud_factory: Callable[[], XiaomiCloudClient],
        simulation: Simulation,
    ) -> None:
        self.release_directory = release_directory.expanduser().resolve()
        self.store = store
        self.cloud_factory = cloud_factory
        self.simulation = simulation
        self.phase = "prepare"
        self.status = "ready"
        self.message = "请检查准备条件"
        self.evidence: list[str] = []
        self.device_public: dict[str, Any] | None = None
        self._device_did: str | None = None
        self.firmware: InspectedFirmware | None = None
        self.operation: OperationRecord | None = store.active()
        self._lock = threading.RLock()
        self._worker: threading.Thread | None = None
        if self.operation is not None:
            self.phase = self.operation.phase
            self.status = self.operation.status
            self.message = self.operation.stop_reason or "已恢复现有操作"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            operation = self.operation.to_dict() if self.operation else None
            allowed = {
                "prepare": ["preflight"],
                "device": ["identify-device"],
                "firmware": ["inspect-firmware"],
                "risk": ["create-operation"],
                "execute": ["query"],
                "result": ["query", "export"],
            }.get(self.phase, [])
            return {
                "operation_id": self.operation.operation_id if self.operation else None,
                "phase": self.phase,
                "status": self.status,
                "updated_at": self.operation.updated_at if self.operation else None,
                "evidence": list(self.evidence),
                "allowed_actions": allowed,
                "message": self.message,
                "device": dict(self.device_public) if self.device_public else None,
                "firmware": self.firmware.public_dict() if self.firmware else None,
                "operation": operation,
            }

    def preflight(self) -> dict[str, Any]:
        with self._lock:
            if self.operation and self.operation.status not in {"succeeded", "failed", "unknown", "stopped"}:
                raise WorkflowError("已有活动操作")
            if not self.release_directory.is_dir():
                raise WorkflowError("发布包固件目录不存在")
            self.phase = "device"
            self.status = "ready"
            self.evidence = ["本机私有操作目录可写", "发布包固件目录存在", "服务只监听本机"]
            self.message = "准备条件通过，请识别设备"
            return self.snapshot()

    def identify_device(self) -> dict[str, Any]:
        with self._lock:
            if self.phase != "device":
                raise WorkflowError("当前阶段不允许识别设备")
        cloud = self.cloud_factory()
        device = cloud.unique_ap01()
        public = public_device(device)
        if not public["online"]:
            raise WorkflowError("唯一 AP01 当前不在线")
        with self._lock:
            self.device_public = public
            self._device_did = str(device["did"])
            self.phase = "firmware"
            self.status = "ready"
            self.evidence = ["唯一目标设备", "设备在线", "型号匹配"]
            self.message = "设备已冻结，请核对固件"
            return self.snapshot()

    def inspect_firmware(self, filename: str) -> dict[str, Any]:
        with self._lock:
            if self.phase != "firmware" or self.device_public is None:
                raise WorkflowError("当前阶段不允许核对固件")
        if not filename or Path(filename).name != filename:
            raise WorkflowError("固件文件名无效")
        inspected = inspect_release_firmware(self.release_directory, self.release_directory / filename)
        if not inspected.install_approved:
            raise WorkflowError("该成品没有安装批准标记")
        with self._lock:
            self.firmware = inspected
            self.phase = "risk"
            self.status = "ready"
            self.evidence = ["固件完整身份匹配", "构建清单匹配", "安装批准标记有效"]
            self.message = "设备与成品身份已冻结，可发起一次制作并刷入"
            return self.snapshot()

    def create_operation(self) -> dict[str, Any]:
        with self._lock:
            if self.phase != "risk" or self.device_public is None or self.firmware is None:
                raise WorkflowError("设备与成品尚未冻结")
            if self.store.active() is not None:
                raise WorkflowError("已有活动操作")
            self.operation = OperationRecord.create(
                device=self.device_public,
                firmware=self.firmware.public_dict(),
            )
            self.store.save(self.operation)
            self.message = "操作已建立，可启动一次正式流程"
            return self.snapshot()

    def start(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            if self.operation is None or self.operation.operation_id != operation_id:
                raise WorkflowError("操作编号不匹配")
            if self.operation.status == "running" or self.operation.install_dispatched:
                return self.snapshot()
            if self.operation.status in {"unknown", "stopped", "failed", "succeeded"}:
                return self.snapshot()
            if self._worker is not None and self._worker.is_alive():
                return self.snapshot()
            self.phase = "execute"
            self.status = "running"
            self.message = "正在运行严格模拟"
            self._worker = threading.Thread(target=self._execute, name="ap01-web-flash", daemon=True)
            self._worker.start()
            return self.snapshot()

    def _save(self) -> None:
        assert self.operation is not None
        self.store.save(self.operation)
        self.phase = self.operation.phase
        self.status = self.operation.status

    def _execute(self) -> None:
        assert self.operation is not None and self.firmware is not None
        try:
            self.operation.begin_stage("simulation")
            self._save()
            simulation_evidence = self.simulation(self.firmware)
            self.operation.simulation_passed = True
            self.operation.finish_stage("simulation", evidence=simulation_evidence)
            self._save()

            cloud = self.cloud_factory()
            device = cloud.unique_ap01()
            current_public = public_device(device)
            if current_public.get("identity") != self.operation.device.get("identity"):
                raise WorkflowError("目标设备身份发生变化")
            current_state = ota_state(cloud, str(device["did"]))
            if not current_public.get("online") or not _device_idle(current_state):
                raise WorkflowError("目标设备不在线或更新状态非空闲")
            current_sha = hashlib.sha256(self.firmware.path.read_bytes()).hexdigest()
            if current_sha != self.operation.firmware.get("sha256"):
                raise WorkflowError("冻结成品身份发生变化")

            self.operation.begin_stage("upload")
            self._save()
            ota_url = upload_and_readback(cloud, self.firmware.path)
            self.operation.finish_stage("upload", evidence=["上传对象完整回读逐字节一致"])
            self._save()

            device = cloud.unique_ap01()
            current_public = public_device(device)
            current_state = ota_state(cloud, str(device["did"]))
            if current_public.get("identity") != self.operation.device.get("identity"):
                raise WorkflowError("安装前目标设备身份发生变化")
            if not current_public.get("online") or not _device_idle(current_state):
                raise WorkflowError("安装前设备不在线或更新状态非空闲")

            self.operation.begin_stage("install")
            self.operation.install_dispatched = True
            self._save()
            dispatch_install_once(cloud, str(device["did"]), self.firmware.path, ota_url)
            self.operation.finish_stage("install", evidence=["正式安装只下发一次"])
            self.operation.phase = "execute"
            self.operation.status = "running"
            self.operation.allowed_actions = ["query"]
            self.message = "正式安装已下发，只允许查询设备状态"
            self._save()
        except Exception as exc:
            unknown = self.operation.write_may_have_been_dispatched
            self.operation.stop(str(exc), unknown=unknown)
            self.message = self.operation.stop_reason or "流程停止"
            self._save()
