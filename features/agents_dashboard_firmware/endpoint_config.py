"""读取个人固件使用的本机服务地址配置。"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from pathlib import Path


HOSTS = "AP01_AGENTS_HOSTS"
PORT = "AP01_AGENTS_PORT"
REQUIRED_KEYS = (HOSTS, PORT)
MAX_HOSTS = 10


class EndpointConfigError(ValueError):
    pass


@dataclass(frozen=True)
class DashboardEndpointConfig:
    hosts: tuple[str, ...]
    port: int

    @property
    def endpoints(self) -> tuple[str, ...]:
        return tuple(
            f"http://{host}:{self.port}/a" for host in self.hosts
        )


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _read_values(path: Path) -> dict[str, str]:
    try:
        lines = path.expanduser().resolve(strict=True).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise EndpointConfigError("无法读取本机看板地址配置") from error

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if separator != "=" or key not in REQUIRED_KEYS:
            raise EndpointConfigError(f"本机看板地址配置第 {line_number} 行格式错误")
        if key in values:
            raise EndpointConfigError(f"本机看板地址配置第 {line_number} 行重复")
        values[key] = _unquote(value.strip())
    missing = [key for key in REQUIRED_KEYS if not values.get(key)]
    if missing:
        raise EndpointConfigError("本机看板地址配置没有填写完整")
    return values


def _private_ipv4(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise EndpointConfigError("看板服务电脑地址必须是 IPv4 局域网地址") from error
    if not isinstance(address, ipaddress.IPv4Address) or not address.is_private:
        raise EndpointConfigError("看板服务电脑地址必须是 IPv4 局域网地址")
    return str(address)


def load_endpoint_config(path: Path) -> DashboardEndpointConfig:
    values = _read_values(path)
    raw_hosts = values[HOSTS].split(",")
    if any(not value.strip() for value in raw_hosts):
        raise EndpointConfigError("看板服务电脑地址列表包含空项")
    if len(raw_hosts) > MAX_HOSTS:
        raise EndpointConfigError("看板服务电脑地址最多填写 10 项")
    hosts = tuple(_private_ipv4(value.strip()) for value in raw_hosts)
    if len(set(hosts)) != len(hosts):
        raise EndpointConfigError("看板服务电脑地址不能重复")
    try:
        port = int(values[PORT], 10)
    except ValueError as error:
        raise EndpointConfigError("看板服务端口必须是数字") from error
    if not 1 <= port <= 65535:
        raise EndpointConfigError("看板服务端口必须在 1 至 65535 之间")
    return DashboardEndpointConfig(hosts, port)
