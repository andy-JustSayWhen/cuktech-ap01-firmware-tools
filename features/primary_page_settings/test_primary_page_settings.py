from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from features.primary_page_settings import (
    build_page_settings_assets,
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

if __name__ == "__main__":
    unittest.main()
