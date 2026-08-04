from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from features.primary_page_settings import (
    build_page_settings_assets,
    build_page_settings_objects,
)
from features.primary_page_settings.build import PrimaryPageSettingsBuildError


REPO_ROOT = Path(__file__).resolve().parents[2]
FONTS = REPO_ROOT / "env/fonts"
OFFICIAL = REPO_ROOT / (
    "env/firmware-inputs/"
    "8a721fc8ef25458d415b2460e4a251e0503a82f7743fdff85b12612190e5c1cb/"
    "ap01-1.0.2_0031.bin"
)


class PrimaryPageSettingsTests(unittest.TestCase):
    def test_assets_are_deterministic_and_fit_small_overlay_budget(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            first = build_page_settings_assets(FONTS, root / "first")
            second = build_page_settings_assets(FONTS, root / "second")
        self.assertEqual(
            [(item.key, item.size, item.sha256) for item in first],
            [(item.key, item.size, item.sha256) for item in second],
        )
        self.assertLess(sum(item.size for item in first), 12_000)

    def test_device_objects_are_blocked_until_stock_alignment_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            output = Path(selected) / "output"
            with self.assertRaisesRegex(
                PrimaryPageSettingsBuildError,
                "原厂逐指令对齐门禁未通过",
            ):
                build_page_settings_objects(
                    output,
                    FONTS,
                    official_firmware=OFFICIAL,
                    assembler=Path("/not-invoked/assembler"),
                    compiler=Path("/not-invoked/compiler"),
                )
            self.assertFalse(output.exists())

    def test_device_object_gate_rejects_an_unknown_firmware_first(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            unknown = root / "unknown.bin"
            unknown.write_bytes(b"BFNP")
            with self.assertRaisesRegex(
                PrimaryPageSettingsBuildError,
                "原厂固件基线长度不匹配",
            ):
                build_page_settings_objects(
                    root / "output",
                    FONTS,
                    official_firmware=unknown,
                    assembler=Path("/not-invoked/assembler"),
                    compiler=Path("/not-invoked/compiler"),
                )

    def test_device_object_gate_rejects_changed_same_size_firmware(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            firmware = bytearray(OFFICIAL.read_bytes())
            firmware[-1] ^= 1
            changed = root / "changed.bin"
            changed.write_bytes(firmware)
            with self.assertRaisesRegex(
                PrimaryPageSettingsBuildError,
                "原厂固件基线完整文件指纹不匹配",
            ):
                build_page_settings_objects(
                    root / "output",
                    FONTS,
                    official_firmware=changed,
                    assembler=Path("/not-invoked/assembler"),
                    compiler=Path("/not-invoked/compiler"),
                )

    def test_persistence_uses_reviewed_stock_write_mode(self) -> None:
        source = (REPO_ROOT / "features/primary_page_settings/persistence.c").read_text(
            encoding="utf-8"
        )
        self.assertIn("#define AP01_O_WRONLY_CREAT_TRUNC 38", source)
        self.assertNotIn("AP01_O_RDWR_CREAT_TRUNC", source)

if __name__ == "__main__":
    unittest.main()
