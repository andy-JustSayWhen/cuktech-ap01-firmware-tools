from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from features.web_firmware_flash.firmware_inspection import (
    FirmwareInspectionError,
    inspect_release_firmware,
)


class FirmwareInspectionTests(unittest.TestCase):
    def _candidate(self, directory: Path) -> Path:
        path = directory / "candidate.bin"
        path.write_bytes(b"BFNP" + bytes(6_804_520 - 4))
        payload = path.read_bytes()
        path.with_suffix(".bin.manifest.json").write_text(
            json.dumps(
                {
                    "kind": "optimized",
                    "model": "njcuk.enstor.ap01",
                    "version": "1.0.2_0031",
                    "size": len(payload),
                    "md5": hashlib.md5(payload).hexdigest(),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "install_approved": False,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_candidate_must_match_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inspected = inspect_release_firmware(root, self._candidate(root))
            self.assertEqual(inspected.kind, "optimized")
            self.assertFalse(inspected.install_approved)

    def test_changed_candidate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = self._candidate(root)
            with path.open("r+b") as stream:
                stream.seek(8)
                stream.write(b"x")
            with self.assertRaises(FirmwareInspectionError):
                inspect_release_firmware(root, path)

    def test_outside_release_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as other:
            path = self._candidate(Path(other))
            with self.assertRaises(FirmwareInspectionError):
                inspect_release_firmware(Path(allowed), path)


if __name__ == "__main__":
    unittest.main()
