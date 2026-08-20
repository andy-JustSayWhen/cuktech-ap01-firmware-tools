from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from features.official_firmware_source import login as login_module
from features.official_firmware_source.login import LoginChallenge, XiaomiQrLogin
from features.official_firmware_source.xiaomi_cloud import _read_env_file


class FakeResponse:
    def __init__(self, payload: bytes, status: int = 200) -> None:
        self.content = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.headers: dict[str, str] = {}
        self.responses = responses

    def get(self, *args: object, **kwargs: object) -> FakeResponse:
        return self.responses.pop(0)


class CompletedLogin:
    def start(self, qr_output: Path, requested_timeout: float) -> LoginChallenge:
        qr_output.parent.mkdir(parents=True, exist_ok=True)
        qr_output.write_bytes(b"PNG")
        return LoginChallenge("qr", "poll", requested_timeout)

    def wait(self, challenge: LoginChallenge) -> dict[str, str]:
        return {
            "CUKTECH_MI_USER_ID": "10001",
            "CUKTECH_MI_PASS_TOKEN": "secret",
            "CUKTECH_MI_DEVICE_ID": "DEVICE",
        }


class FakeClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def ap01_device(self) -> dict[str, str]:
        return {"model": login_module.MODEL}


class XiaomiQrLoginTests(unittest.TestCase):
    def test_qr_login_downloads_image_and_returns_account_values(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    b'&&&START&&&{"qr":"https://example.test/qr",'
                    b'"lp":"https://example.test/poll","timeout":60}'
                ),
                FakeResponse(b"PNG"),
                FakeResponse(
                    b'&&&START&&&{"userId":"10001","passToken":"secret"}'
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            qr = Path(directory) / "login.png"
            login = XiaomiQrLogin(session=session)
            challenge = login.start(qr, 30)
            credentials = login.wait(challenge)
            self.assertEqual(qr.read_bytes(), b"PNG")
            self.assertEqual(credentials["CUKTECH_MI_USER_ID"], "10001")
            self.assertEqual(credentials["CUKTECH_MI_PASS_TOKEN"], "secret")
            self.assertEqual(len(credentials["CUKTECH_MI_DEVICE_ID"]), 16)

    def test_login_saves_credentials_without_user_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / "env" / "mi-cloud.env"
            qr_output = root / "artifacts" / "login.png"
            announced: list[Path] = []
            with patch.object(login_module, "XiaomiCloudClient", FakeClient):
                result = login_module.ensure_login(
                    env_file,
                    qr_output,
                    timeout=30,
                    announce_qr=announced.append,
                    login=CompletedLogin(),
                )
            values = _read_env_file(env_file)
            self.assertFalse(result.reused_existing)
            self.assertEqual(announced, [qr_output])
            self.assertEqual(values["CUKTECH_MI_USER_ID"], "10001")
            self.assertEqual(values["CUKTECH_MI_PASS_TOKEN"], "secret")
            self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)

    def test_login_reuses_existing_project_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / "mi-cloud.env"
            env_file.write_text(
                'CUKTECH_MI_USER_ID="10001"\n'
                'CUKTECH_MI_PASS_TOKEN="secret"\n'
                'CUKTECH_MI_CREDENTIALS="outside.json"\n',
                encoding="utf-8",
            )
            with patch.object(login_module, "XiaomiCloudClient", FakeClient):
                result = login_module.ensure_login(
                    env_file,
                    root / "login.png",
                    timeout=30,
                    announce_qr=lambda path: self.fail("不应生成二维码"),
                )
            self.assertTrue(result.reused_existing)
            self.assertEqual(result.model, login_module.MODEL)

    def test_new_login_removes_obsolete_external_credentials_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / "mi-cloud.env"
            env_file.write_text(
                'CUKTECH_MI_CREDENTIALS="outside.json"\n', encoding="utf-8"
            )
            with patch.object(login_module, "XiaomiCloudClient", FakeClient):
                login_module.ensure_login(
                    env_file,
                    root / "login.png",
                    timeout=30,
                    announce_qr=lambda path: None,
                    login=CompletedLogin(),
                )
            self.assertNotIn("CUKTECH_MI_CREDENTIALS", env_file.read_text())


if __name__ == "__main__":
    unittest.main()
