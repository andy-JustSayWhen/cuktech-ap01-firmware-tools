from __future__ import annotations

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

from features.agents_dashboard.result_package import load_or_create_credentials
from features.agents_dashboard_firmware.sync_build import build_sync_payload
from features.primary_page_settings import (
    REQUIRED_SYMBOLS,
    apply_page_settings_patches,
    build_page_settings_assets,
    build_page_settings_objects,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FONTS = REPO_ROOT / "env/fonts"
STAGE = REPO_ROOT / "artifacts/firmware/opt-setting.bin"
CONFIG = REPO_ROOT / "env/agents-dashboard-device.json"
ASSEMBLER = Path("/opt/homebrew/bin/riscv64-elf-as")
COMPILER = Path("/opt/homebrew/bin/riscv64-elf-gcc")


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

    def test_real_objects_link_with_current_sync_payload(self) -> None:
        if not STAGE.is_file() or not CONFIG.is_file():
            self.skipTest("本机没有已验收阶段固件或设备配置")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            objects = build_page_settings_objects(
                root / "settings",
                FONTS,
                assembler=ASSEMBLER,
                compiler=COMPILER,
            )
            router = root / "combined-primary-key-event.o"
            subprocess.run(
                [
                    str(ASSEMBLER),
                    "-march=rv32imac",
                    "-mabi=ilp32",
                    "-o",
                    str(router),
                    str(REPO_ROOT / "app/combined_primary_key_event.S"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = build_sync_payload(
                STAGE,
                root / "payload",
                load_or_create_credentials(CONFIG),
                tool_revision={"commit": "test", "scoped_code_dirty": False},
                extra_objects=(*objects.objects, router),
                required_extra_symbols=(
                    *REQUIRED_SYMBOLS,
                    "ap01_agents_detail_active",
                    "ap01_combined_primary_key_event",
                ),
            )
            candidate = bytearray(STAGE.read_bytes())
            ranges = apply_page_settings_patches(candidate, result.symbols)
        self.assertEqual(len(ranges), 4)
        self.assertLess(result.size, 60_934)
        self.assertNotEqual(
            hashlib.sha256(candidate).hexdigest(),
            hashlib.sha256(STAGE.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
