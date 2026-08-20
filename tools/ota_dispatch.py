"""向账号内唯一的 AP01 下发一次固件安装指令。

适用范围：本工具适用于任意已通过刷前检查的 AP01，不绑定某台设备、某个局域网地址或
某份固件。调用者必须明确提供固件文件、该固件的 HTTPS 访问地址和本机小米云登录态文件。
执行前应按对应固件的 SOP 完成文件身份核对和设备空闲检查；本脚本只发送安装指令，不代替
后续安装状态检查或屏幕验收。

用法示例：
    python tools/ota_dispatch.py --firmware <固件路径> \\
      --ota-url https://<本机局域网地址>/miio_fw/<固件文件名> \\
      --env-file env/mi-cloud.env

账号中不是恰好一台 AP01 时，脚本会停止，避免错误选择目标设备。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from features.official_firmware_source import XiaomiCloudClient
from features.firmware_installation.install import (
    fingerprint_file,
    require_ap01_firmware,
    select_unique_ap01,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", type=Path, required=True, help="要安装的 AP01 固件")
    parser.add_argument(
        "--ota-url",
        required=True,
        help="固件服务的完整 HTTPS 地址，路径必须是 /miio_fw/<固件文件名>",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        required=True,
        help="本机小米云登录态文件",
    )
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    firmware = require_ap01_firmware(arguments.firmware)
    client = XiaomiCloudClient(env_file=arguments.env_file)

    device = select_unique_ap01(client)
    did = str(device["did"])
    print("DID=", did)

    info = client.rpc(did, "miIO.info")
    print("INFO_RESPONSE code=", info.get("code"), "fw_ver=", (info.get("result") or {}).get("fw_ver"))

    params = {
        "app_url": arguments.ota_url,
        "file_md5": fingerprint_file(firmware).md5,
        "signed_file": False,
        "original_length": firmware.stat().st_size,
        "app_force": 1,
        "cert_verify": "optional",
    }
    response = client.rpc(did, "miIO.ota", params)
    print("OTA_RESPONSE=", json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
