"""生成并一次性提供用于 AP01 真机验收的可控单帧结果包。"""

from __future__ import annotations

import argparse
import hashlib
import io
import ipaddress
import json
import os
import tempfile
import threading
import time
from pathlib import Path

from PIL import Image

from .result_package import decode_package, encode_package


PLAN_SCHEMA_VERSION = 1
FAULT_TYPE = "single-frame-overview"
MAX_VALID_SECONDS = 15 * 60


class ControlledFaultError(RuntimeError):
    """可控损坏包或一次性授权记录不符合固定规则。"""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _single_frame(page: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(page)) as opened:
            first = opened.convert("RGB")
    except OSError as error:
        raise ControlledFaultError("概览页无法解码") from error
    output = io.BytesIO()
    first.save(
        output,
        format="GIF",
        duration=1000,
        loop=0,
        disposal=2,
    )
    payload = output.getvalue()
    try:
        with Image.open(io.BytesIO(payload)) as selected:
            if selected.size != (320, 240) or selected.n_frames != 1:
                raise ControlledFaultError("测试概览页必须恰好只有一帧")
    except OSError as error:
        raise ControlledFaultError("测试概览页无法复读") from error
    if not payload.startswith(b"GIF89a") or not payload.endswith(b"\x3b"):
        raise ControlledFaultError("测试概览页缺少固定动图头或结尾")
    return payload


def build_single_frame_package(normal_package: bytes, *, now: int) -> bytes:
    decoded = decode_package(normal_package)
    if decoded.generation >= 0x7FFFFFFF:
        raise ControlledFaultError("正常结果代号已达到上限")
    pages = (_single_frame(decoded.pages[0]), *decoded.pages[1:])
    package = encode_package(
        pages,
        generation=decoded.generation + 1,
        generated_at=now,
    )
    verified = decode_package(package)
    if verified.pages[1:] != decoded.pages[1:]:
        raise ControlledFaultError("测试包意外修改了其他三页")
    return package


def _fault_package_path(plan_path: Path) -> Path:
    return plan_path.with_name(f"{plan_path.stem}.single-frame.apag")


def _consumed_plan_path(plan_path: Path) -> Path:
    return plan_path.with_name(f"{plan_path.name}.consumed")


def _atomic_write(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.",
        dir=path.parent,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


def arm_single_frame_fault(
    normal_package_path: Path,
    plan_path: Path,
    *,
    target_ip: str,
    valid_seconds: int,
    now: int | None = None,
) -> dict[str, object]:
    try:
        address = ipaddress.ip_address(target_ip)
    except ValueError as error:
        raise ControlledFaultError("目标设备地址无效") from error
    if address.version != 4 or not address.is_private:
        raise ControlledFaultError("目标设备必须使用局域网 IPv4 地址")
    if not 1 <= valid_seconds <= MAX_VALID_SECONDS:
        raise ControlledFaultError("授权有效期必须在 1 到 900 秒之间")
    selected_plan = plan_path.expanduser().resolve()
    fault_path = _fault_package_path(selected_plan)
    consumed_path = _consumed_plan_path(selected_plan)
    if selected_plan.exists() or fault_path.exists() or consumed_path.exists():
        raise ControlledFaultError("授权记录、测试包或已消耗记录已经存在")
    normal_path = normal_package_path.expanduser().resolve(strict=True)
    normal = normal_path.read_bytes()
    decode_package(normal)
    created_at = int(time.time()) if now is None else now
    fault = build_single_frame_package(normal, now=created_at)
    document: dict[str, object] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "fault_type": FAULT_TYPE,
        "target_ip": str(address),
        "source_package_sha256": _sha256(normal),
        "fault_package_sha256": _sha256(fault),
        "created_at": created_at,
        "expires_at": created_at + valid_seconds,
        "remaining_requests": 1,
        "fault_package_name": fault_path.name,
    }
    _atomic_write(fault_path, fault, 0o400)
    try:
        _atomic_write(
            selected_plan,
            json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            ),
            0o400,
        )
    except Exception:
        fault_path.unlink(missing_ok=True)
        raise
    return document


class ControlledFaultGate:
    def __init__(self, plan_path: Path | None) -> None:
        self.plan_path = plan_path.expanduser().resolve() if plan_path else None
        self._lock = threading.Lock()
        self.last_trigger: float | None = None

    def _read_plan(self) -> dict[str, object] | None:
        if self.plan_path is None or not self.plan_path.is_file():
            return None
        try:
            document = json.loads(self.plan_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return document if isinstance(document, dict) else None

    def consume(
        self,
        client_ip: str,
        normal_package: bytes,
        *,
        now: int | None = None,
    ) -> bytes | None:
        with self._lock:
            return self._consume_locked(client_ip, normal_package, now=now)

    def _consume_locked(
        self,
        client_ip: str,
        normal_package: bytes,
        *,
        now: int | None,
    ) -> bytes | None:
        document = self._read_plan()
        if document is None or self.plan_path is None:
            return None
        current_time = int(time.time()) if now is None else now
        required = {
            "schema_version": PLAN_SCHEMA_VERSION,
            "fault_type": FAULT_TYPE,
            "target_ip": client_ip,
            "source_package_sha256": _sha256(normal_package),
            "remaining_requests": 1,
        }
        if any(document.get(key) != value for key, value in required.items()):
            return None
        created_at = document.get("created_at")
        expires_at = document.get("expires_at")
        if (
            not isinstance(created_at, int)
            or not isinstance(expires_at, int)
            or expires_at <= created_at
            or expires_at - created_at > MAX_VALID_SECONDS
            or current_time > expires_at
        ):
            return None
        fault_name = document.get("fault_package_name")
        if not isinstance(fault_name, str) or Path(fault_name).name != fault_name:
            return None
        fault_path = self.plan_path.with_name(fault_name)
        try:
            fault = fault_path.read_bytes()
        except OSError:
            return None
        if document.get("fault_package_sha256") != _sha256(fault):
            return None
        try:
            decoded_normal = decode_package(normal_package)
            decoded_fault = decode_package(fault)
            with Image.open(io.BytesIO(decoded_fault.pages[0])) as overview:
                valid_fault = overview.size == (320, 240) and overview.n_frames == 1
        except (OSError, RuntimeError):
            return None
        if (
            not valid_fault
            or decoded_fault.pages[1:] != decoded_normal.pages[1:]
            or decoded_fault.generation != decoded_normal.generation + 1
        ):
            return None
        consumed_path = _consumed_plan_path(self.plan_path)
        if consumed_path.exists():
            return None
        try:
            os.rename(self.plan_path, consumed_path)
        except OSError:
            return None
        self.last_trigger = time.time() if now is None else float(now)
        return fault

    def health(self) -> dict[str, object]:
        if self.plan_path is None:
            return {
                "controlled_fault_enabled": False,
                "controlled_fault_armed": False,
                "controlled_fault_consumed": False,
                "controlled_fault_last_trigger": None,
            }
        consumed_path = _consumed_plan_path(self.plan_path)
        consumed = consumed_path.is_file()
        document = self._read_plan()
        expires_at = document.get("expires_at") if document else None
        armed = (
            not consumed
            and document is not None
            and document.get("schema_version") == PLAN_SCHEMA_VERSION
            and document.get("fault_type") == FAULT_TYPE
            and document.get("remaining_requests") == 1
            and isinstance(expires_at, int)
            and time.time() <= expires_at
        )
        last_trigger = self.last_trigger
        if consumed and last_trigger is None:
            try:
                last_trigger = consumed_path.stat().st_mtime
            except OSError:
                pass
        return {
            "controlled_fault_enabled": True,
            "controlled_fault_armed": armed,
            "controlled_fault_consumed": consumed,
            "controlled_fault_last_trigger": last_trigger,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normal-package", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--target-ip", required=True)
    parser.add_argument("--valid-seconds", type=int, default=MAX_VALID_SECONDS)
    arguments = parser.parse_args(argv)
    document = arm_single_frame_fault(
        arguments.normal_package,
        arguments.plan,
        target_ip=arguments.target_ip,
        valid_seconds=arguments.valid_seconds,
    )
    print(json.dumps(document, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
