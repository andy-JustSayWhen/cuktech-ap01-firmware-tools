from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from .result_package import (
    HEADER_SIZE,
    DeviceCredentials,
    ResultPackageError,
    decode_package,
    encode_package,
    load_credentials,
    load_or_create_credentials,
    png_to_device_gif,
)
from .bridge import BridgeState


def _gif(color: tuple[int, int, int]) -> bytes:
    first = Image.new("RGB", (320, 240), color)
    second = first.copy()
    second.putpixel((319, 239), ((color[0] + 1) % 256, color[1], color[2]))
    target = io.BytesIO()
    first.save(
        target,
        format="GIF",
        save_all=True,
        append_images=[second],
        duration=(1000, 1000),
        loop=0,
        optimize=True,
        disposal=2,
    )
    return target.getvalue()


class ResultPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.credentials = DeviceCredentials(
            device_id="1234abcd",
            access_token="0123456789abcdef",
            secret_key=bytes(range(32)),
        )
        self.pages = tuple(
            _gif(color)
            for color in ((0, 0, 0), (10, 20, 30), (40, 50, 60), (70, 80, 90))
        )

    def test_four_pages_round_trip(self) -> None:
        package = encode_package(
            self.pages,
            generation=7,
            generated_at=1_700_000_000,
            credentials=self.credentials,
        )
        decoded = decode_package(package, self.credentials)
        self.assertEqual(decoded.generation, 7)
        self.assertEqual(decoded.device_id, "1234abcd")
        self.assertEqual(decoded.pages, self.pages)
        self.assertEqual(package[:4], b"APAG")
        self.assertEqual(len(package), HEADER_SIZE + sum(map(len, self.pages)))

    def test_changed_body_fails_authorization(self) -> None:
        package = bytearray(
            encode_package(
                self.pages,
                generation=8,
                generated_at=1_700_000_001,
                credentials=self.credentials,
            )
        )
        package[-2] ^= 1
        with self.assertRaisesRegex(ResultPackageError, "授权校验失败"):
            decode_package(bytes(package), self.credentials)

    def test_wrong_device_fails_closed(self) -> None:
        package = encode_package(
            self.pages,
            generation=9,
            generated_at=1_700_000_002,
            credentials=self.credentials,
        )
        other = DeviceCredentials(
            device_id="feedbeef",
            access_token=self.credentials.access_token,
            secret_key=self.credentials.secret_key,
        )
        with self.assertRaisesRegex(ResultPackageError, "设备代号不匹配"):
            decode_package(package, other)

    def test_credentials_are_reused_and_private(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "device.json"
            first = load_or_create_credentials(path)
            second = load_or_create_credentials(path)
            self.assertEqual(first, second)
            self.assertEqual(load_credentials(path), first)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_normal_load_refuses_to_create_missing_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "device.json"
            with self.assertRaisesRegex(ResultPackageError, "不存在"):
                load_credentials(path)
            self.assertFalse(path.exists())

    def test_png_conversion_is_two_frame_device_gif(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            target = root / "target.gif"
            Image.new("RGB", (320, 240), (1, 2, 3)).save(source)
            payload = png_to_device_gif(source, target)
            self.assertTrue(payload.startswith(b"GIF89a"))
            self.assertTrue(payload.endswith(b"\x3b"))
            with Image.open(target) as image:
                self.assertEqual(image.size, (320, 240))
                self.assertGreaterEqual(image.n_frames, 2)
            self.assertEqual(hashlib.sha256(payload).digest_size, 32)

    def test_request_authorization_is_one_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = BridgeState(
                self.credentials,
                Path(directory),
                Path(directory),
            )
            query = {
                "d": [self.credentials.device_id[-4:]],
                "t": [self.credentials.access_token[-12:]],
                "n": ["1700000000"],
            }
            self.assertTrue(state.authorize(query))
            self.assertFalse(state.authorize(query))
            self.assertFalse(
                state.authorize(
                    {
                        **query,
                        "n": ["1700000001"],
                        "t": ["0000000000000000"],
                    }
                )
            )

    def test_bridge_refresh_uses_selected_data_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex_home = root / "codex"
            cache = root / "cache"
            state = BridgeState(
                self.credentials,
                root / "output",
                root / "fonts",
                codex_home=codex_home,
                cache_directory=cache,
            )
            sources = {
                "quota": True,
                "reset_cards": False,
                "profile": True,
                "local_sessions": True,
            }
            with patch(
                "features.agents_dashboard.bridge.publish_current_result",
                return_value={"data_sources": sources},
            ) as publish:
                state.refresh()
            publish.assert_called_once_with(
                root / "output",
                root / "fonts",
                self.credentials,
                codex_home=codex_home,
                cache_directory=cache,
            )
            self.assertEqual(state.data_sources, sources)

    def test_health_serves_valid_old_result_while_refresh_is_degraded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            package = encode_package(
                self.pages,
                generation=10,
                generated_at=1_700_000_003,
                credentials=self.credentials,
            )
            (output / "agents-dashboard.apag").write_bytes(package)
            state = BridgeState(self.credentials, output, output)
            state.error = "refresh failed"
            health = json.loads(state.health())
            self.assertTrue(health["ok"])
            self.assertTrue(health["degraded"])
            self.assertEqual(health["error"], "refresh failed")


if __name__ == "__main__":
    unittest.main()
