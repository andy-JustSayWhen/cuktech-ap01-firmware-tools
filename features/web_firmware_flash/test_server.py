from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from features.web_firmware_flash.server import WebFlashServer


class _Workflow:
    def snapshot(self):
        return {"phase": "prepare", "status": "ready"}

    def preflight(self):
        return {"phase": "device", "status": "ready"}

    def export(self, operation_id):
        if operation_id != "operation":
            raise RuntimeError("操作不存在")
        return {"operation_id": operation_id, "device": {"identity": "masked"}}


class WebFlashServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = WebFlashServer(("127.0.0.1", 0), _Workflow(), access_token="access-token")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _connection(self):
        return http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)

    def test_access_token_creates_cookie_without_exposing_it_to_api(self) -> None:
        connection = self._connection()
        connection.request("GET", "/?access=access-token")
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        cookie = response.getheader("Set-Cookie").split(";", 1)[0]
        response.read()
        connection.request("GET", "/api/v1/session", headers={"Cookie": cookie})
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertNotIn("access-token", response.read().decode())

    def test_write_requires_cookie_and_exact_local_origin(self) -> None:
        connection = self._connection()
        connection.request("POST", "/api/v1/preflight", body=b"{}", headers={"Content-Length": "2"})
        self.assertEqual(connection.getresponse().status, 401)

        connection = self._connection()
        connection.request("GET", "/?access=access-token")
        response = connection.getresponse()
        cookie = response.getheader("Set-Cookie").split(";", 1)[0]
        response.read()
        connection.request(
            "POST",
            "/api/v1/preflight",
            body=b"{}",
            headers={"Content-Length": "2", "Cookie": cookie, "Origin": "https://invalid"},
        )
        self.assertEqual(connection.getresponse().status, 403)

        connection = self._connection()
        connection.request(
            "POST",
            "/api/v1/preflight",
            body=b"{}",
            headers={
                "Content-Length": "2",
                "Content-Type": "application/json",
                "Cookie": cookie,
                "Origin": f"http://127.0.0.1:{self.server.server_port}",
            },
        )
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())["phase"], "device")

    def test_server_rejects_non_loopback_bind(self) -> None:
        with self.assertRaises(ValueError):
            WebFlashServer(("0.0.0.0", 0), _Workflow())

    def test_result_export_is_authorized_and_downloadable(self) -> None:
        connection = self._connection()
        connection.request("GET", "/?access=access-token")
        response = connection.getresponse()
        cookie = response.getheader("Set-Cookie").split(";", 1)[0]
        response.read()
        connection.request("GET", "/api/v1/operations/operation/export", headers={"Cookie": cookie})
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertIn("attachment", response.getheader("Content-Disposition"))
        self.assertEqual(json.loads(response.read())["device"]["identity"], "masked")


if __name__ == "__main__":
    unittest.main()
