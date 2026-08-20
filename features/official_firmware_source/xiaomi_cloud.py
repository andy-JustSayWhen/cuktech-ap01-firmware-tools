"""Query and download the AP01 official firmware from Xiaomi Cloud."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import re
import stat
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib import parse

import requests

from core.firmware_image import (
    AP01_1_0_2_0031,
    BaselineDefinition,
    FirmwareValidationError,
    validate_baseline,
)


MODEL = "njcuk.enstor.ap01"
DEFAULT_ENV = Path("env/mi-cloud.env")
READ_ONLY_MODE = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
SAFE_VERSION = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MD5_HEX = re.compile(r"^[0-9a-f]{32}$")


class OfficialFirmwareError(RuntimeError):
    """Official firmware lookup or download failed."""


@dataclass(frozen=True)
class OfficialFirmwareInfo:
    model: str
    version: str
    md5: str
    change_log: str
    upload_time: int | None
    timeout: int | None
    url: str

    def public_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "version": self.version,
            "md5": self.md5,
            "change_log": self.change_log,
            "upload_time": self.upload_time,
            "timeout": self.timeout,
        }


@dataclass(frozen=True)
class OfficialFirmwareResult:
    info: OfficialFirmwareInfo
    path: Path
    size: int
    md5: str
    sha256: str
    reused_existing: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "cloud": self.info.public_dict(),
            "path": str(self.path),
            "size": self.size,
            "md5": self.md5,
            "sha256": self.sha256,
            "read_only": True,
            "reused_existing": self.reused_existing,
        }


def _read_env_file(path: Path) -> dict[str, str]:
    selected = path.expanduser()
    if not selected.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in selected.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def _load_account(
    *,
    env_file: Path | None = None,
) -> dict[str, str]:
    env_values = _read_env_file(env_file or DEFAULT_ENV)
    user_id = (
        os.environ.get("CUKTECH_MI_USER_ID")
        or env_values.get("CUKTECH_MI_USER_ID")
        or ""
    ).strip()
    pass_token = (
        os.environ.get("CUKTECH_MI_PASS_TOKEN")
        or env_values.get("CUKTECH_MI_PASS_TOKEN")
        or ""
    ).strip()
    if user_id and pass_token:
        return {
            "userId": user_id,
            "passToken": pass_token,
            "deviceId": (
                os.environ.get("CUKTECH_MI_DEVICE_ID")
                or env_values.get("CUKTECH_MI_DEVICE_ID")
                or ""
            ).strip(),
        }

    raise OfficialFirmwareError(
        "没有找到米家登录态。请运行官方固件入口的 login 命令扫码登录。"
    )


class XiaomiCloudClient:
    """Small Xiaomi Cloud client scoped to AP01 official firmware metadata."""

    def __init__(
        self,
        *,
        env_file: Path | None = None,
        account: Mapping[str, str] | None = None,
        session: requests.Session | None = None,
        timeout: int = 30,
    ) -> None:
        selected_account = (
            dict(account) if account is not None else _load_account(env_file=env_file)
        )
        if not selected_account.get("userId") or not selected_account.get("passToken"):
            raise OfficialFirmwareError("米家登录态缺少 userId 或 passToken")
        self.user_id = str(selected_account["userId"])
        self.pass_token = str(selected_account["passToken"])
        self.device_id = str(selected_account.get("deviceId") or "B4C9D5BF5C4B6925")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.ssecurity = ""
        self.service_token = ""
        self._refresh_session()

    def _http_get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> tuple[bytes, dict[str, str]]:
        try:
            response = self.session.get(
                url,
                headers=headers,
                cookies=cookies,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OfficialFirmwareError(f"小米云请求失败：{exc}") from exc
        return response.content, dict(response.headers.items())

    def _http_post(
        self,
        url: str,
        *,
        data: dict[str, str],
        headers: dict[str, str],
        cookies: dict[str, str],
    ) -> bytes:
        try:
            response = self.session.post(
                url,
                data=data,
                headers=headers,
                cookies=cookies,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OfficialFirmwareError(f"小米云请求失败：{exc}") from exc
        return response.content

    def _refresh_session(self) -> None:
        cookies = {
            "userId": self.user_id,
            "passToken": self.pass_token,
            "deviceId": self.device_id,
        }
        query = parse.urlencode({"sid": "xiaomiio", "_json": "true"})
        body, headers = self._http_get(
            "https://account.xiaomi.com/pass/serviceLogin?" + query,
            headers={"User-Agent": "APP/com.xiaomi.mihome APPV/9.1.200"},
            cookies=cookies,
        )
        auth = json.loads(body.decode().replace("&&&START&&&", ""))
        if auth.get("code") != 0 or not auth.get("location"):
            raise OfficialFirmwareError(
                f"Xiaomi account refresh failed: code={auth.get('code')}"
            )
        self.ssecurity = str(auth["ssecurity"])
        _, location_headers = self._http_get(str(auth["location"]))
        service_token = (
            self.session.cookies.get("serviceToken")
            or _extract_cookie(headers, "serviceToken")
            or _extract_cookie(location_headers, "serviceToken")
        )
        if not service_token:
            raise OfficialFirmwareError("Xiaomi account refresh returned no service token")
        self.service_token = service_token

    @staticmethod
    def _nonce() -> str:
        first = (random.getrandbits(64) - 2**63).to_bytes(8, "big", signed=True)
        minute = int(time.time() / 60)
        second = minute.to_bytes((minute.bit_length() + 7) // 8, "big")
        return base64.b64encode(first + second).decode()

    def _signed_nonce(self, nonce: str) -> str:
        raw = base64.b64decode(self.ssecurity) + base64.b64decode(nonce)
        return base64.b64encode(hashlib.sha256(raw).digest()).decode()

    @staticmethod
    def _rc4(key: str, payload: str, *, decrypt: bool = False) -> str:
        secret = base64.b64decode(key)
        state = list(range(256))
        j = 0
        for i in range(256):
            j = (j + state[i] + secret[i % len(secret)]) & 0xFF
            state[i], state[j] = state[j], state[i]

        i = j = 0

        def next_byte() -> int:
            nonlocal i, j
            i = (i + 1) & 0xFF
            j = (j + state[i]) & 0xFF
            state[i], state[j] = state[j], state[i]
            return state[(state[i] + state[j]) & 0xFF]

        for _ in range(1024):
            next_byte()
        source = base64.b64decode(payload) if decrypt else payload.encode()
        result = bytes(value ^ next_byte() for value in source)
        if decrypt:
            return result.decode()
        return base64.b64encode(result).decode()

    @staticmethod
    def _signature(method: str, url: str, params: dict[str, str], key: str) -> str:
        path = parse.urlparse(url).path
        if path.startswith("/app/"):
            path = path[4:]
        parts = [method.upper(), path]
        parts.extend(f"{name}={value}" for name, value in params.items())
        parts.append(key)
        digest = hashlib.sha1("&".join(parts).encode()).digest()
        return base64.b64encode(digest).decode()

    def request(self, path: str, data: Any) -> dict[str, Any]:
        url = "https://api.io.mi.com/app/" + path.lstrip("/")
        nonce = self._nonce()
        signed_nonce = self._signed_nonce(nonce)
        params = {"data": json.dumps(data, ensure_ascii=False, separators=(",", ":"))}
        params["rc4_hash__"] = self._signature("POST", url, params, signed_nonce)
        encrypted = {
            name: self._rc4(signed_nonce, value) for name, value in params.items()
        }
        encrypted.update(
            {
                "signature": self._signature("POST", url, encrypted, signed_nonce),
                "ssecurity": self.ssecurity,
                "_nonce": nonce,
            }
        )
        headers = {
            "User-Agent": (
                "Android-7.1.1-1.0.0-ONEPLUS A3010-136-ABCDEF1234567 "
                "APP/xiaomi.smarthome APPV/62830"
            ),
            "Accept-Encoding": "identity",
            "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
        }
        cookies = {
            "userId": self.user_id,
            "yetAnotherServiceToken": self.service_token,
            "serviceToken": self.service_token,
            "locale": "zh_CN",
            "timezone": "GMT+08:00",
            "channel": "MI_APP_STORE",
        }
        decoded = self._rc4(
            signed_nonce,
            self._http_post(url, data=encrypted, headers=headers, cookies=cookies).decode(),
            decrypt=True,
        )
        return json.loads(decoded)

    def firmware_info(self) -> OfficialFirmwareInfo:
        response = self.request("home/latest_version", {"model": MODEL})
        result = response.get("result") or {}
        url = str(result.get("url") or "")
        md5 = str(result.get("md5") or "").lower()
        version = str(result.get("version") or "")
        if not url or not md5 or not version:
            raise OfficialFirmwareError("小米云未返回官方固件地址、版本或 MD5")
        info = OfficialFirmwareInfo(
            model=MODEL,
            version=version,
            md5=md5,
            change_log=str(result.get("changeLog") or ""),
            upload_time=_optional_int(result.get("upload_time")),
            timeout=_optional_int(result.get("time_out")),
            url=url,
        )
        _validate_cloud_info(info)
        return info

    def devices(self) -> list[dict[str, Any]]:
        response = self.request(
            "home/device_list",
            {
                "getVirtualModel": True,
                "getHuamiDevices": 1,
                "get_split_device": False,
                "support_smart_home": True,
            },
        )
        devices = (response.get("result") or {}).get("list") or []
        return [device for device in devices if isinstance(device, dict)]

    def ap01_device(self) -> dict[str, Any]:
        for device in self.devices():
            if isinstance(device, dict) and device.get("model") == MODEL:
                return device
        raise OfficialFirmwareError("扫码账号内没有找到 AP01")

    def rpc(self, did: str, method: str, params: Any = None) -> dict[str, Any]:
        payload = {
            "id": random.randint(1_000_000, 9_999_999),
            "method": method,
            "params": [] if params is None else params,
        }
        return self.request(f"home/rpc/{did}", payload)


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _extract_cookie(headers: dict[str, str], name: str) -> str:
    selected = ""
    for key, value in headers.items():
        if key.lower() != "set-cookie":
            continue
        for item in value.split(","):
            first = item.strip().split(";", 1)[0]
            if first.startswith(name + "="):
                selected = first.split("=", 1)[1]
    return selected


def _download_url(url: str, *, timeout: int) -> bytes:
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OfficialFirmwareError(f"官方固件下载失败：{exc}") from exc
    return response.content


def _fingerprints(payload: bytes) -> tuple[str, str]:
    return hashlib.md5(payload).hexdigest(), hashlib.sha256(payload).hexdigest()


def _validate_cloud_info(info: OfficialFirmwareInfo) -> None:
    if info.model != MODEL:
        raise OfficialFirmwareError(
            f"云端型号不匹配：预期 {MODEL}，实际 {info.model}"
        )
    if not SAFE_VERSION.fullmatch(info.version):
        raise OfficialFirmwareError("云端版本不能安全用于文件名")
    if not MD5_HEX.fullmatch(info.md5):
        raise OfficialFirmwareError("云端 MD5 不是 32 位十六进制值")
    if parse.urlparse(info.url).scheme != "https":
        raise OfficialFirmwareError("云端固件地址不是 HTTPS")


def _latest_target(output_dir: Path, info: OfficialFirmwareInfo) -> Path:
    _validate_cloud_info(info)
    return output_dir.expanduser().resolve() / f"ap01-{info.version}.bin"


def _read_existing_latest(
    target: Path,
    *,
    info: OfficialFirmwareInfo,
) -> OfficialFirmwareResult:
    if target.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
        raise OfficialFirmwareError(f"已有官方固件仍可写，拒绝复用：{target}")
    payload = target.read_bytes()
    if not payload:
        raise OfficialFirmwareError("已有官方固件为空，拒绝复用")
    md5, sha256 = _fingerprints(payload)
    if md5 != info.md5:
        raise OfficialFirmwareError(
            f"已有官方固件 MD5 不匹配：云端 {info.md5}，实际 {md5}"
        )
    return OfficialFirmwareResult(
        info=info,
        path=target,
        size=len(payload),
        md5=md5,
        sha256=sha256,
        reused_existing=True,
    )


def download_latest_official_firmware(
    client: XiaomiCloudClient,
    output_dir: Path,
    *,
    timeout: int = 120,
) -> OfficialFirmwareResult:
    info = client.firmware_info()
    selected = _latest_target(output_dir, info)
    selected.parent.mkdir(parents=True, exist_ok=True)
    if selected.exists():
        return _read_existing_latest(selected, info=info)

    payload = _download_url(info.url, timeout=timeout)
    if not payload:
        raise OfficialFirmwareError("下载文件为空")
    md5, sha256 = _fingerprints(payload)
    if md5 != info.md5:
        raise OfficialFirmwareError(
            f"下载文件 MD5 不匹配：云端 {info.md5}，实际 {md5}"
        )

    temporary_path: Path | None = None
    created_target = False
    keep_target = False
    try:
        with tempfile.NamedTemporaryFile(
            mode="xb",
            dir=selected.parent,
            prefix=f".{selected.name}.",
            suffix=".part",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.chmod(READ_ONLY_MODE)
        if selected.exists():
            raise OfficialFirmwareError(f"准备保存时出现同名文件，拒绝覆盖：{selected}")
        os.replace(temporary_path, selected)
        temporary_path = None
        created_target = True
        if selected.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            raise OfficialFirmwareError("官方固件保存后未成功设为只读")

        saved = selected.read_bytes()
        saved_md5, saved_sha256 = _fingerprints(saved)
        if (
            len(saved) != len(payload)
            or saved_md5 != md5
            or saved_sha256 != sha256
        ):
            raise OfficialFirmwareError("保存后重新读取的文件与下载内容不一致")
        keep_target = True
        return OfficialFirmwareResult(
            info=info,
            path=selected,
            size=len(saved),
            md5=saved_md5,
            sha256=saved_sha256,
            reused_existing=False,
        )
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            temporary_path.unlink()
        if created_target and not keep_target and selected.exists():
            selected.chmod(stat.S_IRUSR | stat.S_IWUSR)
            selected.unlink()


def _assert_cloud_matches_baseline(
    info: OfficialFirmwareInfo,
    definition: BaselineDefinition,
) -> None:
    if info.model != definition.model:
        raise OfficialFirmwareError(
            f"云端型号不匹配：预期 {definition.model}，实际 {info.model}"
        )
    if info.version != definition.version:
        raise OfficialFirmwareError(
            f"云端版本不匹配：预期 {definition.version}，实际 {info.version}"
        )
    if info.md5 != definition.md5:
        raise OfficialFirmwareError(
            f"云端 MD5 不匹配：预期 {definition.md5}，实际 {info.md5}"
        )


def _read_existing(
    target: Path,
    *,
    info: OfficialFirmwareInfo,
    definition: BaselineDefinition,
) -> OfficialFirmwareResult:
    if target.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
        raise OfficialFirmwareError(f"已有官方固件仍可写，拒绝复用：{target}")
    payload = target.read_bytes()
    report = validate_baseline(payload, definition)
    return OfficialFirmwareResult(
        info=info,
        path=target,
        size=report.size,
        md5=report.md5,
        sha256=report.sha256,
        reused_existing=True,
    )


def download_official_firmware(
    client: XiaomiCloudClient,
    target: Path,
    *,
    definition: BaselineDefinition = AP01_1_0_2_0031,
    timeout: int = 120,
) -> OfficialFirmwareResult:
    info = client.firmware_info()
    _assert_cloud_matches_baseline(info, definition)

    selected = target.expanduser().resolve()
    selected.parent.mkdir(parents=True, exist_ok=True)
    if selected.exists():
        return _read_existing(selected, info=info, definition=definition)

    payload = _download_url(info.url, timeout=timeout)
    md5, sha256 = _fingerprints(payload)
    if md5 != info.md5:
        raise OfficialFirmwareError(
            f"下载文件 MD5 不匹配：预期 {info.md5}，实际 {md5}"
        )
    report = validate_baseline(payload, definition)
    if report.sha256 != sha256:
        raise OfficialFirmwareError("下载文件 SHA-256 计算结果不一致")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="xb",
            dir=selected.parent,
            prefix=f".{selected.name}.",
            suffix=".part",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.chmod(READ_ONLY_MODE)
        if selected.exists():
            raise OfficialFirmwareError(f"准备保存时出现同名文件，拒绝覆盖：{selected}")
        os.replace(temporary_path, selected)
        temporary_path = None
        if selected.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            raise OfficialFirmwareError("官方固件保存后未成功设为只读")
        final_report = validate_baseline(selected.read_bytes(), definition)
        return OfficialFirmwareResult(
            info=info,
            path=selected,
            size=final_report.size,
            md5=final_report.md5,
            sha256=final_report.sha256,
            reused_existing=False,
        )
    except FirmwareValidationError as exc:
        raise OfficialFirmwareError(str(exc)) from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            temporary_path.unlink()
