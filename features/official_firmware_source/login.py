"""Create a Xiaomi QR login and persist its reusable account values."""

from __future__ import annotations

import json
import os
import secrets
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests

from .xiaomi_cloud import MODEL, OfficialFirmwareError, XiaomiCloudClient, _read_env_file


LOGIN_ENDPOINT = "https://account.xiaomi.com/longPolling/loginUrl"
USER_AGENT = "APP/com.xiaomi.mihome APPV/10.5.201"
ACCOUNT_KEYS = (
    "CUKTECH_MI_USER_ID",
    "CUKTECH_MI_PASS_TOKEN",
    "CUKTECH_MI_DEVICE_ID",
)
OBSOLETE_ACCOUNT_KEYS = ("CUKTECH_MI_CREDENTIALS",)


@dataclass(frozen=True)
class LoginChallenge:
    qr_url: str
    polling_url: str
    timeout: float


@dataclass(frozen=True)
class LoginResult:
    model: str
    reused_existing: bool


def _xiaomi_json(payload: bytes) -> dict[str, Any]:
    text = payload.decode("utf-8").removeprefix("&&&START&&&")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise OfficialFirmwareError("小米登录响应不是对象")
    return value


class XiaomiQrLogin:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def start(self, qr_output: Path, requested_timeout: float) -> LoginChallenge:
        try:
            response = self.session.get(
                LOGIN_ENDPOINT,
                params={
                    "_qrsize": "480",
                    "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
                    "callback": "https://sts.api.io.mi.com/sts",
                    "_hasLogo": "false",
                    "sid": "xiaomiio",
                    "serviceParam": "",
                    "_locale": "zh_CN",
                    "_dc": str(int(time.time() * 1000)),
                },
                timeout=20,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OfficialFirmwareError(f"小米二维码登录接口失败：{exc}") from exc
        payload = _xiaomi_json(response.content)
        if any(not payload.get(key) for key in ("qr", "lp")):
            raise OfficialFirmwareError("小米没有返回完整的二维码登录信息")

        server_timeout = float(payload.get("timeout") or requested_timeout)
        challenge = LoginChallenge(
            qr_url=str(payload["qr"]),
            polling_url=str(payload["lp"]),
            timeout=min(requested_timeout, server_timeout),
        )
        try:
            image_response = self.session.get(challenge.qr_url, timeout=20)
            image_response.raise_for_status()
        except requests.RequestException as exc:
            raise OfficialFirmwareError(f"小米登录二维码下载失败：{exc}") from exc
        image = image_response.content
        if not image:
            raise OfficialFirmwareError("小米登录二维码下载失败")
        _atomic_write(qr_output, image, mode=0o600)
        return challenge

    def wait(self, challenge: LoginChallenge) -> dict[str, str]:
        started = time.monotonic()
        while time.monotonic() - started < challenge.timeout:
            remaining = challenge.timeout - (time.monotonic() - started)
            try:
                response = self.session.get(
                    challenge.polling_url,
                    timeout=max(1.0, min(10.0, remaining)),
                )
            except requests.Timeout:
                continue
            except requests.RequestException as exc:
                raise OfficialFirmwareError(f"等待扫码结果失败：{exc}") from exc
            if response.status_code != 200:
                time.sleep(0.5)
                continue
            payload = _xiaomi_json(response.content)
            user_id = str(payload.get("userId") or "").strip()
            pass_token = str(payload.get("passToken") or "").strip()
            if user_id and pass_token:
                return {
                    "CUKTECH_MI_USER_ID": user_id,
                    "CUKTECH_MI_PASS_TOKEN": pass_token,
                    "CUKTECH_MI_DEVICE_ID": secrets.token_hex(8).upper(),
                }
        raise OfficialFirmwareError("二维码已超时，请重新生成后扫码")


def ensure_login(
    env_file: Path,
    qr_output: Path,
    *,
    timeout: float,
    announce_qr: Callable[[Path], None],
    login: XiaomiQrLogin | None = None,
) -> LoginResult:
    values = _read_env_file(env_file)
    if values.get("CUKTECH_MI_USER_ID") and values.get("CUKTECH_MI_PASS_TOKEN"):
        try:
            device = XiaomiCloudClient(env_file=env_file).ap01_device()
            return LoginResult(model=str(device["model"]), reused_existing=True)
        except OfficialFirmwareError:
            pass

    selected_login = login or XiaomiQrLogin()
    challenge = selected_login.start(qr_output, timeout)
    announce_qr(qr_output)
    credentials = selected_login.wait(challenge)
    account = {
        "userId": credentials["CUKTECH_MI_USER_ID"],
        "passToken": credentials["CUKTECH_MI_PASS_TOKEN"],
        "deviceId": credentials["CUKTECH_MI_DEVICE_ID"],
    }
    device = XiaomiCloudClient(account=account).ap01_device()
    if str(device.get("model") or "") != MODEL:
        raise OfficialFirmwareError("扫码账号返回的设备型号不是 AP01")
    _update_env_file(env_file, credentials)
    return LoginResult(model=MODEL, reused_existing=False)


def _update_env_file(path: Path, updates: dict[str, str]) -> None:
    for key, value in updates.items():
        if key not in ACCOUNT_KEYS or "\n" in value or "\r" in value:
            raise OfficialFirmwareError("登录态包含无法保存的字段")

    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    rendered: list[str] = []
    remaining = dict(updates)
    for original in lines:
        key, separator, _ = original.strip().partition("=")
        if separator and key in OBSOLETE_ACCOUNT_KEYS:
            continue
        if separator and key in updates:
            if key in remaining:
                rendered.append(f'{key}="{updates[key]}"')
                remaining.pop(key)
            continue
        rendered.append(original)
    if rendered and rendered[-1]:
        rendered.append("")
    rendered.extend(f'{key}="{value}"' for key, value in remaining.items())
    payload = ("\n".join(rendered).rstrip("\n") + "\n").encode("utf-8")
    _atomic_write(path, payload, mode=0o600)


def _atomic_write(path: Path, payload: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
        os.chmod(path, mode)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
