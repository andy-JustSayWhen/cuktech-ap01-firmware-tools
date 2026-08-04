from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from features.web_firmware_flash.xiaomi_cloud import (
    XiaomiCloudError,
    _select_fds_device,
    dispatch_install_once,
    public_device,
    upload_and_readback,
)


class _Response:
    def __init__(self, payload: bytes = b"") -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, size: int):
        del size
        yield self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class XiaomiCloudAdapterTests(unittest.TestCase):
    def test_public_device_hides_cloud_identifiers(self) -> None:
        public = public_device(
            {"did": "secret-did", "localip": "192.0.2.1", "model": "njcuk.enstor.ap01", "isOnline": True}
        )
        self.assertNotIn("did", public)
        self.assertNotIn("localip", public)
        self.assertEqual(public["identity"], hashlib.sha256(b"secret-did").hexdigest()[:12])

    def test_only_compatible_gateway_is_used_for_upload(self) -> None:
        gateway = _select_fds_device(
            [{"model": "njcuk.enstor.ap01"}, {"did": "g", "model": "lumi.gateway.test"}]
        )
        self.assertEqual(gateway["did"], "g")
        with self.assertRaises(XiaomiCloudError):
            _select_fds_device([{"model": "njcuk.enstor.ap01"}])

    def test_upload_requires_full_byte_identical_readback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            firmware = Path(temporary) / "fw.bin"
            firmware.write_bytes(b"BFNP-body")
            cloud = Mock()
            cloud.devices.return_value = [{"did": "g", "model": "lumi.gateway.test"}]
            cloud.request.side_effect = [
                {"result": {"bin": {"ok": True, "url": "https://upload", "obj_name": "o"}}},
                {"result": {"url": "https://generic/path?signature=x"}},
            ]
            cloud.session.put.return_value = _Response()
            cloud.session.get.return_value = _Response(firmware.read_bytes())
            url = upload_and_readback(cloud, firmware)
            self.assertIn("iot-ota-cdn.io.mi.com", url)

            cloud.request.side_effect = [
                {"result": {"bin": {"ok": True, "url": "https://upload", "obj_name": "o"}}},
                {"result": {"url": "https://generic/path?signature=x"}},
            ]
            cloud.session.get.return_value = _Response(b"different")
            with self.assertRaises(XiaomiCloudError):
                upload_and_readback(cloud, firmware)

    def test_install_dispatch_contains_install_once_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            firmware = Path(temporary) / "fw.bin"
            firmware.write_bytes(b"BFNP")
            cloud = Mock()
            cloud.rpc.return_value = {"code": 0, "result": ["ok"]}
            dispatch_install_once(cloud, "device", firmware, "https://ota")
            _, method, params = cloud.rpc.call_args.args
            self.assertEqual(method, "miIO.ota")
            self.assertEqual(params["proc"], "dnld install")
            self.assertEqual(params["install"], "1")


if __name__ == "__main__":
    unittest.main()
