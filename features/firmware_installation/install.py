"""Install a verified AP01 firmware through Xiaomi Cloud OTA."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import requests

from features.official_firmware_source.xiaomi_cloud import MODEL as AP01_MODEL


OTA_CDN_HOST = "iot-ota-cdn.io.mi.com"
OTA_START_GRACE_SECONDS = 15


class FirmwareInstallError(RuntimeError):
    """AP01 firmware upload, verification, or installation failed."""


class XiaomiCloudProtocol(Protocol):
    def devices(self) -> list[dict[str, Any]]: ...

    def request(self, path: str, data: Any) -> dict[str, Any]: ...

    def rpc(self, did: str, method: str, params: Any = None) -> dict[str, Any]: ...


@dataclass(frozen=True)
class FileFingerprint:
    size: int
    md5: str
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {"size": self.size, "md5": self.md5, "sha256": self.sha256}


@dataclass(frozen=True)
class OtaUploadResult:
    url: str
    fds_device: dict[str, Any]
    local: FileFingerprint
    readback: FileFingerprint

    def to_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "fds_device": self.fds_device,
            "local": self.local.to_dict(),
            "readback": self.readback.to_dict(),
            "byte_identical": self.local == self.readback,
        }


@dataclass(frozen=True)
class InstallationResult:
    accepted_response: dict[str, Any]
    final_status: dict[str, Any]
    saw_install_stage: bool
    reboot_observed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted_response": self.accepted_response,
            "final_status": self.final_status,
            "saw_install_stage": self.saw_install_stage,
            "reboot_observed": self.reboot_observed,
        }


def fingerprint_bytes(payload: bytes) -> FileFingerprint:
    return FileFingerprint(
        size=len(payload),
        md5=hashlib.md5(payload).hexdigest(),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def fingerprint_file(path: Path) -> FileFingerprint:
    return fingerprint_bytes(path.read_bytes())


def require_ap01_firmware(path: Path) -> Path:
    selected = path.expanduser().resolve()
    if not selected.is_file():
        raise FirmwareInstallError(f"固件不存在：{selected}")
    if selected.read_bytes()[:4] != b"BFNP":
        raise FirmwareInstallError("固件不是 AP01 BFNP 文件")
    return selected


def choose_fds_device(
    cloud: XiaomiCloudProtocol,
    *,
    did: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    if bool(did) != bool(model):
        raise FirmwareInstallError("FDS DID 和 FDS model 必须同时提供")
    if did and model:
        return {"did": str(did), "model": str(model)}

    candidates = [
        device
        for device in cloud.devices()
        if str(device.get("model", "")).startswith(("lumi.gateway.", "xiaomi.gateway."))
    ]
    if not candidates:
        raise FirmwareInstallError(
            "账号中没有找到可用于 FDS 上传的网关设备。AP01 自身不能作为 FDS 上传设备。"
        )
    return candidates[0]


def select_unique_ap01(cloud: XiaomiCloudProtocol) -> dict[str, Any]:
    candidates = [
        device for device in cloud.devices() if device.get("model") == AP01_MODEL
    ]
    if not candidates:
        raise FirmwareInstallError("扫码账号内没有找到 AP01")
    if len(candidates) > 1:
        names = ", ".join(str(item.get("name") or item.get("did")) for item in candidates)
        raise FirmwareInstallError(f"账号内有多个 AP01，不能自动选择：{names}")
    return candidates[0]


def _cdn_url_from_fds_url(fds_url: str) -> str:
    parsed = urlsplit(fds_url)
    if parsed.scheme != "https":
        raise FirmwareInstallError("FDS 下载地址不是 HTTPS")
    return urlunsplit(
        (parsed.scheme, OTA_CDN_HOST, parsed.path, parsed.query, parsed.fragment)
    )


def _download_url(url: str, *, timeout: int = 180, verify: bool = True) -> bytes:
    try:
        response = requests.get(url, timeout=timeout, verify=verify)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FirmwareInstallError(f"OTA URL 回读失败：{exc}") from exc
    return response.content


def verify_existing_ota_url(
    firmware: Path,
    url: str,
    *,
    timeout: int = 180,
    insecure: bool = False,
) -> OtaUploadResult:
    selected = require_ap01_firmware(firmware)
    local_payload = selected.read_bytes()
    readback_payload = _download_url(url, timeout=timeout, verify=not insecure)
    local = fingerprint_bytes(local_payload)
    readback = fingerprint_bytes(readback_payload)
    if local_payload != readback_payload:
        raise FirmwareInstallError(
            f"OTA URL 回读文件与本机固件不一致：本机 {local.to_dict()}，回读 {readback.to_dict()}"
        )
    return OtaUploadResult(
        url=url,
        fds_device={},
        local=local,
        readback=readback,
    )


def upload_and_verify_firmware(
    cloud: XiaomiCloudProtocol,
    firmware: Path,
    *,
    fds_did: str | None = None,
    fds_model: str | None = None,
    timeout: int = 180,
) -> OtaUploadResult:
    selected = require_ap01_firmware(firmware)
    gateway = choose_fds_device(cloud, did=fds_did, model=fds_model)
    prepared = cloud.request(
        "home/genpresignedurl",
        {"did": str(gateway["did"]), "model": str(gateway["model"]), "suffix": "bin"},
    )
    upload = (prepared.get("result") or {}).get("bin") or {}
    if not upload.get("ok") or not upload.get("url") or not upload.get("obj_name"):
        raise FirmwareInstallError(
            "Xiaomi FDS 预签名失败；传入的 DID/model 必须属于具备 FDS 能力的网关设备"
        )

    try:
        with selected.open("rb") as stream:
            put_response = requests.put(str(upload["url"]), data=stream, timeout=timeout)
        put_response.raise_for_status()
    except requests.RequestException as exc:
        raise FirmwareInstallError(f"FDS 上传失败：{exc}") from exc

    fetched = cloud.request("home/getfileurl", {"obj_name": upload["obj_name"]})
    result = fetched.get("result") or {}
    if not result.get("ok") or not result.get("url"):
        raise FirmwareInstallError("Xiaomi FDS 下载签名失败")

    ota_url = _cdn_url_from_fds_url(str(result["url"]))
    local_payload = selected.read_bytes()
    readback_payload = _download_url(ota_url, timeout=timeout)
    if local_payload != readback_payload:
        local = fingerprint_bytes(local_payload)
        readback = fingerprint_bytes(readback_payload)
        raise FirmwareInstallError(
            f"上传后回读文件与本机固件不一致：本机 {local.to_dict()}，回读 {readback.to_dict()}"
        )
    return OtaUploadResult(
        url=ota_url,
        fds_device={"did": str(gateway["did"]), "model": str(gateway["model"])},
        local=fingerprint_bytes(local_payload),
        readback=fingerprint_bytes(readback_payload),
    )


def rpc_result(response: dict[str, Any]) -> Any:
    if response.get("code") != 0:
        return None
    return response.get("result")


def query_ap01_update_status(
    cloud: XiaomiCloudProtocol,
    *,
    did: str | None = None,
) -> dict[str, Any]:
    device = {"did": did} if did else select_unique_ap01(cloud)
    selected_did = str(device["did"])
    state = rpc_result(cloud.rpc(selected_did, "miIO.get_ota_state"))
    progress = rpc_result(cloud.rpc(selected_did, "miIO.get_ota_progress"))
    info = rpc_result(cloud.rpc(selected_did, "miIO.info"))
    life = info.get("life") if isinstance(info, dict) else None
    return {
        "did": selected_did,
        "state": state[0] if isinstance(state, list) and state else state,
        "progress": progress[0] if isinstance(progress, list) and progress else progress,
        "life": life,
    }


def recent_ota_errors(cloud: XiaomiCloudProtocol, did: str, since: int) -> list[str]:
    response = cloud.request(
        "user/get_user_device_data",
        {
            "did": did,
            "key": "ota_error",
            "type": "event",
            "time_start": since,
            "time_end": int(time.time()) + 5,
            "limit": 20,
        },
    )
    errors: list[str] = []
    for item in response.get("result") or []:
        value = str(item.get("value") or "")
        if value:
            errors.append(value)
    return errors


def ota_install_stage_observed(state: Any, progress: Any) -> bool:
    return state in ("downloaded", "installing", "installed") or progress == 100


def ota_install_reboot_observed(
    *,
    saw_install_stage: bool,
    initial_life: int | None,
    life: Any,
) -> bool:
    return (
        saw_install_stage
        and isinstance(life, int)
        and initial_life is not None
        and life < initial_life
    )


def _accepted(response: dict[str, Any]) -> bool:
    return response.get("code") == 0 and "ok" in (response.get("result") or [])


def install_firmware(
    cloud: XiaomiCloudProtocol,
    firmware: Path,
    ota_url: str,
    *,
    timeout: int = 360,
    cert_verify: str | None = None,
) -> InstallationResult:
    selected = require_ap01_firmware(firmware)
    device = select_unique_ap01(cloud)
    did = str(device["did"])
    checksum = fingerprint_file(selected).md5
    params: dict[str, Any] = {
        "app_url": ota_url,
        "file_md5": checksum,
        "proc": "dnld install",
        "mode": "normal",
        "signed_file": False,
        "original_length": selected.stat().st_size,
        "install": "1",
        "app_force": 1,
    }
    if cert_verify is not None:
        params["cert_verify"] = cert_verify
    dispatch_time = int(time.time()) - 5
    accepted = cloud.rpc(did, "miIO.ota", params)
    if not _accepted(accepted):
        raise FirmwareInstallError(f"AP01 未接受 OTA：code={accepted.get('code')}")

    started = time.monotonic()
    saw_install_stage = False
    initial_life: int | None = None
    last_status: dict[str, Any] = {"did": did, "state": None, "progress": None, "life": None}
    while time.monotonic() - started < timeout:
        try:
            status = query_ap01_update_status(cloud, did=did)
            last_status = status
            if initial_life is None and isinstance(status["life"], int):
                initial_life = status["life"]
            if ota_install_stage_observed(status["state"], status["progress"]):
                saw_install_stage = True
            if ota_install_reboot_observed(
                saw_install_stage=saw_install_stage,
                initial_life=initial_life,
                life=status["life"],
            ):
                return InstallationResult(
                    accepted_response=accepted,
                    final_status=status,
                    saw_install_stage=saw_install_stage,
                    reboot_observed=True,
                )
            if status["progress"] == 101:
                errors = recent_ota_errors(cloud, did, dispatch_time)
                if errors:
                    raise FirmwareInstallError(f"AP01 OTA 失败：{errors[0]}")
                if (
                    not saw_install_stage
                    and time.monotonic() - started >= OTA_START_GRACE_SECONDS
                ):
                    raise FirmwareInstallError(
                        "AP01 OTA 返回 progress=101，但没有安装阶段或错误明细"
                    )
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2)

    return InstallationResult(
        accepted_response=accepted,
        final_status=last_status,
        saw_install_stage=saw_install_stage,
        reboot_observed=False,
    )
