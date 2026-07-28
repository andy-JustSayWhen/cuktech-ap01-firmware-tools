from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from features.primary_page_navigation import (
    decode_jal_target,
    inspect_primary_page_navigation,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = REPO_ROOT / "artifacts/firmware/original/ap01-1.0.2_0031.bin"
STAGE = REPO_ROOT / "artifacts/firmware/opt-setting.bin"


class PrimaryPageNavigationTests(unittest.TestCase):
    def test_direct_jump_decoder_recovers_reviewed_target(self) -> None:
        target, destination_register = decode_jal_target(
            bytes.fromhex("eff0500c"),
            0xA00B2602,
        )

        self.assertEqual(target, 0xA00C1EC6)
        self.assertEqual(destination_register, 1)

    def test_real_original_and_accepted_stage_match_navigation_contract(self) -> None:
        if not ORIGINAL.is_file() or not STAGE.is_file():
            self.skipTest("本机没有只读原厂固件或已验收阶段成品")
        with tempfile.TemporaryDirectory() as selected:
            report_path = Path(selected) / "navigation.json"
            document = inspect_primary_page_navigation(
                ORIGINAL,
                STAGE,
                report_path,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )

        self.assertEqual(len(document["window_create_calls"]), 7)
        self.assertTrue(document["gates"]["page_registration_evidence_ready"])
        self.assertTrue(document["gates"]["dynamic_navigation_evidence_ready"])
        self.assertFalse(document["gates"]["patch_plan_allowed"])


if __name__ == "__main__":
    unittest.main()
