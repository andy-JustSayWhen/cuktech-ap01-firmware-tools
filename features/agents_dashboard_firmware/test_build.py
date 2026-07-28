from __future__ import annotations

import shutil
import stat
import tempfile
import unittest
from pathlib import Path

from features.agents_dashboard_firmware import (
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
        self.assertTrue(document["gates"]["dynamic_primary_count_present"])
        self.assertTrue(document["gates"]["initial_x_call_present"])
        self.assertFalse(document["gates"]["firmware_output_allowed"])
        self.assertEqual(
            document["primary_navigation"]["normal_sequence"],
            [0, 3, 4, 5, 6, 7, 8],
        )
        self.assertEqual(
            document["primary_navigation"]["stock_conditional_port_indices"],
            [1, 2],
        )
        self.assertEqual(
            document["primary_navigation"]["stock_mijia_detail_index"],
            9,
        )
        self.assertEqual(document["payload"]["size"], 27_628)
        self.assertEqual(document["payload"]["remaining"], 33_306)
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

    def test_installed_dynamic_navigation_candidate_is_reproducible(self) -> None:
        if not STAGE.is_file() or not shutil.which("riscv64-elf-as"):
            self.skipTest("本机没有阶段固件或固定编译工具")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            output = root / OBSERVATION_OUTPUT_FILENAME
            manifest = root / "manifest.json"
            result = build_observation_firmware(
                STAGE,
                output,
                manifest,
                root / "build",
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )
            output_bytes = output.read_bytes()
            manifest_text = manifest.read_text(encoding="utf-8")
            output_mode = output.stat().st_mode

        self.assertEqual(len(output_bytes), STAGE.stat().st_size)
        self.assertEqual(result.output.name, OBSERVATION_OUTPUT_FILENAME)
        self.assertEqual(
            result.sha256,
            "2ef4305bd3f29873d7817a495097b074e06f62ba0189e4f35f0be65b77c55813",
        )
        self.assertIn('"outside_allowed_ranges_identical": true', manifest_text)
        self.assertFalse(output_mode & stat.S_IWUSR)


if __name__ == "__main__":
    unittest.main()
