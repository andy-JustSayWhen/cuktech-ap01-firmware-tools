from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from features.offline_firmware_build import BuildGateError, load_patch_plan
from features.settings_menu_wrap import (
    DRAFT_PLAN_STATUS,
    PATCHES,
    assemble_and_verify,
    build_draft_plan,
    write_draft_plan,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_BASELINE = Path(
    "/Users/mac/Desktop/cuktech-ap01-firmware-artifacts/original/"
    "ap01-1.0.2_0031.bin"
)


class SettingsMenuWrapTests(unittest.TestCase):
    def test_patch_definitions_are_ordered_equal_length_and_non_overlapping(self) -> None:
        previous_end = 0
        for patch in PATCHES:
            self.assertGreaterEqual(patch.offset, previous_end)
            self.assertEqual(
                len(patch.expected_before),
                len(patch.expected_replacement),
            )
            self.assertEqual(
                patch.runtime_address,
                patch.offset + 0x9FFFF000,
            )
            previous_end = patch.end

    def test_fixed_toolchain_reproduces_all_reviewed_bytes(self) -> None:
        report = assemble_and_verify()

        self.assertEqual(report["version"], "2.46.1")
        self.assertEqual(set(report["replacements"]), {patch.offset for patch in PATCHES})

    @unittest.skipUnless(REAL_BASELINE.is_file(), "真实原厂基线不在本机")
    def test_real_baseline_matches_every_old_byte_assertion(self) -> None:
        document = build_draft_plan(
            REAL_BASELINE,
            tool_revision={"commit": "test", "scoped_code_dirty": True},
        )

        self.assertEqual(document["status"], DRAFT_PLAN_STATUS)
        self.assertEqual(document["review"]["patch_count"], 6)
        self.assertFalse(document["review"]["firmware_output_allowed"])
        self.assertEqual(len(document["patches"]), 6)

    @unittest.skipUnless(REAL_BASELINE.is_file(), "真实原厂基线不在本机")
    def test_draft_plan_cannot_pass_offline_build_approval_gate(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            plan_path = Path(selected) / "settings-menu-wrap-draft.json"
            write_draft_plan(
                REAL_BASELINE,
                plan_path,
                tool_revision={"commit": "test", "scoped_code_dirty": True},
            )

            with self.assertRaisesRegex(BuildGateError, "尚未明确批准"):
                load_patch_plan(plan_path, REPO_ROOT)


if __name__ == "__main__":
    unittest.main()
