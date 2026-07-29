from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import features.settings_menu_wrap.patch_plan as patch_plan_module
from core.firmware_image import AP01_1_0_2_0031, prepare_read_only_copy
from features.offline_firmware_build import BuildGateError, load_patch_plan
from features.settings_menu_wrap import (
    APPROVAL_LIMIT,
    APPROVAL_RECORD_PATH,
    APPROVED_PLAN_STATUS,
    CODE_GAP_END,
    CODE_GAP_START,
    DRAFT_PLAN_STATUS,
    PATCHES,
    PRESERVED_LOG_RANGES,
    SettingsMenuWrapError,
    assemble_and_verify,
    build_approved_plan,
    build_draft_plan,
    write_approved_plan,
    write_draft_plan,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_BASELINE_SOURCE = (
    REPO_ROOT / "artifacts/firmware/original/ap01-1.0.2_0031.bin"
)


class SettingsMenuWrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not REAL_BASELINE_SOURCE.is_file():
            raise unittest.SkipTest("真实原厂基线不在本机")
        cls._material_directory = tempfile.TemporaryDirectory()
        cls.real_baseline = prepare_read_only_copy(
            REAL_BASELINE_SOURCE,
            Path(cls._material_directory.name),
            expected_size=AP01_1_0_2_0031.size,
            expected_sha256=AP01_1_0_2_0031.sha256,
            expected_md5=AP01_1_0_2_0031.md5,
        ).path

    @classmethod
    def tearDownClass(cls) -> None:
        cls._material_directory.cleanup()

    def test_patch_definitions_are_ordered_equal_length_and_non_overlapping(self) -> None:
        self.assertEqual(
            [patch.offset for patch in PATCHES],
            [0x01C008, 0x0F919E, 0x0F976A, 0x108E20],
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
                {"source_hex": "0xa001b00c", "target_hex": "0xa00c5fe4"},
                {"source_hex": "0xa001b01c", "target_hex": "0xa00f80d8"},
                {"source_hex": "0xa001b028", "target_hex": "0xa00f80d8"},
                {"source_hex": "0xa001b030", "target_hex": "0xa00f81a2"},
                {"source_hex": "0xa001b03c", "target_hex": "0xa00c6dfe"},
                {"source_hex": "0xa001b052", "target_hex": "0xa00f3d5a"},
                {"source_hex": "0xa001b056", "target_hex": "0xa00f80d8"},
                {"source_hex": "0xa001b05e", "target_hex": "0xa00c5fe4"},
                {"source_hex": "0xa001b06e", "target_hex": "0xa00f80d8"},
                {"source_hex": "0xa001b07a", "target_hex": "0xa00f80d8"},
                {"source_hex": "0xa001b080", "target_hex": "0xa00f876e"},
                {"source_hex": "0xa001b08e", "target_hex": "0xa00c6dfe"},
                {"source_hex": "0xa001b0a4", "target_hex": "0xa00f3d5a"},
                {"source_hex": "0xa001b0a8", "target_hex": "0xa00f80d8"},
                {"source_hex": "0xa00f819e", "target_hex": "0xa001b008"},
                {"source_hex": "0xa00f876a", "target_hex": "0xa001b05a"},
                {"source_hex": "0xa0107e20", "target_hex": "0xa0107cbc"},
            ],
        )
        self.assertEqual(
            report["verified_list_count_loads"],
            [
                {"address_hex": "0xa001b008", "operands": "x10,8(x19)"},
                {"address_hex": "0xa001b010", "operands": "x21,x10"},
                {"address_hex": "0xa001b05a", "operands": "x10,8(x19)"},
                {"address_hex": "0xa001b062", "operands": "x21,x10"},
            ],
        )
        self.assertEqual(
            report["verified_position_sync_setup"],
            [
                {"address_hex": "0xa001b034", "operands": "x10,8(x19)"},
                {"address_hex": "0xa001b038", "operands": "x11,0"},
                {"address_hex": "0xa001b03a", "operands": "x12,0"},
                {"address_hex": "0xa001b084", "operands": "x10,8(x19)"},
                {"address_hex": "0xa001b088", "operands": "x11,x0,400"},
                {"address_hex": "0xa001b08c", "operands": "x12,0"},
            ],
        )

    def test_reviewed_function_gap_matches_exact_baseline(self) -> None:
        firmware = self.real_baseline.read_bytes()

        self.assertEqual(
            firmware[CODE_GAP_START:CODE_GAP_END],
            b"\x00" * (CODE_GAP_END - CODE_GAP_START),
        )
        self.assertEqual(firmware[CODE_GAP_START - 2 : CODE_GAP_START], b"\x82\x80")
        self.assertEqual(firmware[CODE_GAP_END : CODE_GAP_END + 4], bytes.fromhex("23221500"))
        self.assertEqual(PATCHES[0].offset, CODE_GAP_START)
        self.assertEqual(PATCHES[0].end, 0x01C0AC)

    def test_candidate_bytes_preserve_every_reviewed_log_region(self) -> None:
        original = self.real_baseline.read_bytes()
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

    def test_real_baseline_builds_four_range_draft(self) -> None:
        document = build_draft_plan(
            self.real_baseline,
            tool_revision={"commit": "test", "scoped_code_dirty": True},
        )

        self.assertEqual(document["status"], DRAFT_PLAN_STATUS)
        self.assertEqual(document["review"]["patch_count"], 4)
        self.assertFalse(document["review"]["firmware_output_allowed"])
        self.assertTrue(document["review"]["logging_changed"])
        self.assertIn("日志正文", document["review"]["logging_behavior_change"])
        self.assertEqual(len(document["patches"]), 4)
        self.assertEqual(document["review"]["code_gap"]["used_bytes"], 164)

    def test_draft_plan_cannot_pass_offline_build_approval_gate(self) -> None:
        with tempfile.TemporaryDirectory() as selected:
            plan_path = Path(selected) / "settings-menu-wrap-draft.json"
            write_draft_plan(
                self.real_baseline,
                plan_path,
                tool_revision={"commit": "test", "scoped_code_dirty": True},
            )

            with self.assertRaisesRegex(BuildGateError, "尚未明确批准"):
                load_patch_plan(plan_path, REPO_ROOT)

    def test_current_four_range_approval_matches_direction_filter_scope(self) -> None:
        document = build_approved_plan(
            self.real_baseline,
            tool_revision={"commit": "test", "scoped_code_dirty": True},
        )
        approval = json.loads(APPROVAL_RECORD_PATH.read_text(encoding="utf-8"))

        self.assertEqual(document["status"], APPROVED_PLAN_STATUS)
        self.assertTrue(document["review"]["firmware_output_allowed"])
        self.assertFalse(document["review"]["experimental_download_allowed"])
        self.assertFalse(document["review"]["installation_allowed"])
        self.assertEqual(document["review"]["patch_count"], 4)
        self.assertEqual(
            approval["installation_statement"],
            "批准第 23 节四区间，生成并刷入当前唯一 AP01",
        )

    def test_changed_approval_scope_is_rejected(self) -> None:
        approval = json.loads(APPROVAL_RECORD_PATH.read_text(encoding="utf-8"))
        approval["patch_count"] = 4
        approval["approval_limit"] = APPROVAL_LIMIT
        approval["scope_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as selected:
            changed_record = Path(selected) / "approval-record.json"
            changed_record.write_text(
                json.dumps(approval, ensure_ascii=False),
                encoding="utf-8",
            )
            with patch.object(
                patch_plan_module,
                "APPROVAL_RECORD_PATH",
                changed_record,
            ):
                with self.assertRaisesRegex(SettingsMenuWrapError, "必须重新审批"):
                    build_approved_plan(
                        self.real_baseline,
                        tool_revision={"commit": "test", "scoped_code_dirty": True},
                    )

    def test_matching_visual_sync_scope_writes_approved_plan(self) -> None:
        with tempfile.TemporaryDirectory(dir=patch_plan_module.MODULE_DIR) as selected:
            plan_path = Path(selected) / "settings-menu-wrap-approved.json"
            draft = build_draft_plan(
                self.real_baseline,
                tool_revision={"commit": "test", "scoped_code_dirty": True},
            )
            approval = json.loads(APPROVAL_RECORD_PATH.read_text(encoding="utf-8"))
            approval["patch_count"] = 4
            approval["approval_limit"] = APPROVAL_LIMIT
            approval["scope_sha256"] = patch_plan_module._approval_scope_sha256(draft)
            approval["approved_at_beijing"] = "test-only"
            matching_record = Path(selected) / "approval-record.json"
            matching_record.write_text(
                json.dumps(approval, ensure_ascii=False),
                encoding="utf-8",
            )
            with patch.object(
                patch_plan_module,
                "APPROVAL_RECORD_PATH",
                matching_record,
            ):
                write_approved_plan(
                    self.real_baseline,
                    plan_path,
                    tool_revision={"commit": "test", "scoped_code_dirty": True},
                )

            plan = load_patch_plan(plan_path, REPO_ROOT)
            self.assertEqual(plan.status, APPROVED_PLAN_STATUS)
            self.assertEqual(len(plan.patches), 4)


if __name__ == "__main__":
    unittest.main()
