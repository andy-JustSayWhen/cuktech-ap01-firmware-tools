from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from features.firmware_installation import (
    FirmwareInstallError,
    install_firmware,
    select_unique_ap01,
    upload_and_verify_firmware,
)
from features.firmware_installation.install import AP01_MODEL
from features.firmware_installation.install import OTA_START_GRACE_SECONDS


class FakeResponse:
    def __init__(self, payload: bytes = b"", status: int = 200) -> None:
        self.content = payload
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")


class FakeCloud:
    def __init__(self) -> None:
        self.requests: list[tuple[str, object]] = []
        self.rpc_calls: list[tuple[str, str, object]] = []
        self.rpc_status = [
            {"state": "downloading", "progress": 30, "life": 100},
            {"state": "downloaded", "progress": 100, "life": 100},
            {"state": "installed", "progress": 100, "life": 8},
        ]

    def devices(self) -> list[dict[str, object]]:
        return [
            {"did": "gateway-did", "model": "lumi.gateway.example"},
            {"did": "ap01-did", "model": AP01_MODEL, "name": "AP01"},
        ]

    def request(self, path: str, data: object) -> dict[str, object]:
        self.requests.append((path, data))
        if path == "home/genpresignedurl":
            return {
                "result": {
                    "bin": {
                        "ok": True,
                        "url": "https://fds.example.test/upload",
                        "obj_name": "object.bin",
                    }
                }
            }
        if path == "home/getfileurl":
            return {
                "result": {
                    "ok": True,
                    "url": "https://fds.example.test/object.bin?signature=test",
                }
            }
        if path == "user/get_user_device_data":
            return {"result": []}
        raise AssertionError(path)

    def rpc(self, did: str, method: str, params: object = None) -> dict[str, object]:
        self.rpc_calls.append((did, method, params))
        if method == "miIO.ota":
            return {"code": 0, "result": ["ok"]}
        index = max((len(self.rpc_calls) - 2) // 3, 0)
        status = self.rpc_status[min(index, len(self.rpc_status) - 1)]
        if method == "miIO.get_ota_state":
            return {"code": 0, "result": [status["state"]]}
        if method == "miIO.get_ota_progress":
            return {"code": 0, "result": [status["progress"]]}
        if method == "miIO.info":
            return {"code": 0, "result": {"life": status["life"]}}
        raise AssertionError(method)


class FirmwareInstallationTests(unittest.TestCase):
    def make_firmware(self, root: Path) -> Path:
        path = root / "ap01-test.bin"
        path.write_bytes(b"BFNP" + b"x" * 64)
        return path

    def test_select_unique_ap01_rejects_multiple_devices(self) -> None:
        class MultiAp01Cloud(FakeCloud):
            def devices(self) -> list[dict[str, object]]:
                return [
                    {"did": "a", "model": AP01_MODEL, "name": "A"},
                    {"did": "b", "model": AP01_MODEL, "name": "B"},
                ]

        with self.assertRaisesRegex(FirmwareInstallError, "多个 AP01"):
            select_unique_ap01(MultiAp01Cloud())

    def test_upload_and_verify_downloads_cdn_url_and_compares_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            firmware = self.make_firmware(Path(directory))
            payload = firmware.read_bytes()
            cloud = FakeCloud()
            with (
                patch("features.firmware_installation.install.requests.put", return_value=FakeResponse()),
                patch(
                    "features.firmware_installation.install.requests.get",
                    return_value=FakeResponse(payload),
                ),
            ):
                result = upload_and_verify_firmware(cloud, firmware)

            self.assertEqual(result.url, "https://iot-ota-cdn.io.mi.com/object.bin?signature=test")
            self.assertEqual(result.local, result.readback)
            self.assertEqual(result.fds_device["did"], "gateway-did")

    def test_upload_and_verify_rejects_changed_readback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            firmware = self.make_firmware(Path(directory))
            cloud = FakeCloud()
            with (
                patch("features.firmware_installation.install.requests.put", return_value=FakeResponse()),
                patch(
                    "features.firmware_installation.install.requests.get",
                    return_value=FakeResponse(b"BFNP-changed"),
                ),
            ):
                with self.assertRaisesRegex(FirmwareInstallError, "回读文件"):
                    upload_and_verify_firmware(cloud, firmware)

    def test_install_requires_stage_then_rebooted_uptime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            firmware = self.make_firmware(Path(directory))
            cloud = FakeCloud()
            with patch("features.firmware_installation.install.time.sleep"):
                result = install_firmware(
                    cloud,
                    firmware,
                    "https://iot-ota-cdn.io.mi.com/object.bin?signature=test",
                    timeout=30,
                )

            self.assertTrue(result.saw_install_stage)
            self.assertTrue(result.reboot_observed)
            self.assertEqual(result.final_status["life"], 8)

    def test_install_tolerates_stale_progress_during_start_grace(self) -> None:
        class StaleStatusCloud(FakeCloud):
            def __init__(self) -> None:
                super().__init__()
                self.rpc_status = [
                    {"state": "idle", "progress": 101, "life": 100},
                    {"state": "downloading", "progress": 10, "life": 100},
                    {"state": "installed", "progress": 100, "life": 8},
                ]

        with tempfile.TemporaryDirectory() as directory:
            firmware = self.make_firmware(Path(directory))
            cloud = StaleStatusCloud()
            ticks = iter((0.0, 1.0, 2.0, 3.0, 4.0, 5.0))
            with (
                patch(
                    "features.firmware_installation.install.time.monotonic",
                    side_effect=lambda: next(ticks),
                ),
                patch("features.firmware_installation.install.time.sleep"),
            ):
                result = install_firmware(
                    cloud,
                    firmware,
                    "https://iot-ota-cdn.io.mi.com/object.bin?signature=test",
                    timeout=OTA_START_GRACE_SECONDS + 5,
                )

            self.assertTrue(result.saw_install_stage)
            self.assertTrue(result.reboot_observed)


if __name__ == "__main__":
    unittest.main()
