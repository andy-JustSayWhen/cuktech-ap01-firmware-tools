from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from core.firmware_image import (
    BaselineDefinition,
    ByteRange,
    recovery_crc,
    refresh_recovery_crc,
)
from features.optimized_firmware_build import (
    OptimizedFirmwareBuildError,
    StageBaselineDefinition,
    inspect_optimized_baseline,
)


def make_test_inputs() -> tuple[bytes, bytes, BaselineDefinition, StageBaselineDefinition]:
    size = 256
    trailer_offset = size - 40
    recovery_tag = b"0x5245434f56455259544147"
    original = bytearray(size)
    original[0:4] = b"BFNP"
    original[8:12] = b"FCFG"
    original[16:20] = b"PCFG"
    model = b"unit.model"
    original[40 : 40 + len(model)] = model
    original[80 : 80 + len(recovery_tag)] = recovery_tag
    original[trailer_offset : trailer_offset + len(recovery_tag)] = recovery_tag
    struct.pack_into(">I", original, trailer_offset + 32, size)
    original_crc = recovery_crc(original[:-4])
    struct.pack_into("<I", original, trailer_offset + 36, original_crc)
    original_bytes = bytes(original)
    original_definition = BaselineDefinition(
        model=model.decode("ascii"),
        version="test-version",
        size=size,
        md5=hashlib.md5(original_bytes).hexdigest(),
        sha256=hashlib.sha256(original_bytes).hexdigest(),
        header_markers=((0, b"BFNP"), (8, b"FCFG"), (16, b"PCFG")),
        model_offsets=(40,),
        recovery_tag=recovery_tag,
        recovery_tag_offsets=(80, trailer_offset),
        recovery_trailer_offset=trailer_offset,
        recovery_crc_value=original_crc,
        immutable_header_end=32,
    )
    stage = bytearray(original)
    stage[64:66] = b"\x01\x02"
    stage_crc = refresh_recovery_crc(stage, original_definition)
    stage_bytes = bytes(stage)
    stage_definition = StageBaselineDefinition(
        filename="opt-setting.bin",
        size=size,
        md5=hashlib.md5(stage_bytes).hexdigest(),
        sha256=hashlib.sha256(stage_bytes).hexdigest(),
        recovery_crc=stage_crc,
        approved_ranges=(
            ByteRange(64, 66),
            ByteRange(trailer_offset + 36, trailer_offset + 40),
        ),
    )
    return original_bytes, stage_bytes, original_definition, stage_definition


class OptimizedFirmwareBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (
            original,
            stage,
            self.original_definition,
            self.stage_definition,
        ) = make_test_inputs()
        self.original_path = self.root / "original.bin"
        self.stage_path = self.root / "opt-setting.bin"
        self.report_path = self.root / "inspection.json"
        self.original_path.write_bytes(original)
        self.stage_path.write_bytes(stage)
        self.original_path.chmod(0o444)
        self.stage_path.chmod(0o444)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def inspect(self) -> dict[str, object]:
        return inspect_optimized_baseline(
            self.original_path,
            self.stage_path,
            self.report_path,
            tool_revision={"commit": "test", "scoped_code_dirty": False},
            original_definition=self.original_definition,
            stage_definition=self.stage_definition,
        )

    def test_accepts_exact_stage_and_does_not_create_final_firmware(self) -> None:
        document = self.inspect()

        self.assertTrue(document["gates"]["optimized_baseline_ready"])
        self.assertFalse(document["gates"]["full_build_allowed"])
        self.assertFalse(document["final_output"]["created"])
        self.assertEqual(
            list(self.root.glob("ap01-1.0.2_0031-opt.bin")),
            [],
        )
        self.assertEqual(
            json.loads(self.report_path.read_text(encoding="utf-8"))["stage_input"][
                "sha256"
            ],
            self.stage_definition.sha256,
        )

    def test_rejects_writable_stage(self) -> None:
        self.stage_path.chmod(0o644)

        with self.assertRaisesRegex(OptimizedFirmwareBuildError, "只读"):
            self.inspect()

    def test_rejects_wrong_stage_identity(self) -> None:
        wrong = replace(self.stage_definition, sha256="0" * 64)

        with self.assertRaisesRegex(OptimizedFirmwareBuildError, "SHA-256"):
            inspect_optimized_baseline(
                self.original_path,
                self.stage_path,
                self.report_path,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
                original_definition=self.original_definition,
                stage_definition=wrong,
            )

    def test_rejects_change_outside_approved_ranges(self) -> None:
        changed = bytearray(self.stage_path.read_bytes())
        changed[70] = 3
        refresh_recovery_crc(changed, self.original_definition)
        self.stage_path.chmod(0o644)
        self.stage_path.write_bytes(changed)
        self.stage_path.chmod(0o444)
        changed_bytes = bytes(changed)
        wrong = replace(
            self.stage_definition,
            md5=hashlib.md5(changed_bytes).hexdigest(),
            sha256=hashlib.sha256(changed_bytes).hexdigest(),
            recovery_crc=struct.unpack_from("<I", changed_bytes, len(changed_bytes) - 4)[0],
        )

        with self.assertRaisesRegex(Exception, "允许范围外"):
            inspect_optimized_baseline(
                self.original_path,
                self.stage_path,
                self.report_path,
                tool_revision={"commit": "test", "scoped_code_dirty": False},
                original_definition=self.original_definition,
                stage_definition=wrong,
            )


if __name__ == "__main__":
    unittest.main()
