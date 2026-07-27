from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from features.offline_firmware_build import BuildGateError, load_patch_plan
from features.settings_menu_wrap import (
    CODE_GAP_END,
    CODE_GAP_START,
    DRAFT_PLAN_STATUS,
    PATCHES,
    PRESERVED_LOG_RANGES,
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
        self.assertEqual(
            [patch.offset for patch in PATCHES],
            [0x01C008, 0x0F919E, 0x0F976A],
        )
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
            for log_start, log_end, _name in PRESERVED_LOG_RANGES:
                self.assertFalse(
                    patch.offset < log_end and log_start < patch.end,
                )
            previous_end = patch.end

    def test_fixed_toolchain_reproduces_all_reviewed_bytes(self) -> None:
        report = assemble_and_verify()

        self.assertEqual(report["version"], "2.46.1")
        self.assertEqual(set(report["replacements"]), {patch.offset for patch in PATCHES})
        self.assertEqual(
            report["verified_control_flow"],
            [
                {"source_hex": "0xa001b012", "target_hex": "0xa00f80d8"},
                {"source_hex": "0xa001b01e", "target_hex": "0xa00f80d8"},
                {"source_hex": "0xa001b026", "target_hex": "0xa00f81a2"},
                {"source_hex": "0xa001b03c", "target_hex": "0xa00f3d5a"},
                {"source_hex": "0xa001b040", "target_hex": "0xa00f80d8"},
                {"source_hex": "0xa001b04e", "target_hex": "0xa00f80d8"},
                {"source_hex": "0xa001b05a", "target_hex": "0xa00f80d8"},
                {"source_hex": "0xa001b060", "target_hex": "0xa00f876e"},
                {"source_hex": "0xa001b076", "target_hex": "0xa00f3d5a"},
                {"source_hex": "0xa001b07a", "target_hex": "0xa00f80d8"},
                {"source_hex": "0xa00f819e", "target_hex": "0xa001b008"},
                {"source_hex": "0xa00f876a", "target_hex": "0xa001b044"},
            ],
        )

    @unittest.skipUnless(REAL_BASELINE.is_file(), "真实原厂基线不在本机")
    def test_reviewed_function_gap_matches_exact_baseline(self) -> None:
        firmware = REAL_BASELINE.read_bytes()

        self.assertEqual(
            firmware[CODE_GAP_START:CODE_GAP_END],
            b"\x00" * (CODE_GAP_END - CODE_GAP_START),
        )
        self.assertEqual(firmware[CODE_GAP_START - 2 : CODE_GAP_START], b"\x82\x80")
        self.assertEqual(firmware[CODE_GAP_END : CODE_GAP_END + 4], bytes.fromhex("23221500"))
        self.assertEqual(PATCHES[0].offset, CODE_GAP_START)
        self.assertEqual(PATCHES[0].end, 0x01C07E)

    @unittest.skipUnless(REAL_BASELINE.is_file(), "真实原厂基线不在本机")
    def test_candidate_bytes_preserve_every_reviewed_log_region(self) -> None:
        original = REAL_BASELINE.read_bytes()
        candidate = bytearray(original)
        for patch in PATCHES:
            self.assertEqual(
                original[patch.offset : patch.end],
                patch.expected_before,
            )
            candidate[patch.offset : patch.end] = patch.expected_replacement

        for start, end, name in PRESERVED_LOG_RANGES:
            with self.subTest(log=name):
                self.assertEqual(candidate[start:end], original[start:end])

    @unittest.skipUnless(REAL_BASELINE.is_file(), "真实原厂基线不在本机")
    def test_real_baseline_builds_three_range_draft(self) -> None:
        document = build_draft_plan(
            REAL_BASELINE,
            tool_revision={"commit": "test", "scoped_code_dirty": True},
        )

        self.assertEqual(document["status"], DRAFT_PLAN_STATUS)
        self.assertEqual(document["review"]["patch_count"], 3)
        self.assertFalse(document["review"]["firmware_output_allowed"])
        self.assertFalse(document["review"]["logging_changed"])
        self.assertEqual(len(document["patches"]), 3)
        self.assertEqual(document["review"]["code_gap"]["used_bytes"], 118)

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
