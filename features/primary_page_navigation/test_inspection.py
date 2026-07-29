from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.firmware_image import AP01_1_0_2_0031, prepare_read_only_copy
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
            root = Path(selected)
            original = prepare_read_only_copy(
                ORIGINAL,
                root / "original",
                expected_size=AP01_1_0_2_0031.size,
                expected_sha256=AP01_1_0_2_0031.sha256,
                expected_md5=AP01_1_0_2_0031.md5,
            ).path
            stage = prepare_read_only_copy(
                STAGE,
                root / "stage",
                expected_size=6_804_520,
                expected_sha256=(
                    "348d0843ac3f3f380eb155170c4104fd"
                    "8467a018ddfd13670d67be998f269dc1"
                ),
            ).path
            report_path = root / "navigation.json"
            document = inspect_primary_page_navigation(
                original,
                stage,
                report_path,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )

        self.assertEqual(len(document["window_create_calls"]), 7)
        self.assertTrue(document["gates"]["page_registration_evidence_ready"])
        self.assertTrue(document["gates"]["dynamic_navigation_evidence_ready"])
        self.assertFalse(document["gates"]["patch_plan_allowed"])


if __name__ == "__main__":
    unittest.main()
