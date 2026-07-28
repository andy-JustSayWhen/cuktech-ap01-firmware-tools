from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from features.agents_dashboard_firmware import build_page_registration_payload


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE = REPO_ROOT / "artifacts/firmware/opt-setting.bin"


class AgentsDashboardFirmwareTests(unittest.TestCase):
    def test_real_stage_builds_linked_page_registration_payload(self) -> None:
        if not STAGE.is_file() or not shutil.which("riscv64-elf-as"):
            self.skipTest("本机没有阶段固件或固定编译工具")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            document = build_page_registration_payload(
                STAGE,
                root / "build",
                root / "report.json",
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )

        self.assertEqual(document["payload"]["relocations"], 0)
        self.assertTrue(document["gates"]["payload_fits"])
        self.assertTrue(document["gates"]["required_callees_present"])
        self.assertFalse(document["gates"]["firmware_output_allowed"])
        self.assertEqual(
            document["draft_modifications"][0]["expected_before_hex"],
            "5285eff02079",
        )


if __name__ == "__main__":
    unittest.main()
