"""小米云设备识别、对象上传、完整回读和 AP01 安装适配。"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse, urlsplit, urlunsplit

import requests


MODEL = "njcuk.enstor.ap01"
OTA_CDN_HOST = "iot-ota-cdn.io.mi.com"
DEFAULT_USER_AGENT = "APP/com.xiaomi.mihome APPV/10.5.201"


class XiaomiCloudError(RuntimeError):
    pass


def _private_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"").strip("'")
    return values


@dataclass(frozen=True)
class XiaomiCredentials:
    user_id: str
    pass_token: str
    device_id: str

    @classmethod
    def load(cls, private_file: Path | None = None) -> "XiaomiCredentials":
        saved = _private_env(private_file) if private_file is not None else {}
        user_id = (os.environ.get("CUKTECH_MI_USER_ID") or saved.get("CUKTECH_MI_USER_ID") or "").strip()
        pass_token = (os.environ.get("CUKTECH_MI_PASS_TOKEN") or saved.get("CUKTECH_MI_PASS_TOKEN") or "").strip()
        device_id = (os.environ.get("CUKTECH_MI_DEVICE_ID") or saved.get("CUKTECH_MI_DEVICE_ID") or "").strip()
        if not user_id or not pass_token:
            raise XiaomiCloudError("没有找到小米登录态")
        return cls(user_id, pass_token, device_id or os.urandom(8).hex().upper())


class XiaomiCloudClient:
    def __init__(self, credentials: XiaomiCredentials, session: requests.Session | None = None) -> None:
        self.credentials = credentials
        self.session = session or requests.Session()
        self.ssecurity = ""
        self.service_token = ""
        self._refresh_session()

    def _refresh_session(self) -> None:
        self.session.headers["User-Agent"] = DEFAULT_USER_AGENT
        self.session.cookies.update(
            {
                "userId": self.credentials.user_id,
                "passToken": self.credentials.pass_token,
                "deviceId": self.credentials.device_id,
            }
        )
        response = self.session.get(
            "https://account.xiaomi.com/pass/serviceLogin",
            params={"sid": "xiaomiio", "_json": "true"},
            timeout=20,
        )
        response.raise_for_status()
        try:
            auth = json.loads(response.text.removeprefix("&&&START&&&"))
        except json.JSONDecodeError as exc:
            raise XiaomiCloudError("小米登录响应无法解析") from exc
        if auth.get("code") != 0 or not auth.get("location") or not auth.get("ssecurity"):
            raise XiaomiCloudError("小米登录态刷新失败")
        self.ssecurity = str(auth["ssecurity"])
        response = self.session.get(str(auth["location"]), timeout=20)
        response.raise_for_status()
        self.service_token = response.cookies.get("serviceToken") or self.session.cookies.get("serviceToken") or ""
        if not self.service_token:
            raise XiaomiCloudError("小米登录态没有返回服务凭证")

    @staticmethod
    def _nonce() -> str:
        first = (random.getrandbits(64) - 2**63).to_bytes(8, "big", signed=True)
        minute = int(time.time() / 60)
        second = minute.to_bytes(max(1, (minute.bit_length() + 7) // 8), "big")
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
        return result.decode() if decrypt else base64.b64encode(result).decode()

    @staticmethod
    def _signature(method: str, url: str, params: dict[str, str], key: str) -> str:
        path = urlparse(url).path
        if path.startswith("/app/"):
            path = path[4:]
        parts = [method.upper(), path]
        parts.extend(f"{name}={value}" for name, value in params.items())
        parts.append(key)
        return base64.b64encode(hashlib.sha1("&".join(parts).encode()).digest()).decode()

    def request(self, path: str, data: Any) -> dict[str, Any]:
        url = "https://api.io.mi.com/app/" + path.lstrip("/")
        nonce = self._nonce()
        signed_nonce = self._signed_nonce(nonce)
        params = {"data": json.dumps(data, ensure_ascii=False, separators=(",", ":"))}
        params["rc4_hash__"] = self._signature("POST", url, params, signed_nonce)
        encrypted = {name: self._rc4(signed_nonce, value) for name, value in params.items()}
        encrypted.update(
            {
                "signature": self._signature("POST", url, encrypted, signed_nonce),
                "ssecurity": self.ssecurity,
                "_nonce": nonce,
            }
        )
        response = self.session.post(
            url,
            data=encrypted,
            headers={
                "User-Agent": "Android-7.1.1 APP/xiaomi.smarthome APPV/62830",
                "Accept-Encoding": "identity",
                "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
            },
            cookies={
                "userId": self.credentials.user_id,
                "yetAnotherServiceToken": self.service_token,
                "serviceToken": self.service_token,
                "locale": "zh_CN",
                "timezone": "GMT+08:00",
                "channel": "MI_APP_STORE",
            },
            timeout=30,
        )
        response.raise_for_status()
        try:
            decoded = self._rc4(signed_nonce, response.text, decrypt=True)
            result = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise XiaomiCloudError("小米云响应无法解析") from exc
        if not isinstance(result, dict):
            raise XiaomiCloudError("小米云响应不是对象")
        return result

    def devices(self) -> list[dict[str, Any]]:
        response = self.request(
            "home/device_list",
            {"getVirtualModel": True, "getHuamiDevices": 1, "get_split_device": False, "support_smart_home": True},
        )
        devices = (response.get("result") or {}).get("list") or []
        return [item for item in devices if isinstance(item, dict)]

    def unique_ap01(self) -> dict[str, Any]:
        devices = [item for item in self.devices() if item.get("model") == MODEL]
        if len(devices) != 1:
            raise XiaomiCloudError(f"账号中符合型号的 AP01 数量不是 1：{len(devices)}")
        return devices[0]

    def rpc(self, did: str, method: str, params: Any = None) -> dict[str, Any]:
        return self.request(
            f"home/rpc/{did}",
            {"id": random.randint(1_000_000, 9_999_999), "method": method, "params": [] if params is None else params},
        )


def public_device(device: dict[str, Any]) -> dict[str, Any]:
    did = str(device.get("did") or "")
    masked = hashlib.sha256(did.encode()).hexdigest()[:12] if did else "unknown"
    return {
        "identity": masked,
        "name": str(device.get("name") or "AP01"),
        "model": str(device.get("model") or ""),
        "firmware_version": str(device.get("fw_version") or ""),
        "online": device.get("isOnline") is True,
    }


def _select_fds_device(devices: Iterable[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        item for item in devices
        if str(item.get("model") or "").startswith(("lumi.gateway.", "xiaomi.gateway."))
    ]
    if not candidates:
        raise XiaomiCloudError("账号中没有可用于对象上传的兼容网关")
    return candidates[0]


def upload_and_readback(cloud: XiaomiCloudClient, firmware: Path) -> str:
    gateway = _select_fds_device(cloud.devices())
    prepared = cloud.request(
        "home/genpresignedurl",
        {"did": str(gateway["did"]), "model": str(gateway["model"]), "suffix": "bin"},
    )
    upload = (prepared.get("result") or {}).get("bin") or {}
    if not upload.get("ok") or not upload.get("url") or not upload.get("obj_name"):
        raise XiaomiCloudError("小米对象存储没有返回完整上传信息")
    with firmware.open("rb") as stream:
        response = cloud.session.put(str(upload["url"]), data=stream, timeout=180)
    response.raise_for_status()
    fetched = cloud.request("home/getfileurl", {"obj_name": upload["obj_name"]})
    generic_url = str(((fetched.get("result") or {}).get("url") or ""))
    if not generic_url:
        raise XiaomiCloudError("小米对象存储没有返回下载地址")
    parsed = urlsplit(generic_url)
    ota_url = urlunsplit((parsed.scheme, OTA_CDN_HOST, parsed.path, parsed.query, parsed.fragment))

    local_sha = hashlib.sha256()
    remote_sha = hashlib.sha256()
    local_size = firmware.stat().st_size
    with firmware.open("rb") as local, cloud.session.get(ota_url, stream=True, timeout=180) as remote:
        remote.raise_for_status()
        remote_size = 0
        for chunk in remote.iter_content(1024 * 1024):
            if chunk:
                remote_size += len(chunk)
                remote_sha.update(chunk)
        for chunk in iter(lambda: local.read(1024 * 1024), b""):
            local_sha.update(chunk)
    if remote_size != local_size or remote_sha.digest() != local_sha.digest():
        raise XiaomiCloudError("上传对象完整回读与冻结成品不一致")
    return ota_url


def ota_state(cloud: XiaomiCloudClient, did: str) -> dict[str, Any]:
    state = cloud.rpc(did, "miIO.get_ota_state").get("result")
    progress = cloud.rpc(did, "miIO.get_ota_progress").get("result")
    info = cloud.rpc(did, "miIO.info").get("result")
    return {"state": state, "progress": progress, "life": info.get("life") if isinstance(info, dict) else None}


def dispatch_install_once(cloud: XiaomiCloudClient, did: str, firmware: Path, ota_url: str) -> None:
    params = {
        "app_url": ota_url,
        "file_md5": hashlib.md5(firmware.read_bytes()).hexdigest(),
        "proc": "dnld install",
        "mode": "normal",
        "signed_file": False,
        "original_length": firmware.stat().st_size,
        "install": "1",
    }
    accepted = cloud.rpc(did, "miIO.ota", params)
    if accepted.get("code") != 0 or "ok" not in (accepted.get("result") or []):
        raise XiaomiCloudError("AP01 没有接受正式安装任务")
