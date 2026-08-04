from __future__ import annotations

import tempfile
import unittest
import subprocess
from pathlib import Path

from features.primary_page_settings import (
    build_page_settings_assets,
    build_page_settings_objects,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FONTS = REPO_ROOT / "env/fonts"
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

    def test_device_objects_include_save_load_and_factory_reset(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            result = build_page_settings_objects(
                Path(selected),
                FONTS,
                assembler=Path("/opt/homebrew/bin/riscv64-elf-as"),
                compiler=Path("/opt/homebrew/bin/riscv64-elf-gcc"),
            )
            symbols = subprocess.run(
                ["/opt/homebrew/bin/riscv64-elf-nm", *map(str, result.objects)],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        self.assertIn("ap01_page_settings_load_mask", symbols)
        self.assertIn("ap01_page_settings_save_mask", symbols)
        self.assertIn("ap01_page_settings_reset", symbols)

if __name__ == "__main__":
    unittest.main()
