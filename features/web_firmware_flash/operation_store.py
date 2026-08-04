"""网页刷机操作的原子记录与重启恢复。"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = frozenset({"succeeded", "failed", "unknown", "stopped"})
WRITE_PHASES = frozenset({"upload", "download", "install", "offline", "online", "acceptance"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OperationRecord:
    operation_id: str
    phase: str = "risk"
    status: str = "ready"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    device: dict[str, Any] = field(default_factory=dict)
    firmware: dict[str, Any] = field(default_factory=dict)
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)
    simulation_passed: bool = False
    install_dispatched: bool = False
    write_may_have_been_dispatched: bool = False
    stop_reason: str | None = None
    allowed_actions: list[str] = field(default_factory=lambda: ["start"])

    @classmethod
    def create(cls, *, device: dict[str, Any], firmware: dict[str, Any]) -> "OperationRecord":
        return cls(
            operation_id=secrets.token_urlsafe(24),
            device=dict(device),
            firmware=dict(firmware),
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "OperationRecord":
        permitted = cls.__dataclass_fields__.keys()
        return cls(**{key: value[key] for key in permitted if key in value})

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "phase": self.phase,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "device": dict(self.device),
            "firmware": dict(self.firmware),
            "stages": {key: dict(value) for key, value in self.stages.items()},
            "simulation_passed": self.simulation_passed,
            "install_dispatched": self.install_dispatched,
            "write_may_have_been_dispatched": self.write_may_have_been_dispatched,
            "stop_reason": self.stop_reason,
            "allowed_actions": list(self.allowed_actions),
        }

    def begin_stage(self, stage: str) -> None:
        self.phase = "execute"
        self.status = "running"
        self.updated_at = utc_now()
        self.stages[stage] = {
            "status": "running",
            "started_at": self.updated_at,
            "ended_at": None,
            "evidence": [],
        }
        if stage in WRITE_PHASES:
            self.write_may_have_been_dispatched = True
        self.allowed_actions = ["query"]

    def finish_stage(self, stage: str, *, evidence: list[str] | None = None) -> None:
        if stage not in self.stages:
            raise ValueError(f"阶段尚未开始：{stage}")
        self.updated_at = utc_now()
        self.stages[stage].update(
            status="succeeded",
            ended_at=self.updated_at,
            evidence=list(evidence or []),
        )

    def stop(self, reason: str, *, unknown: bool = False) -> None:
        self.updated_at = utc_now()
        self.phase = "result"
        self.status = "unknown" if unknown else "stopped"
        self.stop_reason = reason
        self.allowed_actions = ["query", "export"]


class OperationStore:
    """只在私有目录中保存不含凭据的操作记录。"""

    def __init__(self, directory: Path) -> None:
        self.directory = directory.expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)

    def _path(self, operation_id: str) -> Path:
        if not operation_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in operation_id):
            raise ValueError("操作编号格式无效")
        return self.directory / f"{operation_id}.json"

    def save(self, record: OperationRecord) -> None:
        destination = self._path(record.operation_id)
        payload = json.dumps(record.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="xb", dir=self.directory, prefix=".operation-", suffix=".part", delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                os.chmod(temporary_path, 0o600)
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, destination)
            temporary_path = None
            destination.chmod(0o600)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def load(self, operation_id: str) -> OperationRecord:
        payload = json.loads(self._path(operation_id).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("操作记录不是对象")
        record = OperationRecord.from_dict(payload)
        if record.operation_id != operation_id:
            raise ValueError("操作记录编号不匹配")
        return record

    def recover(self, operation_id: str) -> OperationRecord:
        record = self.load(operation_id)
        if record.status == "running" and record.write_may_have_been_dispatched:
            record.stop("服务在可能写入后重新启动，只允许查询设备现状", unknown=True)
            self.save(record)
        return record

    def active(self) -> OperationRecord | None:
        active: list[OperationRecord] = []
        for path in self.directory.glob("*.json"):
            try:
                record = self.recover(path.stem)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if record.status not in TERMINAL_STATUSES:
                active.append(record)
        if len(active) > 1:
            raise RuntimeError("发现多个活动写入操作，已停止创建新操作")
        return active[0] if active else None
