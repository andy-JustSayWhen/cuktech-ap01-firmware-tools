from __future__ import annotations

import hashlib
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import Mock

from features.web_firmware_flash.xiaomi_cloud import (
    XiaomiCloudError,
    XiaomiCredentials,
    XiaomiQrLogin,
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
    def test_credentials_are_saved_atomically_with_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "private" / "xiaomi.env"
            credentials = XiaomiCredentials("user", "token", "device")
            credentials.save(destination)
            self.assertEqual(XiaomiCredentials.load(destination), credentials)
            self.assertEqual(os.stat(destination).st_mode & 0o777, 0o600)

    def test_qr_login_wraps_reference_protocol_and_returns_credentials(self) -> None:
        challenge_response = Mock()
        challenge_response.text = (
            '&&&START&&&{"qr":"https://qr","loginUrl":"https://login",'
            '"lp":"https://poll","timeout":30}'
        )
        challenge_response.raise_for_status.return_value = None
        image_response = Mock()
        image_response.content = b"png"
        image_response.raise_for_status.return_value = None
        poll_response = Mock(status_code=200)
        poll_response.text = '&&&START&&&{"userId":"user","passToken":"token"}'
        session = Mock()
        session.headers = {}
        session.get.side_effect = [challenge_response, image_response, poll_response]
        with tempfile.TemporaryDirectory() as temporary:
            login = XiaomiQrLogin(session)
            challenge = login.start(Path(temporary) / "qr.png", 300)
            credentials = login.wait(challenge)
            self.assertEqual(credentials.user_id, "user")
            self.assertEqual(credentials.pass_token, "token")
            self.assertEqual(len(credentials.device_id), 16)

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
