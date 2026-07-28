from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from features.agents_dashboard_firmware import (
    AgentsDashboardFirmwareError,
    build_observation_firmware,
    build_page_registration_payload,
)
from features.agents_dashboard_firmware.build import OBSERVATION_OUTPUT_FILENAME


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
        self.assertTrue(document["gates"]["fallback_descriptors_valid"])
        self.assertTrue(document["gates"]["key_callback_old_bytes_match"])
        self.assertTrue(document["gates"]["key_event_entry_present"])
        self.assertTrue(document["gates"]["current_index_getter_present"])
        self.assertTrue(document["gates"]["initial_x_call_present"])
        self.assertFalse(document["gates"]["firmware_output_allowed"])
        self.assertEqual(document["payload"]["size"], 27_496)
        self.assertEqual(document["payload"]["remaining"], 33_438)
        self.assertEqual(len(document["fallback_assets"]), 4)
        self.assertEqual(
            document["draft_modifications"][0]["expected_before_hex"],
            "2ae30500",
        )
        self.assertEqual(
            document["draft_modifications"][2]["expected_before_hex"],
            "5285eff02079",
        )
        self.assertEqual(
            document["draft_modifications"][4]["expected_before_hex"],
            "b7c50ba0",
        )
        self.assertEqual(
            document["draft_modifications"][5]["expected_before_hex"],
            "9385e5fe",
        )

    def test_unapproved_position_candidate_is_not_frozen(self) -> None:
        if not STAGE.is_file() or not shutil.which("riscv64-elf-as"):
            self.skipTest("本机没有阶段固件或固定编译工具")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            output = root / OBSERVATION_OUTPUT_FILENAME
            manifest = root / "manifest.json"
            with self.assertRaisesRegex(
                AgentsDashboardFirmwareError,
                "output_sha256",
            ):
                build_observation_firmware(
                    STAGE,
                    output,
                    manifest,
                    root / "build",
                    tool_revision={"commit": "test", "scoped_code_dirty": False},
                )
            self.assertFalse(output.exists())
            self.assertFalse(manifest.exists())


if __name__ == "__main__":
    unittest.main()
