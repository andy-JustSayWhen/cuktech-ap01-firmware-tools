from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from features.web_firmware_flash.release import ReleaseError, build_release


REPO = Path(__file__).resolve().parents[2]


class ReleaseTests(unittest.TestCase):
    def test_same_package_contains_both_launchers_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "release"
            report = build_release(REPO, output)
            self.assertTrue((output / "启动 AP01 刷机.command").is_file())
            self.assertTrue((output / "启动 AP01 刷机.cmd").is_file())
            self.assertTrue((output / "FILE-MANIFEST.json").is_file())
            self.assertGreater(report.file_count, 8)

    def test_existing_output_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "release"
            output.mkdir()
            with self.assertRaises(ReleaseError):
                build_release(REPO, output)


if __name__ == "__main__":
    unittest.main()
