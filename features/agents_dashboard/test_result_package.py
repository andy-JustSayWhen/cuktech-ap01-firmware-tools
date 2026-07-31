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
    ResultPackageError,
    decode_package,
    encode_package,
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
        self.pages = tuple(
            _gif(color)
            for color in ((0, 0, 0), (10, 20, 30), (40, 50, 60), (70, 80, 90))
        )

    def test_four_pages_round_trip(self) -> None:
        package = encode_package(
            self.pages,
            generation=7,
            generated_at=1_700_000_000,
        )
        decoded = decode_package(package)
        self.assertEqual(decoded.generation, 7)
        self.assertEqual(decoded.pages, self.pages)
        self.assertEqual(package[:4], b"APAG")
        self.assertEqual(package[4:8], b"\x02\x00\x40\x00")
        self.assertEqual(len(package), HEADER_SIZE + sum(map(len, self.pages)))

    def test_changed_body_fails_page_check(self) -> None:
        package = bytearray(
            encode_package(
                self.pages,
                generation=8,
                generated_at=1_700_000_001,
            )
        )
        package[-2] ^= 1
        with self.assertRaisesRegex(ResultPackageError, "文件指纹无效"):
            decode_package(bytes(package))

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

    def test_bridge_refresh_uses_selected_data_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex_home = root / "codex"
            cache = root / "cache"
            state = BridgeState(
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
            )
            (output / "agents-dashboard.apag").write_bytes(package)
            state = BridgeState(output, output)
            state.error = "refresh failed"
            health = json.loads(state.health())
            self.assertTrue(health["ok"])
            self.assertTrue(health["degraded"])
            self.assertEqual(health["error"], "refresh failed")


if __name__ == "__main__":
    unittest.main()
