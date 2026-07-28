from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from core.firmware_payload_space import (
    PAYLOAD_CAPACITY,
    PAYLOAD_END,
    PAYLOAD_START,
    inspect_payload_space,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE = REPO_ROOT / "artifacts/firmware/opt-setting.bin"


class FirmwarePayloadSpaceTests(unittest.TestCase):
    def test_fixed_space_is_aligned_and_bounded(self) -> None:
        self.assertEqual(PAYLOAD_START % 16, 0)
        self.assertEqual(PAYLOAD_END - PAYLOAD_START, PAYLOAD_CAPACITY)
        self.assertEqual(PAYLOAD_CAPACITY, 60_934)

    def test_real_stage_produces_deterministic_lossless_resource(self) -> None:
        if (
            not STAGE.is_file()
            or not shutil.which("gifsicle")
            or not shutil.which("ffmpeg")
        ):
            self.skipTest("本机没有阶段固件或固定动图工具")
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected)
            document = inspect_payload_space(
                STAGE,
                root / "optimized.gif",
                root / "report.json",
                tool_revision={"commit": "test", "scoped_code_dirty": False},
            )

        self.assertTrue(document["resource"]["pixel_and_timing_equivalent"])
        self.assertTrue(document["resource"]["independent_decoder_equivalent"])
        self.assertEqual(document["payload_space"]["capacity"], 60_934)
        self.assertTrue(document["gates"]["payload_candidate_space_ready"])
        self.assertFalse(document["gates"]["patch_plan_allowed"])


if __name__ == "__main__":
    unittest.main()
